"""로컬 API(getip.web.app) 테스트. 가짜 위치 공급자와 임시 DB를 쓰므로 네트워크를 쓰지 않는다."""

import pytest  # 테스트 도구
from fastapi.testclient import TestClient  # 서버 없이 앱 호출

from getip import config  # 환경 변수 이름, 타일 주소
from getip.geo.base import GeoLookupError  # 조회 실패 예외
from getip.storage.settings import SettingsStore  # 설정 저장소
from getip.web.app import create_app  # 대상
from getip.web.security import TOKEN_HEADER  # 토큰 헤더 이름

TOKEN = "test-token"  # 테스트용 고정 토큰
BASE = "http://127.0.0.1:8123"  # 실제 실행과 같은 형태의 주소 (Host 검사 통과)


@pytest.fixture
def settings(database, monkeypatch):
    monkeypatch.delenv(config.TILE_KEY_ENV, raising=False)  # 개발자 PC 환경 변수 영향 제거
    return SettingsStore(database)  # 임시 DB 위의 설정


@pytest.fixture
def client(service, settings):
    app = create_app(service, settings, TOKEN)  # 가짜 서비스로 앱 조립
    return TestClient(app, base_url=BASE, headers={TOKEN_HEADER: TOKEN})  # 토큰을 기본으로 싣는 클라이언트


# --- 보안 검사 ---

def test_api_requires_token(service, settings):
    bare = TestClient(create_app(service, settings, TOKEN), base_url=BASE)  # 토큰 없는 클라이언트
    assert bare.get("/api/settings").status_code == 403  # 거부
    assert bare.get("/api/settings", headers={TOKEN_HEADER: "wrong"}).status_code == 403  # 틀린 토큰도 거부


def test_rejects_foreign_host(client):
    assert client.get("/api/settings", headers={"Host": "evil.example"}).status_code == 403  # DNS 리바인딩 형태 거부
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 403  # 화면도 거부


def test_rejects_foreign_origin(client):
    assert client.get("/api/settings", headers={"Origin": "https://evil.example"}).status_code == 403  # 다른 사이트 요청 거부
    assert client.get("/api/settings", headers={"Origin": BASE}).status_code == 200  # 자기 화면은 통과


def test_index_has_token_theme_and_csp(service, settings):
    settings.set_theme("dark")  # 저장된 테마
    page = TestClient(create_app(service, settings, TOKEN), base_url=BASE).get("/")  # 토큰 없이 화면 요청
    assert page.status_code == 200  # 화면은 토큰 없이 열림
    assert 'data-theme="dark"' in page.text and f'content="{TOKEN}"' in page.text  # 테마·토큰이 채워짐
    assert "script-src 'self'" in page.headers["content-security-policy"]  # 보안 정책 헤더
    assert page.headers["cache-control"] == "no-store"  # 토큰이 캐시에 남지 않음


def test_static_js_served_as_javascript(client):
    res = client.get("/static/app.js")  # 모듈 스크립트
    assert res.status_code == 200 and "javascript" in res.headers["content-type"]  # text/plain이면 브라우저가 거부함


# --- 조회 ---

def test_lookup_returns_result_and_saves(client):
    res = client.post("/api/lookup", json={"target": "https://www.example.com/x"})  # 조회
    assert res.status_code == 200  # 성공
    body = res.json()  # 결과
    assert body["target"]["host"] == "example.com" and body["ip"] == "1.2.3.4"  # 정리된 호스트와 IP
    assert body["geo"]["city"] == "Seoul" and body["id"] == 1  # 위치와 기록 번호
    assert client.get("/api/history").json()["total"] == 1  # 기록 1건


def test_lookup_rejects_invalid_and_foreign_ip(client):
    assert client.post("/api/lookup", json={"target": "-h"}).status_code == 400  # 형식 오류
    res = client.post("/api/lookup", json={"target": "example.com", "ip": "9.9.9.9"})  # 대상의 IP가 아닌 값
    assert res.status_code == 400 and "IP 목록에 없는" in res.json()["detail"]  # 거부


def test_lookup_unknown_domain_is_404(client, service):
    service._resolve = lambda host: []  # DNS가 아무것도 돌려주지 않음
    assert client.post("/api/lookup", json={"target": "nope.invalid"}).status_code == 404  # 없는 도메인


def test_lookup_without_geo_still_succeeds(client, provider):
    provider.error = GeoLookupError("IP 정보를 가져오는데 실패했습니다.")  # 위치 조회 실패
    body = client.post("/api/lookup", json={"target": "8.8.8.8"}).json()  # 조회
    assert body["geo"] is None and body["warnings"]  # 위치 없음 + 사유


def test_resolve_lists_ips(client):
    assert client.get("/api/resolve", params={"target": "example.com"}).json() == {
        "host": "example.com", "is_ip": False, "ips": ["1.2.3.4"]}  # 대상 정보와 IP 목록


def test_me_maps_failure_to_502(client, provider):
    assert client.get("/api/me").json()["ip"] == "9.9.9.9"  # 가짜 공급자의 내 IP
    provider.error = GeoLookupError("실패")  # 외부 서비스 실패
    assert client.get("/api/me").status_code == 502  # 502로 전달


# --- 기록 ---

def test_history_get_delete_and_clear(client):
    first = client.post("/api/lookup", json={"target": "example.com"}).json()["id"]  # 1건
    client.post("/api/lookup", json={"target": "1.1.1.1"})  # 2건
    assert client.get(f"/api/history/{first}").json()["target"]["host"] == "example.com"  # 상세 복원
    assert client.get("/api/history", params={"q": "1.1.1"}).json()["items"][0]["ip"] == "1.1.1.1"  # 검색
    assert client.delete(f"/api/history/{first}").status_code == 200  # 한 건 삭제
    assert client.get(f"/api/history/{first}").status_code == 404  # 지워짐
    assert client.delete(f"/api/history/{first}").status_code == 404  # 다시 지우면 404
    assert client.delete("/api/history").json() == {"deleted": 1}  # 남은 1건 전체 삭제


def test_history_limit_is_bounded(client):
    assert client.get("/api/history", params={"limit": 10000}).status_code == 422  # 상한 초과 거부


# --- 설정 ---

def test_settings_without_key_has_no_tiles(client):
    body = client.get("/api/settings").json()  # 설정
    assert body["theme"] == "system" and body["tiles"] is None and body["tile_key_set"] is False  # 키 없음


def test_settings_put_theme_and_key(client):
    body = client.put("/api/settings", json={"theme": "light", "tile_key": "k/e y"}).json()  # 잘못된 키(공백)
    assert "detail" in body  # 거부됨
    body = client.put("/api/settings", json={"theme": "light", "tile_key": "ab+c/d"}).json()  # 정상 키
    assert body["theme"] == "light" and body["tile_key_set"] is True  # 저장됨
    assert body["tiles"]["dark"] == config.TILE_URL_DARK + "?key=ab%2Bc%2Fd"  # 키가 주소용으로 인코딩됨
    assert client.put("/api/settings", json={"theme": "blue"}).status_code == 400  # 잘못된 테마
