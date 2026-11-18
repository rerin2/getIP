// 아래 상세 패널. 조회 결과 하나를 항목: 값 표로 보여준다. 외부 문자열은 textContent로만 넣는다.

import { shortTime } from './history.js'; // 시각 표시
import { renderProbeSection } from './probe.js'; // 지연 측정·경로 추적 부분

// 값이 비었으면 '-' 표시
function text(value) {
  return value === null || value === undefined || value === '' ? '-' : String(value); // 빈 값 대체
}

// <dl>에 항목 하나 추가. value가 Node면 그대로 넣는다
function addRow(dl, label, value) {
  const dt = document.createElement('dt'); // 항목 이름
  dt.textContent = label; // 글자로
  const dd = document.createElement('dd'); // 값
  if (value instanceof Node) dd.append(value); // 버튼 등 요소
  else dd.textContent = text(value); // 일반 글자
  dl.append(dt, dd); // 추가
}

// 다른 IP 목록: 지금 IP는 글자, 나머지는 누르면 그 IP로 다시 조회하는 버튼
function otherIps(result, onPickIp) {
  const box = document.createElement('span'); // 묶음
  result.all_ips.forEach((ip, i) => {
    if (i > 0) box.append(' '); // 사이 띄어쓰기
    if (ip === result.ip) {
      const cur = document.createElement('strong'); // 현재 IP
      cur.textContent = ip; // 글자
      box.append(cur); // 추가
      return; // 다음
    }
    const btn = document.createElement('button'); // 다른 IP
    btn.type = 'button'; // 폼 전송 아님
    btn.className = 'link'; // 링크 모양
    btn.textContent = ip; // 글자
    btn.title = '이 IP로 조회'; // 설명
    btn.addEventListener('click', () => onPickIp(result.target.raw, ip)); // 같은 입력, 다른 IP
    box.append(btn); // 추가
  });
  return box; // 완성
}

// el: 패널 본문, result: 조회 결과 JSON, onPickIp(target, ip): 다른 IP 선택 시
// probe: {handlers: {onLatency, onTrace, onStopTrace}, state: {latencyBusy, tracing}, factors} — 없으면 측정 부분 생략
export function renderDetail(el, result, { onPickIp, probe }) {
  const geo = result.geo || {}; // 위치 정보가 없으면 빈 객체
  const dl = document.createElement('dl'); // 표
  dl.className = 'detail-grid'; // 2열×2 배치

  addRow(dl, '대상', result.target.host); // 정리된 호스트
  addRow(dl, 'IP', result.all_ips.length > 1 ? otherIps(result, onPickIp) : result.ip); // IP (여러 개면 고르기)
  addRow(dl, '국가', geo.country ? `${geo.country}${geo.country_code ? ` (${geo.country_code})` : ''}` : null); // 국가와 코드
  addRow(dl, '도시', geo.city); // 도시
  addRow(dl, 'ISP', geo.isp); // 인터넷 사업자
  addRow(dl, '조직', geo.org); // 조직
  addRow(dl, 'ASN', geo.asn); // AS 번호
  addRow(dl, '호스팅', geo.is_hosting == null ? null : geo.is_hosting ? '예 (데이터센터 대역)' : '아니오'); // 데이터센터 여부
  addRow(dl, '좌표', geo.lat == null ? null : `${geo.lat}, ${geo.lon}`); // 위도, 경도
  addRow(dl, '역방향 DNS', result.reverse_dns); // PTR 이름
  addRow(dl, '조회 시각', shortTime(result.created_at)); // 언제
  addRow(dl, '입력', result.target.raw); // 입력 원문

  const parts = [dl]; // 패널에 넣을 요소들
  if (result.warnings && result.warnings.length) {
    const box = document.createElement('div'); // 경고 상자
    box.className = 'warnings'; // 노란 바탕
    const ul = document.createElement('ul'); // 목록
    for (const w of result.warnings) {
      const li = document.createElement('li'); // 한 줄
      li.textContent = w; // 서버가 준 사유
      ul.append(li); // 추가
    }
    box.append(ul); // 조립
    parts.push(box); // 추가
  }
  if (probe) parts.push(renderProbeSection(result, probe.handlers, probe.state, probe.factors)); // 측정 버튼·결과
  const note = document.createElement('p'); // 한계·전달 안내 (설계 5절)
  note.className = 'note'; // 작은 글자
  note.textContent = '위치는 ip-api.com 데이터베이스 기준이라 실제 서버 위치와 다를 수 있습니다(CDN은 접속 지점 위치). 조회한 IP는 ip-api.com에 암호화되지 않은 채 전달됩니다.'; // 안내 문구
  parts.push(note); // 추가

  el.replaceChildren(...parts); // 패널 교체
}

// "상세 조회" 버튼 (일반 조회를 실행하고 기록에 남김)
function lookupButton(ip, onLookup) {
  const btn = document.createElement('button'); // 버튼
  btn.type = 'button'; // 폼 전송 아님
  btn.className = 'primary'; // 주 버튼 모양
  btn.textContent = '상세 조회'; // 글자
  btn.title = `${ip}를 조회하고 기록에 남깁니다`; // 설명
  btn.addEventListener('click', () => onLookup(ip)); // 실행
  return btn; // 완성
}

// 연결 하나의 상세. program: 묶음, conn: 연결, onLookup(ip): 상세 조회
export function renderConnectionDetail(el, program, conn, { onLookup }) {
  const geo = conn.geo || {}; // 위치 (없으면 빈 객체)
  const dl = document.createElement('dl'); // 표
  dl.className = 'detail-grid'; // 배치
  addRow(dl, '프로그램', program.name); // 이름
  addRow(dl, 'PID', conn.pid); // 프로세스 ID
  addRow(dl, '경로', program.exe_path); // 실행 파일
  addRow(dl, '상태', conn.closed ? '종료됨 (이전 수집 이후 사라짐)' : conn.status); // 연결 상태
  addRow(dl, '원격 주소', `${conn.remote_ip}:${conn.remote_port}`); // 상대
  addRow(dl, '로컬 포트', conn.local_port); // 내 쪽
  addRow(dl, '국가', geo.country ? `${geo.country}${geo.country_code ? ` (${geo.country_code})` : ''}` : (conn.is_public ? null : '사설망')); // 국가
  addRow(dl, '도시', geo.city); // 도시
  addRow(dl, 'ISP', geo.isp); // 사업자
  addRow(dl, '조직', geo.org); // 조직
  addRow(dl, 'ASN', geo.asn); // AS 번호
  addRow(dl, '호스팅', geo.is_hosting == null ? null : geo.is_hosting ? '예 (데이터센터 대역)' : '아니오'); // 데이터센터 여부

  const parts = [dl]; // 패널 내용
  if (conn.is_public) parts.push(lookupButton(conn.remote_ip, onLookup)); // 공인 IP만 상세 조회 가능
  const note = document.createElement('p'); // 안내
  note.className = 'note'; // 작은 글자
  note.textContent = '목록의 위치는 DB 조회만 한 값입니다. [상세 조회]를 누르면 역방향 DNS 등 일반 조회를 실행하고 기록에 남깁니다.'; // 안내 문구
  parts.push(note); // 추가
  el.replaceChildren(...parts); // 패널 교체
}

// 지도에서 좌표 묶음을 누른 경우: 그곳의 연결 목록. spot: {items:[{program, conn}]}, onPick(program, conn)
export function renderSpotDetail(el, spot, { onPick }) {
  const geo = spot.items[0].conn.geo || {}; // 대표 위치
  const head = document.createElement('p'); // 제목 줄
  head.textContent = `${[geo.city, geo.country].filter(Boolean).join(', ') || '위치'} — 연결 ${spot.items.length}개`; // 위치와 개수
  const ul = document.createElement('ul'); // 목록
  ul.className = 'spot-list'; // 모양
  for (const { program, conn } of spot.items) {
    const li = document.createElement('li'); // 한 줄
    const btn = document.createElement('button'); // 누르면 그 연결 상세
    btn.type = 'button'; // 폼 전송 아님
    btn.className = 'link'; // 링크 모양
    btn.textContent = `${program.name} → ${conn.remote_ip}:${conn.remote_port}`; // 프로그램과 주소
    btn.addEventListener('click', () => onPick(program, conn)); // 선택
    const isp = document.createElement('span'); // 사업자
    isp.className = 'muted'; // 흐린 글자
    isp.textContent = conn.geo && conn.geo.isp ? ` ${conn.geo.isp}` : ''; // 있을 때만
    li.append(btn, isp); // 조립
    ul.append(li); // 추가
  }
  el.replaceChildren(head, ul); // 패널 교체
}

// '내 IP' 상세: 내 IP 정보와 지금 쓰는 내 위치, 지도에서 지정·되돌리기 버튼 (D13).
// me: /api/me 응답 {geo, origin, error}, onPick(): 지도에서 지정, onReset(): 자동 위치로
export function renderMeDetail(el, me, { onPick, onReset }) {
  const geo = me.geo || {}; // ip-api 정보 (실패하면 빈 객체)
  const origin = me.origin; // 지금 쓰는 위치
  const dl = document.createElement('dl'); // 표
  dl.className = 'detail-grid'; // 배치
  addRow(dl, '내 IP', geo.ip); // 공인 IP
  addRow(dl, 'ISP', geo.isp); // 사업자
  addRow(dl, 'IP 위치', geo.lat == null ? null : `${[geo.city, geo.country].filter(Boolean).join(', ')} (${geo.lat}, ${geo.lon})`); // ip-api 위치
  let using = '모름'; // 사용 중인 위치 글자
  if (origin) using = origin.source === 'manual' ? `직접 지정 (${origin.lat.toFixed(4)}, ${origin.lon.toFixed(4)})` : 'IP 위치 사용'; // 출처
  addRow(dl, '사용 중인 위치', using); // 반경 원·경로선 시작점

  const bar = document.createElement('div'); // 버튼 줄
  bar.className = 'probe-bar'; // 모양
  const pick = document.createElement('button'); // 지정 버튼
  pick.type = 'button'; // 폼 전송 아님
  pick.className = 'primary'; // 주 버튼
  pick.textContent = '지도에서 내 위치 지정'; // 글자
  pick.addEventListener('click', onPick); // 동작
  const reset = document.createElement('button'); // 되돌리기 버튼
  reset.type = 'button'; // 폼 전송 아님
  reset.textContent = '자동 위치로 되돌리기'; // 글자
  reset.disabled = !origin || origin.source !== 'manual'; // 직접 지정했을 때만
  reset.addEventListener('click', onReset); // 동작
  bar.append(pick, reset); // 조립

  const parts = [dl, bar]; // 패널 내용
  if (me.error) {
    const box = document.createElement('div'); // 경고
    box.className = 'warnings'; // 노란 바탕
    box.textContent = `내 IP 조회 실패: ${me.error}`; // 사유
    parts.push(box); // 추가
  }
  const note = document.createElement('p'); // 안내
  note.className = 'note'; // 작은 글자
  note.textContent = '지연 반경 원과 경로선은 이 위치에서 시작합니다. IP 위치는 통신사 장비 기준이라 실제 위치와 수십 km 이상 다를 수 있으니, 다르면 지도에서 직접 지정하세요. 지정한 위치는 이 PC의 기록 DB에만 저장됩니다.'; // 안내 문구
  parts.push(note); // 추가
  el.replaceChildren(...parts); // 패널 교체
}
