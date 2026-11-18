"""여러 모듈이 함께 쓰는 설정값 모음."""

import os  # 환경 변수와 경로 처리
from pathlib import Path  # 경로 객체

APP_NAME = "getIP"  # 데이터 폴더 이름

GEO_API_URL = "http://ip-api.com/json/{ip}"  # 위치 조회 API 주소 (무료판은 HTTP 전용)
GEO_BATCH_URL = "http://ip-api.com/batch"  # 여러 IP를 한 번에 조회하는 주소
GEO_FIELDS = "status,message,country,countryCode,city,lat,lon,isp,org,as,hosting,query"  # 응답에 포함시킬 항목
GEO_BATCH_SIZE = 100  # 일괄 조회 한 번에 보낼 수 있는 최대 IP 수 (ip-api 제한)
GEO_TIMEOUT_SEC = 5  # 일반 조회 시 API 응답 대기 시간(초)
GEO_HOP_TIMEOUT_SEC = 2  # 경로 추적 중 홉 조회 시 대기 시간(초)
GEO_CACHE_DAYS = 7  # 위치 조회 캐시 유효 기간(일)

REVERSE_DNS_TIMEOUT_SEC = 2  # 역방향 DNS 조회를 기다리는 최대 시간(초)

TRACE_MAX_HOPS = 30  # 경로 추적 최대 홉 수 (tracert/traceroute 기본값과 동일)
TRACE_WAIT_MS_WINDOWS = 1000  # Windows tracert의 홉당 응답 대기 시간(ms)
TRACE_WAIT_SEC_UNIX = 3  # Unix traceroute의 홉당 응답 대기 시간(초)
TRACE_MAX_SILENT_HOPS = 5  # 응답 없는 홉이 이만큼 연속되면 추적을 멈춤 (ICMP를 막은 대상에서 끝까지 기다리지 않게)

LATENCY_SAMPLES = 4  # 지연 측정 방법마다 보내는 횟수
LATENCY_TCP_PORTS = (443, 80)  # TCP 연결 시간을 잴 포트 (앞의 포트가 응답하지 않으면 다음 포트)
LATENCY_TCP_TIMEOUT_SEC = 1.5  # TCP 연결 한 번을 기다리는 최대 시간(초)
LATENCY_PING_WAIT_MS = 1000  # ping 한 번의 응답 대기 시간(ms)

FIBER_KM_PER_MS = 100  # RTT 1ms당 최대 거리(km): 광섬유 속 빛은 1ms에 약 200km, 왕복이므로 절반 → 물리적 상한
REALISTIC_KM_PER_MS = 65  # RTT 1ms당 현실적 최대 거리(km): 실측(2026-11-19, 서울→비CDN 서버 6곳 25~62km/ms)의 최댓값에 여유를 둠. 이 원 밖이면 가능성 낮음
EARTH_HALF_CIRCUMFERENCE_KM = 20015  # 지구 둘레의 절반(평균 반지름 기준): 어떤 두 지점도 이보다 멀 수 없음

MY_LOCATION_CACHE_SEC = 600  # 반경 원 중심으로 쓰는 '내 위치(ip-api)'를 다시 조회하지 않고 재사용하는 시간(초)

HISTORY_PAGE_SIZE = 20  # CLI 기록 목록에 한 번에 보여줄 건수

TILE_URL_LIGHT = "https://basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}{r}.png"  # 라이트 테마 지도 타일 (CARTO, D2)
TILE_URL_DARK = "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png"  # 다크 테마 지도 타일
TILE_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, '
    '&copy; <a href="https://carto.com/attributions">CARTO</a>'
)  # 약관상 항상 보여야 하는 출처 표기 (고정 문자열이라 HTML 허용)
TILE_KEY_ENV = "GETIP_CARTO_KEY"  # 이 환경 변수가 있으면 저장된 키보다 우선 사용 (개발용)
TILE_ORIGIN = "https://basemaps.cartocdn.com"  # 화면 보안 정책(CSP)에서 이미지 출처로 허용할 주소

CONN_REFRESH_SEC = 5  # 프로그램 연결 자동 새로고침 주기(초, D10)
CONN_CLOSED_KEEP_SEC = 600  # 사라진 연결을 '종료됨'으로 남겨 두는 시간(초). 자동 새로고침을 오래 켜 둬도 목록이 끝없이 늘지 않게 함
CONN_GEO_RETRY_SEC = 60  # 일괄 위치 조회가 실패(한도 초과 등)한 뒤 다시 외부 조회를 시도하기까지 기다리는 시간(초)

THEMES = ("system", "light", "dark")  # 고를 수 있는 테마 (system = OS 설정 따름)
DEFAULT_THEME = "system"  # 처음 실행 시 테마

WINDOW_TITLE = "getIP"  # 데스크톱 창 제목
WINDOW_SIZE = (1280, 800)  # 데스크톱 창 기본 크기 (가로, 세로)
WINDOW_BG = {"light": "#f6f7f9", "dark": "#15181d"}  # 창이 처음 뜰 때 배경색 (theme.css의 --bg와 같은 값)


def data_dir() -> Path:
    """기록 DB를 둘 폴더를 돌려준다. GETIP_DATA_DIR 환경 변수로 바꿀 수 있다(테스트용)."""
    override = os.environ.get("GETIP_DATA_DIR")  # 사용자 지정 경로
    if override:  # 지정돼 있으면
        return Path(override)  # 그 경로 사용
    appdata = os.environ.get("APPDATA")  # Windows 사용자 데이터 폴더
    if appdata:  # Windows인 경우
        return Path(appdata) / APP_NAME  # %APPDATA%\getIP
    return Path.home() / ".local" / "share" / APP_NAME.lower()  # 그 외 운영체제


def db_path() -> Path:
    """기록 DB 파일 경로."""
    return data_dir() / "getip.db"  # 폴더 안의 단일 파일
