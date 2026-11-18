"""거리 계산과 RTT → 거리 변환. 네트워크를 쓰지 않는 순수 함수만 둔다."""

import math  # 삼각 함수
from typing import Optional  # 타입 표기

from getip import config  # 계수와 지구 크기

EARTH_RADIUS_KM = 6371.0088  # 지구 평균 반지름(km)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 사이의 지표면 거리(km). 지구를 구로 보는 대권 거리."""
    p1, p2 = math.radians(lat1), math.radians(lat2)  # 위도를 라디안으로
    dlat = p2 - p1  # 위도 차이
    dlon = math.radians(lon2 - lon1)  # 경도 차이
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2  # 하버사인 공식의 중간값
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))  # 반올림 오차로 1을 넘지 않게 자름


def _cap(km: float) -> float:
    """지구 반 바퀴보다 먼 거리는 의미가 없으므로 자른다."""
    return min(km, config.EARTH_HALF_CIRCUMFERENCE_KM)  # 상한 적용


def rtt_upper_km(rtt_ms: float) -> float:
    """이 RTT로 갈 수 있는 물리적 최대 거리(km). 이보다 먼 위치는 불가능하다."""
    return _cap(max(rtt_ms, 0.0) * config.FIBER_KM_PER_MS)  # 광섬유 속 빛의 속도 기준


def rtt_typical_km(rtt_ms: float) -> float:
    """이 RTT에서 현실적으로 예상되는 최대 거리(km). 추정값이라 틀릴 수 있다."""
    return _cap(max(rtt_ms, 0.0) * config.REALISTIC_KM_PER_MS)  # 실측 보정 계수 기준


def is_beyond_upper(distance_km: Optional[float], rtt_ms: Optional[float]) -> Optional[bool]:
    """거리가 RTT의 물리적 상한보다 먼지. 둘 중 하나라도 모르면 None."""
    if distance_km is None or rtt_ms is None:  # 판단 근거 부족
        return None  # 모름
    return distance_km > rtt_upper_km(rtt_ms)  # 상한 밖이면 True
