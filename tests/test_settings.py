"""화면 설정 저장소(getip.storage.settings) 테스트."""

import pytest  # 테스트 도구

from getip import config  # 환경 변수 이름
from getip.storage.settings import InvalidSettingError, SettingsStore  # 대상


@pytest.fixture
def settings(database, monkeypatch):
    monkeypatch.delenv(config.TILE_KEY_ENV, raising=False)  # 개발자 PC의 환경 변수 영향 제거
    return SettingsStore(database)  # 임시 DB 위의 설정


def test_theme_defaults_to_system(settings):
    assert settings.theme() == "system"  # 저장값이 없으면 기본값


def test_theme_roundtrip_and_rejects_unknown(settings):
    settings.set_theme("dark")  # 저장
    assert settings.theme() == "dark"  # 다시 읽힘
    with pytest.raises(InvalidSettingError):  # 허용 목록 밖
        settings.set_theme("blue")  # 거부
    assert settings.theme() == "dark"  # 기존 값 유지


def test_tile_key_save_strip_and_delete(settings):
    assert settings.tile_key() is None  # 처음에는 없음
    settings.set_tile_key("  abc123  ")  # 공백 섞인 붙여넣기
    assert settings.tile_key() == "abc123"  # 공백 제거 후 저장
    settings.set_tile_key("")  # 빈 값
    assert settings.tile_key() is None  # 삭제됨


@pytest.mark.parametrize("bad", ["has space", "한글키", "x" * 201, "line\nbreak"])
def test_tile_key_rejects_bad_format(settings, bad):
    with pytest.raises(InvalidSettingError):  # 키에 올 수 없는 형태
        settings.set_tile_key(bad)  # 거부


def test_env_key_overrides_saved(settings, monkeypatch):
    settings.set_tile_key("saved")  # 저장값
    monkeypatch.setenv(config.TILE_KEY_ENV, "fromenv")  # 환경 변수
    assert settings.tile_key() == "fromenv" and settings.tile_key_from_env()  # 환경 변수 우선
