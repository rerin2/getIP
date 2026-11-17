"""화면 설정(테마, 지도 타일 키) 저장. meta 테이블에 키-값으로 둔다."""

import os  # 환경 변수 읽기
from typing import Optional  # 타입 표기

from getip import config  # 테마 목록, 환경 변수 이름
from getip.storage.db import Database  # DB 연결

_THEME_KEY = "theme"  # meta 테이블에서 테마를 저장하는 키
_TILE_KEY = "carto_api_key"  # meta 테이블에서 CARTO 키를 저장하는 키
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
