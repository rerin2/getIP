// 화면 진입점: 부품(지도, 기록, 상세, 테마, 설정)을 연결한다.

import { api, apiStream } from './api.js'; // 로컬 API (일반, 줄 단위 스트림)
import { connKey, groupByLocation, programKey, renderConnections } from './connections.js'; // 프로그램 연결 목록
import { renderConnectionDetail, renderDetail, renderMeDetail, renderSpotDetail } from './detail.js'; // 상세 패널
import { renderHistory } from './history.js'; // 기록 목록
import { GeoMap } from './map.js'; // 지도
import { openSettings } from './settings.js'; // 설정 대화상자
import { cycleTheme, effectiveTheme, onThemeChange, syncFromSettings, themeLabel } from './theme.js'; // 테마

const $ = (id) => document.getElementById(id); // 요소 찾기 줄임
const targetInput = $('target'); // 입력창
const lookupBtn = $('btn-lookup'); // 조회 버튼
const meBtn = $('btn-me'); // 내 IP 버튼
const themeBtn = $('btn-theme'); // 테마 버튼
const statusEl = $('status'); // 상태 줄
const detailEl = $('detail-body'); // 상세 본문
const noticeEl = $('map-notice'); // 지도 위 안내
const historyList = $('history-list'); // 기록 목록
const historySearch = $('history-search'); // 기록 검색
const historyCount = $('history-count'); // 기록 건수
const connList = $('conn-list'); // 연결 목록
const connCount = $('conn-count'); // 연결 수 (탭 글자)
const connTime = $('conn-time'); // 마지막 수집 시각
const connAuto = $('conn-auto'); // 자동 새로고침 체크
const connPrivate = $('conn-private'); // 사설 IP 표시 체크
const connClosing = $('conn-closing'); // 종료·종료 중 연결 표시 체크
const connRefreshBtn = $('btn-conn-refresh'); // 새로고침 버튼

const state = {
  settings: null, // /api/settings 응답
  selectedId: null, // 지금 보고 있는 기록 번호
  busy: false, // 조회 중 여부 (중복 클릭 방지)
  tab: 'history', // 지금 보이는 왼쪽 탭
  conn: null, // 마지막 /api/connections 응답
  connBusy: false, // 수집 중 여부
  connTimer: null, // 자동 새로고침 타이머
  connUi: { expanded: new Set(), selectedProgram: null, selectedConn: null }, // 펼친 프로그램, 선택 상태 (새로고침해도 유지)
  lastResult: null, // 기록 탭에서 마지막으로 본 조회 결과 (탭을 돌아오면 다시 표시)
  probe: { latencyBusy: false, tracing: false }, // 지연 측정·경로 추적 진행 상태 (버튼 모양)
  tracingId: null, // 추적 중인 기록 번호 (다른 기록을 보는 중이면 화면 갱신 생략)
  me: null, // 마지막 /api/me 응답
};

let map = null; // GeoMap (설정을 읽은 뒤 생성)

// 상태 줄에 문구 표시. isError면 빨간 글자
function setStatus(message, isError = false) {
  statusEl.textContent = message || ''; // 글자로만
  statusEl.classList.toggle('error', isError); // 오류 색
}

// 지도 위 안내 (키 없음, 위치 없음 등). 빈 문구면 숨김
function setNotice(message) {
  noticeEl.textContent = message || ''; // 글자로만
  noticeEl.hidden = !message; // 문구가 없으면 숨김
}

// 지도 타일 안내: 키가 없으면 알려 줌
function tileNotice() {
  return state.settings && !state.settings.tiles ? '지도 키가 없어 배경 지도가 표시되지 않습니다. [설정]에서 CARTO 키를 입력하세요.' : ''; // 키 없음 안내
}

// 설정 반영: 지도 타일, 테마, 저장소 경고
function applySettings(settings) {
  state.settings = settings; // 기억
  syncFromSettings(settings); // 테마 맞춤
  themeBtn.textContent = themeLabel(); // 버튼 글자
  map.setTileUrls(settings.tiles); // 타일 교체 (없으면 바탕만)
  setNotice(tileNotice()); // 키 안내
  if (settings.storage_warning) setStatus(settings.storage_warning, true); // 기록 저장소 문제
}

// 기록 목록 다시 불러오기
async function loadHistory() {
  try {
    const data = await api(`/api/history?limit=200&q=${encodeURIComponent(historySearch.value.trim())}`); // 최신 200건
    historyCount.textContent = `${data.total}건`; // 전체 건수
    renderHistory(historyList, data.items, state.selectedId, { onSelect: openRecord, onDelete: deleteRecord }); // 그리기
  } catch (e) {
    setStatus(`기록을 불러오지 못했습니다: ${e.message}`, true); // 실패 안내
  }
}

// 상세 패널 옵션: 다른 IP 선택 + 측정 버튼
function detailOptions() {
  const s = state.settings || {}; // 서버 설정 (원 설명용 계수)
  return {
    onPickIp: runLookup, // 다른 IP로 다시 조회
    probe: {
      handlers: { onLatency: measureLatency, onTrace: startTrace, onStopTrace: stopTrace }, // 버튼 동작
      state: state.probe, // 진행 상태
      factors: { fiber: s.fiber_km_per_ms, realistic: s.realistic_km_per_ms }, // 원 설명 글자
    },
  };
}

// 지금 보는 결과로 상세 패널만 다시 그림 (측정 상태가 바뀐 경우)
function redrawDetail() {
  if (state.tab === 'history' && state.lastResult) renderDetail(detailEl, state.lastResult, detailOptions()); // 기록 탭에서만
}

// 조회 결과 하나를 지도·상세에 표시
function showResult(result) {
  state.lastResult = result; // 탭 전환 후 다시 보여주기 위해 기억
  state.selectedId = result.id; // 강조할 기록
  renderDetail(detailEl, result, detailOptions()); // 상세 패널
  const shown = map.showResult(result); // 지도 마커
  map.showProbe(result); // 저장된 반경 원·경로 (없으면 지움)
  setNotice(shown ? tileNotice() : '이 IP는 위치 정보가 없어 지도에 표시하지 않았습니다.'); // 좌표 없음 안내
}

// --- 지연 측정·경로 추적 (D12: 버튼을 눌렀을 때만) ---

// [지연 측정]: 서버가 TCP·ping으로 재고 기록에 덧붙인 결과를 받아 다시 표시
async function measureLatency() {
  const id = state.lastResult && state.lastResult.id; // 대상 기록
  if (id == null || state.probe.latencyBusy) return; // 저장 안 된 결과, 측정 중이면 무시
  state.probe.latencyBusy = true; // 시작
  redrawDetail(); // 버튼을 '측정 중'으로
  setStatus('지연 측정 중… (몇 초 걸립니다)'); // 안내
  try {
    const result = await api(`/api/lookup/${id}/latency`, { method: 'POST' }); // 측정 + 저장
    if (state.lastResult && state.lastResult.id === id) showResult(result); // 그 사이 다른 기록을 열지 않았으면 표시
    const v = result.latency_view; // 요약
    setStatus(v && v.min_ms != null ? `지연 최소 ${v.min_ms} ms` : '응답이 없어 지연을 재지 못했습니다 (방화벽이 막았을 수 있음).', !(v && v.min_ms != null)); // 결과 안내
  } catch (e) {
    setStatus(`지연 측정 실패: ${e.message}`, true); // 실패 사유
  } finally {
    state.probe.latencyBusy = false; // 끝
    redrawDetail(); // 버튼 복구
  }
}

// [경로 추적]: 홉이 도착할 때마다 표와 지도를 갱신. 끝나면 서버가 기록에 저장 (D15)
async function startTrace() {
  const id = state.lastResult && state.lastResult.id; // 대상 기록
  if (id == null || state.probe.tracing) return; // 저장 안 된 결과, 이미 추적 중이면 무시
  const working = { origin: null, hops: [], status: 'running', message: null }; // 진행 중 결과 (서버 형식과 같음)
  state.probe.tracing = true; // 시작
  state.tracingId = id; // 추적 대상 기억
  const viewing = () => state.tab === 'history' && state.lastResult && state.lastResult.id === id; // 그 기록을 보고 있는지
  const draw = () => {
    if (!viewing()) return; // 다른 화면이면 갱신 생략 (서버는 계속 추적·저장)
    state.lastResult.trace = working; // 지금 결과에 반영
    map.showTrace(working.origin, working.hops); // 지도 경로
    redrawDetail(); // 홉 표
  };
  draw(); // 빈 표 + '추적 중지' 버튼
  setStatus('경로 추적 중… 홉마다 최대 3초씩 기다립니다.'); // 안내
  try {
    await apiStream(`/api/lookup/${id}/trace`, (event) => {
      if (event.type === 'start') working.origin = event.origin; // 시작점
      if (event.type === 'hop') {
        const at = working.hops.findIndex((h) => h.index === event.hop.index); // 같은 번호가 있으면 위치 갱신
        if (at >= 0) working.hops[at] = event.hop; // 교체
        else working.hops.push(event.hop); // 새 홉
      }
      if (event.type === 'done') Object.assign(working, event.report); // 최종 결과 (상태·안내 문구)
      draw(); // 다시 그림
    });
    setStatus(working.status === 'done' ? '' : working.message || '', working.status === 'error'); // 멈춘 사유
  } catch (e) {
    setStatus(`경로 추적 실패: ${e.message}`, true); // 시작 전 거부 (IPv6 등) 또는 연결 끊김
    if (viewing() && !working.hops.length) state.lastResult.trace = null; // 아무것도 못 받았으면 빈 표 제거
  } finally {
    state.probe.tracing = false; // 끝
    state.tracingId = null; // 비움
    redrawDetail(); // 버튼 복구
  }
}

// [추적 중지]: 서버가 추적을 멈추면 스트림이 'stopped'로 끝난다
async function stopTrace() {
  try {
    await api('/api/trace/stop', { method: 'POST' }); // 중지 요청
  } catch (e) {
    setStatus(`중지 실패: ${e.message}`, true); // 실패 사유
  }
}

// 조회 실행 (target: 입력, ip: 여러 IP 중 고른 것)
async function runLookup(target, ip) {
  const text = (target || '').trim(); // 앞뒤 공백 제거
  if (!text || state.busy) return; // 빈 입력, 조회 중이면 무시
  state.busy = true; // 조회 시작
  lookupBtn.disabled = true; // 중복 클릭 방지
  setStatus(`${text} 조회 중…`); // 진행 안내
  try {
    const result = await api('/api/lookup', { method: 'POST', body: ip ? { target: text, ip } : { target: text } }); // 조회
    showResult(result); // 표시
    setStatus(result.all_ips.length > 1 ? `IP ${result.all_ips.length}개 중 ${result.ip}를 조회했습니다. 다른 IP는 상세의 IP 항목에서 고를 수 있습니다.` : ''); // 여러 IP 안내
    await loadHistory(); // 새 기록 반영
  } catch (e) {
    setStatus(e.message, true); // 실패 사유
  } finally {
    state.busy = false; // 조회 끝
    lookupBtn.disabled = false; // 버튼 복구
  }
}

// 기록 한 건 다시 보기 (다시 조회하지 않고 저장된 결과를 표시)
async function openRecord(id) {
  try {
    const result = await api(`/api/history/${id}`); // 저장된 결과
    showResult(result); // 표시
    setStatus(''); // 상태 지움
    await loadHistory(); // 강조 갱신
  } catch (e) {
    setStatus(e.message, true); // 실패 사유
  }
}

// 기록 한 건 삭제
async function deleteRecord(id) {
  try {
    await api(`/api/history/${id}`, { method: 'DELETE' }); // 삭제
    if (state.selectedId === id) state.selectedId = null; // 보고 있던 기록이면 강조 해제
    await loadHistory(); // 목록 갱신
  } catch (e) {
    setStatus(e.message, true); // 실패 사유
  }
}

// 내 공인 IP와 내 위치를 지도에 표시. showDetail이면 상세 패널에 '내 위치' 화면을 띄움
async function loadMe(showDetail = false) {
  meBtn.disabled = true; // 중복 클릭 방지
  try {
    const me = await api('/api/me'); // 내 IP 조회 + 사용 중인 위치
    state.me = me; // 기억
    map.showMe(me); // 지도에 표시
    if (me.geo) meBtn.title = `내 IP: ${me.geo.ip}`; // 마우스 올리면 IP
    if (me.error && !me.origin) setStatus(`내 위치를 가져오지 못했습니다: ${me.error}`, true); // 위치를 전혀 모름
    if (showDetail) renderMeDetail(detailEl, me, { onPick: pickMyLocation, onReset: resetMyLocation }); // 내 위치 화면
  } catch (e) {
    setStatus(`내 위치를 가져오지 못했습니다: ${e.message}`, true); // 서버 오류
  } finally {
    meBtn.disabled = false; // 버튼 복구
  }
}

// 지도를 클릭해 내 위치 지정 (D13)
async function pickMyLocation() {
  setNotice('지도에서 내 위치를 클릭하세요. (Esc: 취소)'); // 안내
  const point = await map.pickLocation(); // 클릭 대기
  setNotice(tileNotice()); // 안내 복구
  if (!point) return; // 취소
  try {
    await api('/api/me/location', { method: 'PUT', body: point }); // 저장
    setStatus('내 위치를 지정했습니다. 이후 측정부터 이 위치를 기준으로 원을 그립니다.'); // 안내
    await loadMe(true); // 지도·패널 갱신
  } catch (e) {
    setStatus(`내 위치를 저장하지 못했습니다: ${e.message}`, true); // 실패 사유
  }
}

// 직접 지정을 지우고 내 IP 위치로 되돌림
async function resetMyLocation() {
  try {
    await api('/api/me/location', { method: 'DELETE' }); // 삭제
    setStatus('내 IP 위치를 사용합니다.'); // 안내
    await loadMe(true); // 지도·패널 갱신
  } catch (e) {
    setStatus(`되돌리지 못했습니다: ${e.message}`, true); // 실패 사유
  }
}

// --- 프로그램 연결 탭 ---

// 목록·지도 다시 그리기 (수집 없이 선택 상태만 바뀐 경우에도 호출)
function drawConnections() {
  const snap = state.conn; // 마지막 수집 결과
  if (!snap) return; // 아직 없음
  renderConnections(connList, snap, state.connUi, { onToggleProgram: toggleProgram, onSelectConn: selectConn }); // 목록
  map.highlightProgram(state.connUi.selectedProgram); // 지도 강조
}

// 프로그램 이름을 누르면 펼치기/접기 + 지도 강조
function toggleProgram(program) {
  const key = programKey(program); // 구분값
  const ui = state.connUi; // 선택 상태
  if (ui.expanded.has(key)) ui.expanded.delete(key); // 접기
  else ui.expanded.add(key); // 펼치기
  ui.selectedProgram = ui.selectedProgram === key && !ui.expanded.has(key) ? null : key; // 접으면서 같은 것이면 강조 해제
  drawConnections(); // 다시 그리기
}

// 연결 하나를 고르면 상세 + 지도 이동
function selectConn(program, conn) {
  const ui = state.connUi; // 선택 상태
  ui.selectedProgram = programKey(program); // 그 프로그램 강조
  ui.expanded.add(ui.selectedProgram); // 펼쳐서 보이게
  ui.selectedConn = connKey(conn); // 연결 강조
  drawConnections(); // 다시 그리기
  renderConnectionDetail(detailEl, program, conn, { onLookup: lookupFromConnection }); // 상세 패널
  if (conn.geo && conn.geo.lat != null) map.focus(conn.geo.lat, conn.geo.lon); // 지도 이동
}

// 연결 상세에서 [상세 조회]: 기록 탭으로 넘어가 일반 조회 실행
function lookupFromConnection(ip) {
  switchTab('history'); // 결과는 기록 탭에서 봄
  targetInput.value = ip; // 입력창에도 표시
  runLookup(ip); // 조회 + 기록 저장
}

// 서버에서 연결을 한 번 수집
async function refreshConnections() {
  if (state.connBusy) return; // 이미 수집 중이면 건너뜀 (자동 새로고침이 겹치는 경우)
  state.connBusy = true; // 시작
  connRefreshBtn.disabled = true; // 중복 클릭 방지
  try {
    const query = `include_private=${connPrivate.checked}&include_closing=${connClosing.checked}`; // 표시 옵션
    const snap = await api(`/api/connections?${query}`); // 수집 + 위치
    state.conn = snap; // 기억
    connCount.textContent = `${snap.shown}`; // 탭에 연결 수
    connTime.textContent = new Date(snap.collected_at).toLocaleTimeString('ko-KR'); // 수집 시각
    if (state.tab === 'conn') map.showConnections(groupByLocation(snap), programKey, showSpot); // 지도 마커
    drawConnections(); // 목록
    setStatus(snap.error ? `${snap.error} (위치 미조회 IP ${snap.pending.length}개)` : '', Boolean(snap.error)); // 위치 조회 문제 안내
  } catch (e) {
    setStatus(`연결 목록을 불러오지 못했습니다: ${e.message}`, true); // 실패 사유
  } finally {
    state.connBusy = false; // 끝
    connRefreshBtn.disabled = false; // 버튼 복구
  }
}

// 지도에서 좌표 묶음을 누름
function showSpot(spot) {
  if (spot.items.length === 1) selectConn(spot.items[0].program, spot.items[0].conn); // 하나면 바로 상세
  else renderSpotDetail(detailEl, spot, { onPick: selectConn }); // 여러 개면 목록
}

// 자동 새로고침 켜기/끄기 (연결 탭이 보일 때만 동작)
function updateAutoRefresh() {
  clearInterval(state.connTimer); // 기존 타이머 정지
  state.connTimer = null; // 비움
  if (connAuto.checked && state.tab === 'conn') {
    const sec = (state.settings && state.settings.connections_refresh_sec) || 5; // 서버 설정 주기
    state.connTimer = setInterval(refreshConnections, sec * 1000); // 주기적으로 수집
  }
}

// 왼쪽 탭 전환: 'history' | 'conn'
function switchTab(name) {
  if (state.tab === name) return; // 이미 그 탭
  state.tab = name; // 기억
  const isConn = name === 'conn'; // 연결 탭인지
  $('tab-history').classList.toggle('active', !isConn); // 탭 강조
  $('tab-conn').classList.toggle('active', isConn); // 탭 강조
  $('tab-history').setAttribute('aria-selected', String(!isConn)); // 접근성
  $('tab-conn').setAttribute('aria-selected', String(isConn)); // 접근성
  $('panel-history').hidden = isConn; // 패널 전환
  $('panel-conn').hidden = !isConn; // 패널 전환
  map.setTargetVisible(!isConn); // 조회 대상 마커는 기록 탭에서만
  if (isConn) {
    detailEl.replaceChildren(); // 상세 비움 (연결을 고르면 채워짐)
    refreshConnections(); // 탭을 열 때 수집 (설계: 열거나 새로고침할 때만)
  } else {
    map.clearConnections(); // 연결 마커 제거
    if (state.lastResult) renderDetail(detailEl, state.lastResult, detailOptions()); // 보던 결과 복원
    setStatus(''); // 연결 탭 안내 지움
  }
  updateAutoRefresh(); // 자동 새로고침은 연결 탭에서만
}

// 이벤트 연결
function bindEvents() {
  $('tab-history').addEventListener('click', () => switchTab('history')); // 기록 탭
  $('tab-conn').addEventListener('click', () => switchTab('conn')); // 연결 탭
  connRefreshBtn.addEventListener('click', refreshConnections); // 새로고침
  connAuto.addEventListener('change', updateAutoRefresh); // 자동 새로고침 켜기/끄기
  connPrivate.addEventListener('change', refreshConnections); // 옵션이 바뀌면 다시 수집
  connClosing.addEventListener('change', refreshConnections); // 옵션이 바뀌면 다시 수집
  lookupBtn.addEventListener('click', () => runLookup(targetInput.value)); // 조회 버튼
  targetInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runLookup(targetInput.value); // Enter로 조회
  });
  meBtn.addEventListener('click', () => loadMe(true)); // 내 IP 버튼: 지도 + 내 위치 화면
  themeBtn.addEventListener('click', async () => {
    try {
      await cycleTheme(); // 다음 테마로 (화면은 즉시 바뀜)
    } catch (e) {
      setStatus(`테마를 저장하지 못했습니다: ${e.message}`, true); // 저장 실패
    }
    themeBtn.textContent = themeLabel(); // 버튼 글자
  });
  $('btn-settings').addEventListener('click', () => openSettings(state.settings, applySettings)); // 설정 열기
  let searchTimer = null; // 검색 입력 지연 타이머
  historySearch.addEventListener('input', () => {
    clearTimeout(searchTimer); // 이전 예약 취소
    searchTimer = setTimeout(loadHistory, 250); // 입력이 멈추면 검색
  });
  $('btn-clear').addEventListener('click', async () => {
    if (!window.confirm('모든 조회 기록을 삭제할까요? 되돌릴 수 없습니다.')) return; // 확인
    try {
      await api('/api/history', { method: 'DELETE' }); // 전체 삭제
      state.selectedId = null; // 강조 해제
      await loadHistory(); // 목록 갱신
    } catch (e) {
      setStatus(e.message, true); // 실패 사유
    }
  });
  window.addEventListener('resize', () => map.refreshSize()); // 창 크기 변경 시 지도 재계산
}

// 시작
async function main() {
  let settings; // 서버 설정
  try {
    settings = await api('/api/settings'); // 설정 읽기
  } catch (e) {
    setStatus(`설정을 불러오지 못했습니다: ${e.message}`, true); // 서버 문제
    return; // 더 진행 불가
  }
  map = new GeoMap($('map'), settings.attribution); // 지도 생성
  map.setTheme(effectiveTheme()); // 현재 테마
  onThemeChange((theme) => map.setTheme(theme)); // 테마가 바뀌면 타일 교체
  applySettings(settings); // 설정 반영
  bindEvents(); // 버튼 연결
  targetInput.focus(); // 바로 입력할 수 있게
  await Promise.all([loadHistory(), loadMe(false)]); // 기록과 내 위치를 동시에 (상세 패널은 그대로)
}

main(); // 실행
