"""'내 위치' 결정: 수동 지정(D13)이 있으면 그것을, 없으면 내 공인 IP의 위치(ip-api)를 쓴다."""

import threading  # 여러 요청이 동시에 캐시를 건드릴 때 보호
import time  # 캐시 유효 시간
from typing import Callable, Optional, Tuple  # 타입 표기

from getip import config  # 캐시 유지 시간
from getip.geo.base import GeoLookupError  # 내 IP 조회 실패
from getip.models import GeoInfo, MeInfo, Origin  # 데이터 클래스
from getip.storage.settings import SettingsStore  # 수동 위치 저장소


class OriginService:
    """반경 원과 경로선의 시작점을 정한다."""

    def __init__(self, lookup_self: Callable[[], GeoInfo], settings: SettingsStore,
                 clock: Callable[[], float] = time.monotonic, cache_sec: float = config.MY_LOCATION_CACHE_SEC):
        self._lookup_self = lookup_self  # 내 공인 IP 조회 (캐시 없이 공급자 직접)
        self._settings = settings  # 수동 위치 저장소
        self._clock = clock  # 현재 시각 (테스트에서 바꿈)
        self._cache_sec = cache_sec  # 내 IP 정보 재사용 시간
        self._cached: Optional[Tuple[float, GeoInfo]] = None  # (조회 시각, 정보)
        self._lock = threading.Lock()  # 캐시 보호

    def _fetch_self(self) -> GeoInfo:
        """내 IP 정보를 새로 조회해 캐시에 넣는다. 실패하면 GeoLookupError."""
        info = self._lookup_self()  # 공급자 조회
        with self._lock:  # 캐시 갱신
            self._cached = (self._clock(), info)  # 시각과 함께 기억
        return info  # 결과

    def _cached_self(self) -> Optional[GeoInfo]:
        """유효한 캐시가 있으면 돌려준다."""
        with self._lock:  # 캐시 읽기
            if self._cached and self._clock() - self._cached[0] < self._cache_sec:  # 아직 유효
                return self._cached[1]  # 재사용
        return None  # 없음

    def _manual(self) -> Optional[Origin]:
        """수동 지정한 위치."""
        location = self._settings.my_location()  # 저장값
        return Origin(lat=location[0], lon=location[1], source="manual") if location else None  # 없으면 None

    @staticmethod
    def _from_geo(info: Optional[GeoInfo]) -> Optional[Origin]:
        """ip-api 정보에서 시작점을 만든다. 좌표가 없으면 None."""
        if info is None or info.lat is None or info.lon is None:  # 좌표 없음
            return None  # 모름
        return Origin(lat=info.lat, lon=info.lon, source="ip-api")  # 자동 위치

    def me(self) -> MeInfo:
        """'내 IP' 버튼용: 내 IP 정보를 새로 조회하고, 지금 쓰는 시작점을 함께 돌려준다. 예외를 던지지 않는다."""
        try:
            geo: Optional[GeoInfo] = self._fetch_self()  # 항상 새로 조회 (IP가 바뀌었을 수 있음)
            error = None  # 성공
        except GeoLookupError as exc:  # 네트워크 오류, 한도 초과
            geo, error = None, str(exc)  # 사유 기록
        return MeInfo(geo=geo, origin=self._manual() or self._from_geo(geo), error=error)  # 수동 위치 우선

    def origin(self) -> Optional[Origin]:
        """측정용 시작점. 수동 지정 → 캐시된 내 IP 위치 → 새로 조회 순서. 모두 실패하면 None."""
        manual = self._manual()  # 수동 지정
        if manual:  # 있으면
            return manual  # 외부 조회 없이 사용
        info = self._cached_self()  # 최근 조회값
        if info is None:  # 없거나 오래됨
            try:
                info = self._fetch_self()  # 새로 조회
            except GeoLookupError:  # 실패
                return None  # 시작점 모름 (반경 원 없이 측정값만 표시)
        return self._from_geo(info)  # 자동 위치

    def set_manual(self, lat: float, lon: float) -> Origin:
        """내 위치를 지도에서 고른 좌표로 지정한다. 범위 밖이면 InvalidSettingError."""
        lat, lon = self._settings.set_my_location(lat, lon)  # 검사 후 저장
        return Origin(lat=lat, lon=lon, source="manual")  # 저장한 위치

    def clear_manual(self) -> Optional[Origin]:
        """수동 지정을 지우고 자동 위치를 돌려준다 (모르면 None)."""
        self._settings.clear_my_location()  # 삭제
        return self.origin()  # 자동 위치
