"""저장소(getip.storage)와 모델 직렬화 테스트. 임시 DB 파일을 쓴다."""

import json  # 저장된 JSON 조작
from datetime import datetime, timedelta, timezone  # 시각 조작

from conftest import make_geo  # 테스트용 위치 정보
from getip.models import LookupResult, Target, result_from_dict, result_to_dict  # 모델과 변환 함수
from getip.storage.db import Database  # DB 연결
from getip.storage.geo_cache import GeoCacheStore  # 위치 캐시
from getip.storage.history import HistoryStore  # 조회 기록


def _result(host="example.com", ip="1.2.3.4", geo=True, minutes_ago=0):
    """테스트용 조회 결과."""
    return LookupResult(
        target=Target(raw=f"https://{host}/", host=host, is_ip=False),  # 조회 대상
        ip=ip,  # 조회한 IP
        all_ips=[ip, "5.6.7.8"],  # 전체 IP 목록
        geo=make_geo(ip) if geo else None,  # 위치 정보 유무
        reverse_dns="host.example.net",  # 역방향 DNS
        warnings=[] if geo else ["실패 사유"],  # 위치가 없으면 경고 포함
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),  # 조회 시각
    )


def test_result_roundtrip_through_dict():
    original = _result()  # 원본
    restored = result_from_dict(json.loads(json.dumps(result_to_dict(original))), record_id=7)  # JSON을 거쳐 복원
    original.id = 7  # 번호만 맞추면
    assert restored == original  # 완전히 같아야 함


def test_result_from_dict_tolerates_unknown_and_missing_fields():
    data = result_to_dict(_result())  # 저장 형태
    data["future_field"] = 1  # 이후 버전에서 추가될 항목
    data["geo"]["future_geo_field"] = 2  # 위치 정보에 추가될 항목
    del data["warnings"]  # 이전 버전에 없던 항목
    restored = result_from_dict(data)  # 복원
    assert restored.warnings == [] and restored.geo.city == "Seoul"  # 오류 없이 읽힘


def test_history_save_get_and_list(database):
    store = HistoryStore(database)  # 기록 저장소
    old = _result("old.example", minutes_ago=10)  # 오래된 기록
    new = _result("new.example", ip="9.9.9.9")  # 최신 기록
    assert store.save(old) == old.id == 1  # 번호가 부여되고 결과에도 기록됨
    store.save(new)  # 두 번째 저장

    assert store.get(old.id) == old  # 상세 복원
    assert store.get(999) is None  # 없는 번호
    entries = store.list()  # 목록
    assert [entry.host for entry in entries] == ["new.example", "old.example"]  # 최신순
    assert (entries[0].ip, entries[0].country, entries[0].city, entries[0].isp) == ("9.9.9.9", "South Korea", "Seoul", "Example ISP")  # 요약 항목
    assert store.count() == 2  # 건수


def test_history_saves_result_without_geo(database):
    store = HistoryStore(database)  # 기록 저장소
    result = _result(geo=False)  # 위치 없는 결과
    store.save(result)  # 저장
    assert store.list()[0].country is None  # 요약 항목은 비어 있음
    assert store.get(result.id).warnings == ["실패 사유"]  # 경고는 보존


def test_history_search_and_paging(database):
    store = HistoryStore(database)  # 기록 저장소
    for number in range(5):  # 다섯 건 저장
        store.save(_result(f"site{number}.example", ip=f"10.0.0.{number}", minutes_ago=number))  # 서로 다른 호스트·IP
    store.save(_result("under_score.test", minutes_ago=9))  # 밑줄이 든 호스트

    assert [e.host for e in store.list(query="site3")] == ["site3.example"]  # 호스트 검색
    assert [e.host for e in store.list(query="10.0.0.4")] == ["site4.example"]  # IP 검색
    assert [e.host for e in store.list(query="_")] == ["under_score.test"]  # 밑줄은 글자 그대로 검색
    assert store.list(query="%") == []  # 퍼센트도 글자 그대로 검색
    assert [e.host for e in store.list(limit=2, offset=1)] == ["site1.example", "site2.example"]  # 페이지 이동


def test_history_delete_and_clear(database):
    store = HistoryStore(database)  # 기록 저장소
    first, second = _result("a.example"), _result("b.example")  # 두 건
    store.save(first)  # 저장
    store.save(second)  # 저장

    assert store.delete(first.id) is True  # 삭제 성공
    assert store.delete(first.id) is False  # 이미 없는 번호
    assert store.clear() == 1  # 남은 한 건 삭제
    assert store.count() == 0  # 비어 있음


def test_database_persists_between_instances(tmp_path):
    path = tmp_path / "sub" / "getip.db"  # 아직 없는 폴더
    HistoryStore(Database(path)).save(_result())  # 저장 후 객체 버림
    assert HistoryStore(Database(path)).count() == 1  # 다시 열어도 남아 있음


def test_geo_cache_put_get_and_expiry(database):
    cache = GeoCacheStore(database, max_age_days=7)  # 7일 캐시
    cache.put_many([make_geo("1.1.1.1"), make_geo("2.2.2.2")])  # 두 건 저장

    assert cache.get("1.1.1.1", "fake") == make_geo("1.1.1.1")  # 그대로 복원
    assert cache.get("1.1.1.1", "other-source") is None  # 공급자가 다르면 없음
    assert set(cache.get_many(["1.1.1.1", "2.2.2.2", "3.3.3.3"], "fake")) == {"1.1.1.1", "2.2.2.2"}  # 있는 것만

    stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()  # 8일 전 시각
    with database.connect() as conn:  # 직접 수정
        conn.execute("UPDATE geo_cache SET fetched_at = ? WHERE ip = '1.1.1.1'", (stale,))  # 한 건을 오래된 것으로
    assert cache.get("1.1.1.1", "fake") is None  # 유효 기간이 지나면 무시
    assert cache.purge_expired() == 1  # 오래된 항목 정리
    assert cache.get("2.2.2.2", "fake") is not None  # 나머지는 유지
