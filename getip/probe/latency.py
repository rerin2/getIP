"""지연(RTT) 측정: TCP 연결 시간과 ping(ICMP)을 함께 잰다. 출력은 하지 않는다.

이 PC에서는 TCP 연결 시간이 ICMP보다 자주 20ms가량 길게 나와서(설계 6절 4단계), 둘 다 재고 최솟값을 쓴다.
"""

import ipaddress  # 명령 인자로 넘기기 전 IP 형식 확인
import locale  # ping 출력 인코딩 (한글 Windows는 cp949)
import platform  # 운영체제 종류
import re  # ping 출력 파싱
import socket  # TCP 연결
import subprocess  # ping 실행
import time  # 경과 시간 측정
from concurrent.futures import ThreadPoolExecutor  # TCP와 ICMP를 동시에 측정
from typing import Callable, List, Optional, Sequence  # 타입 표기

from getip import config  # 횟수·대기 시간
from getip.models import LatencyResult  # 결과 데이터 클래스
from getip.probe.process import no_window_flags  # 콘솔 창 숨김

# 응답 줄의 "time=11ms", "시간=9ms", "time<1ms", "time=9.81 ms" (기호 바로 뒤에 숫자).
# 통계 줄 "Minimum = 9ms", "최소 = 9ms"는 기호 뒤에 공백이 있어 걸리지 않는다 → 언어와 무관하게 구분.
_PING_TIME = re.compile(r"([=<])(\d+(?:\.\d+)?)\s?ms\b")


def _result(method: str, samples: List[float], attempts: int) -> LatencyResult:
    """측정값 목록으로 결과 객체를 만든다."""
    lost = attempts - len(samples)  # 실패 횟수
    return LatencyResult(
        method=method,  # 측정 방법
        samples_ms=samples,  # 성공한 값
        attempts=attempts,  # 시도 횟수
        min_ms=min(samples) if samples else None,  # 최솟값
        loss=lost / attempts if attempts else 1.0,  # 실패 비율
    )


def tcp_port_samples(ip: str, port: int, count: int, timeout: float,
                     connect: Callable = socket.create_connection,
                     clock: Callable[[], float] = time.perf_counter) -> Optional[LatencyResult]:
    """한 포트로 TCP 연결 시간을 count번 잰다. 포트가 닫혔거나 첫 시도가 실패하면 None (다음 포트로)."""
    samples: List[float] = []  # 성공한 측정값
    for attempt in range(count):  # 정해진 횟수만큼
        start = clock()  # 시작 시각
        try:
            sock = connect((ip, port), timeout=timeout)  # 3방향 핸드셰이크 완료까지 = 왕복 1회
        except ConnectionRefusedError:  # 포트 닫힘 (Windows는 거부 후 재시도해서 시간이 부정확)
            return None  # 이 포트는 측정에 쓰지 않음
        except OSError:  # 시간 초과, 도달 불가
            if attempt == 0:  # 첫 시도부터 실패하면 막힌 포트로 보고
                return None  # 나머지 시도를 기다리지 않음
            continue  # 일시적 손실로 보고 계속
        elapsed = (clock() - start) * 1000  # 경과 시간(ms)
        sock.close()  # 바로 닫음 (데이터는 보내지 않음)
        samples.append(round(elapsed, 2))  # 소수 둘째 자리까지
    return _result(f"tcp:{port}", samples, count)  # 결과


def measure_tcp(ip: str, ports: Sequence[int] = config.LATENCY_TCP_PORTS, count: int = config.LATENCY_SAMPLES,
                timeout: float = config.LATENCY_TCP_TIMEOUT_SEC, connect: Callable = socket.create_connection,
                clock: Callable[[], float] = time.perf_counter) -> LatencyResult:
    """포트를 차례로 시도해 처음 응답한 포트의 결과를 돌려준다. 모두 실패하면 method="tcp", 손실 100%."""
    for port in ports:  # 443 → 80
        result = tcp_port_samples(ip, port, count, timeout, connect, clock)  # 측정
        if result is not None:  # 응답한 포트
            return result  # 사용
    return _result("tcp", [], count)  # 모든 포트 실패


def build_ping_command(ip: str, count: int, wait_ms: int, system: Optional[str] = None) -> List[str]:
    """운영체제에 맞는 ping 명령. ip는 IP 형식이어야 한다 (옵션 주입 방지)."""
    ipaddress.ip_address(ip)  # IP가 아니면 ValueError
    system = (system or platform.system()).lower()  # 운영체제 이름
    if system == "windows":  # Windows ping
        return ["ping", "-n", str(count), "-w", str(wait_ms), ip]  # -n 횟수, -w 대기(ms)
    return ["ping", "-c", str(count), "-W", str(max(1, round(wait_ms / 1000))), ip]  # Linux: -c 횟수, -W 대기(초)


def parse_ping_output(text: str) -> List[float]:
    """ping 출력에서 응답 시간들을 꺼낸다. "<1ms"는 1로 읽는다(상한 계산에 안전한 쪽)."""
    samples: List[float] = []  # 측정값
    for line in text.splitlines():  # 줄마다
        match = _PING_TIME.search(line)  # 응답 시간 찾기
        if match:  # 응답 줄
            samples.append(float(match.group(2)))  # 숫자 부분
    return samples  # 응답 순서대로


def measure_icmp(ip: str, count: int = config.LATENCY_SAMPLES, wait_ms: int = config.LATENCY_PING_WAIT_MS,
                 run: Callable = subprocess.run) -> LatencyResult:
    """ping을 실행해 결과를 돌려준다. 명령이 없거나 실패하면 손실 100%."""
    command = build_ping_command(ip, count, wait_ms)  # 명령 구성
    limit = count * wait_ms / 1000 + 5  # 전체 실행 시간 상한(초)
    try:
        done = run(command, capture_output=True, timeout=limit, creationflags=no_window_flags())  # 셸 없이 실행
    except (OSError, subprocess.TimeoutExpired):  # 명령 없음, 너무 오래 걸림
        return _result("icmp", [], count)  # 측정 실패
    text = done.stdout.decode(locale.getpreferredencoding(False), errors="ignore")  # 한글 Windows는 cp949
    return _result("icmp", parse_ping_output(text)[:count], count)  # 응답 줄만 사용


def measure(ip: str, tcp: Callable[[str], LatencyResult] = measure_tcp,
            icmp: Callable[[str], LatencyResult] = measure_icmp) -> List[LatencyResult]:
    """TCP와 ICMP를 동시에 재서 [TCP 결과, ICMP 결과]를 돌려준다."""
    with ThreadPoolExecutor(max_workers=2) as pool:  # 두 측정은 서로 독립
        tcp_future = pool.submit(tcp, ip)  # TCP 연결 시간
        icmp_future = pool.submit(icmp, ip)  # ping
        return [tcp_future.result(), icmp_future.result()]  # 순서 고정
