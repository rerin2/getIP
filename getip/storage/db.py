"""SQLite 연결과 스키마 생성."""

import sqlite3  # 파이썬 내장 SQLite
from contextlib import contextmanager  # with 문으로 연결을 여닫기 위한 도구
from pathlib import Path  # 경로 객체
from typing import Iterator, Optional, Union  # 타입 표기

from getip import config  # 기본 DB 경로

SCHEMA_VERSION = 1  # 스키마가 바뀌면 올리고 _migrate에 변환을 추가한다

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lookups (
  id          INTEGER PRIMARY KEY,
  created_at  TEXT NOT NULL,
  input       TEXT NOT NULL,
  host        TEXT NOT NULL,
  ip          TEXT NOT NULL,
  country     TEXT,
  city        TEXT,
  isp         TEXT,
  asn         TEXT,
  est_lat     REAL,
  est_lon     REAL,
  confidence  TEXT,
  min_rtt_ms  REAL,
  result_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lookups_created ON lookups(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lookups_host ON lookups(host);
CREATE TABLE IF NOT EXISTS geo_cache (
  ip         TEXT NOT NULL,
  source     TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  data_json  TEXT NOT NULL,
  PRIMARY KEY (ip, source)
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""  # 설계 문서 4.6절의 테이블 정의


class Database:
    """DB 파일 하나를 가리키는 객체. 작업마다 연결을 새로 열어 여러 스레드에서 써도 안전하다."""

    def __init__(self, path: Optional[Union[str, Path]] = None):
        self.path = Path(path) if path else config.db_path()  # 경로가 없으면 기본 위치 사용
        self.path.parent.mkdir(parents=True, exist_ok=True)  # 폴더가 없으면 생성
        with self.connect() as conn:  # 첫 연결에서
            conn.executescript(_SCHEMA)  # 테이블이 없으면 생성
            conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )  # 스키마 버전 기록 (이미 있으면 유지)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """연결을 열고, 블록이 정상 종료되면 저장(commit), 오류가 나면 되돌린(rollback) 뒤 닫는다."""
        conn = sqlite3.connect(self.path, timeout=5)  # 다른 연결이 쓰는 중이면 최대 5초 대기
        conn.row_factory = sqlite3.Row  # 결과를 컬럼 이름으로 읽을 수 있게 함
        try:
            yield conn  # 호출자에게 연결 전달
            conn.commit()  # 정상 종료 시 저장
        except BaseException:  # 어떤 이유로든 중단되면
            conn.rollback()  # 변경 취소
            raise  # 원래 오류를 그대로 전달
        finally:
            conn.close()  # 항상 연결 닫기
