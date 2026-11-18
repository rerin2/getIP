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


def test_me_returns_geo_origin_and_error(client, provider):
    body = client.get("/api/me").json()  # 내 IP
    assert body["geo"]["ip"] == "9.9.9.9" and body["origin"]["source"] == "ip-api" and body["error"] is None  # 자동 위치
    provider.error = GeoLookupError("실패")  # 외부 서비스 실패
    body = client.get("/api/me").json()  # 다시 조회
    assert body["geo"] is None and body["origin"] is None and body["error"] == "실패"  # 200 + 사유 (화면이 안내)


def test_me_location_set_and_clear(client):
    res = client.put("/api/me/location", json={"lat": 35.1, "lon": 129.0})  # 지도에서 지정 (D13)
    assert res.json()["origin"] == {"lat": 35.1, "lon": 129.0, "source": "manual"}  # 저장
    assert client.get("/api/me").json()["origin"]["source"] == "manual"  # 이후 수동 위치 사용
    assert client.put("/api/me/location", json={"lat": 95, "lon": 0}).status_code == 400  # 범위 밖
    assert client.delete("/api/me/location").json()["origin"]["source"] == "ip-api"  # 되돌리기


# --- 지연 측정·경로 추적 ---

def _probe_client(service, settings, run=None):
    """가짜 측정·추적을 끼운 클라이언트."""
    from getip.models import LatencyResult  # 데이터 클래스
    from getip.services.origin import OriginService  # 내 위치
    from getip.services.probe import ProbeService  # 측정 서비스

    probe = ProbeService(service.history, service.geo, OriginService(service.my_ip, settings),
                         measure=lambda ip: [LatencyResult("tcp:443", [31.0], 1, 31.0, 0.0),
                                             LatencyResult("icmp", [10.0], 1, 10.0, 0.0)],  # TCP 31ms, ICMP 10ms
                         start_run=lambda ip: run)  # 가짜 추적
    app = create_app(service, settings, TOKEN, probe=probe)  # 앱
    return TestClient(app, base_url=BASE, headers={TOKEN_HEADER: TOKEN})  # 클라이언트


def test_latency_endpoint_adds_view(service, settings):
    client = _probe_client(service, settings)  # 클라이언트
    record = client.post("/api/lookup", json={"target": "8.8.8.8"}).json()  # 조회 (측정 없음, D12)
    assert record["latency"] is None and record["latency_view"] is None  # 자동 측정 안 함
    body = client.post(f"/api/lookup/{record['id']}/latency").json()  # 버튼
    view = body["latency_view"]  # 화면용 요약
    assert view["min_ms"] == 10.0 and view["upper_km"] == 10 * config.FIBER_KM_PER_MS  # 두 방법 중 최솟값 기준
    assert view["typical_km"] == 10 * config.REALISTIC_KM_PER_MS and view["db_distance_km"] == 0  # 가짜 위치가 모두 서울 좌표
    assert client.get(f"/api/history/{record['id']}").json()["latency"]["results"][0]["method"] == "tcp:443"  # 저장됨
    assert client.post("/api/lookup/999/latency").status_code == 404  # 없는 기록


def test_trace_stream_lines(service, settings):
    import json  # 줄 해석

    from getip.models import Hop  # 데이터 클래스
    from test_probe_service import FakeRun  # 가짜 추적

    client = _probe_client(service, settings, FakeRun([Hop(1, "192.168.0.1", 1.0, True), Hop(2, "8.8.8.8", 30.0)]))  # 클라이언트
    record = client.post("/api/lookup", json={"target": "8.8.8.8"}).json()  # 조회
    res = client.post(f"/api/lookup/{record['id']}/trace")  # 추적
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/x-ndjson")  # 줄 단위 JSON
    events = [json.loads(line) for line in res.text.splitlines()]  # 사건들
    assert [e["type"] for e in events] == ["start", "hop", "hop", "done"]  # 순서
    assert events[2]["hop"]["geo"]["city"] == "Seoul" and events[-1]["report"]["status"] == "done"  # 위치와 종료 상태
    saved = client.get(f"/api/history/{record['id']}").json()["trace"]  # 기록
    assert len(saved["hops"]) == 2  # 덧붙어 저장됨 (D15)
    assert client.post("/api/trace/stop").json() == {"stopped": False}  # 실행 중인 추적 없음


def test_trace_rejects_ipv6_and_unknown(client):
    record = client.post("/api/lookup", json={"target": "2606:4700:4700::1111"}).json()  # IPv6 기록
    res = client.post(f"/api/lookup/{record['id']}/trace")  # 추적
    assert res.status_code == 400 and "IPv6" in res.json()["detail"]  # 명령을 실행하지 않고 거부
    assert client.post("/api/lookup/999/trace").status_code == 404  # 없는 기록


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


# --- 프로그램 연결 ---

def test_connections_endpoint(service, settings):
    from getip.models import Connection  # 데이터 클래스
    from getip.services.connections import ConnectionService  # 연결 서비스

    fake = [Connection(pid=1, process_name="a.exe", exe_path=None, local_port=5, remote_ip="1.1.1.1",
                       remote_port=443, status="ESTABLISHED", is_public=True)]  # 가짜 연결 하나
    conns = ConnectionService(service.geo, collector=lambda: list(fake))  # 가짜 수집
    client = TestClient(create_app(service, settings, TOKEN, conns), base_url=BASE, headers={TOKEN_HEADER: TOKEN})  # 앱
    body = client.get("/api/connections").json()  # 수집
    assert body["shown"] == 1 and body["programs"][0]["name"] == "a.exe"  # 프로그램 묶음
    assert body["programs"][0]["connections"][0]["geo"]["city"] == "Seoul"  # 위치 포함
    assert client.get("/api/history").json()["total"] == 0  # 기록에는 저장하지 않음 (D9)


def test_connections_unavailable_is_503(service, settings):
    from getip.services.connections import ConnectionService  # 연결 서비스
    from getip.system.connections import ConnectionsUnavailableError  # 읽기 실패

    def broken():
        raise ConnectionsUnavailableError("연결 목록을 읽을 수 없습니다: 권한")  # 실패 흉내

    client = TestClient(create_app(service, settings, TOKEN, ConnectionService(service.geo, collector=broken)),
                        base_url=BASE, headers={TOKEN_HEADER: TOKEN})  # 앱
    res = client.get("/api/connections")  # 수집
    assert res.status_code == 503 and "권한" in res.json()["detail"]  # 사유 전달


def test_lookup_accepts_ipv6_literal(client):
    body = client.post("/api/lookup", json={"target": "2606:4700:4700::1111"}).json()  # IPv6 직접 입력 (연결 목록의 상세 조회)
    assert body["ip"] == "2606:4700:4700::1111" and body["all_ips"] == ["2606:4700:4700::1111"]  # DNS 없이 그대로
