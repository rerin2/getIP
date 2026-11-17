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
