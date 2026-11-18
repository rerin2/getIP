// "프로그램 연결" 탭의 목록 그리기와 좌표별 묶기. 외부 문자열은 모두 textContent로만 넣는다.

// 프로그램 묶음을 구분하는 값 (새로고침해도 같은 프로그램이면 같은 값)
export function programKey(program) {
  return `${program.name}|${program.exe_path || ''}`; // 이름 + 경로
}

// 연결 하나를 구분하는 값 (서버의 Connection.key와 같은 구성)
export function connKey(conn) {
  return `${conn.pid}|${conn.local_port}|${conn.remote_ip}|${conn.remote_port}`; // 프로세스 + 양 끝 주소
}

// 위치 문자열 "국가코드 도시"
export function shortPlace(geo) {
  if (!geo) return ''; // 위치 없음
  return [geo.country_code || geo.country, geo.city].filter(Boolean).join(' '); // 빈 값 제외
}

// 같은 좌표의 연결을 하나로 묶는다 (Cloudflare처럼 여러 IP가 한 곳으로 나오는 경우). [{lat, lon, items:[{program, conn}]}]
export function groupByLocation(snapshot) {
  const spots = new Map(); // 좌표 문자열 → 묶음
  for (const program of snapshot.programs) {
    for (const conn of program.connections) {
      const geo = conn.geo; // 위치
      if (!geo || geo.lat == null || geo.lon == null) continue; // 좌표 없는 연결은 지도에서 제외
      const key = `${geo.lat.toFixed(3)},${geo.lon.toFixed(3)}`; // 약 100m 단위로 같은 곳 판정
      if (!spots.has(key)) spots.set(key, { lat: geo.lat, lon: geo.lon, items: [] }); // 새 묶음
      spots.get(key).items.push({ program, conn }); // 연결 추가
    }
  }
  return [...spots.values()]; // 묶음 목록
}

// 상태 표시 (종료됨 / 종료 중 상태 이름)
function statusText(conn) {
  if (conn.closed) return '종료됨'; // 이전 수집 이후 사라짐
  return conn.status === 'ESTABLISHED' ? '' : conn.status; // 수립 상태는 생략
}

// 연결 한 줄 버튼
function connRow(program, conn, ui, handlers) {
  const li = document.createElement('li'); // 줄
  const btn = document.createElement('button'); // 누르면 상세
  btn.type = 'button'; // 폼 전송 아님
  btn.className = 'conn'; // 모양
  if (conn.closed) btn.classList.add('closed'); // 종료됨 표시
  if (ui.selectedConn === connKey(conn)) btn.classList.add('selected'); // 선택 강조
  const addr = document.createElement('span'); // 주소
  addr.className = 'addr'; // 고정폭 글꼴
  addr.textContent = `${conn.remote_ip}:${conn.remote_port}`; // IP:포트
  const place = document.createElement('span'); // 위치·상태
  place.className = 'muted'; // 흐린 글자
  place.textContent = [shortPlace(conn.geo) || (conn.is_public ? '조회 대기' : '사설망'), statusText(conn)].filter(Boolean).join(' · '); // 위치와 상태
  btn.append(addr, place); // 조립
  btn.title = conn.geo ? [conn.geo.isp, conn.geo.org].filter(Boolean).join(' / ') : ''; // 마우스 올리면 사업자
  btn.addEventListener('click', () => handlers.onSelectConn(program, conn)); // 선택
  li.append(btn); // 추가
  return li; // 완성
}

// listEl: <ul>, snapshot: /api/connections 응답, ui: {expanded:Set, selectedProgram, selectedConn}
// handlers: {onToggleProgram(program), onSelectConn(program, conn)}
export function renderConnections(listEl, snapshot, ui, handlers) {
  listEl.replaceChildren(); // 비우기
  if (snapshot.programs.length === 0) {
    const li = document.createElement('li'); // 빈 목록 안내
    li.className = 'empty'; // 흐린 글자
    li.textContent = '표시할 연결이 없습니다.'; // 안내
    listEl.append(li); // 추가
    return; // 끝
  }
  for (const program of snapshot.programs) {
    const key = programKey(program); // 묶음 구분값
    const open = ui.expanded.has(key); // 펼침 여부
    const li = document.createElement('li'); // 프로그램 줄
    if (ui.selectedProgram === key) li.classList.add('selected'); // 선택 강조

    const head = document.createElement('button'); // 프로그램 이름 버튼
    head.type = 'button'; // 폼 전송 아님
    head.className = 'prog'; // 모양
    head.title = program.exe_path || ''; // 마우스 올리면 경로
    const caret = document.createElement('span'); // ▸/▾
    caret.className = 'caret'; // 흐린 기호
    caret.textContent = open ? '▾' : '▸'; // 펼침 표시
    const name = document.createElement('span'); // 이름
    name.className = 'name'; // 굵게
    name.textContent = program.name; // 프로그램 이름
    const count = document.createElement('span'); // 연결 수
    count.className = 'muted'; // 흐린 글자
    count.textContent = `(${program.connections.length})`; // 개수
    head.append(caret, name, count); // 조립
    head.addEventListener('click', () => handlers.onToggleProgram(program)); // 펼치기 + 강조
    li.append(head); // 추가

    if (open) {
      const sub = document.createElement('ul'); // 연결 목록
      for (const conn of program.connections) sub.append(connRow(program, conn, ui, handlers)); // 연결마다
      li.append(sub); // 추가
    }
    listEl.append(li); // 목록에 추가
  }
}
