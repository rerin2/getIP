"""위치 공급자가 지켜야 할 공통 규칙. 공급자를 바꾸거나 추가할 때 이 형태만 맞추면 된다."""

from typing import Dict, Iterable, Optional, Protocol  # 타입 표기

from getip.models import GeoInfo  # 조회 결과 데이터 클래스


class GeoLookupError(Exception):
    """위치 조회에 실패했을 때 발생. 메시지는 사용자에게 그대로 보여줄 수 있다."""


class GeoRateLimitError(GeoLookupError):
    """공급자의 호출 한도를 넘었을 때 발생."""

    def __init__(self, retry_after_sec: Optional[int] = None):
        self.retry_after_sec = retry_after_sec  # 다시 시도할 수 있을 때까지 남은 시간(초)
        wait = f" {retry_after_sec}초 후 다시 시도하세요." if retry_after_sec else ""  # 대기 시간 안내
        super().__init__("위치 조회 한도를 초과했습니다." + wait)  # 사용자용 문구


class GeoProvider(Protocol):
    """위치 공급자 인터페이스."""

    name: str  # 공급자 이름 (캐시 구분과 출처 표시에 사용)

    def lookup(self, ip: str = "", timeout: float = 5) -> GeoInfo:
        """IP 하나를 조회한다. 실패하면 GeoLookupError."""

    def lookup_batch(self, ips: Iterable[str], timeout: float = 5) -> Dict[str, GeoInfo]:
        """여러 IP를 조회해 성공한 것만 {ip: 정보}로 돌려준다. 호출 자체가 실패하면 GeoLookupError."""
