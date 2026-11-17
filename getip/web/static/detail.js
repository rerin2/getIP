// 아래 상세 패널. 조회 결과 하나를 항목: 값 표로 보여준다. 외부 문자열은 textContent로만 넣는다.

import { shortTime } from './history.js'; // 시각 표시

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
export function renderDetail(el, result, { onPickIp }) {
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
  const note = document.createElement('p'); // 한계·전달 안내 (설계 5절)
  note.className = 'note'; // 작은 글자
  note.textContent = '위치는 ip-api.com 데이터베이스 기준이라 실제 서버 위치와 다를 수 있습니다(CDN은 접속 지점 위치). 조회한 IP는 ip-api.com에 암호화되지 않은 채 전달됩니다.'; // 안내 문구
  parts.push(note); // 추가

  el.replaceChildren(...parts); // 패널 교체
}
