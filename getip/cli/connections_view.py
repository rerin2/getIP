"""CLI 'c' 명령: 프로그램별 TCP 연결 표 출력."""

from typing import Callable, List  # 타입 표기

from getip.models import Connection, ConnectionSnapshot  # 데이터 클래스
from getip.services.connections import ConnectionService  # 연결 조회
from getip.system.connections import ConnectionsUnavailableError  # 읽기 실패

_LINE = "-" * 90  # 구분선
NOTICE = "TCP 연결만 표시됩니다 (UDP·QUIC 제외). 연결된 IP는 위치 조회를 위해 ip-api.com에 전달됩니다."  # 한계·전달 안내


def format_connection(conn: Connection) -> str:
    """연결 한 줄: 주소, 국가, 도시, 사업자."""
    address = f"{conn.remote_ip}:{conn.remote_port}"  # 상대 주소
    geo = conn.geo  # 위치 정보
    if geo is None:  # 위치 없음
        place = "위치 정보 없음" if conn.is_public else "사설망"  # 사유
        return f"    {address:<28} {place}"  # 주소와 사유만
    country = geo.country_code or geo.country or "N/A"  # 국가 코드 우선
    city = geo.city or "N/A"  # 도시
    isp = geo.isp or "N/A"  # 사업자
    return f"    {address:<28} {country:<4} {city:<18} {isp}"  # 한 줄


def format_snapshot(snapshot: ConnectionSnapshot) -> List[str]:
    """수집 결과 전체를 출력할 줄 목록으로 만든다."""
    lines = [
        f"[*] 프로그램 {len(snapshot.programs)}개, 연결 {snapshot.shown}개 (전체 {snapshot.total}개 중 수립된 공인 IP 연결)",  # 요약
        _LINE,  # 구분선
    ]
    for program in snapshot.programs:  # 연결 많은 프로그램부터
        pids = ", ".join(str(p) for p in program.pids) or "-"  # 프로세스 ID들
        lines.append(f"{program.name} ({len(program.connections)})  PID {pids}")  # 프로그램 줄
        lines.extend(format_connection(conn) for conn in program.connections)  # 연결 줄들
    if not snapshot.programs:  # 연결이 하나도 없음
        lines.append("표시할 연결이 없습니다.")  # 안내
    lines.append(_LINE)  # 구분선
    if snapshot.error:  # 일부 위치를 못 붙인 경우
        lines.append(f"[!] {snapshot.error} (위치 미조회 IP {len(snapshot.pending)}개)")  # 사유
    lines.append(f"[*] {NOTICE}")  # 한계 안내
    return lines  # 출력할 줄


def handle_connections(service: ConnectionService, out: Callable[[str], None] = print) -> None:
    """연결을 한 번 수집해 표로 출력한다."""
    out("\n[*] 이 PC의 프로그램별 연결을 수집합니다...")  # 진행 안내
    try:
        snapshot = service.snapshot()  # 기본 필터: 수립된 공인 IP
    except ConnectionsUnavailableError as exc:  # 권한 등
        out(f"[!] {exc}")  # 사유
        return  # 메뉴로 복귀
    for line in format_snapshot(snapshot):  # 줄마다
        out(line)  # 출력
