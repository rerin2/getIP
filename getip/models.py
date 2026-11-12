"""계층 사이에서 주고받는 데이터 클래스. 로직 계층은 print 대신 이 객체를 반환한다."""

from dataclasses import asdict, dataclass, field, fields  # 데이터 클래스 도구
from datetime import datetime, timezone  # 조회 시각 기록
from typing import Any, Dict, List, Optional  # 타입 표기


@dataclass(frozen=True)  # 생성 후 변경 불가
class Target:
    """사용자 입력을 정리한 조회 대상."""

    raw: str  # 사용자가 입력한 원문
    host: str  # 추출·검증된 호스트명 또는 IP
    is_ip: bool  # IP 주소를 직접 입력했는지 여부


@dataclass(frozen=True)  # 생성 후 변경 불가
class GeoInfo:
    """위치 DB 조회 결과."""

    ip: str  # 조회된 IP 주소
    country: Optional[str]  # 국가명
    city: Optional[str]  # 도시명
    isp: Optional[str]  # 인터넷 사업자
    org: Optional[str]  # 조직명
    source: str  # 정보를 준 공급자 이름
    country_code: Optional[str] = None  # 두 글자 국가 코드 (예: KR)
    lat: Optional[float] = None  # 위도
    lon: Optional[float] = None  # 경도
    asn: Optional[str] = None  # AS 번호와 이름 (예: "AS13335 Cloudflare, Inc.")
    is_hosting: Optional[bool] = None  # 데이터센터/호스팅 대역 여부


@dataclass(frozen=True)  # 생성 후 변경 불가
class Hop:
    """경로 추적의 한 홉."""

    index: int  # 홉 번호 (1부터)
    ip: Optional[str]  # 응답한 IP, 응답이 없으면 None
    rtt_ms: Optional[float]  # 지연시간(ms), 측정값이 없으면 None
    rtt_less_than: bool = False  # True면 "rtt_ms 미만"이라는 뜻 (tracert의 "<1 ms")


@dataclass  # 조회 후 id가 채워지므로 변경 가능
class LookupResult:
    """조회 한 건의 전체 결과. 기록에 그대로 저장된다."""

    target: Target  # 조회 대상
    ip: str  # 실제로 조회한 IP
    all_ips: List[str]  # DNS가 돌려준 전체 IP 목록
    geo: Optional[GeoInfo]  # 위치 정보, 얻지 못하면 None
    reverse_dns: Optional[str]  # 역방향 DNS 이름, 없으면 None
    warnings: List[str] = field(default_factory=list)  # 일부 항목이 실패한 사유 등
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # 조회 시각(UTC)
    id: Optional[int] = None  # 기록에 저장된 뒤의 번호


@dataclass(frozen=True)  # 생성 후 변경 불가
class HistoryEntry:
    """기록 목록의 한 줄 (요약)."""

    id: int  # 기록 번호
    created_at: datetime  # 조회 시각(UTC)
    input: str  # 입력 원문
    host: str  # 정리된 호스트
    ip: str  # 조회한 IP
    country: Optional[str]  # 국가명
    city: Optional[str]  # 도시명
    isp: Optional[str]  # 인터넷 사업자


def _pick(cls, data: Dict[str, Any]) -> Dict[str, Any]:
    """dict에서 cls가 아는 필드만 골라낸다. 이후 버전에서 필드가 늘거나 줄어도 읽을 수 있게 한다."""
    names = {f.name for f in fields(cls)}  # 클래스에 정의된 필드 이름
    return {key: value for key, value in data.items() if key in names}  # 모르는 키는 버림


def geo_to_dict(info: GeoInfo) -> Dict[str, Any]:
    """GeoInfo를 JSON으로 저장할 수 있는 dict로 바꾼다."""
    return asdict(info)  # 모든 필드가 기본 타입이라 그대로 변환


def geo_from_dict(data: Dict[str, Any]) -> GeoInfo:
    """저장된 dict에서 GeoInfo를 복원한다."""
    return GeoInfo(**_pick(GeoInfo, data))  # 아는 필드만 사용


def result_to_dict(result: LookupResult) -> Dict[str, Any]:
    """LookupResult를 JSON으로 저장할 수 있는 dict로 바꾼다."""
    data = asdict(result)  # 중첩된 데이터 클래스까지 dict로 변환
    data["created_at"] = result.created_at.isoformat()  # 시각은 ISO8601 문자열로
    data.pop("id", None)  # 번호는 테이블 컬럼으로 따로 관리
    return data  # 저장용 dict


def result_from_dict(data: Dict[str, Any], record_id: Optional[int] = None) -> LookupResult:
    """저장된 dict에서 LookupResult를 복원한다."""
    geo = data.get("geo")  # 위치 정보 부분
    return LookupResult(
        target=Target(**_pick(Target, data["target"])),  # 조회 대상 복원
        ip=data["ip"],  # 조회한 IP
        all_ips=list(data.get("all_ips") or []),  # IP 목록 (없으면 빈 목록)
        geo=geo_from_dict(geo) if geo else None,  # 위치 정보가 있을 때만 복원
        reverse_dns=data.get("reverse_dns"),  # 역방향 DNS
        warnings=list(data.get("warnings") or []),  # 경고 목록
        created_at=datetime.fromisoformat(data["created_at"]),  # 문자열을 시각으로
        id=record_id,  # 기록 번호
    )
