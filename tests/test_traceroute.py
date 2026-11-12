"""경로 추적 출력 파싱(getip.probe.traceroute) 테스트. 실제 명령은 실행하지 않는다."""

from pathlib import Path  # 샘플 파일 경로

from getip.models import Hop  # 기대값 작성용
from getip.probe.traceroute import build_command, parse_hop_line  # 검사 대상

SAMPLES = Path(__file__).parent / "samples"  # 저장된 명령 출력 위치


def _parse_file(name: str):
    """샘플 파일의 모든 줄을 파싱해 홉만 모은다."""
    lines = (SAMPLES / name).read_text(encoding="utf-8").splitlines()  # 줄 단위로 읽기
    return [hop for hop in map(parse_hop_line, lines) if hop is not None]  # 홉 줄만 남김


def test_parse_korean_windows_output():
    assert _parse_file("tracert_ko.txt") == [
        Hop(1, "192.168.0.1", 1.0, True),  # "<1 ms"는 1 미만으로 기록
        Hop(2, "198.51.100.1", 10.0),  # 첫 번째 측정값 사용
        Hop(3, "100.64.9.233", 3.0),  # 첫 번째 측정값 사용
        Hop(4, None, None),  # 전부 시간 초과
        Hop(5, "198.51.100.77", 12.0),  # 일부만 응답한 홉
        Hop(6, "203.0.113.50", 9.0),  # 목적지
    ]


def test_parse_english_windows_output():
    assert _parse_file("tracert_en.txt") == [
        Hop(1, "192.168.0.1", 1.0, True),  # "<1 ms"
        Hop(2, "198.51.100.1", 10.0),  # 일반 홉
        Hop(3, None, None),  # 시간 초과
        Hop(4, "192.168.0.1", None),  # 도달 불가 보고: 주소는 있고 지연은 없음
    ]


def test_parse_linux_output_keeps_decimal():
    assert _parse_file("traceroute_linux.txt") == [
        Hop(1, "192.168.0.1", 0.512),  # 소수점 지연을 그대로 읽음 (기존에는 "512"로 잘못 읽힘)
        Hop(2, "198.51.100.1", 9.871),  # 일반 홉
        Hop(3, None, None),  # 시간 초과
        Hop(4, "203.0.113.50", 12.004),  # 목적지
    ]


def test_header_lines_are_ignored():
    assert parse_hop_line("최대 30홉 이상의 203.0.113.50(으)로 가는 경로 추적") is None  # 머리말
    assert parse_hop_line("") is None  # 빈 줄
    assert parse_hop_line("Trace complete.") is None  # 완료 문구


def test_build_command_windows():
    command = build_command("example.com", system="Windows")  # Windows용 명령
    assert command[0] == "tracert"  # 실행 파일
    assert command[-1] == "example.com"  # 대상은 마지막 인자
    assert "-d" in command and "-4" in command  # 이름 조회 생략, IPv4 고정


def test_build_command_unix():
    command = build_command("example.com", system="Linux")  # Unix용 명령
    assert command[0] == "traceroute"  # 실행 파일
    assert command[-1] == "example.com"  # 대상은 마지막 인자
    assert "-n" in command and "-4" in command  # 이름 조회 생략, IPv4 고정
