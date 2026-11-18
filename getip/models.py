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
    geo: Optional[GeoInfo] = None  # 홉의 위치 (사설 IP·조회 실패면 None)


@dataclass(frozen=True)  # 생성 후 변경 불가
class Origin:
    """지연·경로를 측정한 곳 (반경 원과 경로선의 시작점)."""

    lat: float  # 위도
    lon: float  # 경도
    source: str  # "manual"(지도에서 지정) | "ip-api"(내 공인 IP 위치)


@dataclass(frozen=True)  # 생성 후 변경 불가
class LatencyResult:
    """지연 측정 방법 하나의 결과."""

    method: str  # "tcp:443", "tcp:80", "tcp"(모든 포트 실패), "icmp"
    samples_ms: List[float]  # 성공한 측정값(ms)
    attempts: int  # 시도 횟수
    min_ms: Optional[float]  # 최솟값, 성공이 없으면 None
    loss: float  # 실패 비율 0~1


@dataclass(frozen=True)  # 생성 후 변경 불가
class LatencyReport:
    """지연 측정 한 번의 전체 결과."""

    measured_at: datetime  # 측정 시각(UTC)
    origin: Optional[Origin]  # 측정한 곳, 모르면 None (반경 원을 그릴 수 없음)
    results: List[LatencyResult]  # 방법별 결과 (TCP, ICMP)

    @property
    def min_ms(self) -> Optional[float]:
        """모든 방법 중 가장 작은 값. 측정값은 실제 전파 시간보다 항상 크므로 최솟값이 가장 정확하다."""
        values = [r.min_ms for r in self.results if r.min_ms is not None]  # 성공한 방법의 최솟값
        return min(values) if values else None  # 하나도 없으면 None


@dataclass(frozen=True)  # 생성 후 변경 불가
class TraceReport:
    """경로 추적 한 번의 결과."""

    started_at: datetime  # 시작 시각(UTC)
    origin: Optional[Origin]  # 추적한 곳 (경로선의 시작점)
    hops: List[Hop]  # 확인된 홉 (순서대로)
    status: str  # "done"(끝까지), "silent"(응답 없는 홉이 이어져 멈춤), "stopped"(사용자가 중지), "error"
    message: Optional[str] = None  # 멈춘 사유 등 안내 문구


@dataclass(frozen=True)  # 생성 후 변경 불가
class MeInfo:
    """내 공인 IP 정보와 지금 쓰는 내 위치."""

    geo: Optional[GeoInfo]  # ip-api가 알려준 내 IP 정보, 실패하면 None
    origin: Optional[Origin]  # 반경 원·경로선의 시작점 (수동 지정이 우선), 모르면 None
    error: Optional[str] = None  # 내 IP 조회 실패 사유


@dataclass(frozen=True)  # 생성 후 변경 불가
class TraceEvent:
    """경로 추적 중 화면에 흘려보내는 사건 하나."""

    kind: str  # "start"(시작, origin), "hop"(홉 확인·갱신, hop), "done"(끝, report)
    origin: Optional[Origin] = None  # 시작점 (kind="start")
    hop: Optional[Hop] = None  # 홉 (kind="hop", 같은 번호가 다시 오면 위치가 채워진 갱신)
    report: Optional[TraceReport] = None  # 최종 결과 (kind="done")


@dataclass  # 조회 후 id가 채워지므로 변경 가능
class LookupResult:
    """조회 한 건의 전체 결과. 기록에 그대로 저장된다."""

    target: Target  # 조회 대상
    ip: str  # 실제로 조회한 IP
    all_ips: List[str]  # DNS가 돌려준 전체 IP 목록
    geo: Optional[GeoInfo]  # 위치 정보, 얻지 못하면 None
    reverse_dns: Optional[str]  # 역방향 DNS 이름, 없으면 None
    warnings: List[str] = field(default_factory=list)  # 일부 항목이 실패한 사유 등
    latency: Optional[LatencyReport] = None  # 지연 측정 결과 (버튼을 눌렀을 때만, D12)
    trace: Optional[TraceReport] = None  # 경로 추적 결과 (D15)
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


@dataclass  # 수집 후 위치·종료 여부를 채우므로 변경 가능
class Connection:
    """이 PC의 프로그램이 맺은 TCP 연결 한 건 (R7)."""

    pid: Optional[int]  # 프로세스 ID, 소유 프로세스가 없으면(TIME_WAIT 등) None
    process_name: Optional[str]  # 프로그램 이름, 읽지 못하면 None
    exe_path: Optional[str]  # 실행 파일 경로, 읽지 못하면 None
    local_port: int  # 이 PC 쪽 포트
    remote_ip: str  # 상대 IP
    remote_port: int  # 상대 포트
    status: str  # "ESTABLISHED", "TIME_WAIT" 등
    is_public: bool  # 공인 IP 여부 (False면 위치 조회 생략)
    protocol: str = "tcp"  # 지금은 TCP만 수집 (설계 3.7절)
    closed: bool = False  # 이전 수집에는 있었지만 지금은 없는 연결
    geo: Optional[GeoInfo] = None  # 캐시·일괄 조회로 붙인 위치 정보

    def key(self) -> tuple:
        """같은 연결인지 비교할 때 쓰는 값. 종료된 연결을 찾는 데 쓴다."""
        return (self.pid, self.local_port, self.remote_ip, self.remote_port)  # 프로세스 + 양 끝 주소


@dataclass
class ProgramConnections:
    """프로그램 하나와 그 연결들."""

    name: str  # 화면에 보일 프로그램 이름
    exe_path: Optional[str]  # 실행 파일 경로
    pids: List[int]  # 이 이름으로 묶인 프로세스 ID들
    connections: List[Connection]  # 연결 목록


@dataclass
class ConnectionSnapshot:
    """한 번 수집한 결과 전체."""

    collected_at: datetime  # 수집 시각(UTC)
    programs: List[ProgramConnections]  # 프로그램별 묶음 (연결 많은 순)
    total: int  # 필터 전 원격 주소가 있는 연결 수
    shown: int  # 화면에 보이는 연결 수
    pending: List[str] = field(default_factory=list)  # 위치를 아직 조회하지 못한 IP
    error: Optional[str] = None  # 위치 조회 실패 사유


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


def _origin_from_dict(data: Optional[Dict[str, Any]]) -> Optional[Origin]:
    """저장된 dict에서 측정 위치를 복원한다."""
    return Origin(**_pick(Origin, data)) if data else None  # 없으면 None


def _hop_from_dict(data: Dict[str, Any]) -> Hop:
    """저장된 dict에서 홉을 복원한다."""
    values = _pick(Hop, data)  # 아는 필드만
    values["geo"] = geo_from_dict(data["geo"]) if data.get("geo") else None  # 위치는 데이터 클래스로
    return Hop(**values)  # 홉


def _latency_from_dict(data: Optional[Dict[str, Any]]) -> Optional[LatencyReport]:
    """저장된 dict에서 지연 측정 결과를 복원한다."""
    if not data:  # 측정하지 않은 기록
        return None  # 없음
    return LatencyReport(
        measured_at=datetime.fromisoformat(data["measured_at"]),  # 문자열을 시각으로
        origin=_origin_from_dict(data.get("origin")),  # 측정 위치
        results=[LatencyResult(**_pick(LatencyResult, r)) for r in data.get("results") or []],  # 방법별 결과
    )


def _trace_from_dict(data: Optional[Dict[str, Any]]) -> Optional[TraceReport]:
    """저장된 dict에서 경로 추적 결과를 복원한다."""
    if not data:  # 추적하지 않은 기록
        return None  # 없음
    return TraceReport(
        started_at=datetime.fromisoformat(data["started_at"]),  # 문자열을 시각으로
        origin=_origin_from_dict(data.get("origin")),  # 추적 위치
        hops=[_hop_from_dict(h) for h in data.get("hops") or []],  # 홉 목록
        status=data.get("status", "done"),  # 종료 상태
        message=data.get("message"),  # 안내 문구
    )


def result_to_dict(result: LookupResult) -> Dict[str, Any]:
    """LookupResult를 JSON으로 저장할 수 있는 dict로 바꾼다."""
    data = asdict(result)  # 중첩된 데이터 클래스까지 dict로 변환
    data["created_at"] = result.created_at.isoformat()  # 시각은 ISO8601 문자열로
    if result.latency is not None:  # 지연 측정 결과가 있으면
        data["latency"]["measured_at"] = result.latency.measured_at.isoformat()  # 시각을 문자열로
    if result.trace is not None:  # 경로 추적 결과가 있으면
        data["trace"]["started_at"] = result.trace.started_at.isoformat()  # 시각을 문자열로
    data.pop("id", None)  # 번호는 테이블 컬럼으로 따로 관리
    return data  # 저장용 dict


def result_from_dict(data: Dict[str, Any], record_id: Optional[int] = None) -> LookupResult:
    """저장된 dict에서 LookupResult를 복원한다. 이전 버전 기록(latency·trace 없음)도 읽는다."""
    geo = data.get("geo")  # 위치 정보 부분
    return LookupResult(
        target=Target(**_pick(Target, data["target"])),  # 조회 대상 복원
        ip=data["ip"],  # 조회한 IP
        all_ips=list(data.get("all_ips") or []),  # IP 목록 (없으면 빈 목록)
        geo=geo_from_dict(geo) if geo else None,  # 위치 정보가 있을 때만 복원
        reverse_dns=data.get("reverse_dns"),  # 역방향 DNS
        warnings=list(data.get("warnings") or []),  # 경고 목록
        latency=_latency_from_dict(data.get("latency")),  # 지연 측정
        trace=_trace_from_dict(data.get("trace")),  # 경로 추적
        created_at=datetime.fromisoformat(data["created_at"]),  # 문자열을 시각으로
        id=record_id,  # 기록 번호
    )
