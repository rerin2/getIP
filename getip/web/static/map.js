// Leaflet 지도: 테마별 타일, 내 위치·조회 대상 마커, 둘을 잇는 선, 지연 반경 원, 경로 추적선.
// 마커 색은 CSS 클래스(.mk-*, .rtt-*)로 정해 테마 변수를 따른다.

import { geodesicRing, nearLon } from './geodesic.js'; // 지구 위의 원, 경도 이어 붙이기

const WORLD_VIEW = { center: [20, 0], zoom: 2 }; // 처음 보이는 범위 (세계 전체)
const TARGET_ZOOM = 5; // 내 위치 없이 대상만 있을 때 확대 정도

// 외부 문자열을 넣을 툴팁 내용을 DOM으로 만든다 (innerHTML 금지 규칙)
function tooltipContent(title, subtitle) {
  const box = document.createElement('div'); // 툴팁 상자
  const head = document.createElement('strong'); // 제목 줄
  head.textContent = title; // 글자로만 넣음
  box.append(head); // 추가
  for (const line of (subtitle || '').split('\n').filter(Boolean)) {
    const sub = document.createElement('div'); // 보조 줄 (여러 줄이면 줄마다)
    sub.textContent = line; // 글자로만 넣음
    box.append(sub); // 추가
  }
  return box; // 완성된 요소
}

// 선을 이을 때 경도를 ±180° 밖으로 이어 붙이므로(태평양을 건너는 선) 그 부분은 옆 '지도 사본'에 놓인다.
// worldCopyJump가 화면을 원래 세계로 되돌리면 그 부분이 사라지므로, 왼쪽·가운데·오른쪽 세 사본에 모두 그린다.
const WORLD_SHIFTS = [-360, 0, 360]; // 경도 이동량

// 좌표 [위도, 경도]를 경도 방향으로 dx만큼 옮김
function shift([lat, lon], dx) {
  return [lat, lon + dx]; // 새 좌표
}

// make(dx)로 만든 레이어를 세 사본만큼 모아 한 묶음으로 돌려준다
function inEveryWorld(make) {
  return L.layerGroup(WORLD_SHIFTS.map((dx) => make(dx))); // 묶음 (함께 추가·제거)
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
    this.connLayer = null; // 프로그램 연결 마커 묶음
    this.connMarkers = []; // 강조 처리용 마커 정보
    this.rttLayer = null; // 지연 반경 원 묶음
    this.traceLayer = null; // 경로 추적선·홉 마커 묶음
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

  // 내 위치 표시 (me: /api/me 응답 {geo, origin, error}). 수동 지정 위치가 있으면 그곳에 찍는다
  showMe(me) {
    if (this.me) this.me.remove(); // 이전 마커 제거
    this.me = null; // 비움
    this.meLatLng = null; // 비움
    const origin = me && me.origin; // 지금 쓰는 내 위치
    if (!origin) return; // 위치 모름
    this.meLatLng = [origin.lat, origin.lon]; // 좌표 기억
    const geo = me.geo || {}; // ip-api 정보 (실패하면 빈 객체)
    const title = origin.source === 'manual' ? '내 위치 (직접 지정)' : `내 위치 (${geo.ip || '?'})`; // 출처에 따라 제목
    const sub = origin.source === 'manual' ? `${origin.lat.toFixed(4)}, ${origin.lon.toFixed(4)}` : placeText(geo); // 좌표 또는 도시
    this.me = L.circleMarker(this.meLatLng, { radius: 7, className: 'mk-me' }) // 파란 원
      .bindTooltip(tooltipContent(title, sub), { direction: 'top' }) // 마우스 올리면 정보
      .addTo(this.map); // 지도에 추가
    if (!this.target) this.map.setView(this.meLatLng, 4); // 대상이 없으면 내 위치로 이동
  }

  // 지도를 한 번 클릭해 좌표를 고른다. Esc를 누르면 null. 고르는 동안 커서가 십자 모양
  pickLocation() {
    return new Promise((resolve) => {
      const box = this.map.getContainer(); // 지도 요소
      box.classList.add('picking'); // 십자 커서
      const finish = (value) => {
        box.classList.remove('picking'); // 커서 복구
        this.map.off('click', onClick); // 이벤트 해제
        document.removeEventListener('keydown', onKey); // 이벤트 해제
        resolve(value); // 결과 전달
      };
      const onClick = (e) => finish({ lat: e.latlng.lat, lon: e.latlng.lng }); // 클릭한 좌표 (경도 정리는 서버가 함)
      const onKey = (e) => { if (e.key === 'Escape') finish(null); }; // 취소
      this.map.on('click', onClick); // 클릭 대기
      document.addEventListener('keydown', onKey); // Esc 대기
    });
  }

  // 조회 결과 표시. 좌표가 없으면 false
  showResult(result) {
    this.clearTarget(); // 이전 대상 제거
    const geo = result.geo; // 위치 정보
    if (!geo || geo.lat == null || geo.lon == null) return false; // 표시할 좌표 없음
    let latlng = [geo.lat, geo.lon]; // 대상 좌표
    if (this.meLatLng) latlng = [geo.lat, nearLon(this.meLatLng[1], geo.lon)]; // 내 위치 쪽 지도 사본으로 옮김
    const tip = tooltipContent(`${result.target.host} (${result.ip})`, placeText(geo)); // 툴팁 내용
    this.target = inEveryWorld((dx) => L.circleMarker(shift(latlng, dx), { radius: 9, className: 'mk-target' }) // 빨간 원
      .bindTooltip(tip.cloneNode(true), { direction: 'top' })).addTo(this.map); // 사본마다 (경도를 옮겼으면 원래 세계에도 보이게)
    if (this.meLatLng) {
      this.route = inEveryWorld((dx) => L.polyline([shift(this.meLatLng, dx), shift(latlng, dx)], { className: 'mk-route', interactive: false })).addTo(this.map); // 점선
      this.map.fitBounds(L.latLngBounds([this.meLatLng, latlng]), { padding: [60, 60], maxZoom: 8 }); // 둘 다 보이게
    } else {
      this.map.setView(latlng, TARGET_ZOOM); // 대상으로 이동
    }
    return true; // 표시함
  }

  // 지연 측정·경로 추적 결과 표시 (조회 결과에 저장된 값으로). 없으면 지움
  showProbe(result) {
    this.clearProbe(); // 이전 원·경로 제거
    const view = result.latency_view; // 서버가 계산한 반경
    const origin = result.latency && result.latency.origin; // 측정한 곳 (지금 내 위치가 아니라 측정 당시 위치)
    if (origin && view && view.upper_km) this.showRtt(origin, view); // 반경 원
    if (result.trace) this.showTrace(result.trace.origin, result.trace.hops); // 경로
  }

  // 반경 원 두 겹: 옅은 점선 = 물리적 상한, 진한 원 = 현실 추정. 지구 대부분을 덮는 원은 생략
  showRtt(origin, view) {
    if (this.rttLayer) this.rttLayer.remove(); // 이전 원 제거
    this.rttLayer = L.layerGroup().addTo(this.map); // 원 묶음
    const rings = [['rtt-upper', view.upper_km], ['rtt-typical', view.typical_km]]; // 바깥 → 안쪽 순서
    for (const [className, km] of rings) {
      const points = geodesicRing(origin.lat, origin.lon, km); // 둘레 좌표
      if (!points) continue; // 지구 대부분을 덮으면 생략
      inEveryWorld((dx) => L.polygon(points.map((p) => shift(p, dx)), { className, interactive: false })).addTo(this.rttLayer); // 다각형 (클릭 통과, 날짜변경선을 넘어도 끊기지 않게)
    }
  }

  // 경로 추적선: 시작점 → 위치를 아는 홉들. 홉이 도착할 때마다 다시 그린다 (30개 이하라 부담 없음)
  showTrace(origin, hops) {
    if (this.traceLayer) this.traceLayer.remove(); // 이전 경로 제거
    this.traceLayer = L.layerGroup().addTo(this.map); // 경로 묶음
    const points = []; // 선을 이을 좌표
    let prevLon = origin ? origin.lon : null; // 경도 이어 붙이기 기준
    if (origin) points.push([origin.lat, origin.lon]); // 시작점
    for (const hop of hops || []) {
      const geo = hop.geo; // 홉 위치
      if (!geo || geo.lat == null || geo.lon == null) continue; // 사설·무응답 홉은 선에서 제외
      const lon = prevLon == null ? geo.lon : nearLon(prevLon, geo.lon); // 태평양을 건너는 선이 튀지 않게
      prevLon = lon; // 다음 기준
      points.push([geo.lat, lon]); // 선에 추가
      const rtt = hop.rtt_ms == null ? '-' : `${hop.rtt_less_than ? '<' : ''}${hop.rtt_ms}ms`; // 지연 글자
      const tip = tooltipContent(`${hop.index}. ${hop.ip}`, [rtt, placeText(geo), geo.isp].join('\n')); // 지연·위치·사업자
      inEveryWorld((dx) => L.circleMarker([geo.lat, lon + dx], { radius: 4, className: 'mk-hop' }) // 작은 원
        .bindTooltip(tip.cloneNode(true), { direction: 'top' })).addTo(this.traceLayer); // 사본마다 추가
    }
    if (points.length > 1) {
      inEveryWorld((dx) => L.polyline(points.map((p) => shift(p, dx)), { className: 'mk-trace', interactive: false })).addTo(this.traceLayer); // 경로선 (한국→미국→영국처럼 경도가 180°를 넘어도 끊기지 않게)
    }
  }

  clearProbe() {
    if (this.rttLayer) this.rttLayer.remove(); // 원 제거
    if (this.traceLayer) this.traceLayer.remove(); // 경로 제거
    this.rttLayer = null; // 비움
    this.traceLayer = null; // 비움
  }

  // 조회 대상 마커·선·반경·경로를 보이거나 숨긴다 (연결 탭에서는 숨김)
  setTargetVisible(show) {
    for (const layer of [this.target, this.route, this.rttLayer, this.traceLayer]) {
      if (!layer) continue; // 없는 레이어
      if (show) layer.addTo(this.map); // 다시 표시
      else layer.remove(); // 숨김
    }
  }

  // 프로그램 연결 마커. spots: [{lat, lon, items:[{program, conn}]}], keyOf(program): 강조용 구분값, onClick(spot)
  showConnections(spots, keyOf, onClick) {
    this.clearConnections(); // 이전 마커 제거
    this.connLayer = L.layerGroup().addTo(this.map); // 연결 마커 묶음
    this.connMarkers = []; // [{layer, keys:Set}] 강조 처리용
    for (const spot of spots) {
      const count = spot.items.length; // 이 좌표의 연결 수
      const first = spot.items[0]; // 툴팁 제목용
      const title = count > 1 ? `${count}개 연결` : `${first.program.name}`; // 제목
      const lines = spot.items.slice(0, 8).map(({ program, conn }) => `${program.name} → ${conn.remote_ip}:${conn.remote_port}`); // 최대 8줄
      if (count > 8) lines.push(`… 외 ${count - 8}개`); // 나머지 개수
      const place = [first.conn.geo.city, first.conn.geo.country].filter(Boolean).join(', '); // 위치
      let layer; // 마커
      if (count === 1) {
        layer = L.circleMarker([spot.lat, spot.lon], { radius: 6, className: 'mk-conn' }); // 작은 원
      } else {
        const badge = document.createElement('div'); // 개수 배지
        badge.textContent = String(count); // 숫자
        const size = count >= 10 ? 26 : 22; // 두 자리면 조금 크게
        layer = L.marker([spot.lat, spot.lon], {
          icon: L.divIcon({ html: badge, className: 'mk-count', iconSize: [size, size] }), // DOM 요소 그대로 사용
        });
      }
      layer.bindTooltip(tooltipContent(title, [place, ...lines].join('\n')), { direction: 'top', className: 'conn-tip' }); // 정보
      layer.on('click', () => onClick(spot)); // 선택
      layer.addTo(this.connLayer); // 묶음에 추가
      this.connMarkers.push({ layer, keys: new Set(spot.items.map(({ program }) => keyOf(program))) }); // 강조용 정보
    }
  }

  // 선택한 프로그램의 마커만 강조하고 나머지는 흐리게. key가 null이면 모두 보통
  highlightProgram(key) {
    for (const { layer, keys } of this.connMarkers || []) {
      const el = layer.getElement ? layer.getElement() : null; // SVG 경로 또는 배지 요소
      if (!el) continue; // 아직 그려지지 않음
      const hot = key !== null && keys.has(key); // 선택한 프로그램 포함
      el.classList.toggle('hot', hot); // 강조
      el.classList.toggle('dim', key !== null && !hot); // 흐리게
    }
  }

  clearConnections() {
    if (this.connLayer) this.connLayer.remove(); // 마커 묶음 제거
    this.connLayer = null; // 비움
    this.connMarkers = []; // 비움
  }

  // 좌표 하나로 이동 (목록에서 연결을 고른 경우)
  focus(lat, lon) {
    this.map.setView([lat, lon], Math.max(this.map.getZoom(), 4)); // 너무 멀면 조금 확대
  }

  clearTarget() {
    this.clearProbe(); // 원·경로도 함께 제거
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
