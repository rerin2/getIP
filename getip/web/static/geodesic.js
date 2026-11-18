// 지구 위의 원(한 점에서 같은 거리인 곳)을 지도에 그릴 좌표 목록으로 만든다.
// Leaflet의 L.circle은 평면 원이라 수천 km 반경에서는 모양이 틀리므로 직접 계산한다.

const EARTH_RADIUS_KM = 6371.0088; // 서버 geomath.py와 같은 값
const RAD = Math.PI / 180; // 도 → 라디안
const DEG = 180 / Math.PI; // 라디안 → 도
const POLE_LAT = 89.9; // 극점 근처 위도 (메르카토르 지도는 90도를 그릴 수 없음)

// 시작점에서 bearing(도) 방향으로 km만큼 간 지점 [위도, 경도]
function destination(lat, lon, km, bearing) {
  const d = km / EARTH_RADIUS_KM; // 중심각(라디안)
  const p1 = lat * RAD; // 시작 위도
  const b = bearing * RAD; // 방위각
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b)); // 도착 위도
  const l2 = lon * RAD + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2)); // 도착 경도
  return [p2 * DEG, l2 * DEG]; // 도 단위
}

// 경도를 이전 점 기준 ±180° 안으로 옮긴다 (선이 지도 반대편으로 튀지 않게)
export function nearLon(fromLon, lon) {
  let out = lon; // 옮길 경도
  while (out - fromLon > 180) out -= 360; // 너무 동쪽이면 한 바퀴 서쪽으로
  while (out - fromLon < -180) out += 360; // 너무 서쪽이면 한 바퀴 동쪽으로
  return out; // 가까운 쪽 경도
}

// 반경 km의 원 둘레 좌표. 원이 남극·북극을 모두 감싸면(지구 대부분을 덮음) null.
export function geodesicRing(lat, lon, km, steps = 180) {
  const angle = (km / EARTH_RADIUS_KM) * DEG; // 반경의 중심각(도)
  const north = angle > 90 - lat; // 북극을 감싸는지
  const south = angle > 90 + lat; // 남극을 감싸는지
  if (north && south) return null; // 그려도 의미가 없음 (호출자가 안내)
  const points = []; // 둘레 좌표
  let prevLon = lon; // 이어 붙일 기준 경도
  for (let i = 0; i <= steps; i += 1) {
    const [pLat, pLon] = destination(lat, lon, km, (360 * i) / steps); // 방위각마다 한 점
    prevLon = nearLon(prevLon, pLon); // 연속된 경도로
    points.push([pLat, prevLon]); // 추가
  }
  if (north || south) {
    // 극을 감싸면 한 바퀴 돌았을 때 경도가 360° 어긋난다 → 극점을 지나 닫아 줘야 안쪽이 채워진다
    const poleLat = north ? POLE_LAT : -POLE_LAT; // 감싼 극
    const last = points[points.length - 1][1]; // 끝 경도
    points.push([poleLat, last], [poleLat, points[0][1]]); // 극을 따라 처음으로 돌아감
  }
  return points; // 다각형 좌표
}
