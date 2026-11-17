"""조회 흐름: 입력 정리 → DNS → (위치 조회, 역방향 DNS 동시 실행) → 기록 저장."""

import sqlite3  # 기록 저장 실패 예외
import tempfile  # 기본 DB를 쓸 수 없을 때의 임시 폴더
from concurrent.futures import ThreadPoolExecutor  # 독립된 조회를 동시에 실행
from pathlib import Path  # 경로 객체
from typing import Callable, List, Optional, Tuple  # 타입 표기

from getip import config  # 타임아웃·캐시 기간
from getip.geo import ip_api  # 기본 위치 공급자
from getip.geo.base import GeoLookupError  # 위치 조회 실패 예외
from getip.geo.cached import CachedGeo  # 캐시가 붙은 위치 조회
from getip.models import GeoInfo, LookupResult, Target  # 데이터 클래스
from getip.net import resolver, target as target_module  # DNS 조회, 입력 정리
from getip.storage.db import Database  # DB 연결
from getip.storage.geo_cache import GeoCacheStore  # 위치 캐시
from getip.storage.history import HistoryStore  # 조회 기록


class LookupService:
    """조회에 필요한 부품을 묶어 한 번에 실행한다."""

    def __init__(
        self,
        geo: CachedGeo,
        history: HistoryStore,
        resolve: Callable[[str], List[str]] = resolver.resolve_ipv4,
        reverse: Callable[[str], Optional[str]] = resolver.reverse_dns,
        storage_warning: Optional[str] = None,
    ):
        self.geo = geo  # 위치 조회
        self.history = history  # 조회 기록
        self._resolve = resolve  # DNS 조회 함수 (테스트에서 바꿀 수 있음)
        self._reverse = reverse  # 역방향 DNS 함수 (테스트에서 바꿀 수 있음)
        self.storage_warning = storage_warning  # 기록 저장소에 문제가 있을 때 화면에 알릴 문구

    def resolve(self, text: str) -> Tuple[Target, List[str]]:
        """입력을 정리하고 IP 목록을 찾는다. 형식이 잘못되면 InvalidTargetError."""
        target = target_module.normalize(text)  # 입력 검증
        return target, self._resolve(target.host)  # 대상과 IP 목록 (못 찾으면 빈 목록)

    def lookup(self, target: Target, ip: str, all_ips: List[str]) -> LookupResult:
        """선택된 IP를 조회하고 기록에 저장한다. 일부가 실패해도 결과를 돌려준다."""
        warnings: List[str] = []  # 실패 사유 모음
        with ThreadPoolExecutor(max_workers=2) as pool:  # 두 조회는 서로 독립이라 동시에 실행
            geo_future = pool.submit(self.geo.lookup, ip)  # 위치 조회
            reverse_future = pool.submit(self._reverse, ip)  # 역방향 DNS
            try:
                geo: Optional[GeoInfo] = geo_future.result()  # 위치 결과
            except GeoLookupError as exc:  # 사설 IP, 한도 초과, 네트워크 오류
                geo = None  # 위치 없음
                warnings.append(str(exc))  # 사유 기록
            reverse_name = reverse_future.result()  # 역방향 DNS 결과 (없으면 None)

        result = LookupResult(target=target, ip=ip, all_ips=list(all_ips), geo=geo,
                              reverse_dns=reverse_name, warnings=warnings)  # 결과 조립
        try:
            self.history.save(result)  # 기록 저장 (result.id가 채워짐)
        except (sqlite3.Error, OSError) as exc:  # DB 잠김, 디스크 오류 등
            result.warnings.append(f"기록 저장 실패: {exc}")  # 조회 결과는 그대로 보여줌
        return result  # 최종 결과

    def my_ip(self) -> GeoInfo:
        """현재 기기의 공인 IP 정보. 실패하면 GeoLookupError."""
        return self.geo.lookup_self()  # 캐시를 거치지 않는 조회

    def hop_geo(self, ip: str) -> Optional[GeoInfo]:
        """경로상 홉의 위치를 짧은 타임아웃으로 조회한다. 사설 IP거나 실패하면 None."""
        try:
            return self.geo.lookup(ip, timeout=config.GEO_HOP_TIMEOUT_SEC)  # 캐시 → 공급자
        except GeoLookupError:  # 사설 IP, 조회 실패
            return None  # 정보 없음


def open_database(db_file: Optional[Path] = None) -> Tuple[Database, Optional[str]]:
    """기본 DB를 연다. 열 수 없으면 임시 DB와 안내 문구를 돌려준다."""
    try:
        return Database(db_file), None  # 기본 위치에 DB 열기
    except (sqlite3.Error, OSError) as exc:  # 폴더를 만들 수 없거나 파일이 손상된 경우
        fallback = Path(tempfile.mkdtemp(prefix="getip-")) / "getip.db"  # 임시 폴더에 새 DB
        warning = f"기록 저장소를 열 수 없어 임시 저장소를 사용합니다. 이번 실행의 기록은 보존되지 않습니다. ({exc})"  # 화면 안내용
        return Database(fallback), warning  # 조회 기능은 계속 쓸 수 있게 함


def create_service(database: Database, warning: Optional[str] = None) -> LookupService:
    """열린 DB로 기본 구성(ip-api + 캐시 + 기록) 서비스를 만든다. GUI는 같은 DB를 설정 저장에도 쓴다."""
    cache = GeoCacheStore(database, config.GEO_CACHE_DAYS)  # 위치 캐시
    return LookupService(CachedGeo(ip_api, cache), HistoryStore(database), storage_warning=warning)  # 서비스 조립


def create_default(db_file: Optional[Path] = None) -> LookupService:
    """기본 구성(ip-api + 사용자 폴더의 DB)으로 서비스를 만든다."""
    database, warning = open_database(db_file)  # DB 열기 (실패 시 임시 DB)
    return create_service(database, warning)  # 서비스 조립
