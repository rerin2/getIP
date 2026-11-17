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

HISTORY_PAGE_SIZE = 20  # CLI 기록 목록에 한 번에 보여줄 건수

TILE_URL_LIGHT = "https://basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}{r}.png"  # 라이트 테마 지도 타일 (CARTO, D2)
TILE_URL_DARK = "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png"  # 다크 테마 지도 타일
TILE_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, '
    '&copy; <a href="https://carto.com/attributions">CARTO</a>'
)  # 약관상 항상 보여야 하는 출처 표기 (고정 문자열이라 HTML 허용)
TILE_KEY_ENV = "GETIP_CARTO_KEY"  # 이 환경 변수가 있으면 저장된 키보다 우선 사용 (개발용)
TILE_ORIGIN = "https://basemaps.cartocdn.com"  # 화면 보안 정책(CSP)에서 이미지 출처로 허용할 주소

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
