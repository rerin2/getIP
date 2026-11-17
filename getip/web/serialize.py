"""데이터 클래스를 화면(JSON)용 dict로 바꾼다. 화면이 쓰는 모양을 한곳에서 정한다."""

from dataclasses import asdict  # 데이터 클래스 → dict
from typing import Any, Dict  # 타입 표기

from getip.models import GeoInfo, HistoryEntry, LookupResult, result_to_dict  # 데이터 클래스와 변환 함수


def result_json(result: LookupResult) -> Dict[str, Any]:
    """조회 결과 전체. 저장 형식에 기록 번호를 더한다."""
    data = result_to_dict(result)  # 저장용과 같은 모양 (시각은 ISO 문자열)
    data["id"] = result.id  # 화면에서 기록 강조·삭제에 쓰는 번호
    return data  # JSON 응답 본문


def geo_json(info: GeoInfo) -> Dict[str, Any]:
    """위치 정보 하나."""
    return asdict(info)  # 모든 필드가 기본 타입


def history_json(entry: HistoryEntry) -> Dict[str, Any]:
    """기록 목록의 한 줄."""
    data = asdict(entry)  # 요약 필드
    data["created_at"] = entry.created_at.isoformat()  # 시각은 ISO 문자열로
    return data  # 목록 항목
