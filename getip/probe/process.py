"""외부 명령(ping, tracert) 실행에 공통으로 쓰는 옵션."""

import subprocess  # 프로세스 생성 플래그
import sys  # 운영체제 확인


def no_window_flags() -> int:
    """Windows에서 콘솔 창 없이 실행하는 플래그. GUI(pywebview) 실행 중 검은 창이 깜빡이지 않게 한다."""
    if sys.platform == "win32":  # Windows인 경우
        return subprocess.CREATE_NO_WINDOW  # 콘솔 창을 만들지 않음
    return 0  # 다른 운영체제는 해당 없음
