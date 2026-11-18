"""FastAPI 라우트. 화면(static/)과 로컬 API(설계 4.7절)를 제공한다.

라우트 함수는 일반 def로 둔다. FastAPI가 스레드풀에서 실행하므로 DNS·위치 조회처럼 기다리는 작업이 서버를 막지 않는다.
"""

import json  # 경로 추적 스트림의 줄 단위 JSON
import mimetypes  # 정적 파일 형식 판별
from pathlib import Path  # 경로 객체
from typing import Optional  # 타입 표기
from urllib.parse import quote  # 키를 주소에 안전하게 넣기

from fastapi import FastAPI, HTTPException, Query  # 웹 프레임워크
from fastapi.responses import HTMLResponse, StreamingResponse  # index.html 응답, 경로 추적 스트림
from fastapi.staticfiles import StaticFiles  # 정적 파일 제공
from pydantic import BaseModel, Field  # 요청 본문 검증

from getip import config  # 타일 주소, 테마 목록
from getip.net.target import InvalidTargetError  # 입력 형식 오류
from getip.probe.traceroute import TracerouteUnavailableError, TracerouteUnsupportedError  # 추적 불가 사유
from getip.services.connections import ConnectionService  # 프로그램 연결 조회
from getip.services.lookup import LookupService  # 조회 서비스
from getip.services.origin import OriginService  # 내 위치
from getip.services.probe import ProbeService, RecordNotFoundError  # 지연 측정·경로 추적
from getip.storage.settings import InvalidSettingError, SettingsStore  # 화면 설정
from getip.system.connections import ConnectionsUnavailableError  # 연결 목록 읽기 실패
from getip.web import serialize  # JSON 변환
from getip.web.security import make_guard  # 로컬 서버 보호 미들웨어

STATIC_DIR = Path(__file__).parent / "static"  # 화면 파일 폴더
_HISTORY_MAX_LIMIT = 200  # 기록 목록 한 번에 돌려줄 최대 건수

mimetypes.add_type("text/javascript", ".js")  # Windows 레지스트리가 .js를 text/plain으로 잡으면 모듈 스크립트가 거부되므로 고정
mimetypes.add_type("text/css", ".css")  # 같은 이유로 CSS도 고정

_CSP = "; ".join([
    "default-src 'self'",  # 기본: 이 서버의 자원만
    f"img-src 'self' data: {config.TILE_ORIGIN}",  # 지도 타일 이미지 허용
    "script-src 'self'",  # 인라인·외부 스크립트 금지
    "style-src 'self'",  # 인라인 스타일 태그 금지 (JS로 바꾸는 style 속성은 영향 없음)
    "connect-src 'self'",  # API 호출은 이 서버로만
    "base-uri 'none'",  # <base> 태그로 주소 바꿔치기 금지
    "form-action 'none'",  # 폼 전송 금지 (화면은 fetch만 씀)
    "frame-ancestors 'none'",  # 다른 사이트가 이 화면을 iframe에 넣지 못하게 함
])  # index.html에 붙이는 보안 정책


class LookupRequest(BaseModel):
    """POST /api/lookup 본문."""

    target: str = Field(min_length=1, max_length=2048)  # 도메인, URL 또는 IP
    ip: Optional[str] = Field(default=None, max_length=64)  # IP가 여러 개일 때 고른 것 (없으면 첫 번째)


class LocationRequest(BaseModel):
    """PUT /api/me/location 본문 (지도에서 클릭한 좌표)."""

    lat: float  # 위도
    lon: float  # 경도 (지도 사본을 클릭하면 ±180 밖일 수 있음 → 저장 시 정리)


class SettingsUpdate(BaseModel):
    """PUT /api/settings 본문. 보낸 항목만 바꾼다."""

    theme: Optional[str] = None  # system / light / dark
    tile_key: Optional[str] = Field(default=None, max_length=500)  # CARTO 키 (빈 문자열이면 삭제)


def _tile_urls(settings: SettingsStore) -> Optional[dict]:
    """키를 붙인 타일 주소. 키가 없으면 None (화면이 '키 필요' 안내를 띄움)."""
    key = settings.tile_key()  # 환경 변수 또는 저장값
    if not key:  # 키 없음
        return None  # 타일을 불러오지 않음
    suffix = "?key=" + quote(key, safe="")  # 키를 주소 파라미터로
    return {"light": config.TILE_URL_LIGHT + suffix, "dark": config.TILE_URL_DARK + suffix}  # 테마별 주소


def create_app(service: LookupService, settings: SettingsStore, token: str,
               connections: Optional[ConnectionService] = None, probe: Optional[ProbeService] = None) -> FastAPI:
    """서비스와 설정 저장소를 연결한 앱을 만든다. token은 실행마다 새로 만든 임의 문자열.

    connections·probe가 없으면 위치 조회 서비스의 캐시·기록을 그대로 써서 기본 구성을 만든다.
    """
    connections = connections or ConnectionService(service.geo)  # 같은 위치 캐시 공유
    probe = probe or ProbeService(service.history, service.geo, OriginService(service.my_ip, settings))  # 측정 서비스
    origins = probe.origins  # 내 위치 (측정과 같은 것을 써야 원 중심이 일치)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)  # 문서 화면은 끔 (로컬 전용 앱)
    app.middleware("http")(make_guard(token))  # 모든 요청에 Host·Origin·토큰 검사
    index_template = (STATIC_DIR / "index.html").read_text(encoding="utf-8")  # 화면 틀 (실행 중 바뀌지 않음)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        """화면. 저장된 테마와 토큰을 미리 채워 넣어 첫 화면이 깜빡이지 않게 한다."""
        html = index_template.replace("__THEME__", settings.theme()).replace("__TOKEN__", token)  # 두 값 모두 안전한 문자만 포함
        return HTMLResponse(html, headers={"Content-Security-Policy": _CSP, "Cache-Control": "no-store"})  # 토큰이 캐시에 남지 않게 함

    @app.get("/api/resolve")
    def resolve(target: str = Query(min_length=1, max_length=2048)):
        """입력을 정리하고 IP 목록만 돌려준다."""
        try:
            parsed, ips = service.resolve(target)  # 입력 검증 + DNS
        except InvalidTargetError as exc:  # 형식 오류
            raise HTTPException(400, str(exc)) from exc  # 사유를 그대로 전달
        return {"host": parsed.host, "is_ip": parsed.is_ip, "ips": ips}  # 대상 정보와 IP 목록

    @app.post("/api/lookup")
    def lookup(body: LookupRequest):
        """조회 실행 후 기록에 저장하고 결과를 돌려준다."""
        try:
            parsed, ips = service.resolve(body.target)  # 입력 검증 + DNS (고른 IP가 목록에 있는지 확인하는 데도 씀)
        except InvalidTargetError as exc:  # 형식 오류
            raise HTTPException(400, str(exc)) from exc  # 400
        if not ips:  # DNS가 IP를 주지 않음
            raise HTTPException(404, f"IP 주소를 찾을 수 없습니다: {parsed.host}")  # 없는 도메인
        ip = body.ip or ips[0]  # 고른 IP가 없으면 첫 번째
        if ip not in ips:  # 이 대상의 IP가 아닌 값
            raise HTTPException(400, f"{parsed.host}의 IP 목록에 없는 주소입니다: {ip}")  # 거부
        return serialize.result_json(service.lookup(parsed, ip, ips))  # 조회 + 저장 결과

    @app.post("/api/lookup/{record_id}/latency")
    def latency_measure(record_id: int):
        """기록의 IP로 지연을 재서 그 기록에 덧붙인다 (D12: 버튼을 눌렀을 때만)."""
        try:
            return serialize.result_json(probe.measure_latency(record_id))  # 측정 + 저장 결과
        except RecordNotFoundError as exc:  # 없는 기록
            raise HTTPException(404, str(exc)) from exc  # 404

    @app.post("/api/lookup/{record_id}/trace")
    def trace_start(record_id: int):
        """경로 추적. 홉이 나올 때마다 JSON 한 줄씩 보낸다 (EventSource는 토큰 헤더를 못 보내 fetch 스트림 사용)."""
        try:
            session = probe.start_trace(record_id)  # 명령 실행 (실행 중인 다른 추적은 멈춤)
        except RecordNotFoundError as exc:  # 없는 기록
            raise HTTPException(404, str(exc)) from exc  # 404
        except TracerouteUnsupportedError as exc:  # IPv6
            raise HTTPException(400, str(exc)) from exc  # 400
        except TracerouteUnavailableError as exc:  # 명령 없음
            raise HTTPException(503, f"경로 추적 명령을 찾을 수 없습니다: {exc}") from exc  # 503

        def lines():
            events = session.events()  # 사건 생성기
            try:
                for event in events:  # 사건마다
                    yield json.dumps(serialize.trace_event_json(event), ensure_ascii=False) + "\n"  # 한 줄
            finally:
                events.close()  # 화면이 끊겨도 프로세스 정리·저장이 바로 일어나게 함

        return StreamingResponse(lines(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store"})  # 줄 단위 JSON 스트림

    @app.post("/api/trace/stop")
    def trace_stop():
        """실행 중인 경로 추적을 멈춘다 (그때까지의 홉은 기록에 저장됨)."""
        return {"stopped": probe.stop_trace()}  # 멈춘 것이 있었는지

    @app.get("/api/me")
    def me():
        """내 공인 IP 정보와 지금 쓰는 내 위치(수동 지정 우선). 조회가 실패해도 200 + error."""
        return serialize.me_json(origins.me())  # 공급자 직접 조회

    @app.put("/api/me/location")
    def me_location_set(body: LocationRequest):
        """내 위치를 지도에서 고른 좌표로 지정 (D13)."""
        try:
            return {"origin": serialize.origin_json(origins.set_manual(body.lat, body.lon))}  # 저장한 위치
        except InvalidSettingError as exc:  # 범위 밖
            raise HTTPException(400, str(exc)) from exc  # 400

    @app.delete("/api/me/location")
    def me_location_clear():
        """수동 지정을 지우고 자동(ip-api) 위치로 되돌린다."""
        return {"origin": serialize.origin_json(origins.clear_manual())}  # 자동 위치 (모르면 null)

    @app.get("/api/connections")
    def connections_list(include_private: bool = False, include_closing: bool = False):
        """이 PC의 프로그램별 TCP 연결과 위치 (한 번 수집). 기록에는 저장하지 않는다 (D9)."""
        try:
            return serialize.snapshot_json(connections.snapshot(include_private, include_closing))  # 수집 + 위치 + 묶기
        except ConnectionsUnavailableError as exc:  # 권한 등으로 읽기 실패
            raise HTTPException(503, str(exc)) from exc  # 사유 전달

    @app.get("/api/history")
    def history_list(q: str = "", limit: int = Query(50, ge=1, le=_HISTORY_MAX_LIMIT), offset: int = Query(0, ge=0)):
        """기록 목록 (최신순, 검색 가능)."""
        entries = service.history.list(q.strip(), limit, offset)  # 요약 목록
        return {"items": [serialize.history_json(e) for e in entries], "total": service.history.count()}  # 목록과 전체 건수

    @app.get("/api/history/{record_id}")
    def history_get(record_id: int):
        """기록 한 건의 전체 결과."""
        result = service.history.get(record_id)  # 저장된 결과 복원
        if result is None:  # 없는 번호
            raise HTTPException(404, "기록을 찾을 수 없습니다.")  # 404
        return serialize.result_json(result)  # 조회 직후와 같은 모양

    @app.delete("/api/history/{record_id}")
    def history_delete(record_id: int):
        """기록 한 건 삭제."""
        if not service.history.delete(record_id):  # 지워진 것이 없으면
            raise HTTPException(404, "기록을 찾을 수 없습니다.")  # 404
        return {"deleted": 1}  # 지운 건수

    @app.delete("/api/history")
    def history_clear():
        """기록 전체 삭제."""
        return {"deleted": service.history.clear()}  # 지운 건수

    @app.get("/api/settings")
    def settings_get():
        """화면 설정과 지도 타일 정보."""
        return {
            "theme": settings.theme(),  # system / light / dark
            "themes": list(config.THEMES),  # 고를 수 있는 값
            "tile_key_set": settings.tile_key() is not None,  # 키가 있는지 (키 자체는 tiles 주소에만 들어감)
            "tile_key_from_env": settings.tile_key_from_env(),  # 환경 변수 사용 중이면 화면에서 수정 불가 안내
            "tiles": _tile_urls(settings),  # 테마별 타일 주소 또는 None
            "attribution": config.TILE_ATTRIBUTION,  # 출처 표기
            "storage_warning": service.storage_warning,  # 기록 저장소 문제 안내 (없으면 None)
            "connections_refresh_sec": config.CONN_REFRESH_SEC,  # 연결 목록 자동 새로고침 주기
            "fiber_km_per_ms": config.FIBER_KM_PER_MS,  # 반경 원 설명용: 물리적 상한 계수
            "realistic_km_per_ms": config.REALISTIC_KM_PER_MS,  # 반경 원 설명용: 현실 추정 계수
        }

    @app.put("/api/settings")
    def settings_put(body: SettingsUpdate):
        """설정 저장. 보낸 항목만 바꾸고 바뀐 전체 설정을 돌려준다."""
        try:
            if body.theme is not None:  # 테마 변경 요청
                settings.set_theme(body.theme)  # 허용 목록 검사 후 저장
            if body.tile_key is not None:  # 키 변경 요청
                settings.set_tile_key(body.tile_key)  # 형식 검사 후 저장 (빈 값이면 삭제)
        except InvalidSettingError as exc:  # 허용되지 않는 값
            raise HTTPException(400, str(exc)) from exc  # 400
        return settings_get()  # 최신 설정

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")  # css, js, leaflet 파일
    return app  # 완성된 앱
