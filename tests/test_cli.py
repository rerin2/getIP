"""CLI 출력 형식과 흐름(getip.cli) 테스트. 가짜 공급자와 임시 DB를 쓴다."""

from conftest import make_geo  # 테스트용 위치 정보
from getip.cli import main as cli  # 검사 대상
from getip.cli.history_view import format_entry, handle_history  # 기록 화면
from getip.geo.base import GeoLookupError  # 조회 실패 예외
from getip.models import Hop  # 홉 데이터

GEO = make_geo()  # 공용 예시


def _feed(monkeypatch, *answers):
    """input()이 차례로 돌려줄 답을 설정한다."""
    queue = list(answers)  # 남은 답
    monkeypatch.setattr("builtins.input", lambda prompt="": queue.pop(0))  # 순서대로 꺼냄


def test_format_geo_keeps_original_six_items_first():
    lines = cli.format_geo(GEO, "example.com")  # 출력 묶음
    assert list(lines)[:6] == ["Domain", "IP Address", "ISP", "Country", "City", "Organization"]  # 기존 항목 순서 유지
    assert (lines["ASN"], lines["Coordinates"], lines["Hosting"]) == ("AS64500 Example", "37.5, 127.0", "No")  # 추가 항목


def test_format_geo_without_domain_or_extras():
    lines = cli.format_geo(make_geo(asn=None, lat=None, lon=None, is_hosting=None))  # 추가 정보 없음
    assert lines["Domain"] == "N/A (My Public IP)"  # 내 IP 조회 표시
    assert list(lines) == ["Domain", "IP Address", "ISP", "Country", "City", "Organization"]  # 없는 항목은 출력하지 않음


def test_format_latency():
    assert cli.format_latency(Hop(1, "1.1.1.1", 1.0, True)) == "<1ms"  # 1 미만
    assert cli.format_latency(Hop(1, "1.1.1.1", 12.0)) == "12ms"  # 정수는 소수점 없이
    assert cli.format_latency(Hop(1, "1.1.1.1", 0.512)) == "0.512ms"  # 소수는 그대로
    assert cli.format_latency(Hop(1, "1.1.1.1", None)) == "N/A"  # 측정값 없음


def test_format_hop_lines():
    hop = Hop(2, "1.2.3.4", 10.0)  # 일반 홉
    assert cli.format_hop(hop, GEO) == (
        "[Hop  2] 1.2.3.4         | 지연: 10ms   | 국가: South Korea  | 도시: Seoul           | ISP: Example ISP"
    )  # 위치 정보가 있는 줄
    assert cli.format_hop(hop, None) == "[Hop  2] 1.2.3.4         | 지연: 10ms   | 정보 없음 (사설망 또는 조회 불가)"  # 위치 없음
    assert cli.format_hop(Hop(3, None, None), None) == "[Hop  3] * 요청 시간 초과 (3초 대기 후 패스)"  # 시간 초과


def test_handle_lookup_prints_result_and_saves(service, capsys):
    cli.handle_lookup(service, "https://www.example.com/page")  # 조회 실행

    out = capsys.readouterr().out  # 화면 출력 수집
    assert "[*] 대상 도메인: example.com" in out  # 정리된 호스트 안내
    assert "[*] 1개의 IP가 발견되었습니다: 1.2.3.4" in out  # IP 안내
    assert "Domain: example.com" in out and "City: Seoul" in out  # 기존 결과 항목
    assert "Reverse DNS: host.example.net" in out and "ASN: AS64500 Example" in out  # 추가 항목
    assert "기록 #1 로 저장되었습니다" in out and service.history.count() == 1  # 기록 저장


def test_handle_lookup_reports_invalid_input(service, capsys):
    cli.handle_lookup(service, "-h")  # 옵션처럼 보이는 입력
    assert "[!]" in capsys.readouterr().out and service.history.count() == 0  # 오류 안내만, 기록 없음


def test_handle_lookup_reports_dns_failure(service, capsys, monkeypatch):
    monkeypatch.setattr(service, "_resolve", lambda host: [])  # DNS 실패
    cli.handle_lookup(service, "no-such-host.example")  # 조회 실행
    assert "[!] 도메인의 IP 주소를 찾을 수 없습니다. 다시 확인해주세요." in capsys.readouterr().out  # 기존 문구


def test_handle_lookup_private_ip_shows_error_item(service, capsys):
    cli.handle_lookup(service, "192.168.0.1")  # 사설 IP 조회
    out = capsys.readouterr().out  # 화면 출력
    assert "IP Address: 192.168.0.1" in out and "Error: 공인 IP가 아니라" in out  # 주소와 사유 표시


def test_handle_my_ip_error_is_printed_as_error_item(service, provider, capsys):
    provider.error = GeoLookupError("IP 정보를 가져오는데 실패했습니다.")  # 조회 실패
    cli.handle_my_ip(service)  # 내 IP 조회 실행
    assert "Error: IP 정보를 가져오는데 실패했습니다." in capsys.readouterr().out  # 기존과 같은 오류 표시


def test_history_view_list_detail_search_delete(service, capsys, monkeypatch):
    cli.handle_lookup(service, "alpha.example")  # 기록 1
    cli.handle_lookup(service, "beta.example")  # 기록 2
    capsys.readouterr()  # 앞선 출력 버림

    _feed(monkeypatch, "1", "/beta", "d 2", "/", "")  # 상세 → 검색 → 삭제 → 검색 해제 → 돌아가기
    handle_history(service.history, print_result=lambda r: cli.print_lines(cli.format_result(r)))  # 기록 화면 실행

    out = capsys.readouterr().out  # 화면 출력
    assert "[기록] 전체 2건" in out  # 첫 목록
    assert "[기록 #1]" in out and "Domain: alpha.example" in out  # 상세 보기
    assert "[기록] 검색 'beta'" in out  # 검색 결과 제목
    assert "기록 #2 을 삭제했습니다" in out  # 삭제 안내
    assert [entry.host for entry in service.history.list()] == ["alpha.example"]  # 한 건만 남음


def test_history_view_clear_requires_confirmation(service, capsys, monkeypatch):
    cli.handle_lookup(service, "alpha.example")  # 기록 1
    _feed(monkeypatch, "clear", "n", "clear", "y", "")  # 거절 후 승인
    handle_history(service.history, print_result=lambda r: None)  # 기록 화면 실행
    out = capsys.readouterr().out  # 화면 출력
    assert "취소했습니다" in out and "1건을 삭제했습니다" in out  # 두 경우 모두 확인
    assert service.history.count() == 0  # 비어 있음


def test_history_view_unknown_number_and_command(service, capsys, monkeypatch):
    _feed(monkeypatch, "42", "d 42", "???", "")  # 없는 번호, 없는 삭제 대상, 알 수 없는 명령
    handle_history(service.history, print_result=lambda r: None)  # 기록 화면 실행
    out = capsys.readouterr().out  # 화면 출력
    assert "(기록이 없습니다)" in out and out.count("기록 #42 이 없습니다") == 2 and "알 수 없는 명령" in out  # 각 안내


def test_format_entry_handles_missing_location(service):
    cli.handle_lookup(service, "192.168.0.1")  # 위치 없는 기록
    line = format_entry(service.history.list()[0])  # 목록 한 줄
    assert "#1" in line and "192.168.0.1" in line and line.endswith(" -")  # 빈 항목은 - 로 표시


def test_main_loop_dispatches_commands(service, capsys, monkeypatch):
    _feed(monkeypatch, "", "m", "example.com", "h", "", "q")  # 빈 입력 → 내 IP → 조회 → 기록(바로 복귀) → 종료
    cli.main(service)  # 메인 반복 실행
    out = capsys.readouterr().out  # 화면 출력
    assert "Domain: N/A (My Public IP)" in out and "Domain: example.com" in out  # 두 조회 결과
    assert "[기록] 전체 1건" in out and out.rstrip().endswith("프로그램을 종료합니다.")  # 기록 화면과 종료 문구


# --- 지연 측정 ('l') ---

def _probe(service, database):
    """가짜 측정을 끼운 지연 측정 서비스."""
    from getip.models import LatencyResult  # 데이터 클래스
    from getip.services.origin import OriginService  # 내 위치
    from getip.services.probe import ProbeService  # 측정 서비스
    from getip.storage.settings import SettingsStore  # 설정 저장소

    measure = lambda ip: [LatencyResult("tcp:443", [24.0], 4, 24.0, 0.0), LatencyResult("icmp", [], 4, None, 1.0)]  # TCP만 응답
    return ProbeService(service.history, service.geo, OriginService(service.my_ip, SettingsStore(database)), measure=measure)  # 서비스


def test_latency_command_needs_lookup_first(service, database, capsys, monkeypatch):
    _feed(monkeypatch, "l", "q")  # 조회 없이 지연 측정 → 종료
    cli.main(service, _probe(service, database))  # 실행
    assert "먼저 도메인이나 IP를 조회하세요" in capsys.readouterr().out  # 안내


def test_latency_command_measures_last_lookup(service, database, capsys, monkeypatch):
    _feed(monkeypatch, "8.8.8.8", "l", "q")  # 조회 → 지연 측정 → 종료
    cli.main(service, _probe(service, database))  # 실행
    out = capsys.readouterr().out  # 화면 출력
    assert "TCP 443: 최소 24 ms (4회 중 1회 응답)" in out and "ICMP (ping): 응답 없음 (4회 시도)" in out  # 방법별 결과
    assert "반경: 현실 추정" in out and "DB 위치까지: 0 km" in out and "기록 #1에 저장" in out  # 요약과 저장
    lines = cli.format_result(service.history.get(1))  # 기록 다시 보기
    assert lines["Latency 1"].startswith("TCP 443") and "Trace" not in lines  # 기록 상세에 지연 포함, 추적 없음
