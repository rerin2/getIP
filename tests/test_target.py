"""입력 정리·검증(getip.net.target) 테스트."""

import pytest  # 테스트 도구

from getip.net.target import InvalidTargetError, normalize  # 검사 대상


@pytest.mark.parametrize(
    "text, expected",
    [
        ("example.com", "example.com"),  # 도메인만
        ("  example.com  ", "example.com"),  # 앞뒤 공백
        ("http://example.com/path?q=1", "example.com"),  # 경로·쿼리 제거
        ("https://www.example.com", "example.com"),  # www. 제거 (설계 결정)
        ("www.example.com", "example.com"),  # 스킴 없이 www.
        ("HTTPS://Example.COM", "example.com"),  # 대문자 스킴·호스트
        ("example.com:8080", "example.com"),  # 포트 제거 (P3)
        ("http://user:pw@example.com:8080/x", "example.com"),  # 계정 정보 제거 (P3)
        ("example.com.", "example.com"),  # 끝의 루트 점
        ("_dmarc.example.com", "_dmarc.example.com"),  # 밑줄 라벨
        ("sub-1.example.co.kr", "sub-1.example.co.kr"),  # 중간 하이픈
    ],
)
def test_normalize_hostname(text, expected):
    result = normalize(text)  # 정리 실행
    assert result.host == expected  # 호스트가 기대값과 같은지
    assert result.is_ip is False  # 도메인으로 분류되는지


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1.1.1.1", "1.1.1.1"),  # IPv4
        ("http://8.8.8.8:53/", "8.8.8.8"),  # URL 안의 IPv4
        ("[2606:4700:4700::1111]", "2606:4700:4700::1111"),  # 대괄호 IPv6
    ],
)
def test_normalize_ip(text, expected):
    result = normalize(text)  # 정리 실행
    assert result.host == expected  # IP가 그대로 나오는지
    assert result.is_ip is True  # IP로 분류되는지


def test_normalize_keeps_raw_input():
    assert normalize(" www.example.com ").raw == "www.example.com"  # 원문은 공백만 제거해 보존


def test_normalize_idn_to_punycode():
    assert normalize("한글.kr").host.startswith("xn--")  # 한글 도메인은 퓨니코드로 변환


@pytest.mark.parametrize(
    "text",
    [
        "",  # 빈 입력
        "   ",  # 공백뿐
        "http://",  # 호스트 없음
        "-h",  # 옵션처럼 보이는 입력 (P4)
        "-w.example.com",  # 하이픈으로 시작하는 라벨 (P4)
        "exa mple.com",  # 공백 포함
        "example.com;calc",  # 명령 구분자
        "a..b",  # 빈 라벨
        "www.",  # www. 제거 후 빈 값
        "http://[::1",  # 깨진 IPv6 표기
        "a" * 64 + ".com",  # 라벨 길이 초과
    ],
)
def test_normalize_rejects_invalid(text):
    with pytest.raises(InvalidTargetError):  # 형식 오류 예외가 나야 함
        normalize(text)  # 정리 실행


@pytest.mark.parametrize("raw, host", [
    ("2606:4700:4700::1111", "2606:4700:4700::1111"),  # 대괄호 없는 IPv6 (연결 목록에서 넘어오는 형태)
    ("2001:DB8::1", "2001:db8::1"),  # 대문자 → 표준 표기
    ("[2001:db8::1]:443", "2001:db8::1"),  # URL식 표기
])
def test_ipv6_literal(raw, host):
    target = normalize(raw)  # 정리
    assert target.host == host and target.is_ip  # IP로 인식
