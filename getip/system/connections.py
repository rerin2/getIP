"""이 PC의 TCP 연결 목록 수집 (설계 3.7절). psutil로 읽고, 위치 조회는 하지 않는다."""

import ipaddress  # IPv4 매핑 주소 정리
from typing import Callable, Dict, Iterable, List, Optional, Tuple  # 타입 표기

import psutil  # 운영체제 연결·프로세스 정보

from getip.geo.cached import is_public_ip  # 공인 IP 판별 (위치 조회와 같은 기준)
from getip.models import Connection  # 결과 데이터 클래스

ProcessInfo = Tuple[Optional[str], Optional[str]]  # (프로그램 이름, 실행 파일 경로)


class ConnectionsUnavailableError(Exception):
    """운영체제가 연결 목록을 주지 않을 때 발생 (권한 등). 메시지는 화면에 그대로 보여줄 수 있다."""


def _plain_ip(ip: str) -> str:
    """'::ffff:1.2.3.4'처럼 IPv6로 감싼 IPv4 주소를 '1.2.3.4'로 바꾼다."""
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])  # 링크 로컬의 '%인터페이스' 꼬리 제거
    except ValueError:  # IP 형식이 아님
        return ip  # 그대로 둠
    mapped = getattr(addr, "ipv4_mapped", None)  # IPv6 주소면 감싼 IPv4 확인
    return str(mapped or addr)  # 감싼 IPv4가 있으면 그것, 아니면 정규화한 주소


def read_process(pid: int) -> ProcessInfo:
    """프로세스 이름과 경로. 권한이 없거나 이미 끝난 프로세스면 읽을 수 있는 것만 돌려준다."""
    try:
        proc = psutil.Process(pid)  # 프로세스 객체
        name = proc.name()  # 이름 (보통 권한 없이도 읽힘)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):  # 끝났거나 거부됨
        return None, None  # 둘 다 모름
    try:
        exe = proc.exe() or None  # 경로 (시스템 서비스는 거부될 수 있음)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):  # 거부·종료
        exe = None  # 경로만 모름
    return name, exe  # 읽은 만큼


def collect(
    net_connections: Callable[[], Iterable] = lambda: psutil.net_connections(kind="tcp"),
    process_info: Callable[[int], ProcessInfo] = read_process,
) -> List[Connection]:
    """원격 주소가 있는 TCP 연결을 모두 돌려준다. 필터(공인/상태)는 호출하는 쪽에서 한다.

    net_connections, process_info는 테스트에서 가짜로 바꿀 수 있다.
    """
    try:
        raw = list(net_connections())  # 운영체제에서 한 번에 읽기 (IPv4·IPv6 TCP)
    except (psutil.AccessDenied, OSError) as exc:  # 권한 부족 등
        raise ConnectionsUnavailableError(f"연결 목록을 읽을 수 없습니다: {exc}") from exc  # 화면 안내용

    names: Dict[int, ProcessInfo] = {}  # 같은 프로세스를 여러 번 읽지 않도록 저장
    result: List[Connection] = []  # 결과
    for item in raw:  # 소켓마다
        if not item.raddr:  # 원격 주소가 없는 소켓 (LISTEN 등)
            continue  # 제외
        pid = item.pid or None  # 0(소유 프로세스 없음)도 None으로 통일
        if pid is not None and pid not in names:  # 처음 보는 프로세스면
            names[pid] = process_info(pid)  # 이름·경로 읽기
        name, exe = names.get(pid, (None, None)) if pid is not None else (None, None)  # 프로세스 정보
        remote_ip = _plain_ip(item.raddr.ip)  # 상대 주소 정리
        result.append(Connection(
            pid=pid,  # 프로세스 ID
            process_name=name,  # 이름
            exe_path=exe,  # 경로
            local_port=item.laddr.port if item.laddr else 0,  # 내 쪽 포트
            remote_ip=remote_ip,  # 상대 IP
            remote_port=item.raddr.port,  # 상대 포트
            status=str(item.status),  # 연결 상태 문자열
            is_public=is_public_ip(remote_ip),  # 공인 IP 여부
        ))  # 한 건 추가
    return result  # 수집 결과
