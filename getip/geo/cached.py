"""공급자 앞에 캐시와 사설 IP 필터를 둔 위치 조회. API 호출 수를 줄이는 것이 목적이다."""

import ipaddress  # 공인/사설 IP 판별
import sqlite3  # 캐시 저장소 오류 예외
from dataclasses import dataclass, field  # 일괄 조회 결과 묶음
from typing import Dict, Iterable, List, Optional  # 타입 표기

from getip import config  # 타임아웃 설정
from getip.geo.base import GeoLookupError, GeoProvider  # 공급자 규칙과 예외
from getip.models import GeoInfo  # 조회 결과 데이터 클래스
from getip.storage.geo_cache import GeoCacheStore  # 캐시 저장소

NOT_PUBLIC_MESSAGE = "공인 IP가 아니라 위치 정보가 없습니다. (사설망·예약 대역)"  # 사설 IP 안내 문구


def is_public_ip(ip: str) -> bool:
    """인터넷에서 통용되는 공인 IP인지 판별한다. 사설·루프백·예약 대역은 False."""
    try:
        return ipaddress.ip_address(ip).is_global  # 전역 라우팅 가능한 주소인지
    except ValueError:  # IP 형식이 아님
        return False  # 조회 대상 아님


@dataclass
class BatchResult:
    """여러 IP 조회 결과."""

    found: Dict[str, GeoInfo] = field(default_factory=dict)  # 위치를 얻은 IP
    skipped: List[str] = field(default_factory=list)  # 공인 IP가 아니라 조회하지 않은 IP
    pending: List[str] = field(default_factory=list)  # 한도·오류로 이번에 조회하지 못한 IP
    error: Optional[str] = None  # 조회 실패 사유 (pending이 있을 때)


class CachedGeo:
    """캐시 → 공급자 순서로 위치를 찾는다."""

    def __init__(self, provider: GeoProvider, cache: GeoCacheStore):
        self._provider = provider  # 실제 조회를 하는 공급자
        self._cache = cache  # 조회 결과 저장소

    def _cache_get(self, ips: List[str]) -> Dict[str, GeoInfo]:
        """캐시에서 찾는다. 캐시는 보조 수단이므로 저장소 오류는 '없음'으로 처리한다."""
        try:
            return self._cache.get_many(ips, self._provider.name)  # 유효한 항목만
        except (sqlite3.Error, OSError):  # DB 잠김·손상 등
            return {}  # 캐시 없이 진행

    def _cache_put(self, infos: Iterable[GeoInfo]) -> None:
        """캐시에 저장한다. 실패해도 조회 결과에는 영향을 주지 않는다."""
        try:
            self._cache.put_many(infos)  # 결과 저장
        except (sqlite3.Error, OSError):  # DB 잠김·손상 등
            pass  # 저장을 건너뜀

    def lookup_self(self, timeout: float = config.GEO_TIMEOUT_SEC) -> GeoInfo:
        """현재 기기의 공인 IP 정보를 조회한다. 내 IP는 바뀔 수 있어 캐시를 거치지 않는다."""
        info = self._provider.lookup("", timeout)  # IP 없이 조회 → 내 공인 IP
        self._cache_put([info])  # 이후 같은 IP 조회에 재사용
        return info  # 조회 결과

    def lookup(self, ip: str, timeout: float = config.GEO_TIMEOUT_SEC) -> GeoInfo:
        """IP 하나를 조회한다. 공인 IP가 아니거나 실패하면 GeoLookupError."""
        if not is_public_ip(ip):  # 사설·예약 대역이면
            raise GeoLookupError(NOT_PUBLIC_MESSAGE)  # API를 호출하지 않고 종료
        cached = self._cache_get([ip]).get(ip)  # 캐시 확인
        if cached is not None:  # 유효한 캐시가 있으면
            return cached  # API 호출 생략
        info = self._provider.lookup(ip, timeout)  # 공급자에 조회
        self._cache_put([info])  # 결과 저장
        return info  # 조회 결과

    def lookup_many(self, ips: Iterable[str], timeout: float = config.GEO_TIMEOUT_SEC,
                    fetch: bool = True) -> BatchResult:
        """여러 IP를 조회한다. 캐시에 없는 공인 IP만 모아 한 번에 요청한다. 예외를 던지지 않는다.

        fetch=False면 캐시만 보고, 없는 IP는 pending으로 돌려준다 (한도 초과 후 대기 중일 때).
        """
        unique = list(dict.fromkeys(ips))  # 순서를 유지하며 중복 제거
        result = BatchResult()  # 결과 묶음
        public = [ip for ip in unique if is_public_ip(ip)]  # 조회 대상
        result.skipped = [ip for ip in unique if not is_public_ip(ip)]  # 조회하지 않을 IP
        result.found = self._cache_get(public)  # 캐시에 있는 것 먼저
        missing = [ip for ip in public if ip not in result.found]  # 새로 조회할 IP
        if not missing:  # 전부 캐시에 있으면
            return result  # API 호출 없음
        if not fetch:  # 외부 호출 금지
            result.pending = missing  # 나중에 조회할 목록
            return result  # 캐시 결과만
        try:
            fetched = self._provider.lookup_batch(missing, timeout)  # 일괄 조회
        except GeoLookupError as exc:  # 한도 초과·네트워크 오류
            result.pending = missing  # 다음 기회에 다시 조회할 목록
            result.error = str(exc)  # 사유 기록
            return result  # 캐시에서 찾은 것만 반환
        self._cache_put(fetched.values())  # 새 결과 저장
        result.found.update(fetched)  # 결과에 합침
        result.pending = [ip for ip in missing if ip not in fetched]  # 공급자가 정보를 주지 않은 IP
        return result  # 최종 결과
