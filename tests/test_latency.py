"""지연 측정(getip.probe.latency)과 거리 계산(getip.estimate.geomath) 테스트. 실제 네트워크는 쓰지 않는다."""

from pathlib import Path  # 샘플 파일 경로
from types import SimpleNamespace  # 가짜 실행 결과

import pytest  # 테스트 도구

from getip import config  # 계수
from getip.estimate import geomath  # 거리 계산
from getip.models import LatencyReport, LatencyResult  # 데이터 클래스
from getip.probe import latency  # 대상

SAMPLES = Path(__file__).parent / "samples"  # 저장된 명령 출력


def _sample(name):
    return (SAMPLES / name).read_text(encoding="utf-8")  # 샘플 읽기


# --- ping 출력 파싱 ---

def test_parse_korean_ping():
    assert latency.parse_ping_output(_sample("ping_ko.txt")) == [9.0, 9.0, 11.0]  # 응답 줄만, 통계 줄("최소 = 9ms") 제외


def test_parse_korean_ping_timeouts():
    assert latency.parse_ping_output(_sample("ping_ko_timeout.txt")) == []  # 응답 없음


def test_parse_english_ping_with_less_than_and_loss():
    assert latency.parse_ping_output(_sample("ping_en.txt")) == [11.0, 1.0, 9.0]  # "<1ms"는 1, 시간 초과 줄 제외


def test_parse_linux_ping_decimals():
    assert latency.parse_ping_output(_sample("ping_linux.txt")) == [9.81, 10.2]  # 소수점, 통계 줄 제외


def test_build_ping_command_rejects_non_ip():
    assert latency.build_ping_command("1.1.1.1", 4, 1000, system="Windows") == ["ping", "-n", "4", "-w", "1000", "1.1.1.1"]  # Windows
    assert latency.build_ping_command("1.1.1.1", 2, 1000, system="Linux")[:5] == ["ping", "-c", "2", "-W", "1"]  # Linux
    with pytest.raises(ValueError):  # 옵션 주입 차단
        latency.build_ping_command("-t", 4, 1000)  # IP가 아님


def test_measure_icmp_uses_runner():
    out = SimpleNamespace(stdout=_sample("ping_en.txt").encode("utf-8"))  # 가짜 실행 결과
    result = latency.measure_icmp("1.1.1.1", count=4, run=lambda *a, **k: out)  # 측정
    assert result.method == "icmp" and result.min_ms == 1.0 and result.loss == 0.25  # 4번 중 3번 응답


def test_measure_icmp_missing_command_is_full_loss():
    def missing(*args, **kwargs):
        raise FileNotFoundError("ping")  # 명령 없음

    result = latency.measure_icmp("1.1.1.1", count=2, run=missing)  # 측정
    assert result.min_ms is None and result.loss == 1.0  # 실패로 기록


# --- TCP 연결 시간 ---

class FakeNetwork:
    """연결할 때마다 정해 둔 시간이 흐르는 가짜 네트워크와 시계. 값이 예외면 그 예외를 던진다."""

    def __init__(self, outcomes):
        self.now = 0.0  # 현재 시각(초)
        self.outcomes = list(outcomes)  # 연결마다 걸릴 시간(초) 또는 예외
        self.addresses = []  # 연결 시도한 주소

    def clock(self):
        return self.now  # 현재 시각

    def connect(self, address, timeout):
        self.addresses.append(address)  # 기록
        outcome = self.outcomes.pop(0)  # 이번 결과
        if isinstance(outcome, Exception):  # 실패
            raise outcome  # 예외
        self.now += outcome  # 연결 시간만큼 흐름
        return FakeSocket()  # 성공


class FakeSocket:
    def close(self):
        pass  # 닫기 흉내


def test_tcp_takes_min_and_counts_loss():
    net = FakeNetwork([0.030, TimeoutError(), 0.010])  # 30ms, 손실, 10ms
    result = latency.measure_tcp("1.1.1.1", ports=(443,), count=3, connect=net.connect, clock=net.clock)  # 측정
    assert result.method == "tcp:443" and result.min_ms == 10.0 and result.samples_ms == [30.0, 10.0]  # 최솟값
    assert result.loss == pytest.approx(1 / 3)  # 3번 중 1번 실패


def test_tcp_falls_back_to_next_port():
    net = FakeNetwork([TimeoutError(), 0.02, 0.02])  # 443 첫 시도 실패 → 80 두 번 성공
    result = latency.measure_tcp("1.1.1.1", ports=(443, 80), count=2, connect=net.connect, clock=net.clock)  # 측정
    assert result.method == "tcp:80" and result.min_ms == 20.0  # 80번 포트 결과
    assert [a[1] for a in net.addresses] == [443, 80, 80]  # 443은 한 번만 시도 (막힌 포트를 계속 기다리지 않음)


def test_tcp_all_ports_fail():
    def refused(address, timeout):
        raise ConnectionRefusedError()  # 포트 닫힘

    result = latency.measure_tcp("1.1.1.1", ports=(443, 80), count=2, connect=refused)  # 측정
    assert result.method == "tcp" and result.min_ms is None and result.loss == 1.0  # 실패로 기록


def test_measure_runs_both_methods():
    tcp = LatencyResult("tcp:443", [30.0], 1, 30.0, 0.0)  # 가짜 TCP 결과
    icmp = LatencyResult("icmp", [9.0], 1, 9.0, 0.0)  # 가짜 ICMP 결과
    results = latency.measure("1.1.1.1", tcp=lambda ip: tcp, icmp=lambda ip: icmp)  # 측정
    assert results == [tcp, icmp]  # 순서 고정
    assert LatencyReport(measured_at=None, origin=None, results=results).min_ms == 9.0  # 둘 중 최솟값 사용


# --- 거리 계산 ---

def test_haversine_known_distances():
    assert geomath.haversine_km(37.5665, 126.978, 35.6762, 139.6503) == pytest.approx(1160, rel=0.01)  # 서울–도쿄 약 1,160km
    assert geomath.haversine_km(0, 0, 0, 180) == pytest.approx(config.EARTH_HALF_CIRCUMFERENCE_KM, rel=0.0001)  # 지구 반 바퀴


def test_rtt_radius_and_cap():
    assert geomath.rtt_upper_km(10) == 10 * config.FIBER_KM_PER_MS  # 10ms → 1,000km
    assert geomath.rtt_typical_km(10) == 10 * config.REALISTIC_KM_PER_MS  # 현실 계수
    assert geomath.rtt_upper_km(1000) == config.EARTH_HALF_CIRCUMFERENCE_KM  # 지구 반 바퀴로 자름


def test_is_beyond_upper():
    assert geomath.is_beyond_upper(10600, 36) is True  # 0단계 관찰 사례: 36ms인데 토론토(10,600km) → 불가능
    assert geomath.is_beyond_upper(1160, 36) is False  # 도쿄는 가능
    assert geomath.is_beyond_upper(None, 36) is None  # 모름
