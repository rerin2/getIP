"""CLI의 조회 기록 화면: 목록, 검색, 상세, 삭제."""

import sqlite3  # 저장소 오류 예외
from typing import Callable, List  # 타입 표기

from getip import config  # 한 번에 보여줄 건수
from getip.models import HistoryEntry, LookupResult  # 기록 데이터 클래스
from getip.storage.history import HistoryStore  # 기록 저장소

_HELP = "번호: 상세 | d 번호: 삭제 | clear: 전체 삭제 | /검색어: 검색 | /: 검색 해제 | Enter: 돌아가기"  # 명령 안내


def format_entry(entry: HistoryEntry) -> str:
    """기록 한 건을 목록의 한 줄로 만든다."""
    when = entry.created_at.astimezone().strftime("%Y-%m-%d %H:%M")  # 저장된 UTC 시각을 현지 시각으로
    place = " / ".join(part for part in (entry.country, entry.city) if part) or "-"  # 국가 / 도시 (없으면 -)
    return f"  #{entry.id:<4} {when}  {entry.host:<28} {entry.ip:<15}  {place:<28} {entry.isp or '-'}"  # 정렬된 한 줄


def _print_list(store: HistoryStore, query: str) -> List[HistoryEntry]:
    """기록 목록을 출력하고 출력한 항목을 돌려준다."""
    entries = store.list(query=query, limit=config.HISTORY_PAGE_SIZE)  # 최신순 목록
    title = f"검색 '{query}'" if query else f"전체 {store.count()}건 중 최근 {config.HISTORY_PAGE_SIZE}건까지"  # 목록 제목
    print(f"\n[기록] {title}")  # 제목 출력
    if not entries:  # 기록이 없으면
        print("  (기록이 없습니다)")  # 빈 목록 안내
    for entry in entries:  # 항목마다
        print(format_entry(entry))  # 한 줄 출력
    return entries  # 출력한 항목


def handle_history(store: HistoryStore, print_result: Callable[[LookupResult], None]) -> None:
    """기록 화면을 보여주고 Enter가 입력될 때까지 명령을 처리한다."""
    query = ""  # 현재 검색어
    try:
        _print_list(store, query)  # 처음 목록 출력
        while True:  # 돌아가기 전까지 반복
            command = input(f"{_HELP}\n> ").strip()  # 명령 입력
            if not command:  # Enter만 누르면
                return  # 메뉴로 복귀
            if command.startswith("/"):  # 검색 명령
                query = command[1:].strip()  # 슬래시 뒤가 검색어 (비면 검색 해제)
                _print_list(store, query)  # 목록 다시 출력
            elif command.lower() == "clear":  # 전체 삭제
                if input("모든 기록을 삭제합니다. 되돌릴 수 없습니다. 계속하려면 y: ").strip().lower() == "y":  # 확인
                    print(f"[*] {store.clear()}건을 삭제했습니다.")  # 삭제 결과
                    _print_list(store, query)  # 목록 다시 출력
                else:  # 확인하지 않으면
                    print("[*] 취소했습니다.")  # 취소 안내
            elif command.lower().startswith("d") and command[1:].strip().lstrip("#").isdigit():  # "d 3" 형태
                record_id = int(command[1:].strip().lstrip("#"))  # 지울 번호
                if store.delete(record_id):  # 삭제 성공
                    print(f"[*] 기록 #{record_id} 을 삭제했습니다.")  # 결과 안내
                    _print_list(store, query)  # 목록 다시 출력
                else:  # 해당 번호 없음
                    print(f"[!] 기록 #{record_id} 이 없습니다.")  # 실패 안내
            elif command.lstrip("#").isdigit():  # 번호만 입력 → 상세 보기
                result = store.get(int(command.lstrip("#")))  # 기록 조회
                if result is None:  # 해당 번호 없음
                    print(f"[!] 기록 #{command.lstrip('#')} 이 없습니다.")  # 실패 안내
                else:  # 기록이 있으면
                    when = result.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")  # 현지 시각
                    print(f"\n[기록 #{result.id}] {when} | 입력: {result.target.raw}")  # 머리말
                    print_result(result)  # 조회 당시 결과 그대로 출력
            else:  # 알 수 없는 명령
                print("[!] 알 수 없는 명령입니다.")  # 안내
    except (sqlite3.Error, OSError) as exc:  # DB를 읽거나 쓸 수 없는 경우
        print(f"[!] 기록 저장소 오류: {exc}")  # 원인 안내 후 메뉴로 복귀
