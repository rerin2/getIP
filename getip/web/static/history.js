// 왼쪽 기록 목록. 외부 문자열은 모두 textContent로만 넣는다.

// ISO 시각을 짧은 현지 시각 문자열로
export function shortTime(iso) {
  const d = new Date(iso); // 문자열 → 날짜
  if (Number.isNaN(d.getTime())) return ''; // 잘못된 값
  return d.toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); // 월/일 시:분
}

// listEl: <ul>, items: /api/history 항목, selectedId: 강조할 번호, handlers: {onSelect(id), onDelete(id)}
export function renderHistory(listEl, items, selectedId, { onSelect, onDelete }) {
  listEl.replaceChildren(); // 기존 항목 비우기
  if (items.length === 0) {
    const li = document.createElement('li'); // 빈 목록 안내
    li.className = 'empty'; // 흐린 글자
    li.textContent = '기록이 없습니다.'; // 안내 문구
    listEl.append(li); // 추가
    return; // 끝
  }
  for (const item of items) {
    const li = document.createElement('li'); // 한 줄
    if (item.id === selectedId) li.classList.add('selected'); // 현재 보고 있는 기록 강조

    const main = document.createElement('button'); // 누르면 다시 보기
    main.type = 'button'; // 폼 전송 아님
    main.className = 'item'; // 목록 항목 모양
    const name = document.createElement('span'); // 입력 원문
    name.className = 'name'; // 첫 줄
    name.textContent = item.input; // 사용자가 입력한 그대로
    const meta = document.createElement('span'); // IP · 위치 · 시각
    meta.className = 'meta'; // 둘째 줄
    meta.textContent = [item.ip, item.country, shortTime(item.created_at)].filter(Boolean).join(' · '); // 빈 값 제외
    main.append(name, meta); // 조립
    main.title = [item.host, item.ip, item.city, item.country, item.isp].filter(Boolean).join(' / '); // 마우스 올리면 자세히
    main.addEventListener('click', () => onSelect(item.id)); // 선택

    const remove = document.createElement('button'); // 한 건 삭제
    remove.type = 'button'; // 폼 전송 아님
    remove.className = 'remove'; // 작은 × 모양
    remove.textContent = '×'; // 기호
    remove.title = '이 기록 삭제'; // 설명
    remove.setAttribute('aria-label', '이 기록 삭제'); // 화면 낭독기용
    remove.addEventListener('click', () => onDelete(item.id)); // 삭제

    li.append(main, remove); // 조립
    listEl.append(li); // 목록에 추가
  }
}
