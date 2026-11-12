"""조회 서비스(getip.services.lookup)와 역방향 DNS 테스트."""

import socket  # 역방향 DNS 예외
import sqlite3  # 저장 실패 예외
import time  # 느린 조회 흉내

import pytest  # 테스트 도구

from getip.geo.base import GeoRateLimitError  # 한도 초과 예외
from getip.net import resolver  # 역방향 DNS
from getip.net.target import InvalidTargetError  # 입력 오류 예외
from getip.services import lookup as lookup_module  # 서비스 생성 함수


def test_resolve_returns_target_and_ips(service):
    target, ips = service.resolve("https://www.example.com/x")  # 입력 정리 + DNS
    assert (target.host, ips) == ("example.com", ["1.2.3.4"])  # 정리된 호스트와 IP


def test_resolve_rejects_invalid_input(service):
    with pytest.raises(InvalidTargetError):  # 형식 오류
        service.resolve("-h")  # 옵션처럼 보이는 입력


def test_lookup_collects_everything_and_saves_history(service):
    target, ips = service.resolve("example.com")  # 대상 준비
    result = service.lookup(target, ips[0], ips)  # 조회

    assert result.geo.city == "Seoul" and result.reverse_dns == "host.example.net"  # 위치 + 역방향 DNS
    assert result.warnings == [] and result.id == 1  # 경고 없음, 기록 번호 부여
    assert service.history.get(1) == result  # 기록에서 그대로 복원됨


def test_lookup_private_ip_saved_with_warning(service, provider):
    target, _ = service.resolve("192.168.0.1")  # 사설 IP 대상
    result = service.lookup(target, "192.168.0.1", ["192.168.0.1"])  # 조회

    assert result.geo is None and "공인 IP가 아니라" in result.warnings[0]  # 위치 없음 + 사유
    assert provider.single_calls == []  # API 호출 없음
    assert service.history.count() == 1  # 그래도 기록에는 남음


def test_lookup_rate_limit_becomes_warning(service, provider):
    provider.error = GeoRateLimitError(12)  # 한도 초과
    target, ips = service.resolve("example.com")  # 대상 준비
    result = service.lookup(target, ips[0], ips)  # 예외 없이 끝나야 함
    assert result.geo is None and "12초" in result.warnings[0]  # 사유가 경고로 전달


def test_lookup_survives_history_failure(service, monkeypatch):
    def broken(result):
        raise sqlite3.OperationalError("database is locked")  # 저장 실패 흉내

    monkeypatch.setattr(service.history, "save", broken)  # 저장 함수 교체
    target, ips = service.resolve("example.com")  # 대상 준비
    result = service.lookup(target, ips[0], ips)  # 조회

    assert result.geo is not None and result.id is None  # 결과는 나오고 번호는 없음
    assert "기록 저장 실패" in result.warnings[0]  # 저장 실패 안내


def test_hop_geo_returns_none_for_private_ip(service):
    assert service.hop_geo("10.0.0.1") is None  # 사설 홉은 정보 없음
    assert service.hop_geo("8.8.8.8").city == "Seoul"  # 공인 홉은 조회


def test_create_default_uses_given_db_file(tmp_path):
    created = lookup_module.create_default(tmp_path / "x" / "getip.db")  # 지정 경로로 생성
    assert created.storage_warning is None and (tmp_path / "x" / "getip.db").exists()  # 파일이 만들어짐


def test_create_default_falls_back_when_db_unusable(tmp_path):
    blocker = tmp_path / "file"  # 폴더가 와야 할 자리에
    blocker.write_text("x")  # 파일을 둠
    created = lookup_module.create_default(blocker / "getip.db")  # 열 수 없는 경로
    assert "임시 저장소" in created.storage_warning  # 임시 저장소로 전환 안내
    assert created.history.count() == 0  # 조회 기능은 동작


def test_reverse_dns_success(monkeypatch):
    monkeypatch.setattr(resolver.socket, "gethostbyaddr", lambda ip: ("dns.google", [], [ip]))  # 이름 있음
    assert resolver.reverse_dns("8.8.8.8") == "dns.google"  # 이름 반환


def test_reverse_dns_missing_or_same_as_ip(monkeypatch):
    def not_found(ip):
        raise socket.herror(11004, "host not found")  # 등록된 이름 없음

    monkeypatch.setattr(resolver.socket, "gethostbyaddr", not_found)  # 실패 흉내
    assert resolver.reverse_dns("8.8.8.8") is None  # 없음
    monkeypatch.setattr(resolver.socket, "gethostbyaddr", lambda ip: (ip, [], [ip]))  # IP가 그대로 돌아옴
    assert resolver.reverse_dns("8.8.8.8") is None  # 이름 없음으로 처리


def test_reverse_dns_gives_up_after_timeout(monkeypatch):
    monkeypatch.setattr(resolver.socket, "gethostbyaddr", lambda ip: time.sleep(1) or ("late.example", [], []))  # 느린 조회
    started = time.monotonic()  # 시작 시각
    assert resolver.reverse_dns("8.8.8.8", timeout=0.05) is None  # 시간 안에 못 끝내면 없음
    assert time.monotonic() - started < 0.5  # 오래 기다리지 않음
