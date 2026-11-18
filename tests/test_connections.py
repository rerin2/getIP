"""프로그램 연결 수집(getip.system.connections)과 연결 서비스(getip.services.connections) 테스트.

실제 운영체제 연결 대신 가짜 소켓 목록을 쓴다.
"""

from collections import namedtuple  # psutil 결과 흉내

import psutil  # 예외 클래스
import pytest  # 테스트 도구

from getip.cli.connections_view import format_snapshot  # CLI 출력
from getip.geo.base import GeoRateLimitError  # 한도 초과 예외
from getip.models import Connection  # 데이터 클래스
from getip.services.connections import ConnectionService, group_by_program  # 대상
from getip.system import connections as system_connections  # 대상
from getip.system.connections import ConnectionsUnavailableError  # 읽기 실패 예외

Addr = namedtuple("Addr", "ip port")  # psutil의 주소 형태
Sock = namedtuple("Sock", "pid laddr raddr status")  # psutil의 연결 형태


def sock(pid, remote_ip, remote_port=443, status="ESTABLISHED", local_port=50000):
    """가짜 소켓 하나."""
    return Sock(pid, Addr("192.168.0.2", local_port), Addr(remote_ip, remote_port) if remote_ip else (), status)  # 원격 주소가 없으면 빈 값


def conn(pid=10, name="chrome.exe", ip="1.1.1.1", port=443, status="ESTABLISHED", local_port=50000, exe=None):
    """가짜 연결 하나 (수집 이후 형태)."""
    from getip.geo.cached import is_public_ip  # 공인 판별
    return Connection(pid=pid, process_name=name, exe_path=exe or (f"C:\\{name}" if name else None),
                      local_port=local_port, remote_ip=ip, remote_port=port, status=status, is_public=is_public_ip(ip))  # 연결


# --- 수집 ---

def test_collect_skips_listeners_and_normalizes():
    calls = []  # 프로세스 정보 조회 기록

    def info(pid):
        calls.append(pid)  # 호출 기록
        return ("app.exe", "C:\\app.exe")  # 이름과 경로

    raw = [
        sock(5, None, status="LISTEN"),  # 원격 주소 없음 → 제외
        sock(5, "::ffff:8.8.8.8", local_port=1),  # IPv6로 감싼 IPv4
        sock(5, "10.0.0.1", local_port=2),  # 사설
        sock(0, "1.1.1.1", status="TIME_WAIT", local_port=3),  # 소유 프로세스 없음
    ]
    result = system_connections.collect(lambda: raw, info)  # 수집
    assert [c.remote_ip for c in result] == ["8.8.8.8", "10.0.0.1", "1.1.1.1"]  # 리스너 제외, 주소 정리
    assert [c.is_public for c in result] == [True, False, True]  # 공인 판별
    assert result[2].pid is None and result[2].process_name is None  # PID 0은 None
    assert calls == [5]  # 같은 프로세스는 한 번만 조회


def test_collect_access_denied_raises_friendly_error():
    def denied():
        raise psutil.AccessDenied()  # 권한 거부

    with pytest.raises(ConnectionsUnavailableError):  # 화면용 예외로 변환
        system_connections.collect(denied, lambda pid: (None, None))  # 수집


def test_read_process_handles_missing_process():
    assert system_connections.read_process(2 ** 31 - 2) == (None, None)  # 없는 PID는 예외 없이 None


# --- 묶기·필터 ---

def test_group_by_program_merges_pids_and_sorts():
    groups = group_by_program([
        conn(1, "chrome.exe", "1.1.1.1"), conn(2, "Chrome.exe", "2.2.2.2", exe="c:\\chrome.exe"),  # 대소문자만 다른 같은 프로그램
        conn(3, "a.exe", "3.3.3.3"), conn(None, None, "4.4.4.4"), conn(7, None, "5.5.5.5"),  # 다른 프로그램, 소유 없음, 이름 모름
    ])
    assert groups[0].name == "chrome.exe" and groups[0].pids == [1, 2] and len(groups[0].connections) == 2  # 하나로 묶임, 가장 많음
    names = [g.name for g in groups[1:]]  # 나머지 이름 (연결 수가 같으면 이름순)
    assert names == ["a.exe", "소유 프로그램 없음 (종료 중인 연결)", "알 수 없음 (PID 7)"]  # 이름 규칙


@pytest.fixture
def collected():
    return {"items": []}  # 테스트가 바꿔 끼우는 '현재 연결'


@pytest.fixture
def clock():
    return {"now": 1000.0}  # 테스트가 조작하는 시각


@pytest.fixture
def conn_service(cached_geo, collected, clock):
    return ConnectionService(cached_geo, collector=lambda: list(collected["items"]), clock=lambda: clock["now"],
                             closed_keep_sec=600, geo_retry_sec=60)  # 가짜 수집 + 가짜 시계


def test_snapshot_default_filter_and_geo(conn_service, collected):
    collected["items"] = [conn(1, ip="1.1.1.1"), conn(1, ip="10.0.0.1", local_port=2),
                          conn(1, ip="2.2.2.2", status="TIME_WAIT", local_port=3)]  # 공인, 사설, 종료 중
    snap = conn_service.snapshot()  # 기본 필터
    shown = [c.remote_ip for p in snap.programs for c in p.connections]  # 보이는 연결
    assert shown == ["1.1.1.1"] and snap.total == 3 and snap.shown == 1  # 수립된 공인 IP만
    assert snap.programs[0].connections[0].geo.city == "Seoul"  # 위치가 붙음
    snap = conn_service.snapshot(include_private=True, include_closing=True)  # 옵션 모두 켬
    assert snap.shown == 3  # 전부 보임


def test_snapshot_batches_once_then_uses_cache(conn_service, collected, provider):
    collected["items"] = [conn(1, ip=f"1.1.1.{i}", local_port=i) for i in range(1, 70)]  # 69개 공인 IP
    first = conn_service.snapshot()  # 첫 수집
    assert first.shown == 69 and first.pending == []  # 모두 위치 붙음
    assert len(provider.batch_calls) == 1 and provider.single_calls == []  # 한 번의 일괄 조회 (한도 걱정 없음)
    conn_service.snapshot()  # 다시 수집
    assert len(provider.batch_calls) == 1  # 캐시에 있어 다시 요청하지 않음


def test_closed_connections_are_kept_then_forgotten(conn_service, collected, clock):
    a, b = conn(1, ip="1.1.1.1", local_port=1), conn(1, ip="2.2.2.2", local_port=2)  # 두 연결
    collected["items"] = [a, b]  # 둘 다 열림
    conn_service.snapshot()  # 첫 수집
    collected["items"] = [a]  # b가 닫힘
    clock["now"] += 5  # 5초 뒤
    snap = conn_service.snapshot(include_closing=True)  # 종료된 것도 표시
    closed = {c.remote_ip: c.closed for p in snap.programs for c in p.connections}  # IP → 종료 여부
    assert closed == {"1.1.1.1": False, "2.2.2.2": True}  # b는 종료됨으로 남음
    assert conn_service.snapshot().shown == 1  # 기본 필터에서는 숨김
    clock["now"] += 601  # 보관 시간 초과
    snap = conn_service.snapshot(include_closing=True)  # 다시 수집
    assert [c.remote_ip for p in snap.programs for c in p.connections] == ["1.1.1.1"]  # b는 잊음


def test_rate_limit_pauses_external_lookups(conn_service, collected, clock, provider):
    collected["items"] = [conn(1, ip="1.1.1.1")]  # 공인 IP 하나
    provider.error = GeoRateLimitError(30)  # 한도 초과
    snap = conn_service.snapshot()  # 수집
    assert snap.pending == ["1.1.1.1"] and "한도" in snap.error  # 위치 못 붙임 + 사유
    provider.error = None  # 한도 풀림
    clock["now"] += 10  # 대기 시간(60초) 안
    snap = conn_service.snapshot()  # 자동 새로고침
    assert len(provider.batch_calls) == 1 and "잠시" in snap.error  # 외부 호출 없이 안내만
    clock["now"] += 60  # 대기 시간 지남
    snap = conn_service.snapshot()  # 다시 수집
    assert snap.pending == [] and snap.error is None and len(provider.batch_calls) == 2  # 다시 조회해 성공


# --- CLI 출력 ---

def test_cli_format_snapshot(conn_service, collected):
    collected["items"] = [conn(1, ip="1.1.1.1"), conn(2, "b.exe", ip="2.2.2.2")]  # 두 프로그램
    lines = format_snapshot(conn_service.snapshot())  # 출력 줄
    text = "\n".join(lines)  # 한 문자열로
    assert "프로그램 2개, 연결 2개" in text and "chrome.exe (1)  PID 1" in text  # 요약과 프로그램 줄
    assert "1.1.1.1:443" in text and "Seoul" in text and "UDP" in text  # 연결 줄과 한계 안내
