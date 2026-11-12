"""위치 조회(getip.geo.ip_api) 테스트. HTTP 요청은 가짜로 대체한다."""

import pytest  # 테스트 도구
import requests  # 예외 클래스 사용

from getip.geo import ip_api  # 검사 대상
from getip.geo.base import GeoLookupError, GeoRateLimitError  # 공통 예외


class _FakeResponse:
    """requests 응답 흉내."""

    def __init__(self, payload=None, error=None, status_code=200, headers=None):
        self._payload = payload  # 돌려줄 JSON 내용
        self._error = error  # json() 호출 시 던질 예외
        self.status_code = status_code  # HTTP 상태 코드
        self.headers = headers or {}  # 응답 헤더

    def json(self):
        if self._error:  # 예외가 지정돼 있으면
            raise self._error  # JSON 해석 실패 흉내
        return self._payload  # 정상 응답


def _patch(monkeypatch, response=None, error=None, calls=None):
    """requests.request를 가짜 함수로 바꾼다."""

    def fake_request(method, url, **kwargs):
        if calls is not None:  # 호출 기록을 원하면
            calls.append((method, url, kwargs))  # 인자 저장
        if error:  # 네트워크 오류 흉내
            raise error  # 예외 발생
        return response  # 준비된 응답 반환

    monkeypatch.setattr(ip_api.requests, "request", fake_request)  # 실제 요청 차단


SUCCESS = {"status": "success", "query": "1.2.3.4", "country": "South Korea", "countryCode": "KR",
           "city": "Seoul", "lat": 37.5, "lon": 127.0, "isp": "Example ISP", "org": "Example Org",
           "as": "AS64500 Example", "hosting": True}  # 성공 응답 예시


def test_lookup_success_maps_all_fields(monkeypatch):
    calls = []  # 호출 기록
    _patch(monkeypatch, _FakeResponse(SUCCESS), calls=calls)  # 가짜 응답 설치

    info = ip_api.lookup("1.2.3.4", timeout=2)  # 조회 실행

    assert (info.ip, info.country, info.city, info.isp, info.org) == ("1.2.3.4", "South Korea", "Seoul", "Example ISP", "Example Org")  # 기존 항목
    assert (info.country_code, info.lat, info.lon, info.asn, info.is_hosting) == ("KR", 37.5, 127.0, "AS64500 Example", True)  # 추가 항목
    assert info.source == "ip-api.com"  # 출처
    method, url, kwargs = calls[0]  # 실제 호출 인자
    assert (method, url, kwargs["timeout"]) == ("GET", "http://ip-api.com/json/1.2.3.4", 2)  # 주소와 타임아웃
    assert "lat" in kwargs["params"]["fields"] and "as" in kwargs["params"]["fields"].split(",")  # 필요한 항목을 요청하는지


def test_lookup_empty_ip_queries_own_address(monkeypatch):
    calls = []  # 호출 기록
    _patch(monkeypatch, _FakeResponse({"status": "success", "query": "9.9.9.9"}), calls=calls)  # 내 IP 응답

    assert ip_api.lookup().ip == "9.9.9.9"  # API가 알려준 내 IP 사용
    assert calls[0][1] == "http://ip-api.com/json/"  # IP 없는 주소로 호출


def test_lookup_api_failure(monkeypatch):
    _patch(monkeypatch, _FakeResponse({"status": "fail", "message": "private range"}))  # 사설 IP 응답
    with pytest.raises(GeoLookupError, match="IP 정보를 가져오는데 실패했습니다."):  # 기존 문구 유지
        ip_api.lookup("192.168.0.1")  # 조회 실행


def test_lookup_network_error(monkeypatch):
    _patch(monkeypatch, error=requests.ConnectionError("연결 실패"))  # 네트워크 오류
    with pytest.raises(GeoLookupError, match="연결 실패"):  # 원인 문구가 전달되는지
        ip_api.lookup("1.2.3.4")  # 조회 실행


def test_lookup_invalid_json(monkeypatch):
    _patch(monkeypatch, _FakeResponse(error=ValueError("not json")))  # JSON이 아닌 응답
    with pytest.raises(GeoLookupError):  # 조회 실패로 통일되는지
        ip_api.lookup("1.2.3.4")  # 조회 실행


def test_lookup_rate_limited(monkeypatch):
    _patch(monkeypatch, _FakeResponse(status_code=429, headers={"X-Ttl": "37"}))  # 한도 초과 응답
    with pytest.raises(GeoRateLimitError) as caught:  # 전용 예외가 나야 함
        ip_api.lookup("1.2.3.4")  # 조회 실행
    assert caught.value.retry_after_sec == 37  # 남은 대기 시간 전달
    assert "37초" in str(caught.value)  # 사용자 문구에 포함


def test_lookup_batch_returns_only_successes(monkeypatch):
    payload = [dict(SUCCESS, query="8.8.8.8"), {"status": "fail", "message": "private range", "query": "192.168.0.1"}]  # 성공 1, 실패 1
    calls = []  # 호출 기록
    _patch(monkeypatch, _FakeResponse(payload), calls=calls)  # 가짜 응답 설치

    found = ip_api.lookup_batch(["8.8.8.8", "192.168.0.1", "8.8.8.8"])  # 중복 포함 요청

    assert list(found) == ["8.8.8.8"]  # 성공한 IP만
    method, url, kwargs = calls[0]  # 실제 호출 인자
    assert (method, url) == ("POST", "http://ip-api.com/batch")  # 일괄 조회 주소
    assert kwargs["json"] == ["8.8.8.8", "192.168.0.1"]  # 중복이 제거돼 전송됨


def test_lookup_batch_splits_into_chunks_of_100(monkeypatch):
    calls = []  # 호출 기록
    _patch(monkeypatch, _FakeResponse([]), calls=calls)  # 빈 응답
    ip_api.lookup_batch([f"10.0.{n // 256}.{n % 256}" for n in range(250)])  # 250개 요청
    assert [len(call[2]["json"]) for call in calls] == [100, 100, 50]  # 100개씩 나눠 전송
