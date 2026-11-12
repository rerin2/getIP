"""DNS 조회."""

import socket  # 운영체제 DNS 조회 기능
import threading  # 역방향 조회에 시간 제한을 두기 위한 스레드
from typing import List, Optional  # 타입 표기

from getip import config  # 역방향 조회 대기 시간


def resolve_ipv4(host: str) -> List[str]:
    """호스트의 IPv4 주소 목록을 중복 없이 반환한다. 찾지 못하면 빈 목록."""
    try:
        _, _, addresses = socket.gethostbyname_ex(host)  # (이름, 별칭, 주소 목록) 중 주소만 사용
    except (socket.gaierror, socket.herror, UnicodeError):  # 없는 도메인, 조회 실패, 인코딩 불가
        return []  # 실패는 빈 목록으로 표현
    return list(dict.fromkeys(addresses))  # 순서를 유지하며 중복 제거


def reverse_dns(ip: str, timeout: float = config.REVERSE_DNS_TIMEOUT_SEC) -> Optional[str]:
    """IP의 역방향 DNS 이름(PTR)을 찾는다. 없거나 시간 안에 응답이 없으면 None."""
    found: List[str] = []  # 스레드가 결과를 담을 곳

    def work() -> None:
        try:
            found.append(socket.gethostbyaddr(ip)[0])  # (이름, 별칭, 주소) 중 이름만 사용
        except OSError:  # 등록된 이름 없음, 조회 실패 (herror·gaierror 포함)
            pass  # 결과 없음으로 둠

    thread = threading.Thread(target=work, daemon=True)  # 운영체제 조회는 자체 시간 제한이 없어 별도 스레드로 실행
    thread.start()  # 조회 시작
    thread.join(timeout)  # 정해진 시간만 기다림
    name = found[0] if found else None  # 시간 안에 끝났으면 결과 사용
    return name if name and name != ip else None  # IP가 그대로 돌아온 경우는 이름 없음으로 처리
