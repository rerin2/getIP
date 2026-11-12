"""`python -m getip` 실행 진입점."""

from getip.cli.main import main  # 대화형 CLI 시작 함수

if __name__ == "__main__":  # 모듈로 직접 실행된 경우에만
    main()  # CLI 실행
