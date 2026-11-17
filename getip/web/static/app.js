// 화면 진입점: 부품(지도, 기록, 상세, 테마, 설정)을 연결한다.

import { api } from './api.js'; // 로컬 API
import { renderDetail } from './detail.js'; // 상세 패널
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

const state = {
  settings: null, // /api/settings 응답
  selectedId: null, // 지금 보고 있는 기록 번호
  busy: false, // 조회 중 여부 (중복 클릭 방지)
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

// 조회 결과 하나를 지도·상세에 표시
function showResult(result) {
  state.selectedId = result.id; // 강조할 기록
  renderDetail(detailEl, result, { onPickIp: runLookup }); // 상세 패널
  const shown = map.showResult(result); // 지도 마커
  setNotice(shown ? tileNotice() : '이 IP는 위치 정보가 없어 지도에 표시하지 않았습니다.'); // 좌표 없음 안내
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

// 내 공인 IP 위치를 지도에 표시
async function loadMe() {
  meBtn.disabled = true; // 중복 클릭 방지
  try {
    const me = await api('/api/me'); // 내 IP 조회
    map.showMe(me); // 지도에 표시
    meBtn.title = `내 IP: ${me.ip}`; // 마우스 올리면 IP
  } catch (e) {
    setStatus(`내 위치를 가져오지 못했습니다: ${e.message}`, true); // 실패 사유
  } finally {
    meBtn.disabled = false; // 버튼 복구
  }
}

// 이벤트 연결
function bindEvents() {
  lookupBtn.addEventListener('click', () => runLookup(targetInput.value)); // 조회 버튼
  targetInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runLookup(targetInput.value); // Enter로 조회
  });
  meBtn.addEventListener('click', loadMe); // 내 IP 버튼
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
  await Promise.all([loadHistory(), loadMe()]); // 기록과 내 위치를 동시에
}

main(); // 실행
