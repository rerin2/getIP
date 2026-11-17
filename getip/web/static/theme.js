// 테마 선택(system/light/dark) 관리. 실제 색은 theme.css가 data-theme 속성을 보고 정한다.

import { api } from './api.js'; // 설정 저장

const ORDER = ['system', 'light', 'dark']; // 버튼을 누를 때 바뀌는 순서
const LABELS = { system: '테마: 시스템', light: '테마: 라이트', dark: '테마: 다크' }; // 버튼 글자
const root = document.documentElement; // <html>
const media = window.matchMedia('(prefers-color-scheme: dark)'); // OS 다크 모드 여부
const listeners = []; // 실제 테마가 바뀔 때 부를 함수들 (지도 타일 교체 등)

let preference = ORDER.includes(root.dataset.theme) ? root.dataset.theme : 'system'; // 서버가 채운 저장값

// 지금 화면에 적용된 테마: 'light' 또는 'dark'
export function effectiveTheme() {
  if (preference === 'system') return media.matches ? 'dark' : 'light'; // OS 설정 따름
  return preference; // 사용자가 고른 값
}

// 사용자가 고른 값: 'system' | 'light' | 'dark'
export function themePreference() {
  return preference; // 현재 선택
}

// 버튼에 보일 글자
export function themeLabel() {
  return LABELS[preference]; // 현재 선택 이름
}

// 실제 테마가 바뀔 때 fn('light'|'dark')을 부른다
export function onThemeChange(fn) {
  listeners.push(fn); // 등록
}

function notify() {
  const theme = effectiveTheme(); // 바뀐 실제 테마
  listeners.forEach((fn) => fn(theme)); // 모두에게 알림
}

media.addEventListener('change', () => {
  if (preference === 'system') notify(); // OS 설정이 바뀌면 system일 때만 따라감
});

// 화면에 즉시 적용하고 서버에 저장한다 (저장 실패는 호출자에게 Error로 전달)
export async function setThemePreference(value) {
  if (!ORDER.includes(value)) return; // 잘못된 값 무시
  preference = value; // 기억
  root.dataset.theme = value; // CSS 적용
  notify(); // 지도 등 갱신
  await api('/api/settings', { method: 'PUT', body: { theme: value } }); // 다음 실행에도 유지되게 저장
}

// 다음 테마로 넘긴다 (상단 버튼)
export function cycleTheme() {
  return setThemePreference(ORDER[(ORDER.indexOf(preference) + 1) % ORDER.length]); // 순환
}

// 서버가 돌려준 설정과 맞춘다 (설정 대화상자에서 저장한 경우)
export function syncFromSettings(settings) {
  if (settings.theme === preference) return; // 같으면 할 일 없음
  preference = settings.theme; // 갱신
  root.dataset.theme = preference; // CSS 적용
  notify(); // 지도 등 갱신
}
