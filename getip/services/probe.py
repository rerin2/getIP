"""능동 측정(지연·경로 추적)을 조회 기록에 덧붙인다. 사용자가 버튼을 눌렀을 때만 실행한다(D12).

대상 서버에 직접 패킷을 보내므로 대상 로그에 내 IP가 남을 수 있다 (설계 5절 '능동 접속').
"""

import threading  # 동시에 하나의 경로 추적만 실행
from dataclasses import replace  # 결과에 측정값을 덧붙인 사본
from datetime import datetime, timezone  # 측정 시각
from typing import Callable, Iterator, List, Optional  # 타입 표기

from getip import config  # 홉 위치 조회 대기 시간
from getip.geo.base import GeoLookupError, GeoRateLimitError  # 위치 조회 실패 예외
from getip.geo.cached import CachedGeo, is_public_ip  # 위치 조회, 공인 IP 판별
from getip.models import Hop, LatencyReport, LatencyResult, LookupResult, Origin, TraceEvent, TraceReport  # 데이터 클래스
from getip.probe import latency  # 지연 측정
from getip.probe.traceroute import TraceRun  # 경로 추적 실행
from getip.services.origin import OriginService  # 시작점(내 위치)
from getip.storage.history import HistoryStore  # 조회 기록


class RecordNotFoundError(LookupError):
    """기록 번호에 해당하는 조회가 없을 때 발생."""


def _now() -> datetime:
    """현재 시각(UTC)."""
    return datetime.now(timezone.utc)  # 시간대 포함


class TraceSession:
    """경로 추적 한 번. events()를 끝까지 읽거나 중간에 닫으면 결과를 기록에 저장한다."""

    def __init__(self, service: "ProbeService", record_id: int, run: TraceRun, origin: Optional[Origin]):
        self._service = service  # 기록 저장·위치 조회에 사용
        self.record_id = record_id  # 덧붙일 기록
        self.run = run  # 실행 중인 추적
        self.origin = origin  # 경로선 시작점
        self.started_at = _now()  # 시작 시각

    def events(self) -> Iterator[TraceEvent]:
        """시작 → 홉(위치 포함) → 끝 순서로 사건을 돌려준다."""
        hops: List[Hop] = []  # 확인된 홉
        status, message = "done", None  # 기본: 끝까지 추적
        try:
            yield TraceEvent("start", origin=self.origin)  # 화면이 시작점을 먼저 그림 (여기서 끊겨도 아래 finally가 정리)
            limited = False  # 단건 위치 조회가 한도에 걸렸는지
            for hop in self.run.hops():  # 홉이 나오는 대로
                if hop.ip and not limited:  # 응답한 홉이고 한도 전이면
                    try:
                        hop = replace(hop, geo=self._service.geo.lookup(hop.ip, timeout=config.GEO_HOP_TIMEOUT_SEC))  # 캐시 → 단건 조회
                    except GeoRateLimitError:  # 한도 초과
                        limited = True  # 남은 홉은 끝난 뒤 일괄 조회
                    except GeoLookupError:  # 사설 IP, 실패
                        pass  # 위치 없이 진행
                hops.append(hop)  # 기록
                yield TraceEvent("hop", hop=hop)  # 바로 화면에
            if limited:  # 위치를 못 붙인 홉이 있으면
                yield from self._fill_missing_geo(hops)  # 일괄 조회로 채우고 갱신 사건 전송
            status, message = self._end_status()  # 끝난 이유
        except GeneratorExit:  # 화면이 연결을 끊음 (창 닫기 등)
            status, message = "stopped", "화면 연결이 끊겨 추적을 멈췄습니다."  # 사유
            raise  # 생성기 종료는 그대로 전달
        except OSError as exc:  # 프로세스 오류
            status, message = "error", f"추적 중 오류가 발생했습니다: {exc}"  # 사유
        finally:
            self.run.close()  # 어떤 이유로 끝나든 프로세스가 남지 않게 함 (이미 끝났으면 아무 일 없음)
            report = TraceReport(started_at=self.started_at, origin=self.origin, hops=hops,
                                 status=status, message=message)  # 최종 결과
            self._service._finish_trace(self, report)  # 기록에 저장 + 실행 중 표시 해제
        yield TraceEvent("done", report=report)  # 화면에 끝 알림 (연결이 끊긴 경우는 여기 오지 않음)

    def _fill_missing_geo(self, hops: List[Hop]) -> Iterator[TraceEvent]:
        """위치가 비어 있는 공인 IP 홉을 한 번에 조회하고, 채워진 홉을 다시 보낸다."""
        missing = [h.ip for h in hops if h.ip and h.geo is None and is_public_ip(h.ip)]  # 대상
        found = self._service.geo.lookup_many(missing).found  # 일괄 조회 (실패해도 예외 없음)
        for i, hop in enumerate(hops):  # 순서대로
            if hop.ip in found and hop.geo is None:  # 새로 위치를 얻은 홉
                hops[i] = replace(hop, geo=found[hop.ip])  # 교체
                yield TraceEvent("hop", hop=hops[i])  # 같은 번호로 갱신 전송

    def _end_status(self):
        """추적이 끝난 이유와 안내 문구."""
        if self.run.stopped:  # 사용자가 중지 (또는 새 추적이 시작됨)
            return "stopped", "추적을 중지했습니다."  # 중지
        if self.run.silent_cut:  # 응답 없는 홉이 이어짐
            return "silent", (f"응답 없는 홉이 {self.run.max_silent}개 이어져 추적을 멈췄습니다. "
                              "대상이나 중간 장비가 추적 패킷에 응답하지 않는 것으로 보입니다.")  # 사유
        return "done", None  # 정상 완료


class ProbeService:
    """지연 측정과 경로 추적을 실행하고 결과를 조회 기록에 덧붙인다."""

    def __init__(self, history: HistoryStore, geo: CachedGeo, origins: OriginService,
                 measure: Callable[[str], List[LatencyResult]] = latency.measure,
                 start_run: Callable[[str], TraceRun] = TraceRun):
        self.history = history  # 조회 기록
        self.geo = geo  # 홉 위치 조회
        self.origins = origins  # 시작점
        self._measure = measure  # 지연 측정 함수 (테스트에서 바꿈)
        self._start_run = start_run  # 추적 시작 함수 (테스트에서 바꿈)
        self._active: Optional[TraceSession] = None  # 실행 중인 추적
        self._lock = threading.Lock()  # _active 보호

    def _record(self, record_id: int) -> LookupResult:
        """기록 한 건. 없으면 RecordNotFoundError."""
        result = self.history.get(record_id)  # 저장된 결과
        if result is None:  # 없는 번호 (삭제됨)
            raise RecordNotFoundError("기록을 찾을 수 없습니다.")  # 화면에서 404
        return result  # 결과

    def measure_latency(self, record_id: int) -> LookupResult:
        """기록의 IP로 지연을 재고 결과를 그 기록에 덧붙여 저장한다."""
        result = self._record(record_id)  # 대상 기록
        results = self._measure(result.ip)  # TCP + ICMP 측정 (몇 초 걸림)
        report = LatencyReport(measured_at=_now(), origin=self.origins.origin(), results=results)  # 측정 위치와 함께
        updated = replace(self._record(record_id), latency=report)  # 측정 중 다른 변경(추적 저장)을 덮어쓰지 않게 다시 읽음
        self.history.update(updated)  # 저장
        return updated  # 화면용

    def start_trace(self, record_id: int) -> TraceSession:
        """경로 추적을 시작한다. 실행 중인 다른 추적은 멈춘다. 기록이 없거나 IPv6면 예외."""
        result = self._record(record_id)  # 대상 기록
        run = self._start_run(result.ip)  # 명령 실행 (IPv6 거부, 명령 없음 예외는 그대로 전달)
        session = TraceSession(self, record_id, run, self.origins.origin())  # 세션
        with self._lock:  # 실행 중 표시 교체
            previous, self._active = self._active, session  # 새 추적을 등록
        if previous is not None:  # 이전 추적이 아직 돌고 있으면
            previous.run.stop()  # 멈춤 (그 세션은 'stopped'로 저장됨)
        return session  # 화면이 events()를 읽음

    def stop_trace(self) -> bool:
        """실행 중인 추적을 멈춘다. 멈춘 것이 있으면 True."""
        with self._lock:  # 실행 중 표시 읽기
            session = self._active  # 현재 추적
        if session is None:  # 없음
            return False  # 할 일 없음
        session.run.stop()  # 멈춤 (세션이 결과를 저장)
        return True  # 멈춤

    def _finish_trace(self, session: TraceSession, report: TraceReport) -> None:
        """추적 결과를 기록에 저장하고 실행 중 표시를 지운다."""
        with self._lock:  # 실행 중 표시 정리
            if self._active is session:  # 다른 추적으로 바뀌지 않았으면
                self._active = None  # 해제
        result = self.history.get(session.record_id)  # 최신 기록 (그 사이 지연 측정이 저장됐을 수 있음)
        if result is not None:  # 기록이 아직 있으면 (추적 중 삭제됐으면 저장하지 않음)
            self.history.update(replace(result, trace=report))  # 덧붙여 저장
