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
