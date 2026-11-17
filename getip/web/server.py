"""로컬 서버를 백그라운드 스레드에서 띄우고 멈추는 도구. 데스크톱 창과 브라우저 개발 모드가 함께 쓴다."""

import secrets  # 실행별 토큰 생성
import socket  # 임의 포트에 미리 묶어 두기
import threading  # 서버를 별도 스레드에서 실행
import time  # 시작 대기
from dataclasses import dataclass  # 실행 중인 서버 정보 묶음
from typing import Optional  # 타입 표기

import uvicorn  # ASGI 서버

from getip.services.lookup import LookupService, create_service, open_database  # 조회 서비스 조립
from getip.storage.settings import SettingsStore  # 화면 설정
from getip.web.app import create_app  # FastAPI 앱

_HOST = "127.0.0.1"  # 이 PC 안에서만 접속 가능 (같은 네트워크의 다른 PC는 접근 불가)
_START_TIMEOUT_SEC = 10  # 서버가 뜰 때까지 기다리는 최대 시간


@dataclass
class RunningServer:
    """실행 중인 로컬 서버."""

    url: str  # 화면 주소 (http://127.0.0.1:포트/)
    settings: SettingsStore  # 설정 저장소 (창 배경색을 정할 때 테마를 읽음)
    _server: uvicorn.Server  # uvicorn 서버 객체
    _thread: threading.Thread  # 서버 스레드

    def stop(self) -> None:
        """서버에 종료를 알리고 스레드가 끝날 때까지 잠시 기다린다."""
        self._server.should_exit = True  # uvicorn이 다음 루프에서 정리 후 종료
        self._thread.join(timeout=5)  # 너무 오래 걸리면 포기 (데몬 스레드라 프로세스 종료 시 함께 끝남)


def start(service: Optional[LookupService] = None, settings: Optional[SettingsStore] = None) -> RunningServer:
    """서버를 임의 포트로 띄우고 접속 준비가 될 때까지 기다린다. 실패하면 RuntimeError."""
    if service is None or settings is None:  # 기본 구성 사용
        database, warning = open_database()  # 사용자 폴더의 DB (실패 시 임시 DB)
        service = service or create_service(database, warning)  # 조회 서비스
        settings = settings or SettingsStore(database)  # 같은 DB에 설정 저장
    token = secrets.token_urlsafe(32)  # 실행마다 바뀌는 API 토큰
    app = create_app(service, settings, token)  # 앱 조립

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 포트를 먼저 잡아 두어 다른 프로그램과 겹치지 않게 함
    sock.bind((_HOST, 0))  # 0번 = 운영체제가 빈 포트를 골라 줌
    port = sock.getsockname()[1]  # 실제로 받은 포트

    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))  # 요청마다 로그를 찍지 않음
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True, name="getip-web")  # 잡아 둔 소켓으로 실행
    thread.start()  # 서버 시작

    deadline = time.monotonic() + _START_TIMEOUT_SEC  # 대기 마감 시각
    while not server.started:  # uvicorn이 준비 완료를 표시할 때까지
        if not thread.is_alive() or time.monotonic() > deadline:  # 시작 중 죽었거나 너무 오래 걸림
            server.should_exit = True  # 혹시 살아 있으면 종료 요청
            raise RuntimeError("로컬 서버를 시작하지 못했습니다.")  # 호출자가 안내
        time.sleep(0.05)  # 잠깐 쉬고 다시 확인
    return RunningServer(f"http://{_HOST}:{port}/", settings, server, thread)  # 접속 정보
