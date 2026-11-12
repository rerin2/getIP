"""운영체제의 tracert/traceroute를 실행해 홉을 하나씩 돌려준다. 출력은 하지 않는다."""

import platform  # 운영체제 종류 확인
import re  # 출력 줄 파싱용 정규식
import subprocess  # 외부 명령 실행
from typing import Iterator, List, Optional  # 타입 표기

from getip import config  # 홉 수·대기 시간 설정
from getip.models import Hop  # 홉 데이터 클래스

_HOP_PATTERN = re.compile(r"^\s*(\d+)\s+")  # 줄 맨 앞의 홉 번호
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")  # IPv4 주소
_TIME_PATTERN = re.compile(r"(<?)\s*(\d+(?:\.\d+)?)\s*ms")  # "12 ms", "<1 ms", "0.5 ms" 형태의 지연시간


class TracerouteUnavailableError(Exception):
    """tracert/traceroute 명령을 찾을 수 없을 때 발생."""


def build_command(host: str, system: Optional[str] = None) -> List[str]:
    """운영체제에 맞는 경로 추적 명령을 만든다. host는 target.normalize로 검증된 값이어야 한다."""
    system = (system or platform.system()).lower()  # 인자가 없으면 현재 운영체제 사용
    if system == "windows":  # Windows인 경우
        wait = str(config.TRACE_WAIT_MS_WINDOWS)  # 홉당 대기 시간(ms)
        return ["tracert", "-d", "-4", "-h", str(config.TRACE_MAX_HOPS), "-w", wait, host]  # -d: 이름 조회 생략, -4: IPv4
    wait = str(config.TRACE_WAIT_SEC_UNIX)  # 홉당 대기 시간(초)
    return ["traceroute", "-n", "-4", "-m", str(config.TRACE_MAX_HOPS), "-w", wait, "-q", "1", host]  # -n: 이름 조회 생략, -q 1: 홉당 1회 측정


def parse_hop_line(line: str) -> Optional[Hop]:
    """출력 한 줄을 Hop으로 변환한다. 홉 줄이 아니면 None."""
    hop_match = _HOP_PATTERN.search(line)  # 홉 번호로 시작하는지 확인
    if not hop_match:  # 머리말·빈 줄·완료 문구 등
        return None  # 홉 아님
    index = int(hop_match.group(1))  # 홉 번호

    ips = _IP_PATTERN.findall(line)  # 줄에 있는 모든 IPv4 주소
    if not ips:  # 주소가 없는 경우
        if "*" in line:  # 응답 없음 표시가 있으면
            return Hop(index=index, ip=None, rtt_ms=None)  # 시간 초과 홉
        return None  # 주소도 '*'도 없으면 홉으로 보지 않음

    times = _TIME_PATTERN.findall(line)  # (부등호, 숫자) 쌍 목록
    if not times:  # 주소는 있지만 측정값이 없는 경우 (도달 불가 보고 등)
        return Hop(index=index, ip=ips[-1], rtt_ms=None)  # 지연 없음으로 기록
    less_than, value = times[0]  # 첫 번째 측정값 사용 (기존 동작 유지)
    return Hop(index=index, ip=ips[-1], rtt_ms=float(value), rtt_less_than=bool(less_than))  # 주소는 줄의 마지막 것(응답한 장비)


def trace(host: str) -> Iterator[Hop]:
    """host까지의 경로를 추적하며 홉이 확인될 때마다 yield한다."""
    command = build_command(host)  # 실행할 명령 구성
    try:
        process = subprocess.Popen(  # 명령 실행 (셸을 거치지 않으므로 문자열 주입 불가)
            command,  # 인자 목록
            stdout=subprocess.PIPE,  # 표준 출력을 읽어옴
            stderr=subprocess.STDOUT,  # 오류 출력도 같은 흐름으로 합침
            text=True,  # 바이트가 아닌 문자열로 읽음
            errors="ignore",  # 깨진 글자는 무시 (숫자·IP만 필요하므로 무해)
        )
    except FileNotFoundError as exc:  # 명령이 설치돼 있지 않음
        raise TracerouteUnavailableError(command[0]) from exc  # 전용 예외로 전달

    try:
        for line in process.stdout:  # 출력이 나오는 대로 한 줄씩 처리
            hop = parse_hop_line(line)  # 줄을 홉으로 해석
            if hop is not None:  # 홉 줄이면
                yield hop  # 호출자에게 즉시 전달
        process.wait()  # 명령 종료 대기
    finally:
        if process.poll() is None:  # 호출자가 중간에 그만둬 아직 실행 중이면
            process.kill()  # 프로세스 종료
        process.stdout.close()  # 파이프 닫기
