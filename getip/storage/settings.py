"""화면 설정(테마, 지도 타일 키) 저장. meta 테이블에 키-값으로 둔다."""

import os  # 환경 변수 읽기
import math  # 숫자 검사 (NaN·무한대 거부)
from typing import Optional, Tuple  # 타입 표기

from getip import config  # 테마 목록, 환경 변수 이름
from getip.storage.db import Database  # DB 연결

_THEME_KEY = "theme"  # meta 테이블에서 테마를 저장하는 키
_TILE_KEY = "carto_api_key"  # meta 테이블에서 CARTO 키를 저장하는 키
_MY_LOCATION_KEY = "my_location"  # meta 테이블에서 수동 지정한 내 위치("위도,경도")를 저장하는 키 (D13)
_MAX_KEY_LENGTH = 200  # 키 길이 상한 (잘못 붙여넣은 긴 글 방지)


class InvalidSettingError(ValueError):
    """허용되지 않는 설정값을 저장하려 할 때 발생."""


class SettingsStore:
    """meta 테이블의 설정 항목을 읽고 쓴다."""

    def __init__(self, database: Database):
        self._db = database  # 사용할 DB

    def _get(self, key: str) -> Optional[str]:
        """meta 값 하나를 읽는다. 없으면 None."""
        with self._db.connect() as conn:  # 연결 열기
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()  # 한 건 조회
        return row["value"] if row else None  # 값 또는 None

    def _set(self, key: str, value: Optional[str]) -> None:
        """meta 값 하나를 저장한다. None이면 지운다."""
        with self._db.connect() as conn:  # 연결 열기
            if value is None:  # 지우기 요청
                conn.execute("DELETE FROM meta WHERE key = ?", (key,))  # 항목 삭제
            else:  # 저장 요청
                conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))  # 있으면 덮어씀

    def theme(self) -> str:
        """저장된 테마. 없거나 잘못된 값이면 기본값."""
        value = self._get(_THEME_KEY)  # 저장값
        return value if value in config.THEMES else config.DEFAULT_THEME  # 허용 목록 밖이면 기본값

    def set_theme(self, theme: str) -> None:
        """테마를 저장한다. 허용 목록 밖이면 InvalidSettingError."""
        if theme not in config.THEMES:  # system/light/dark 외의 값
            raise InvalidSettingError(f"알 수 없는 테마입니다: {theme}")  # 저장 거부
        self._set(_THEME_KEY, theme)  # 저장

    def tile_key(self) -> Optional[str]:
        """지도 타일 키. 환경 변수가 있으면 그것을, 없으면 저장값을 쓴다. 둘 다 없으면 None."""
        env = os.environ.get(config.TILE_KEY_ENV, "").strip()  # 개발용 환경 변수
        return env or self._get(_TILE_KEY) or None  # 우선순위: 환경 변수 → 저장값

    def tile_key_from_env(self) -> bool:
        """키가 환경 변수에서 왔는지 (화면에서 '환경 변수 사용 중' 안내용)."""
        return bool(os.environ.get(config.TILE_KEY_ENV, "").strip())  # 값이 있으면 True

    def set_tile_key(self, key: str) -> None:
        """타일 키를 저장한다. 빈 문자열이면 지운다. 형식이 이상하면 InvalidSettingError."""
        key = key.strip()  # 붙여넣을 때 섞인 공백 제거
        if not key:  # 빈 값
            self._set(_TILE_KEY, None)  # 키 삭제
            return  # 끝
        if len(key) > _MAX_KEY_LENGTH or not key.isascii() or not key.isprintable() or " " in key:  # 키에 올 수 없는 형태
            raise InvalidSettingError("키 형식이 올바르지 않습니다.")  # 저장 거부
        self._set(_TILE_KEY, key)  # 저장

    def my_location(self) -> Optional[Tuple[float, float]]:
        """수동 지정한 내 위치 (위도, 경도). 없거나 저장값이 깨졌으면 None."""
        value = self._get(_MY_LOCATION_KEY)  # "위도,경도"
        if not value:  # 지정하지 않음
            return None  # 자동(ip-api) 위치 사용
        try:
            lat, lon = (float(part) for part in value.split(","))  # 두 숫자로 분리
            return _check_location(lat, lon)  # 범위 검사
        except (ValueError, InvalidSettingError):  # 형식이 깨진 값
            return None  # 없는 것으로 처리

    def set_my_location(self, lat: float, lon: float) -> Tuple[float, float]:
        """내 위치를 저장한다. 범위를 벗어나면 InvalidSettingError. 경도는 -180~180으로 맞춘다."""
        lat, lon = _check_location(lat, lon)  # 검사·정리
        self._set(_MY_LOCATION_KEY, f"{lat:.6f},{lon:.6f}")  # 소수 6자리(약 10cm)면 충분
        return lat, lon  # 저장한 값

    def clear_my_location(self) -> None:
        """수동 지정을 지워 자동(ip-api) 위치로 되돌린다."""
        self._set(_MY_LOCATION_KEY, None)  # 삭제


def _check_location(lat: float, lon: float) -> Tuple[float, float]:
    """좌표 범위를 검사하고 경도를 -180~180으로 맞춘다. 지도 사본(경도 +360 등)을 클릭한 경우를 위해."""
    if not (math.isfinite(lat) and math.isfinite(lon)):  # NaN, 무한대
        raise InvalidSettingError("좌표가 올바르지 않습니다.")  # 거부
    if not -90 <= lat <= 90:  # 위도 범위 밖
        raise InvalidSettingError("위도는 -90~90 사이여야 합니다.")  # 거부
    lon = ((lon + 180) % 360) - 180  # 경도를 한 바퀴 안으로 (540 → 180이 아니라 -180이 되지만 같은 곳)
    return lat, lon  # 정리된 좌표
