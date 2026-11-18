// 로컬 API 호출. 모든 요청에 실행별 토큰을 싣고, 실패하면 서버가 준 사유로 Error를 던진다.

const TOKEN = document.querySelector('meta[name="getip-token"]').content; // index.html에 서버가 심어 둔 토큰

// 서버 오류 본문에서 사람이 읽을 문구를 뽑는다
function errorMessage(body, status) {
  const detail = body && body.detail; // FastAPI 오류 형식 {detail: ...}
  if (typeof detail === 'string') return detail; // 직접 만든 오류 문구
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join(', '); // 입력 검증 오류 목록
  return `요청 실패 (${status})`; // 알 수 없는 형식
}

// path: '/api/...', options: {method, body}. JSON 응답을 돌려준다
export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'X-GetIP-Token': TOKEN }; // 토큰 헤더
  if (body !== undefined) headers['Content-Type'] = 'application/json'; // 본문이 있으면 JSON
  let res; // 응답 객체
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }); // 요청
  } catch (e) {
    throw new Error('로컬 서버에 연결할 수 없습니다.'); // 서버가 꺼진 경우
  }
  const data = await res.json().catch(() => null); // 본문이 JSON이 아니면 null
  if (!res.ok) throw new Error(errorMessage(data, res.status)); // 4xx/5xx
  return data; // 정상 응답
}

// 줄 단위 JSON 스트림(경로 추적). 한 줄이 도착할 때마다 onEvent(객체)를 부른다.
// EventSource는 토큰 헤더를 보낼 수 없어서 fetch 스트림으로 읽는다.
export async function apiStream(path, onEvent, { method = 'POST' } = {}) {
  let res; // 응답 객체
  try {
    res = await fetch(path, { method, headers: { 'X-GetIP-Token': TOKEN } }); // 요청
  } catch (e) {
    throw new Error('로컬 서버에 연결할 수 없습니다.'); // 서버가 꺼진 경우
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null); // 오류 본문
    throw new Error(errorMessage(data, res.status)); // 시작 전 거부 (IPv6, 없는 기록 등)
  }
  const reader = res.body.getReader(); // 조각 단위로 읽기
  const decoder = new TextDecoder(); // 바이트 → 글자 (한글이 조각 경계에서 잘려도 이어 붙임)
  let buffer = ''; // 아직 줄바꿈이 오지 않은 부분
  for (;;) {
    const { value, done } = await reader.read(); // 다음 조각
    if (done) break; // 스트림 끝
    buffer += decoder.decode(value, { stream: true }); // 이어 붙임
    let cut; // 줄바꿈 위치
    while ((cut = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, cut).trim(); // 한 줄
      buffer = buffer.slice(cut + 1); // 나머지
      if (line) onEvent(JSON.parse(line)); // 사건 전달
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer)); // 마지막 줄 (줄바꿈 없이 끝난 경우)
}
