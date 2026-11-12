"""ip-api.com을 이용한 IP 위치 조회."""

from typing import Any, Dict, Iterable, List, Optional  # 타입 표기

import requests  # HTTP 요청 라이브러리

from getip import config  # API 주소와 타임아웃 설정
from getip.geo.base import GeoLookupError, GeoRateLimitError  # 공통 예외
from getip.models import GeoInfo  # 조회 결과 데이터 클래스

SOURCE_NAME = "ip-api.com"  # GeoInfo.source에 기록할 공급자 이름
name = SOURCE_NAME  # GeoProvider 규칙의 이름 항목 (모듈 자체를 공급자로 사용)
_PARAMS = {"fields": config.GEO_FIELDS}  # 필요한 항목만 요청


def _request(method: str, url: str, timeout: float, **kwargs: Any) -> Any:
    """API를 호출해 JSON을 돌려준다. 네트워크·한도·형식 오류를 공통 예외로 바꾼다."""
    try:
        response = requests.request(method, url, params=_PARAMS, timeout=timeout, **kwargs)  # API 호출
    except requests.RequestException as exc:  # 연결 실패, 시간 초과 등
        raise GeoLookupError(str(exc)) from exc  # 조회 실패로 통일

    if response.status_code == 429:  # 호출 한도 초과
        raise GeoRateLimitError(_retry_after(response))  # 남은 대기 시간과 함께 알림
    try:
        return response.json()  # 응답 본문을 JSON으로 해석
    except ValueError as exc:  # JSON이 아닌 응답
        raise GeoLookupError(str(exc)) from exc  # 조회 실패로 통일


def _retry_after(response: Any) -> Optional[int]:
    """응답 헤더 X-Ttl에서 한도가 풀릴 때까지 남은 초를 읽는다."""
    value = response.headers.get("X-Ttl")  # ip-api가 알려주는 남은 시간
    return int(value) if value and value.isdigit() else None  # 숫자일 때만 사용


def _to_geo(data: Dict[str, Any], fallback_ip: str = "") -> GeoInfo:
    """API 응답 한 건을 GeoInfo로 바꾼다."""
    return GeoInfo(
        ip=data.get("query") or fallback_ip,  # API가 인식한 IP (내 IP 조회 시 여기서 알게 됨)
        country=data.get("country"),  # 국가명
        city=data.get("city"),  # 도시명
        isp=data.get("isp"),  # 인터넷 사업자
        org=data.get("org"),  # 조직명
        source=SOURCE_NAME,  # 공급자 표시
        country_code=data.get("countryCode"),  # 두 글자 국가 코드
        lat=data.get("lat"),  # 위도
        lon=data.get("lon"),  # 경도
        asn=data.get("as") or None,  # AS 번호와 이름 (빈 문자열이면 없음)
        is_hosting=data.get("hosting"),  # 호스팅 대역 여부
    )


def lookup(ip: str = "", timeout: float = config.GEO_TIMEOUT_SEC) -> GeoInfo:
    """IP의 위치 정보를 조회한다. ip가 빈 문자열이면 현재 기기의 공인 IP를 조회한다."""
    data = _request("GET", config.GEO_API_URL.format(ip=ip), timeout)  # 단건 조회
    if not isinstance(data, dict) or data.get("status") != "success":  # 사설 IP·잘못된 IP 등 API가 실패를 알린 경우
        raise GeoLookupError("IP 정보를 가져오는데 실패했습니다.")  # 기존 CLI와 같은 문구
    return _to_geo(data, ip)  # 결과 변환


def lookup_batch(ips: Iterable[str], timeout: float = config.GEO_TIMEOUT_SEC) -> Dict[str, GeoInfo]:
    """여러 IP를 일괄 조회해 성공한 것만 {ip: 정보}로 돌려준다."""
    pending: List[str] = list(dict.fromkeys(ips))  # 순서를 유지하며 중복 제거
    found: Dict[str, GeoInfo] = {}  # 조회에 성공한 결과
    for start in range(0, len(pending), config.GEO_BATCH_SIZE):  # 100개씩 나눠 요청
        chunk = pending[start:start + config.GEO_BATCH_SIZE]  # 이번에 보낼 묶음
        data = _request("POST", config.GEO_BATCH_URL, timeout, json=chunk)  # 일괄 조회
        if not isinstance(data, list):  # 예상과 다른 응답
            raise GeoLookupError("IP 정보를 가져오는데 실패했습니다.")  # 조회 실패
        for item in data:  # 응답 항목마다
            if isinstance(item, dict) and item.get("status") == "success" and item.get("query"):  # 성공한 것만
                found[item["query"]] = _to_geo(item)  # IP를 키로 저장
    return found  # 실패한 IP는 결과에 없음
