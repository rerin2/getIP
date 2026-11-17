// 설정 대화상자: 테마와 CARTO 지도 키.

import { api } from './api.js'; // 설정 저장

const dialog = document.getElementById('settings-dialog'); // 대화상자
const themeSelect = document.getElementById('set-theme'); // 테마 선택
const keyInput = document.getElementById('set-key'); // 키 입력
const keyState = document.getElementById('set-key-state'); // 키 상태 안내
const errorEl = document.getElementById('set-error'); // 오류 문구

let onSaved = () => {}; // 저장 후 부를 함수 (app.js가 지정)

// settings: /api/settings 응답, savedFn(newSettings): 저장 성공 시
export function openSettings(settings, savedFn) {
  onSaved = savedFn; // 기억
  themeSelect.value = settings.theme; // 현재 테마
  keyInput.value = ''; // 키는 다시 보여주지 않음 (입력하면 교체)
  keyInput.disabled = settings.tile_key_from_env; // 환경 변수 사용 중이면 수정 불가
  document.getElementById('set-key-delete').disabled = settings.tile_key_from_env || !settings.tile_key_set; // 지울 키가 있을 때만
  if (settings.tile_key_from_env) keyState.textContent = '환경 변수 GETIP_CARTO_KEY의 키를 사용 중입니다.'; // 개발 모드 안내
  else if (settings.tile_key_set) keyState.textContent = '키가 저장되어 있습니다. 바꾸려면 새 키를 입력하세요. 비워 두면 그대로 둡니다.'; // 이미 있음
  else keyState.textContent = '키가 없습니다. 키가 없으면 지도 배경이 표시되지 않습니다.'; // 없음
  errorEl.textContent = ''; // 이전 오류 지움
  dialog.showModal(); // 열기
}

document.getElementById('set-cancel').addEventListener('click', () => dialog.close()); // 취소

// 설정을 서버에 보내고 성공하면 닫는다
async function save(body) {
  try {
    const saved = await api('/api/settings', { method: 'PUT', body }); // 저장
    dialog.close(); // 닫기
    onSaved(saved); // 화면 반영
  } catch (e) {
    errorEl.textContent = e.message; // 사유 표시
  }
}

document.getElementById('set-save').addEventListener('click', () => {
  const body = { theme: themeSelect.value }; // 테마는 항상 보냄
  const key = keyInput.value.trim(); // 입력한 키
  if (key && !keyInput.disabled) body.tile_key = key; // 입력했을 때만 교체 (빈 칸 = 그대로)
  save(body); // 저장
});

document.getElementById('set-key-delete').addEventListener('click', () => {
  if (keyInput.disabled) return; // 환경 변수 키는 여기서 지울 수 없음
  if (!window.confirm('저장된 지도 키를 삭제할까요?')) return; // 확인
  save({ tile_key: '' }); // 빈 값 = 삭제
});
