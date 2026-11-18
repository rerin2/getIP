// 상세 패널의 '측정' 부분: [지연 측정] [경로 추적] 버튼, 지연 결과, 홉 표. 외부 문자열은 textContent로만 넣는다.

import { geodesicRing } from './geodesic.js'; // 원을 그릴 수 있는지 확인

// 요소 하나 만들기 (글자는 textContent로)
function el(tag, className, text) {
  const node = document.createElement(tag); // 요소
  if (className) node.className = className; // 모양
  if (text !== undefined && text !== null) node.textContent = String(text); // 글자로만
  return node; // 완성
}

// 버튼 하나
function button(label, { primary = false, disabled = false, title = '', onClick }) {
  const btn = el('button', primary ? 'primary' : '', label); // 버튼
  btn.type = 'button'; // 폼 전송 아님
  btn.disabled = disabled; // 사용 가능 여부
  if (title) btn.title = title; // 설명
  btn.addEventListener('click', onClick); // 동작
  return btn; // 완성
}

// 1234 → "1,234 km"
function km(value) {
  return `${Math.round(value).toLocaleString('ko-KR')} km`; // 천 단위 쉼표
}

// 방법 이름을 화면 글자로
function methodLabel(method) {
  if (method === 'icmp') return 'ICMP (ping)'; // ping
  if (method === 'tcp') return 'TCP (443·80)'; // 모든 포트 실패
  return method.replace('tcp:', 'TCP '); // "tcp:443" → "TCP 443"
}

// 방법 하나의 결과 글자: "최소 31 ms · 4회 중 4회 응답"
function methodText(r) {
  const answered = r.samples_ms.length; // 응답 수
  if (r.min_ms == null) return `응답 없음 (${r.attempts}회 시도)`; // 전부 실패
  return `최소 ${r.min_ms} ms · ${r.attempts}회 중 ${answered}회 응답`; // 요약
}

// 출처 글자
function originText(origin) {
  if (!origin) return '모름 (반경 원을 그리지 못함)'; // 내 위치 조회 실패
  const where = `${origin.lat.toFixed(3)}, ${origin.lon.toFixed(3)}`; // 좌표
  return origin.source === 'manual' ? `직접 지정 (${where})` : `내 IP 위치 (${where})`; // 출처
}

// 지연 측정 결과 표
function latencyBlock(result, factors) {
  const box = el('div', 'probe-block'); // 묶음
  box.append(el('h4', '', '지연 측정')); // 제목
  const dl = el('dl', 'detail-grid'); // 표
  const row = (label, value) => dl.append(el('dt', '', label), el('dd', '', value)); // 한 줄 추가
  for (const r of result.latency.results) row(methodLabel(r.method), methodText(r)); // 방법별
  const view = result.latency_view || {}; // 서버 계산값
  if (view.min_ms != null) {
    const origin = result.latency.origin; // 원의 중심
    const tooBig = origin && !geodesicRing(origin.lat, origin.lon, view.typical_km); // 현실 원조차 지구 대부분을 덮음
    const hint = tooBig ? ' (지구 대부분을 덮어 지도에 원을 그리지 않음)' : ''; // 원이 안 보이는 이유
    row('반경', `현실 추정 ${km(view.typical_km)} 이내 · 물리적 상한 ${km(view.upper_km)}${hint}`); // 두 원
  }
  if (view.db_distance_km != null) {
    const beyond = view.db_beyond_upper ? ' — 물리적 상한 밖: DB 위치가 틀렸거나 여러 곳에서 응답하는 주소(애니캐스트)' : ''; // 모순 안내
    row('DB 위치까지', `${km(view.db_distance_km)}${beyond}`); // 측정 위치 → DB 위치
  }
  row('측정 위치', originText(result.latency.origin)); // 원의 중심
  row('측정 시각', new Date(result.latency.measured_at).toLocaleString('ko-KR')); // 언제
  box.append(dl); // 표 추가
  if (view.db_beyond_upper) {
    const warn = el('div', 'warnings', '지연이 너무 짧아 DB 위치에 있을 수 없습니다. 지도의 원 안쪽 어딘가에서 응답하고 있습니다.'); // 경고
    box.append(warn); // 추가
  }
  if (factors) {
    box.append(el('p', 'note', `옅은 점선 원: 빛이 광섬유로 갈 수 있는 최대 거리(1ms당 ${factors.fiber}km) — 이 밖은 불가능. `
      + `진한 원: 실측으로 정한 현실적 최대 거리(1ms당 ${factors.realistic}km) — 이 밖일 가능성은 낮음.`)); // 원 설명
  }
  return box; // 완성
}

// 경로 추적 상태 글자
function traceStatus(trace, tracing) {
  if (tracing) return `추적 중… 홉 ${trace.hops.length}개 확인`; // 진행 중
  if (trace.status === 'done') return `완료 — 홉 ${trace.hops.length}개`; // 정상
  return trace.message || `멈춤 (${trace.status})`; // 중지·무응답·오류
}

// 홉 표
function traceBlock(trace, tracing) {
  const box = el('div', 'probe-block'); // 묶음
  box.append(el('h4', '', '경로 추적'), el('p', 'muted small', traceStatus(trace, tracing))); // 제목, 상태
  const table = el('table', 'hops'); // 표
  const head = el('tr'); // 머리 줄
  for (const t of ['#', 'IP', '지연', '위치', '사업자']) head.append(el('th', '', t)); // 열 이름
  table.append(head); // 추가
  for (const hop of trace.hops) {
    const tr = el('tr', hop.ip ? '' : 'silent'); // 한 줄 (무응답은 흐리게)
    const geo = hop.geo || {}; // 위치
    const rtt = hop.rtt_ms == null ? '-' : `${hop.rtt_less_than ? '<' : ''}${hop.rtt_ms} ms`; // 지연
    const place = hop.ip ? ([geo.city, geo.country].filter(Boolean).join(', ') || '사설망·정보 없음') : '응답 없음'; // 위치
    for (const v of [hop.index, hop.ip || '*', rtt, place, geo.isp || '']) tr.append(el('td', '', v)); // 칸
    table.append(tr); // 추가
  }
  box.append(table); // 표 추가
  return box; // 완성
}

// 측정 부분 전체. handlers: {onLatency, onTrace, onStopTrace}, probe: {latencyBusy, tracing}, factors: {fiber, realistic}
export function renderProbeSection(result, handlers, probe, factors) {
  const section = el('section', 'probe'); // 묶음
  const saved = result.id != null; // 기록에 저장된 결과만 측정 가능 (결과를 덧붙일 곳)
  const why = saved ? '' : '기록에 저장되지 않은 결과라 측정할 수 없습니다.'; // 비활성 사유
  const bar = el('div', 'probe-bar'); // 버튼 줄
  bar.append(button(probe.latencyBusy ? '측정 중…' : '지연 측정', {
    disabled: !saved || probe.latencyBusy, title: why || 'TCP 연결과 ping으로 왕복 시간을 잽니다 (몇 초)', onClick: handlers.onLatency,
  })); // 지연 측정
  if (probe.tracing) {
    bar.append(button('추적 중지', { onClick: handlers.onStopTrace })); // 중지
  } else {
    bar.append(button('경로 추적', {
      disabled: !saved, title: why || '대상까지 거치는 장비를 차례로 확인합니다 (수십 초)', onClick: handlers.onTrace,
    })); // 추적
  }
  bar.append(el('span', 'muted small', '대상 서버에 직접 패킷을 보냅니다. 대상 로그에 내 IP가 남을 수 있습니다.')); // 능동 접속 안내 (설계 5절)
  section.append(bar); // 버튼 줄 추가
  if (result.latency) section.append(latencyBlock(result, factors)); // 지연 결과
  if (result.trace) section.append(traceBlock(result.trace, probe.tracing)); // 홉 표
  return section; // 완성
}
