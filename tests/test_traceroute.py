"""경로 추적 출력 파싱(getip.probe.traceroute) 테스트. 실제 명령은 실행하지 않는다."""

import io  # 가짜 프로세스 출력
from pathlib import Path  # 샘플 파일 경로

import pytest  # 예외 검사

from getip.models import Hop  # 기대값 작성용
from getip.probe.traceroute import (TraceRun, TracerouteUnsupportedError, build_command,  # 검사 대상
                                    parse_hop_line)

SAMPLES = Path(__file__).parent / "samples"  # 저장된 명령 출력 위치


def _parse_file(name: str):
    """샘플 파일의 모든 줄을 파싱해 홉만 모은다."""
    lines = (SAMPLES / name).read_text(encoding="utf-8").splitlines()  # 줄 단위로 읽기
    return [hop for hop in map(parse_hop_line, lines) if hop is not None]  # 홉 줄만 남김


def test_parse_korean_windows_output():
    assert _parse_file("tracert_ko.txt") == [
        Hop(1, "192.168.0.1", 1.0, True),  # "<1 ms"는 1 미만으로 기록
        Hop(2, "198.51.100.1", 9.0),  # 세 값(10, 9, 10) 중 최솟값 (P6)
        Hop(3, "100.64.9.233", 1.0),  # 세 값(3, 3, 1) 중 최솟값
        Hop(4, None, None),  # 전부 시간 초과
        Hop(5, "198.51.100.77", 12.0),  # 일부만 응답한 홉
        Hop(6, "203.0.113.50", 9.0),  # 목적지
    ]


def test_parse_english_windows_output():
    assert _parse_file("tracert_en.txt") == [
        Hop(1, "192.168.0.1", 1.0, True),  # "<1 ms"
        Hop(2, "198.51.100.1", 9.0),  # 일반 홉 (최솟값)
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


def test_less_than_wins_when_smallest():
    hop = parse_hop_line("  1     2 ms    <1 ms     3 ms  192.168.0.1")  # 섞인 측정값
    assert hop.rtt_ms == 1.0 and hop.rtt_less_than  # "<1"이 가장 작음


class FakeProcess:
    """출력 줄을 미리 정해 둔 가짜 tracert 프로세스."""

    def __init__(self, text):
        self.stdout = io.StringIO(text)  # 출력
        self.killed = False  # kill() 호출 여부
        self.done = False  # 끝났는지

    def poll(self):
        return 0 if self.done or self.killed else None  # 끝났으면 0

    def wait(self):
        self.done = True  # 끝남 처리

    def kill(self):
        self.killed = True  # 종료 기록


def fake_popen(text, holder):
    def popen(command, **kwargs):
        holder["command"] = command  # 실행 명령 기록
        holder["process"] = FakeProcess(text)  # 가짜 프로세스
        return holder["process"]  # 반환
    return popen


def test_trace_run_stops_after_silent_hops():
    lines = "  1    <1 ms    <1 ms    <1 ms  192.168.0.1\n" + "".join(
        f"  {i}     *        *        *     요청 시간이 만료되었습니다.\n" for i in range(2, 12))  # 응답 없는 홉 10개
    holder = {}  # 가짜 프로세스 보관
    run = TraceRun("203.0.113.50", max_silent=3, popen=fake_popen(lines, holder))  # 3개 연속이면 멈춤
    hops = list(run.hops())  # 실행
    assert [h.index for h in hops] == [1, 2, 3, 4] and run.silent_cut  # 2~4번 응답 없음에서 멈춤
    assert holder["process"].killed  # 남은 프로세스는 종료됨


def test_trace_run_stop_kills_process():
    holder = {}  # 가짜 프로세스 보관
    run = TraceRun("example.com", popen=fake_popen("  1    <1 ms    <1 ms    <1 ms  192.168.0.1\n", holder))  # 실행
    run.stop()  # 사용자가 중지
    assert run.stopped and holder["process"].killed  # 종료됨


def test_trace_rejects_ipv6():
    with pytest.raises(TracerouteUnsupportedError):  # IPv6는 거부 (P8)
        TraceRun("2606:4700::1111", popen=lambda *a, **k: None)  # 명령을 실행하지 않음
