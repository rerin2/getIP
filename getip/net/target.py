"""사용자 입력(URL/도메인/IP)을 조회 가능한 호스트로 정리하고 검증한다."""

import ipaddress  # IP 주소 형식 판별
import re  # 호스트명 라벨 검증용 정규식
from urllib.parse import urlparse  # URL에서 호스트 부분 추출

from getip.models import Target  # 정리 결과를 담는 데이터 클래스

_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_]([A-Za-z0-9_-]*[A-Za-z0-9_])?$")  # 라벨: 영숫자/밑줄로 시작·끝, 중간에 하이픈 허용
_MAX_HOST_LENGTH = 253  # DNS 규격상 호스트명 최대 길이


class InvalidTargetError(ValueError):
    """입력에서 올바른 호스트를 얻지 못했을 때 발생."""


def normalize(user_input: str) -> Target:
    """입력 문자열을 Target으로 변환한다. 형식이 잘못되면 InvalidTargetError."""
    raw = user_input.strip()  # 앞뒤 공백 제거
    if not raw:  # 빈 입력이면
        raise InvalidTargetError("입력이 비어 있습니다.")  # 조회 불가

    if _is_ip(raw):  # 대괄호 없는 IPv6("2606:4700::1111")는 URL로 해석하면 콜론이 포트로 잘리므로 먼저 확인
        return Target(raw=raw, host=str(ipaddress.ip_address(raw)), is_ip=True)  # 표준 표기로 정리해 반환

    url = raw if "://" in raw else "http://" + raw  # 스킴이 없으면 붙여서 urlparse가 호스트를 인식하게 함
    try:
        host = urlparse(url).hostname  # 포트·계정·경로를 뺀 호스트만 추출 (소문자로 반환됨)
    except ValueError as exc:  # 대괄호가 깨진 IPv6 표기 등
        raise InvalidTargetError(f"주소 형식이 올바르지 않습니다: {raw}") from exc  # 형식 오류로 통일

    if not host:  # 호스트를 찾지 못한 경우 ("http://" 등)
        raise InvalidTargetError(f"호스트를 찾을 수 없습니다: {raw}")  # 조회 불가

    if _is_ip(host):  # IP 주소를 직접 입력한 경우
        return Target(raw=raw, host=host, is_ip=True)  # 추가 가공 없이 반환

    if host.startswith("www."):  # 앞의 www.는 제거 (설계 결정: 주소 복사 시 www.가 빠지는 것과 맞춤)
        host = host[4:]  # "www." 네 글자 제거

    host = _validate_hostname(host, raw)  # 호스트명 규칙 검사 및 ASCII 변환
    return Target(raw=raw, host=host, is_ip=False)  # 도메인 대상 반환


def _is_ip(host: str) -> bool:
    """문자열이 IPv4/IPv6 주소인지 판별한다."""
    try:
        ipaddress.ip_address(host)  # 파싱 성공하면 IP
        return True  # IP 맞음
    except ValueError:  # 파싱 실패
        return False  # IP 아님


def _validate_hostname(host: str, raw: str) -> str:
    """호스트명을 검증하고 ASCII(퓨니코드) 형태로 돌려준다."""
    host = host.rstrip(".")  # 끝의 루트 점 제거 ("example.com.")
    try:
        ascii_host = host.encode("idna").decode("ascii")  # 한글 도메인 등을 ASCII로 변환, 빈 라벨·과도한 길이는 여기서 걸림
    except UnicodeError as exc:  # 변환 불가능한 호스트명
        raise InvalidTargetError(f"호스트명이 올바르지 않습니다: {raw}") from exc  # 형식 오류로 통일

    if not ascii_host or len(ascii_host) > _MAX_HOST_LENGTH:  # 비었거나 너무 긴 경우
        raise InvalidTargetError(f"호스트명이 올바르지 않습니다: {raw}")  # 조회 불가

    for label in ascii_host.split("."):  # 점으로 나눈 각 라벨 검사
        if not _LABEL_PATTERN.match(label):  # 허용 문자 외 포함 또는 하이픈으로 시작/끝 (명령 옵션 주입 차단)
            raise InvalidTargetError(f"호스트명이 올바르지 않습니다: {raw}")  # 조회 불가

    return ascii_host  # 검증된 호스트명
