"""대화형 CLI. 입력과 출력만 담당하고, 실제 조회는 서비스 계층에 맡긴다."""

from typing import Dict, List, Optional  # 타입 표기

from getip import config  # 홉 수·목록 건수 설정
from getip.cli.history_view import handle_history  # 기록 보기 화면
from getip.geo.base import GeoLookupError  # 위치 조회 실패 예외
from getip.models import GeoInfo, Hop, LookupResult  # 결과 데이터 클래스
from getip.net import target  # 입력 형식 오류 예외
from getip.probe import traceroute  # 경로 추적
from getip.services.lookup import LookupService, create_default  # 조회 서비스

_RESULT_LINE = "-" * 35  # 조회 결과 구분선
_TRACE_LINE = "-" * 90  # 경로 추적 구분선


def format_geo(info: GeoInfo, domain: str = "") -> Dict[str, object]:
    """위치 정보를 화면에 찍을 '항목: 값' 묶음으로 바꾼다."""
    lines: Dict[str, object] = {
        "Domain": domain if domain else "N/A (My Public IP)",  # 도메인이 없으면 내 IP 조회라는 뜻
        "IP Address": info.ip,  # 조회된 IP
        "ISP": info.isp,  # 인터넷 사업자
        "Country": info.country,  # 국가
        "City": info.city,  # 도시
        "Organization": info.org,  # 조직
    }  # 기존 화면과 같은 여섯 항목
    if info.asn:  # ASN이 있으면
        lines["ASN"] = info.asn  # AS 번호와 이름
    if info.lat is not None and info.lon is not None:  # 좌표가 있으면
        lines["Coordinates"] = f"{info.lat}, {info.lon}"  # 위도, 경도
    if info.is_hosting is not None:  # 호스팅 여부를 알면
        lines["Hosting"] = "Yes" if info.is_hosting else "No"  # 데이터센터 대역인지
    return lines  # 출력용 묶음


def format_result(result: LookupResult) -> Dict[str, object]:
    """조회 결과 전체를 화면에 찍을 '항목: 값' 묶음으로 바꾼다."""
    if result.geo is not None:  # 위치 정보가 있으면
        lines = format_geo(result.geo, result.target.host)  # 위치 항목부터
    else:  # 위치를 얻지 못했으면
        lines = {"Domain": result.target.host, "IP Address": result.ip}  # 기본 항목만
    if result.reverse_dns:  # 역방향 DNS 이름이 있으면
        lines["Reverse DNS"] = result.reverse_dns  # 이름 표시
    for number, warning in enumerate(result.warnings, start=1):  # 실패 사유마다
        lines["Error" if number == 1 else f"Error {number}"] = warning  # 첫 번째는 기존과 같은 항목 이름
    return lines  # 출력용 묶음


def format_latency(hop: Hop) -> str:
    """홉의 지연시간을 '<1ms', '12ms', 'N/A' 형태로 바꾼다."""
    if hop.rtt_ms is None:  # 측정값이 없으면
        return "N/A"  # 없음 표시
    prefix = "<" if hop.rtt_less_than else ""  # "미만" 표시 여부
    return f"{prefix}{hop.rtt_ms:g}ms"  # 불필요한 소수점 없이 출력 (12.0 → 12)


def format_hop(hop: Hop, info: Optional[GeoInfo]) -> str:
    """홉 한 줄을 화면 출력용 문자열로 만든다."""
    if hop.ip is None:  # 응답이 없던 홉
        return f"[Hop {hop.index:>2}] * 요청 시간 초과 (3초 대기 후 패스)"  # 시간 초과 문구
    head = f"[Hop {hop.index:>2}] {hop.ip:<15} | 지연: {format_latency(hop):<6} | "  # 번호·주소·지연 공통 부분
    if info is None:  # 위치를 얻지 못한 경우
        return head + "정보 없음 (사설망 또는 조회 불가)"  # 사설 IP 등
    country = info.country or "N/A"  # 국가가 비면 N/A
    city = info.city or "N/A"  # 도시가 비면 N/A
    isp = info.isp or "N/A"  # 사업자가 비면 N/A
    return head + f"국가: {country:<12} | 도시: {city:<15} | ISP: {isp}"  # 위치 정보 포함 줄


def print_lines(lines: Dict[str, object]) -> None:
    """'항목: 값' 묶음을 구분선과 함께 출력한다."""
    print(_RESULT_LINE)  # 위 구분선
    for key, value in lines.items():  # 항목 순서대로
        print(f"{key}: {value}")  # 한 줄씩 출력
    print(_RESULT_LINE)  # 아래 구분선


def _choose_ip(ip_list: List[str]) -> Optional[str]:
    """IP가 여러 개일 때 사용자에게 고르게 한다. 취소하면 None."""
    if len(ip_list) == 1:  # 하나뿐이면
        print(f"[*] 1개의 IP가 발견되었습니다: {ip_list[0]}")  # 안내만 하고
        return ip_list[0]  # 바로 선택

    print(f"[*] {len(ip_list)}개의 IP가 발견되었습니다. 조회할 IP를 선택하세요:")  # 선택 안내
    for number, ip in enumerate(ip_list, start=1):  # 1번부터 번호 매김
        print(f"  {number}. {ip}")  # 목록 출력

    while True:  # 올바른 입력이 들어올 때까지 반복
        choice = input("조회할 번호를 선택하세요 (취소: 'c'): ").strip()  # 번호 입력
        if choice.lower() == "c":  # 취소
            return None  # 선택 없음
        if choice.isdigit() and 1 <= int(choice) <= len(ip_list):  # 목록 범위 안의 번호
            return ip_list[int(choice) - 1]  # 선택한 IP
        print("[!] 목록에 있는 올바른 번호를 입력해주세요.")  # 재입력 안내


def handle_my_ip(service: LookupService) -> None:
    """현재 기기의 공인 IP 정보를 출력한다."""
    print("\n[*] 현재 기기의 공인 IP 정보를 조회합니다...")  # 진행 안내
    try:
        print_lines(format_geo(service.my_ip()))  # 조회 후 출력
    except GeoLookupError as exc:  # 조회 실패
        print_lines({"Error": str(exc)})  # 오류 문구만 출력


def handle_trace(service: LookupService) -> None:
    """추적 대상을 입력받아 경로를 홉 단위로 출력한다."""
    trace_target = input("라우팅을 추적할 도메인 또는 IP를 입력하세요: ").strip()  # 대상 입력
    if not trace_target:  # 빈 입력
        print("[!] 입력이 취소되었습니다.")  # 취소 안내
        return  # 메뉴로 복귀
    try:
        host = target.normalize(trace_target).host  # 입력 검증
    except target.InvalidTargetError as exc:  # 형식 오류
        print(f"[!] {exc}")  # 사유 안내
        return  # 메뉴로 복귀

    print(f"\n[*] '{host}' 라우팅 경로 추적을 시작합니다. (최대 {config.TRACE_MAX_HOPS}홉)")  # 시작 안내
    print(_TRACE_LINE)  # 구분선
    try:
        for hop in traceroute.trace(host):  # 홉이 확인되는 대로
            info = service.hop_geo(hop.ip) if hop.ip else None  # 응답한 홉만 위치 조회 (사설 IP·캐시는 API 호출 없음)
            print(format_hop(hop, info))  # 한 줄 출력
        print(_TRACE_LINE)  # 구분선
        print("[*] 라우팅 경로 추적이 완료되었습니다.")  # 완료 안내
    except traceroute.TracerouteUnavailableError:  # 명령이 없음
        print("[!] tracert(또는 traceroute) 명령어를 찾을 수 없습니다. OS 환경을 확인해주세요.")  # 환경 안내
    except OSError as exc:  # 실행 권한 등 운영체제 오류
        print(f"[!] 추적 중 오류 발생: {exc}")  # 원인 출력


def handle_lookup(service: LookupService, text: str) -> None:
    """도메인/URL/IP를 조회해 정보를 출력하고 기록에 남긴다."""
    try:
        lookup_target, ip_list = service.resolve(text)  # 입력 검증 + DNS 조회
    except target.InvalidTargetError as exc:  # 형식 오류
        print(f"[!] {exc}")  # 사유 안내
        return  # 메뉴로 복귀
    print(f"\n[*] 대상 도메인: {lookup_target.host}")  # 정리된 대상 안내

    if not ip_list:  # 주소를 찾지 못함
        print("[!] 도메인의 IP 주소를 찾을 수 없습니다. 다시 확인해주세요.")  # 실패 안내
        return  # 메뉴로 복귀

    selected_ip = _choose_ip(ip_list)  # 조회할 IP 결정
    if selected_ip is None:  # 사용자가 취소
        return  # 메뉴로 복귀

    print(f"\n[*] {selected_ip} 정보 조회 중...")  # 진행 안내
    result = service.lookup(lookup_target, selected_ip, ip_list)  # 조회 + 기록 저장
    print_lines(format_result(result))  # 결과 출력
    if result.id is not None:  # 기록에 저장됐으면
        print(f"[*] 기록 #{result.id} 로 저장되었습니다. ('h' 입력으로 기록 보기)")  # 기록 번호 안내


def main(service: Optional[LookupService] = None) -> None:
    """메뉴를 보여주고 종료 명령이 올 때까지 입력을 처리한다."""
    service = service or create_default()  # 서비스가 주어지지 않으면 기본 구성 사용
    print("=== IP & ISP 및 라우팅 조회 도구 ===")  # 제목
    print("- URL 또는 도메인 입력: 해당 주소 IP/ISP 조회")  # 사용법 1
    print("- 'm' 입력: 현재 기기의 공인 IP 조회")  # 사용법 2
    print("- 't' 입력: 라우팅 추적 (Traceroute) 실행")  # 사용법 3
    print("- 'h' 입력: 조회 기록 보기")  # 사용법 4
    print("- 'q' 입력: 프로그램 종료")  # 사용법 5
    if service.storage_warning:  # 기록 저장소에 문제가 있으면
        print(f"[!] {service.storage_warning}")  # 시작할 때 알림

    while True:  # 종료 명령 전까지 반복
        try:
            text = input("\n[입력 대기] 도메인/URL, m(내 IP), t(라우팅 추적), h(기록), q(종료) : ").strip()  # 명령 입력
            command = text.lower()  # 대소문자 구분 없이 비교
            if command in ("q", "exit"):  # 종료 명령
                print("프로그램을 종료합니다.")  # 종료 안내
                break  # 반복 탈출
            if not text:  # 빈 입력
                continue  # 다시 입력받음
            if command == "m":  # 내 IP 조회
                handle_my_ip(service)  # 실행
            elif command == "t":  # 경로 추적
                handle_trace(service)  # 실행
            elif command == "h":  # 기록 보기
                handle_history(service.history, print_result=lambda r: print_lines(format_result(r)))  # 실행
            else:  # 그 외는 조회 대상으로 간주
                handle_lookup(service, text)  # 실행
        except (EOFError, KeyboardInterrupt):  # 입력 종료(Ctrl+Z) 또는 Ctrl+C
            print("\n프로그램을 종료합니다.")  # 종료 안내
            break  # 반복 탈출


if __name__ == "__main__":  # 이 파일을 직접 실행한 경우
    main()  # CLI 시작
