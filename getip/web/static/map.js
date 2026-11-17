// Leaflet 지도: 테마별 타일, 내 위치·조회 대상 마커, 둘을 잇는 선.
// 마커 색은 CSS 클래스(.mk-*)로 정해 테마 변수를 따른다.

const WORLD_VIEW = { center: [20, 0], zoom: 2 }; // 처음 보이는 범위 (세계 전체)
const TARGET_ZOOM = 5; // 내 위치 없이 대상만 있을 때 확대 정도

// 외부 문자열을 넣을 툴팁 내용을 DOM으로 만든다 (innerHTML 금지 규칙)
function tooltipContent(title, subtitle) {
  const box = document.createElement('div'); // 툴팁 상자
  const head = document.createElement('strong'); // 제목 줄
  head.textContent = title; // 글자로만 넣음
  box.append(head); // 추가
  if (subtitle) {
    const sub = document.createElement('div'); // 보조 줄
    sub.textContent = subtitle; // 글자로만 넣음
    box.append(sub); // 추가
  }
  return box; // 완성된 요소
}

// 대상 경도를 내 위치 기준 ±180° 안으로 옮긴다 (태평양을 건너는 선이 지구 반대편으로 돌아가지 않게)
function nearLon(fromLon, lon) {
  let out = lon; // 옮길 경도
  while (out - fromLon > 180) out -= 360; // 너무 동쪽이면 한 바퀴 서쪽으로
  while (out - fromLon < -180) out += 360; // 너무 서쪽이면 한 바퀴 동쪽으로
  return out; // 가까운 쪽 경도
}

// 위치 문자열 "도시, 국가"
function placeText(geo) {
  return [geo.city, geo.country].filter(Boolean).join(', '); // 빈 값 제외
}

export class GeoMap {
  // el: 지도 요소, attribution: 타일 출처 표기 (서버 설정값)
  constructor(el, attribution) {
    this.attribution = attribution; // 타일 레이어마다 붙일 출처
    this.map = L.map(el, { worldCopyJump: true, minZoom: 2, zoomControl: true }).setView(WORLD_VIEW.center, WORLD_VIEW.zoom); // 지도 생성
    this.tiles = null; // 현재 타일 레이어
    this.tileUrls = null; // {light, dark} 또는 null(키 없음)
    this.theme = 'light'; // 현재 실제 테마
    this.me = null; // 내 위치 마커
    this.meLatLng = null; // 내 좌표
    this.target = null; // 조회 대상 마커
    this.route = null; // 연결선
  }

  // 타일 주소를 바꾼다. null이면 타일 없이 바탕색만 보인다
  setTileUrls(urls) {
    this.tileUrls = urls; // 기억
    this.applyTiles(); // 반영
  }

  // 실제 테마가 바뀌면 타일을 교체한다
  setTheme(theme) {
    this.theme = theme; // 기억
    this.applyTiles(); // 반영
  }

  applyTiles() {
    if (this.tiles) this.tiles.remove(); // 이전 레이어 제거
    this.tiles = null; // 비움
    if (!this.tileUrls) return; // 키가 없으면 타일 없음
    const url = this.tileUrls[this.theme] || this.tileUrls.light; // 테마에 맞는 주소
    this.tiles = L.tileLayer(url, { attribution: this.attribution, maxZoom: 19, subdomains: '' }).addTo(this.map); // 새 레이어
  }

  // 내 위치 표시 (geo: /api/me 응답)
  showMe(geo) {
    if (this.me) this.me.remove(); // 이전 마커 제거
    this.me = null; // 비움
    this.meLatLng = null; // 비움
    if (geo.lat == null || geo.lon == null) return; // 좌표 없음
    this.meLatLng = [geo.lat, geo.lon]; // 좌표 기억
    this.me = L.circleMarker(this.meLatLng, { radius: 7, className: 'mk-me' }) // 파란 원
      .bindTooltip(tooltipContent(`내 위치 (${geo.ip})`, placeText(geo)), { direction: 'top' }) // 마우스 올리면 정보
      .addTo(this.map); // 지도에 추가
    if (!this.target) this.map.setView(this.meLatLng, 4); // 대상이 없으면 내 위치로 이동
  }

  // 조회 결과 표시. 좌표가 없으면 false
  showResult(result) {
    this.clearTarget(); // 이전 대상 제거
    const geo = result.geo; // 위치 정보
    if (!geo || geo.lat == null || geo.lon == null) return false; // 표시할 좌표 없음
    let latlng = [geo.lat, geo.lon]; // 대상 좌표
    if (this.meLatLng) latlng = [geo.lat, nearLon(this.meLatLng[1], geo.lon)]; // 내 위치 쪽 지도 사본으로 옮김
    this.target = L.circleMarker(latlng, { radius: 9, className: 'mk-target' }) // 빨간 원
      .bindTooltip(tooltipContent(`${result.target.host} (${result.ip})`, placeText(geo)), { direction: 'top' }) // 정보
      .addTo(this.map); // 지도에 추가
    if (this.meLatLng) {
      this.route = L.polyline([this.meLatLng, latlng], { className: 'mk-route', interactive: false }).addTo(this.map); // 점선
      this.map.fitBounds(L.latLngBounds([this.meLatLng, latlng]), { padding: [60, 60], maxZoom: 8 }); // 둘 다 보이게
    } else {
      this.map.setView(latlng, TARGET_ZOOM); // 대상으로 이동
    }
    return true; // 표시함
  }

  clearTarget() {
    if (this.target) this.target.remove(); // 대상 마커 제거
    if (this.route) this.route.remove(); // 연결선 제거
    this.target = null; // 비움
    this.route = null; // 비움
  }

  // 레이아웃이 바뀐 뒤 지도 크기를 다시 계산
  refreshSize() {
    this.map.invalidateSize(); // Leaflet 크기 재계산
  }
}
