"""여러 테스트가 함께 쓰는 준비물. 실제 네트워크와 사용자 DB는 건드리지 않는다."""

from typing import Dict, Iterable, List  # 타입 표기

import pytest  # 테스트 도구

from getip.geo.base import GeoLookupError  # 조회 실패 예외
from getip.geo.cached import CachedGeo  # 캐시가 붙은 위치 조회
from getip.models import GeoInfo  # 위치 데이터 클래스
from getip.services.lookup import LookupService  # 조회 서비스
from getip.storage.db import Database  # DB 연결
from getip.storage.geo_cache import GeoCacheStore  # 위치 캐시
from getip.storage.history import HistoryStore  # 조회 기록


def make_geo(ip: str = "1.2.3.4", **overrides) -> GeoInfo:
    """테스트용 위치 정보를 만든다."""
    values = dict(ip=ip, country="South Korea", city="Seoul", isp="Example ISP", org="Example Org",
                  source="fake", country_code="KR", lat=37.5, lon=127.0, asn="AS64500 Example", is_hosting=False)  # 기본값
    values.update(overrides)  # 필요한 항목만 바꿈
    return GeoInfo(**values)  # 데이터 객체 생성


class FakeProvider:
    """네트워크 없이 동작하는 가짜 위치 공급자. 호출 내역을 기록한다."""

    name = "fake"  # 캐시 구분용 이름

    def __init__(self):
        self.single_calls: List[str] = []  # lookup에 들어온 IP
        self.batch_calls: List[List[str]] = []  # lookup_batch에 들어온 IP 묶음
        self.error = None  # 지정하면 모든 호출이 이 예외를 던짐
        self.unknown = set()  # 공급자가 정보를 주지 않을 IP

    def lookup(self, ip: str = "", timeout: float = 5) -> GeoInfo:
        self.single_calls.append(ip)  # 호출 기록
        if self.error:  # 실패하도록 설정된 경우
            raise self.error  # 예외 발생
        if ip in self.unknown:  # 정보가 없는 IP
            raise GeoLookupError("IP 정보를 가져오는데 실패했습니다.")  # 실제 공급자와 같은 문구
        return make_geo(ip or "9.9.9.9")  # 빈 IP는 내 IP로 간주

    def lookup_batch(self, ips: Iterable[str], timeout: float = 5) -> Dict[str, GeoInfo]:
        ips = list(ips)  # 반복 가능 객체를 목록으로
        self.batch_calls.append(ips)  # 호출 기록
        if self.error:  # 실패하도록 설정된 경우
            raise self.error  # 예외 발생
        return {ip: make_geo(ip) for ip in ips if ip not in self.unknown}  # 정보가 있는 IP만


@pytest.fixture
def database(tmp_path):
    return Database(tmp_path / "test.db")  # 테스트마다 새 임시 DB


@pytest.fixture
def provider():
    return FakeProvider()  # 가짜 공급자


@pytest.fixture
def cached_geo(provider, database):
    return CachedGeo(provider, GeoCacheStore(database, max_age_days=7))  # 가짜 공급자 + 임시 캐시


@pytest.fixture
def service(cached_geo, database):
    return LookupService(
        cached_geo,
        HistoryStore(database),
        resolve=lambda host: [host] if host[0].isdigit() else ["1.2.3.4"],  # IP 입력은 그대로, 도메인은 고정 IP
        reverse=lambda ip: "host.example.net",  # 역방향 DNS 고정
    )
