"""로컬 서버 보호: 다른 웹사이트가 이 서버를 몰래 호출하지 못하게 한다 (설계 5절).

- Host 검사: 악성 사이트가 자기 도메인을 127.0.0.1로 바꿔치기(DNS 리바인딩)해도 Host가 달라 거부된다.
- Origin 검사: 다른 사이트에서 보낸 요청은 Origin이 달라 거부된다.
- 토큰 검사: /api/ 요청은 index.html에 심어 둔 실행별 토큰이 있어야 한다. 다른 사이트는 이 값을 읽을 수 없다.
"""

import hmac  # 시간 차이로 토큰을 추측하지 못하게 하는 비교 함수
from typing import Awaitable, Callable, Optional  # 타입 표기
from urllib.parse import urlsplit  # Origin 헤더에서 호스트 추출

from starlette.requests import Request  # 요청 객체
from starlette.responses import JSONResponse, Response  # 응답 객체

TOKEN_HEADER = "X-GetIP-Token"  # 화면이 토큰을 실어 보내는 헤더 이름
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})  # 이 서버로 인정하는 호스트 이름


def _hostname(host_header: str) -> str:
    """'127.0.0.1:8000' 형태의 Host 헤더에서 호스트 이름만 뽑는다."""
    return (urlsplit("//" + host_header).hostname or "") if host_header else ""  # 포트 제거, 소문자화


def _origin_ok(origin: Optional[str]) -> bool:
    """Origin 헤더가 없거나(같은 페이지 내 일반 요청) 이 서버 주소면 통과."""
    if origin is None:  # 브라우저가 Origin을 붙이지 않은 요청 (주소창 이동, 같은 출처 GET)
        return True  # 통과 (토큰 검사가 따로 있음)
    return (urlsplit(origin).hostname or "") in ALLOWED_HOSTS  # 다른 사이트에서 온 요청이면 거부


def _forbidden(reason: str) -> Response:
    """거부 응답."""
    return JSONResponse({"detail": reason}, status_code=403)  # 사유를 담은 403


def make_guard(token: str) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """토큰을 기억하는 HTTP 미들웨어 함수를 만든다."""

    async def guard(request: Request, call_next):
        if _hostname(request.headers.get("host", "")) not in ALLOWED_HOSTS:  # 바꿔치기된 도메인
            return _forbidden("허용되지 않은 호스트입니다.")  # 거부
        if not _origin_ok(request.headers.get("origin")):  # 다른 사이트에서 보낸 요청
            return _forbidden("허용되지 않은 출처입니다.")  # 거부
        if request.url.path.startswith("/api/"):  # API 요청이면
            sent = request.headers.get(TOKEN_HEADER, "")  # 화면이 보낸 토큰
            if not hmac.compare_digest(sent.encode(), token.encode()):  # 실행별 토큰과 다르면
                return _forbidden("토큰이 올바르지 않습니다.")  # 거부
        return await call_next(request)  # 통과: 실제 처리로 넘김

    return guard  # 미들웨어 함수
