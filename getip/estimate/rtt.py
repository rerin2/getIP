"""지연 측정 결과 요약: 최솟값, 반경 두 개, 측정 위치에서 DB 위치까지 거리. CLI와 화면이 함께 쓴다."""

from typing import Any, Dict, Optional  # 타입 표기

from getip.estimate import geomath  # 거리 계산
from getip.models import LookupResult  # 조회 결과


def latency_summary(result: LookupResult) -> Optional[Dict[str, Any]]:
    """측정하지 않은 결과면 None. 값을 모르는 항목은 None으로 둔다."""
    report = result.latency  # 측정 결과
    if report is None:  # 측정하지 않은 기록
        return None  # 없음
    rtt = report.min_ms  # 모든 방법 중 최솟값
    summary: Dict[str, Any] = {"min_ms": rtt, "upper_km": None, "typical_km": None,
                               "db_distance_km": None, "db_beyond_upper": None}  # 기본값
    if rtt is not None:  # 측정 성공
        summary["upper_km"] = round(geomath.rtt_upper_km(rtt))  # 물리적 상한 반경 (옅은 원)
        summary["typical_km"] = round(geomath.rtt_typical_km(rtt))  # 현실 추정 반경 (진한 원)
    origin, geo = report.origin, result.geo  # 측정 위치와 DB 위치
    if origin and geo and geo.lat is not None and geo.lon is not None:  # 둘 다 좌표가 있으면
        distance = geomath.haversine_km(origin.lat, origin.lon, geo.lat, geo.lon)  # 측정 위치 → DB 위치 거리
        summary["db_distance_km"] = round(distance)  # km 단위 정수
        summary["db_beyond_upper"] = geomath.is_beyond_upper(distance, rtt)  # 상한 밖이면 DB 위치가 물리적으로 불가능
    return summary  # 요약
