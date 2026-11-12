"""캐시가 붙은 위치 조회(getip.geo.cached) 테스트. API 호출 수가 줄어드는지 확인한다."""

import pytest  # 테스트 도구

from getip.geo.base import GeoLookupError, GeoRateLimitError  # 예외
from getip.geo.cached import is_public_ip  # 공인 IP 판별


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_ips(ip):
    assert is_public_ip(ip) is True  # 공인 IP


@pytest.mark.parametrize("ip", ["192.168.0.1", "10.1.2.3", "172.16.0.1", "127.0.0.1", "100.64.9.233", "169.254.1.1", "::1", "not-an-ip"])
def test_non_public_ips(ip):
    assert is_public_ip(ip) is False  # 사설·루프백·통신사 내부망(100.64/10)·형식 오류


def test_lookup_uses_cache_on_second_call(cached_geo, provider):
    first = cached_geo.lookup("8.8.8.8")  # 첫 조회
    second = cached_geo.lookup("8.8.8.8")  # 같은 IP 재조회
    assert first == second  # 같은 결과
    assert provider.single_calls == ["8.8.8.8"]  # 공급자 호출은 한 번뿐


def test_lookup_private_ip_never_calls_provider(cached_geo, provider):
    with pytest.raises(GeoLookupError, match="공인 IP가 아니라"):  # 안내 문구
        cached_geo.lookup("192.168.0.1")  # 사설 IP 조회
    assert provider.single_calls == []  # API 호출 없음


def test_lookup_self_always_calls_provider(cached_geo, provider):
    cached_geo.lookup_self()  # 내 IP 조회
    cached_geo.lookup_self()  # 다시 조회
    assert provider.single_calls == ["", ""]  # 내 IP는 바뀔 수 있어 매번 호출


def test_lookup_many_batches_only_uncached_public_ips(cached_geo, provider):
    cached_geo.lookup("8.8.8.8")  # 한 건은 미리 캐시에 넣음
    result = cached_geo.lookup_many(["8.8.8.8", "9.9.9.9", "192.168.0.1", "9.9.9.9", "1.0.0.1"])  # 섞어서 요청

    assert provider.batch_calls == [["9.9.9.9", "1.0.0.1"]]  # 캐시에 없고 공인인 IP만, 중복 없이, 한 번에
    assert set(result.found) == {"8.8.8.8", "9.9.9.9", "1.0.0.1"}  # 캐시 + 새 조회
    assert result.skipped == ["192.168.0.1"]  # 사설 IP는 건너뜀
    assert result.pending == [] and result.error is None  # 남은 것 없음

    cached_geo.lookup_many(["9.9.9.9", "1.0.0.1"])  # 같은 IP 재요청
    assert len(provider.batch_calls) == 1  # 전부 캐시에 있어 추가 호출 없음


def test_lookup_many_keeps_cached_results_when_rate_limited(cached_geo, provider):
    cached_geo.lookup("8.8.8.8")  # 캐시에 한 건
    provider.error = GeoRateLimitError(30)  # 이후 호출은 한도 초과
    result = cached_geo.lookup_many(["8.8.8.8", "9.9.9.9"])  # 예외 없이 끝나야 함

    assert set(result.found) == {"8.8.8.8"}  # 캐시에 있던 것은 반환
    assert result.pending == ["9.9.9.9"]  # 못 한 것은 대기 목록
    assert "30초" in result.error  # 사유 전달


def test_lookup_many_marks_unknown_ips_as_pending(cached_geo, provider):
    provider.unknown = {"9.9.9.9"}  # 공급자가 정보를 주지 않는 IP
    result = cached_geo.lookup_many(["8.8.8.8", "9.9.9.9"])  # 조회
    assert set(result.found) == {"8.8.8.8"} and result.pending == ["9.9.9.9"]  # 성공과 미해결 구분
