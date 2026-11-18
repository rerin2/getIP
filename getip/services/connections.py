"""프로그램 연결 조회 흐름 (설계 4.4절 아래쪽).

수집 → 종료된 연결 표시 → 필터 → 캐시·일괄 위치 조회 → 프로그램별 묶기.
능동 접속(지연 측정 등)은 하지 않는다. 위치는 DB 조회만 한다.
"""

import threading  # 자동 새로고침과 수동 새로고침이 겹쳐도 상태가 꼬이지 않게 함
import time  # 경과 시간 측정
from dataclasses import replace  # 종료된 연결 복사본 만들기
from datetime import datetime, timezone  # 수집 시각
from typing import Callable, Dict, List, Optional, Tuple  # 타입 표기

from getip import config  # 보관 시간, 재시도 대기
from getip.geo.cached import CachedGeo  # 캐시가 붙은 위치 조회
from getip.models import Connection, ConnectionSnapshot, ProgramConnections  # 데이터 클래스
from getip.system import connections as system_connections  # 연결 수집

ESTABLISHED = "ESTABLISHED"  # 연결이 수립된 상태 (기본 표시 대상)


def _group_key(conn: Connection) -> Tuple:
    """같은 프로그램으로 묶을 기준. 이름+경로가 같으면 프로세스가 여러 개여도 하나로 묶는다."""
    if conn.process_name:  # 이름을 읽은 경우
        return ("name", conn.process_name.lower(), (conn.exe_path or "").lower())  # 대소문자 무시
    if conn.pid is not None:  # 이름은 모르지만 프로세스는 있는 경우
        return ("pid", conn.pid)  # 프로세스별로 따로
    return ("none",)  # 소유 프로세스가 없는 연결 (TIME_WAIT 등)


def _group_name(conn: Connection) -> str:
    """묶음의 화면 이름."""
    if conn.process_name:  # 이름을 읽은 경우
        return conn.process_name  # 그대로
    if conn.pid is not None:  # 권한 거부 등
        return f"알 수 없음 (PID {conn.pid})"  # PID로 구분
    return "소유 프로그램 없음 (종료 중인 연결)"  # 운영체제가 정리 중인 연결


def group_by_program(conns: List[Connection]) -> List[ProgramConnections]:
    """연결을 프로그램별로 묶고 연결이 많은 순으로 정렬한다."""
    groups: Dict[Tuple, ProgramConnections] = {}  # 묶음 저장소
    for conn in conns:  # 연결마다
        key = _group_key(conn)  # 묶음 기준
        group = groups.get(key)  # 기존 묶음
        if group is None:  # 처음 보는 프로그램
            group = ProgramConnections(name=_group_name(conn), exe_path=conn.exe_path, pids=[], connections=[])  # 새 묶음
            groups[key] = group  # 저장
        if conn.pid is not None and conn.pid not in group.pids:  # 새 프로세스 ID
            group.pids.append(conn.pid)  # 기록
        group.connections.append(conn)  # 연결 추가
    for group in groups.values():  # 묶음마다
        group.pids.sort()  # PID 순서 정리
        group.connections.sort(key=lambda c: (c.closed, c.remote_ip, c.remote_port))  # 살아 있는 연결 먼저, 주소순
    return sorted(groups.values(), key=lambda g: (-len(g.connections), g.name.lower()))  # 연결 많은 순, 같으면 이름순


def visible(conn: Connection, include_private: bool, include_closing: bool) -> bool:
    """화면에 보일 연결인지. 기본은 수립된(ESTABLISHED) 공인 IP 연결만."""
    if not include_private and not conn.is_public:  # 사설·루프백 숨김
        return False  # 제외
    if not include_closing and (conn.closed or conn.status != ESTABLISHED):  # 종료됨·종료 중 숨김
        return False  # 제외
    return True  # 표시


class ConnectionService:
    """연결 수집과 위치 붙이기. 이전 수집 결과를 기억해 종료된 연결을 표시한다."""

    def __init__(
        self,
        geo: CachedGeo,
        collector: Callable[[], List[Connection]] = system_connections.collect,
        clock: Callable[[], float] = time.monotonic,
        closed_keep_sec: float = config.CONN_CLOSED_KEEP_SEC,
        geo_retry_sec: float = config.CONN_GEO_RETRY_SEC,
    ):
        self._geo = geo  # 위치 조회 (캐시 + 일괄 조회)
        self._collect = collector  # 수집 함수 (테스트에서 가짜로 바꿈)
        self._clock = clock  # 현재 시각 함수 (테스트에서 시간을 흉내냄)
        self._closed_keep = closed_keep_sec  # 종료된 연결 보관 시간
        self._geo_retry = geo_retry_sec  # 위치 조회 실패 후 대기 시간
        self._seen: Dict[Tuple, Tuple[Connection, float]] = {}  # 연결 키 → (마지막 모습, 마지막으로 본 시각)
        self._geo_blocked_until = 0.0  # 이 시각 전에는 외부 위치 조회를 하지 않음
        self._lock = threading.Lock()  # 한 번에 하나의 수집만

    def _mark_closed(self, current: List[Connection], now: float) -> List[Connection]:
        """이번에 없는 연결 중 보관 시간이 안 지난 것을 '종료됨' 복사본으로 돌려준다."""
        current_keys = set()  # 이번 수집의 연결 키
        for conn in current:  # 지금 열린 연결마다
            key = conn.key()  # 비교용 키
            current_keys.add(key)  # 기록
            self._seen[key] = (conn, now)  # 마지막 모습과 시각 갱신
        closed: List[Connection] = []  # 종료된 연결
        for key, (conn, last_seen) in list(self._seen.items()):  # 기억하는 연결마다
            if key in current_keys:  # 아직 열려 있음
                continue  # 다음
            if now - last_seen > self._closed_keep:  # 너무 오래전에 사라짐
                del self._seen[key]  # 잊음
                continue  # 다음
            closed.append(replace(conn, closed=True, geo=None))  # 종료 표시 복사본 (위치는 다시 붙임)
        return closed  # 종료된 연결 목록

    def _attach_geo(self, conns: List[Connection], now: float) -> Tuple[List[str], Optional[str]]:
        """공인 IP 연결에 위치를 붙인다. (아직 못 붙인 IP, 실패 사유)를 돌려준다."""
        ips = [c.remote_ip for c in conns if c.is_public]  # 조회 대상
        if not ips:  # 공인 IP 없음
            return [], None  # 할 일 없음
        fetch = now >= self._geo_blocked_until  # 대기 중이면 캐시만 봄
        batch = self._geo.lookup_many(ips, fetch=fetch)  # 캐시 → 없는 것만 한 번에 조회
        if batch.error:  # 한도 초과·네트워크 오류
            self._geo_blocked_until = now + self._geo_retry  # 잠시 외부 조회 중단 (자동 새로고침이 계속 호출해도 한도를 더 쓰지 않음)
        for conn in conns:  # 연결마다
            conn.geo = batch.found.get(conn.remote_ip)  # 위치 붙이기 (없으면 None)
        error = batch.error  # 실패 사유
        if not fetch and batch.pending:  # 대기 때문에 조회하지 않은 IP가 있으면
            error = "위치 조회를 잠시 쉬는 중입니다. 잠시 후 새로고침하면 나머지 IP도 조회합니다."  # 안내
        return batch.pending, error  # 남은 IP와 사유

    def snapshot(self, include_private: bool = False, include_closing: bool = False) -> ConnectionSnapshot:
        """연결을 한 번 수집해 위치를 붙이고 프로그램별로 묶는다. 수집 실패 시 ConnectionsUnavailableError."""
        with self._lock:  # 동시에 두 번 수집하지 않음 (종료 판정이 꼬이지 않게)
            now = self._clock()  # 현재 시각
            current = self._collect()  # 운영체제에서 읽기
            everything = current + self._mark_closed(current, now)  # 열린 연결 + 종료된 연결
            shown = [c for c in everything if visible(c, include_private, include_closing)]  # 필터
            pending, error = self._attach_geo(shown, now)  # 보이는 것만 위치 조회
        return ConnectionSnapshot(
            collected_at=datetime.now(timezone.utc),  # 수집 시각
            programs=group_by_program(shown),  # 프로그램별 묶음
            total=len(current),  # 필터 전 연결 수
            shown=len(shown),  # 보이는 연결 수
            pending=pending,  # 위치를 못 붙인 IP
            error=error,  # 실패 사유
        )
