"""지연 측정·경로 추적 서비스(getip.services.probe)와 내 위치(getip.services.origin) 테스트.

실제 ping·tracert 대신 가짜 측정 함수와 가짜 추적을 쓴다.
"""

import pytest  # 테스트 도구

from getip.geo.base import GeoLookupError, GeoRateLimitError  # 위치 조회 실패 예외
from getip.models import Hop, LatencyResult  # 데이터 클래스
from getip.net.target import normalize  # 조회 대상 만들기
from getip.services.origin import OriginService  # 내 위치
from getip.services.probe import ProbeService, RecordNotFoundError  # 대상
from getip.storage.settings import InvalidSettingError, SettingsStore  # 수동 위치 저장


class FakeRun:
    """가짜 경로 추적. 정해 둔 홉을 내보내고, stop()이 불리면 멈춘다."""

    def __init__(self, hops, stop_after=None, silent=False):
        self._hops = hops  # 내보낼 홉
        self._stop_after = stop_after  # 이 개수만큼 낸 뒤 사용자가 중지한 것처럼
        self.stopped = False  # 사용자 중지
        self.silent_cut = silent  # 응답 없는 홉으로 멈춤
        self.max_silent = 5  # 안내 문구용
        self.closed = False  # close() 호출 여부

    def hops(self):
        for i, hop in enumerate(self._hops):  # 순서대로
            if self.stopped:  # 중지됨
                return  # 끝
            yield hop  # 전달
            if self._stop_after is not None and i + 1 >= self._stop_after:  # 중지 시점
                self.stop()  # 사용자 중지 흉내

    def stop(self):
        self.stopped = True  # 기록

    def close(self):
        self.closed = True  # 기록


@pytest.fixture
def settings(database):
    return SettingsStore(database)  # 임시 DB 위의 설정


@pytest.fixture
def origins(service, settings):
    return OriginService(service.my_ip, settings)  # 가짜 공급자의 내 IP(9.9.9.9, 서울 좌표)


@pytest.fixture
def record(service):
    return service.lookup(normalize("8.8.8.8"), "8.8.8.8", ["8.8.8.8"])  # 저장된 기록 하나


def make_probe(service, origins, run=None, measure=None):
    """가짜 측정·추적을 끼운 서비스."""
    return ProbeService(service.history, service.geo, origins,
                        measure=measure or (lambda ip: [LatencyResult("icmp", [12.0], 1, 12.0, 0.0)]),  # 12ms
                        start_run=lambda ip: run)  # 정해 둔 추적


# --- 내 위치 ---

def test_origin_prefers_manual_and_validates(origins, settings, provider):
    assert origins.origin().source == "ip-api"  # 수동 지정이 없으면 내 IP 위치
    calls = len(provider.single_calls)  # 지금까지 공급자 호출 수
    origins.origin()  # 다시 요청
    assert len(provider.single_calls) == calls  # 10분 안에는 다시 조회하지 않음
    placed = origins.set_manual(35.1, 129.0 + 360)  # 지도 사본(경도 +360)을 클릭한 경우
    assert (placed.lat, placed.lon, placed.source) == (35.1, pytest.approx(129.0), "manual")  # 경도 정리
    assert origins.origin() == placed  # 수동 위치 우선
    with pytest.raises(InvalidSettingError):  # 위도 범위 밖
        origins.set_manual(91, 0)  # 거부
    assert origins.clear_manual().source == "ip-api"  # 되돌리기


def test_me_reports_error_but_keeps_manual(origins, provider):
    origins.set_manual(35.0, 129.0)  # 수동 지정
    provider.error = GeoLookupError("실패")  # 내 IP 조회 실패
    me = origins.me()  # 조회
    assert me.geo is None and me.error == "실패" and me.origin.source == "manual"  # 위치는 수동값으로 계속 사용


# --- 지연 측정 ---

def test_measure_latency_saves_with_origin(service, origins, record):
    probe = make_probe(service, origins)  # 서비스
    result = probe.measure_latency(record.id)  # 측정
    assert result.latency.min_ms == 12.0 and result.latency.origin.source == "ip-api"  # 결과와 측정 위치
    saved = service.history.get(record.id)  # 저장된 기록
    assert saved.latency == result.latency  # 기록에 덧붙음 (JSON 왕복 후에도 같음)
    with service.history._db.connect() as conn:  # 요약 컬럼 확인
        assert conn.execute("SELECT min_rtt_ms FROM lookups WHERE id=?", (record.id,)).fetchone()[0] == 12.0  # 목록용


def test_measure_latency_unknown_record(service, origins):
    with pytest.raises(RecordNotFoundError):  # 없는 기록
        make_probe(service, origins).measure_latency(999)  # 측정


# --- 경로 추적 ---

def test_trace_events_geo_and_save(service, origins, record):
    run = FakeRun([Hop(1, "192.168.0.1", 1.0, True), Hop(2, None, None), Hop(3, "8.8.8.8", 30.0)])  # 사설, 무응답, 공인
    probe = make_probe(service, origins, run=run)  # 서비스
    events = list(probe.start_trace(record.id).events())  # 끝까지 읽음
    kinds = [e.kind for e in events]  # 사건 종류
    assert kinds == ["start", "hop", "hop", "hop", "done"]  # 순서
    assert events[0].origin.source == "ip-api"  # 시작점
    assert events[1].hop.geo is None and events[3].hop.geo.city == "Seoul"  # 사설 IP는 위치 없음, 공인은 위치 붙음
    report = events[-1].report  # 최종 결과
    assert report.status == "done" and len(report.hops) == 3 and run.closed  # 정상 완료, 프로세스 정리
    assert service.history.get(record.id).trace == report  # 기록에 저장 (D15)


def test_trace_rate_limit_fills_by_batch(service, origins, record, provider):
    provider.error = GeoRateLimitError(30)  # 단건 조회 한도 초과
    run = FakeRun([Hop(1, "1.1.1.1", 5.0), Hop(2, "8.8.4.4", 9.0)])  # 공인 홉 둘
    probe = make_probe(service, origins, run=run)  # 서비스
    session = probe.start_trace(record.id)  # 시작
    events = session.events()  # 생성기
    next(events)  # start
    first = next(events)  # 1번 홉 (한도 초과로 위치 없음)
    assert first.hop.geo is None  # 비어 있음
    provider.error = None  # 일괄 조회는 성공
    rest = list(events)  # 나머지
    updates = [e.hop for e in rest if e.kind == "hop" and e.hop.geo is not None]  # 위치가 채워진 갱신
    assert [h.index for h in updates] == [1, 2] and provider.batch_calls == [["1.1.1.1", "8.8.4.4"]]  # 한 번에 채움
    assert all(h.geo for h in rest[-1].report.hops)  # 저장 결과에도 위치


def test_trace_stop_saves_partial(service, origins, record):
    run = FakeRun([Hop(1, "1.1.1.1", 5.0), Hop(2, "8.8.4.4", 9.0), Hop(3, "8.8.8.8", 12.0)], stop_after=1)  # 1개 뒤 중지
    report = list(make_probe(service, origins, run=run).start_trace(record.id).events())[-1].report  # 실행
    assert report.status == "stopped" and [h.index for h in report.hops] == [1]  # 그때까지만 저장


def test_trace_silent_status(service, origins, record):
    run = FakeRun([Hop(1, None, None)], silent=True)  # 응답 없는 홉으로 멈춤
    report = list(make_probe(service, origins, run=run).start_trace(record.id).events())[-1].report  # 실행
    assert report.status == "silent" and "응답 없는 홉" in report.message  # 사유 안내


def test_trace_disconnect_saves_and_closes(service, origins, record):
    run = FakeRun([Hop(1, "1.1.1.1", 5.0), Hop(2, "8.8.4.4", 9.0)])  # 홉 둘
    events = make_probe(service, origins, run=run).start_trace(record.id).events()  # 생성기
    next(events), next(events)  # start, 1번 홉까지 읽고
    events.close()  # 화면 연결 끊김
    saved = service.history.get(record.id).trace  # 저장된 결과
    assert saved.status == "stopped" and len(saved.hops) == 1 and run.closed  # 그때까지 저장, 프로세스 정리


def test_new_trace_stops_previous(service, origins, record):
    first, second = FakeRun([Hop(1, "1.1.1.1", 5.0)]), FakeRun([Hop(1, "1.1.1.1", 5.0)])  # 두 추적
    runs = iter([first, second])  # 차례로 사용
    probe = ProbeService(service.history, service.geo, origins, start_run=lambda ip: next(runs))  # 서비스
    probe.start_trace(record.id)  # 첫 추적 시작 (읽지 않음)
    probe.start_trace(record.id)  # 두 번째 시작
    assert first.stopped and not second.stopped  # 이전 추적은 멈춤
    assert probe.stop_trace() and second.stopped  # 중지 API
