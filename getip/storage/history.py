"""조회 기록 저장·목록·상세·삭제."""

import json  # 결과 전체를 JSON 문자열로 저장
from datetime import datetime  # 저장된 시각 문자열 복원
from typing import List, Optional  # 타입 표기

from getip.models import HistoryEntry, LookupResult, result_from_dict, result_to_dict  # 데이터 클래스와 변환 함수
from getip.storage.db import Database  # DB 연결


def _like_pattern(query: str) -> str:
    """검색어를 LIKE 패턴으로 바꾼다. %, _ 같은 특수 문자는 글자 그대로 찾게 한다."""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")  # 특수 문자 무력화
    return f"%{escaped}%"  # 부분 일치


class HistoryStore:
    """조회 기록 테이블(lookups)을 다룬다."""

    def __init__(self, database: Database):
        self._db = database  # 사용할 DB

    def save(self, result: LookupResult) -> int:
        """조회 결과를 저장하고 기록 번호를 돌려준다. result.id도 채운다."""
        geo = result.geo  # 위치 정보 (없을 수 있음)
        with self._db.connect() as conn:  # 연결 열기
            cursor = conn.execute(
                "INSERT INTO lookups(created_at, input, host, ip, country, city, isp, asn,"
                " est_lat, est_lon, result_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result.created_at.isoformat(),  # 조회 시각
                    result.target.raw,  # 입력 원문
                    result.target.host,  # 정리된 호스트
                    result.ip,  # 조회한 IP
                    geo.country if geo else None,  # 목록 표시용 국가
                    geo.city if geo else None,  # 목록 표시용 도시
                    geo.isp if geo else None,  # 목록 표시용 사업자
                    geo.asn if geo else None,  # 검색용 ASN
                    geo.lat if geo else None,  # 지도 표시용 위도 (추정 엔진 도입 전에는 DB 위치)
                    geo.lon if geo else None,  # 지도 표시용 경도
                    json.dumps(result_to_dict(result), ensure_ascii=False),  # 결과 전체
                ),
            )  # 한 건 삽입
            result.id = cursor.lastrowid  # 부여된 번호를 결과에 기록
        return result.id  # 기록 번호

    def list(self, query: str = "", limit: int = 20, offset: int = 0) -> List[HistoryEntry]:
        """최신순 기록 목록. query가 있으면 입력·호스트·IP에서 부분 일치 검색."""
        sql = "SELECT id, created_at, input, host, ip, country, city, isp FROM lookups"  # 요약 컬럼만 조회
        params: list = []  # SQL에 넣을 값
        if query:  # 검색어가 있으면
            sql += " WHERE input LIKE ? ESCAPE '\\' OR host LIKE ? ESCAPE '\\' OR ip LIKE ? ESCAPE '\\'"  # 세 컬럼 검색
            params += [_like_pattern(query)] * 3  # 같은 패턴을 세 번 사용
        sql += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"  # 최신순, 페이지 단위
        params += [limit, offset]  # 건수와 시작 위치
        with self._db.connect() as conn:  # 연결 열기
            rows = conn.execute(sql, params).fetchall()  # 조회 실행
        return [
            HistoryEntry(
                id=row["id"],  # 기록 번호
                created_at=datetime.fromisoformat(row["created_at"]),  # 문자열을 시각으로
                input=row["input"],  # 입력 원문
                host=row["host"],  # 호스트
                ip=row["ip"],  # IP
                country=row["country"],  # 국가
                city=row["city"],  # 도시
                isp=row["isp"],  # 사업자
            )
            for row in rows  # 행마다 요약 객체 생성
        ]

    def get(self, record_id: int) -> Optional[LookupResult]:
        """기록 한 건의 전체 결과. 없으면 None."""
        with self._db.connect() as conn:  # 연결 열기
            row = conn.execute("SELECT result_json FROM lookups WHERE id = ?", (record_id,)).fetchone()  # 한 건 조회
        if row is None:  # 해당 번호가 없으면
            return None  # 없음
        return result_from_dict(json.loads(row["result_json"]), record_id)  # JSON에서 복원

    def delete(self, record_id: int) -> bool:
        """기록 한 건을 지운다. 지웠으면 True."""
        with self._db.connect() as conn:  # 연결 열기
            cursor = conn.execute("DELETE FROM lookups WHERE id = ?", (record_id,))  # 삭제 실행
            return cursor.rowcount > 0  # 실제로 지워졌는지

    def clear(self) -> int:
        """모든 기록을 지우고 지운 건수를 돌려준다."""
        with self._db.connect() as conn:  # 연결 열기
            return conn.execute("DELETE FROM lookups").rowcount  # 전체 삭제

    def count(self) -> int:
        """저장된 기록 수."""
        with self._db.connect() as conn:  # 연결 열기
            return conn.execute("SELECT COUNT(*) FROM lookups").fetchone()[0]  # 건수 조회
