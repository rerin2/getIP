"""GUI 진입점. 로컬 서버를 띄우고 pywebview 창(또는 개발용 브라우저 탭)으로 화면을 연다.

실행:
  python -m getip.desktop            전용 창 (배포용)
  python -m getip.desktop --browser  기본 브라우저 탭 (개발용, Ctrl+C로 종료)
"""

import argparse  # 실행 옵션
import sys  # 운영체제 판별, 종료 코드
import time  # 브라우저 모드 대기
import webbrowser  # 기본 브라우저 열기

from getip import config  # 창 제목·크기·배경색
from getip.web import server  # 로컬 서버


def os_prefers_dark() -> bool:
    """Windows가 앱 다크 모드인지. 확인할 수 없으면 False(라이트)."""
    if sys.platform != "win32":  # Windows가 아니면
        return False  # 라이트로 간주
    try:
        import winreg  # Windows 레지스트리 (Windows에서만 존재)

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")  # 개인 설정 키
        with key:  # 사용 후 닫기
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")  # 0 = 다크, 1 = 라이트
        return value == 0  # 다크 여부
    except OSError:  # 키가 없는 오래된 Windows 등
        return False  # 라이트로 간주


def window_background(theme: str) -> str:
    """창이 처음 그려질 때의 배경색. 화면 바탕(--bg)과 같게 해 흰 화면 깜빡임을 막는다."""
    if theme == "system":  # OS 설정 따름
        theme = "dark" if os_prefers_dark() else "light"  # 레지스트리로 판단
    return config.WINDOW_BG.get(theme, config.WINDOW_BG["light"])  # 테마별 색


def run_browser(running: server.RunningServer) -> None:
    """기본 브라우저로 화면을 열고 Ctrl+C까지 서버를 유지한다."""
    print(f"getIP 화면: {running.url}  (종료: Ctrl+C)")  # 주소 안내
    webbrowser.open(running.url)  # 브라우저 탭 열기
    try:
        while True:  # 서버 스레드가 일하는 동안
            time.sleep(1)  # 주 스레드는 대기
    except KeyboardInterrupt:  # Ctrl+C
        pass  # 정상 종료로 진행


def run_window(running: server.RunningServer) -> None:
    """pywebview 창으로 화면을 연다. 창을 닫으면 돌아온다."""
    import webview  # 창 라이브러리 (브라우저 모드에서는 필요 없으므로 여기서 불러옴)

    width, height = config.WINDOW_SIZE  # 기본 크기
    webview.create_window(
        config.WINDOW_TITLE,  # 창 제목
        running.url,  # 로컬 서버 화면
        width=width,  # 가로
        height=height,  # 세로
        min_size=(720, 480),  # 너무 작게 줄이지 못하게
        background_color=window_background(running.settings.theme()),  # 첫 배경색
    )  # 창 등록
    webview.start(private_mode=True)  # 창 실행 (닫힐 때까지 대기). 쿠키·저장소를 디스크에 남기지 않음


def main(argv=None) -> int:
    """실행 옵션을 읽고 서버와 화면을 띄운다. 종료 코드를 돌려준다."""
    parser = argparse.ArgumentParser(prog="getip.desktop", description="getIP 지도 화면")  # 옵션 정의
    parser.add_argument("--browser", action="store_true", help="전용 창 대신 기본 브라우저로 열기 (개발용)")  # 브라우저 모드
    args = parser.parse_args(argv)  # 옵션 읽기

    try:
        running = server.start()  # 로컬 서버 시작 (127.0.0.1, 임의 포트)
    except RuntimeError as exc:  # 시작 실패
        print(f"[!] {exc}", file=sys.stderr)  # 사유 출력
        return 1  # 실패 코드
    try:
        if args.browser:  # 개발 모드
            run_browser(running)  # 브라우저 탭
        else:  # 기본
            run_window(running)  # 전용 창
    finally:
        running.stop()  # 창을 닫거나 Ctrl+C를 누르면 서버도 종료
    return 0  # 정상 종료


if __name__ == "__main__":  # 직접 실행된 경우에만
    sys.exit(main())  # 종료 코드 전달
