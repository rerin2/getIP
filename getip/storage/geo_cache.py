"""위치 조회 결과 캐시. 같은 IP를 반복 조회해 API 한도를 쓰는 일을 막는다."""

import json  # 위치 정보를 JSON 문자열로 저장
from datetime import datetime, timedelta, timezone  # 유효 기간 계산
from typing import Dict, Iterable, Optional  # 타입 표기

from getip.models import GeoInfo, geo_from_dict, geo_to_dict  # 데이터 클래스와 변환 함수
from getip.storage.db import Database  # DB 연결

_SQLITE_MAX_PARAMS = 500  # 한 SQL에 넣을 값의 수 (SQLite 제한보다 작게)


class GeoCacheStore:
    """위치 캐시 테이블(geo_cache)을 다룬다."""

    def __init__(self, database: Database, max_age_days: int):
        self._db = database  # 사용할 DB
        self._max_age = timedelta(days=max_age_days)  # 이보다 오래된 항목은 무시

    def _cutoff(self) -> str:
        """이 시각 이후에 저장된 항목만 유효하다."""
        return (datetime.now(timezone.utc) - self._max_age).isoformat()  # 현재 - 유효 기간

    def get(self, ip: str, source: str) -> Optional[GeoInfo]:
        """캐시에서 IP 하나를 찾는다. 없거나 오래됐으면 None."""
        return self.get_many([ip], source).get(ip)  # 여러 건 조회를 재사용

    def get_many(self, ips: Iterable[str], source: str) -> Dict[str, GeoInfo]:
        """캐시에 유효하게 남아 있는 IP만 {ip: 정보}로 돌려준다."""
        wanted = list(dict.fromkeys(ips))  # 중복 제거
        found: Dict[str, GeoInfo] = {}  # 찾은 결과
        with self._db.connect() as conn:  # 연결 열기
            for start in range(0, len(wanted), _SQLITE_MAX_PARAMS):  # 값 개수 제한에 맞춰 나눔
                chunk = wanted[start:start + _SQLITE_MAX_PARAMS]  # 이번 묶음
                marks = ",".join("?" * len(chunk))  # IN (?, ?, ...) 자리 표시
                rows = conn.execute(
                    f"SELECT ip, data_json FROM geo_cache WHERE source = ? AND fetched_at >= ? AND ip IN ({marks})",
                    [source, self._cutoff(), *chunk],
                ).fetchall()  # 유효한 항목만 조회
                for row in rows:  # 행마다
                    found[row["ip"]] = geo_from_dict(json.loads(row["data_json"]))  # 위치 정보 복원
        return found  # 캐시에 있던 것만

    def put_many(self, infos: Iterable[GeoInfo]) -> None:
        """조회 결과를 캐시에 저장한다. 같은 IP가 있으면 덮어쓴다."""
        now = datetime.now(timezone.utc).isoformat()  # 저장 시각
        rows = [(info.ip, info.source, now, json.dumps(geo_to_dict(info), ensure_ascii=False)) for info in infos]  # 삽입할 값
        with self._db.connect() as conn:  # 연결 열기
            conn.executemany(
                "INSERT OR REPLACE INTO geo_cache(ip, source, fetched_at, data_json) VALUES (?, ?, ?, ?)", rows
            )  # 여러 건 저장

    def purge_expired(self) -> int:
        """유효 기간이 지난 항목을 지우고 지운 건수를 돌려준다."""
        with self._db.connect() as conn:  # 연결 열기
            return conn.execute("DELETE FROM geo_cache WHERE fetched_at < ?", (self._cutoff(),)).rowcount  # 오래된 항목 삭제
