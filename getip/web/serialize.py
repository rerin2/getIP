"""데이터 클래스를 화면(JSON)용 dict로 바꾼다. 화면이 쓰는 모양을 한곳에서 정한다."""

from dataclasses import asdict  # 데이터 클래스 → dict
from typing import Any, Dict, Optional  # 타입 표기

from getip.estimate.rtt import latency_summary  # 지연 요약 (CLI와 공용)
from getip.models import (ConnectionSnapshot, GeoInfo, HistoryEntry, LookupResult, MeInfo, Origin,  # 데이터 클래스
                          TraceEvent, TraceReport, result_to_dict)


def result_json(result: LookupResult) -> Dict[str, Any]:
    """조회 결과 전체. 저장 형식에 기록 번호와 지연 요약을 더한다."""
    data = result_to_dict(result)  # 저장용과 같은 모양 (시각은 ISO 문자열)
    data["id"] = result.id  # 화면에서 기록 강조·삭제에 쓰는 번호
    data["latency_view"] = latency_summary(result)  # 반경·거리 계산 결과 (계산식은 서버 한곳에만 둠)
    return data  # JSON 응답 본문


def geo_json(info: GeoInfo) -> Dict[str, Any]:
    """위치 정보 하나."""
    return asdict(info)  # 모든 필드가 기본 타입


def origin_json(origin: Optional[Origin]) -> Optional[Dict[str, Any]]:
    """시작점(내 위치) 하나. 모르면 None."""
    return asdict(origin) if origin else None  # 위도·경도·출처


def me_json(me: MeInfo) -> Dict[str, Any]:
    """내 IP 정보와 지금 쓰는 내 위치."""
    return {"geo": geo_json(me.geo) if me.geo else None, "origin": origin_json(me.origin), "error": me.error}  # 세 항목


def trace_json(report: TraceReport) -> Dict[str, Any]:
    """경로 추적 결과."""
    data = asdict(report)  # 홉·위치까지 중첩 변환
    data["started_at"] = report.started_at.isoformat()  # 시각은 ISO 문자열로
    return data  # JSON


def trace_event_json(event: TraceEvent) -> Dict[str, Any]:
    """경로 추적 스트림의 한 줄."""
    return {
        "type": event.kind,  # start / hop / done
        "origin": origin_json(event.origin),  # 시작점 (start)
        "hop": asdict(event.hop) if event.hop else None,  # 홉 (hop)
        "report": trace_json(event.report) if event.report else None,  # 최종 결과 (done)
    }


def history_json(entry: HistoryEntry) -> Dict[str, Any]:
    """기록 목록의 한 줄."""
    data = asdict(entry)  # 요약 필드
    data["created_at"] = entry.created_at.isoformat()  # 시각은 ISO 문자열로
    return data  # 목록 항목


def snapshot_json(snapshot: ConnectionSnapshot) -> Dict[str, Any]:
    """프로그램 연결 수집 결과 전체."""
    data = asdict(snapshot)  # 프로그램 → 연결 → 위치까지 중첩 변환
    data["collected_at"] = snapshot.collected_at.isoformat()  # 시각은 ISO 문자열로
    return data  # JSON 응답 본문
