"""CLI 지연 측정 화면 ('l' 명령). 마지막으로 조회한 기록에 지연 측정 결과를 덧붙인다 (D12: 사용자가 명령했을 때만)."""

from typing import Callable, List, Optional  # 타입 표기

from getip.estimate.rtt import latency_summary  # 반경·거리 요약
from getip.models import LatencyResult, LookupResult, TraceReport  # 데이터 클래스
from getip.services.probe import ProbeService, RecordNotFoundError  # 측정 서비스

_LINE = "-" * 35  # 구분선
ACTIVE_NOTICE = "대상 서버에 직접 패킷을 보냅니다. 대상 로그에 내 IP가 남을 수 있습니다."  # 능동 접속 안내 (설계 5절)


def _method_name(method: str) -> str:
    """측정 방법을 화면 글자로."""
    if method == "icmp":  # ping
        return "ICMP (ping)"  # 이름
    if method == "tcp":  # 모든 포트 실패
        return "TCP (443·80)"  # 이름
    return method.replace("tcp:", "TCP ")  # "tcp:443" → "TCP 443"


def format_method(result: LatencyResult) -> str:
    """방법 하나의 결과 한 줄."""
    if result.min_ms is None:  # 전부 실패
        return f"{_method_name(result.method)}: 응답 없음 ({result.attempts}회 시도)"  # 실패
    answered = len(result.samples_ms)  # 응답 수
    return f"{_method_name(result.method)}: 최소 {result.min_ms:g} ms ({result.attempts}회 중 {answered}회 응답)"  # 요약


def format_latency(result: LookupResult) -> List[str]:
    """지연 측정 결과 여러 줄. 측정하지 않은 결과면 빈 목록."""
    if result.latency is None:  # 측정 안 함
        return []  # 없음
    lines = [format_method(r) for r in result.latency.results]  # 방법별
    summary = latency_summary(result) or {}  # 반경·거리
    if summary.get("min_ms") is not None:  # 측정 성공
        lines.append(f"반경: 현실 추정 {summary['typical_km']:,} km 이내 / 물리적 상한 {summary['upper_km']:,} km")  # 두 원
    if summary.get("db_distance_km") is not None:  # DB 위치까지 거리
        beyond = " (물리적 상한 밖: DB 위치가 틀렸거나 애니캐스트)" if summary["db_beyond_upper"] else ""  # 모순 안내
        lines.append(f"DB 위치까지: {summary['db_distance_km']:,} km{beyond}")  # 거리
    origin = result.latency.origin  # 측정 위치
    if origin is None:  # 모름
        lines.append("측정 위치: 모름 (내 IP 위치 조회 실패)")  # 안내
    else:  # 앎
        source = "직접 지정" if origin.source == "manual" else "내 IP 위치"  # 출처
        lines.append(f"측정 위치: {source} ({origin.lat:.3f}, {origin.lon:.3f})")  # 좌표
    return lines  # 출력 줄


def format_trace_summary(trace: Optional[TraceReport]) -> Optional[str]:
    """기록 상세에 넣을 경로 추적 한 줄 요약."""
    if trace is None:  # 추적 안 함
        return None  # 없음
    answered = sum(1 for h in trace.hops if h.ip)  # 응답한 홉 수
    status = {"done": "완료", "silent": "무응답으로 멈춤", "stopped": "중지", "error": "오류"}.get(trace.status, trace.status)  # 상태 글자
    return f"홉 {len(trace.hops)}개 (응답 {answered}개), {status}"  # 요약


def handle_latency(probe: ProbeService, last: Optional[LookupResult], out: Callable[[str], None] = print) -> Optional[LookupResult]:
    """마지막 조회 기록의 지연을 재고 출력한다. 갱신된 결과를 돌려준다 (없으면 None)."""
    if last is None or last.id is None:  # 이번 실행에서 저장된 조회가 없음
        out("[!] 먼저 도메인이나 IP를 조회하세요. 마지막 조회 결과의 지연을 잽니다.")  # 안내
        return None  # 할 일 없음
    out(f"\n[*] {last.ip} 지연 측정 중... (TCP 연결 + ping, 몇 초 걸립니다)")  # 진행 안내
    out(f"[*] {ACTIVE_NOTICE}")  # 능동 접속 안내
    try:
        result = probe.measure_latency(last.id)  # 측정 + 기록 저장
    except RecordNotFoundError:  # 그 사이 기록이 삭제됨
        out("[!] 기록이 삭제되어 측정 결과를 저장할 수 없습니다. 다시 조회하세요.")  # 안내
        return None  # 실패
    out(_LINE)  # 위 구분선
    for line in format_latency(result):  # 결과 줄
        out(line)  # 출력
    out(_LINE)  # 아래 구분선
    out(f"[*] 기록 #{result.id}에 저장되었습니다.")  # 저장 안내
    return result  # 갱신된 결과
