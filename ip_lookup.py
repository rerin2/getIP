"""기존 실행 방식(python ip_lookup.py, ip_lookup.spec 빌드)을 유지하기 위한 진입점."""

from getip.cli.main import main  # 실제 로직은 getip 패키지에 있음

if __name__ == "__main__":  # 직접 실행된 경우에만
    main()  # 대화형 CLI 시작
