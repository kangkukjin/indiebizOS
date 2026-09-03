/** 지도 마커 아이콘 — 이미지 의존 없는 leaflet divIcon. */
import L from 'leaflet';

/** 검색 결과 번호 핀(카카오맵식). active=선택된 항목. */
export const pinIcon = (num: number, active = false) => L.divIcon({
  className: '',
  html: `<div style="position:relative;width:${active ? 34 : 28}px;height:${active ? 34 : 28}px;">
    <div style="width:100%;height:100%;border-radius:50% 50% 50% 0;transform:rotate(-45deg);
      background:${active ? '#F97316' : '#2563EB'};border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35)"></div>
    <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
      color:#fff;font-weight:700;font-size:${active ? 13 : 11}px;padding-bottom:3px">${num}</div></div>`,
  iconSize: active ? [34, 34] : [28, 28],
  iconAnchor: active ? [17, 34] : [14, 28],
  tooltipAnchor: [0, active ? -30 : -24],
});

/** 저장한 장소 — 노란 별. */
export const starIcon = (active = false) => L.divIcon({
  className: '',
  html: `<div style="font-size:${active ? 26 : 20}px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))">⭐</div>`,
  iconSize: active ? [26, 26] : [20, 20],
  iconAnchor: active ? [13, 13] : [10, 10],
  tooltipAnchor: [0, active ? -14 : -10],
});

/** 출발·도착·현재 위치 점. */
export const dotIcon = (color: string, size = 16) => L.divIcon({
  className: '',
  html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
  iconSize: [size, size], iconAnchor: [size / 2, size / 2],
});

/** 내 위치 — 파란 점 + 정밀도 원은 별도 circle 로. */
export const hereIcon = L.divIcon({
  className: '',
  html: `<div style="width:18px;height:18px;border-radius:50%;background:#2563EB;border:3px solid #fff;box-shadow:0 0 0 6px rgba(37,99,235,.25)"></div>`,
  iconSize: [18, 18], iconAnchor: [9, 9],
});

/** 지도 클릭 지점(주소 카드) 핀. */
export const spotIcon = L.divIcon({
  className: '',
  html: `<div style="font-size:26px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))">📍</div>`,
  iconSize: [26, 26], iconAnchor: [13, 26],
});

export const CCTV_ICON = L.divIcon({
  className: '',
  html: `<div style="font-size:20px;line-height:20px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))">📹</div>`,
  iconSize: [20, 20], iconAnchor: [10, 10],
});
