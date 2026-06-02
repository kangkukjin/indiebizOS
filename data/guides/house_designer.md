# House Designer v4 가이드

## 개요
사용자와 대화하면서 집을 설계하는 도구입니다. 다각형 방, 재질, 구조 요소(기둥/보), 계단(직선/L자/U턴/나선형/Winder), 발코니 난간, 다양한 지붕, 필로티, 건물 프로파일, 축선 그리드, 방 마감재, 복사/미러/배열을 지원합니다. 전문 건축 심볼의 2D 평면도(PNG, 지붕 평면 포함), 단면도, 입면도(4방향)와 고품질 3D 인터랙티브 뷰(HTML)를 생성합니다. PDF/SVG/DXF 도면 출력, 좌표 기반 문/창문 배치를 지원합니다.

## v4 주요 개선사항
- **단면도**: 절단선 기준 건물 횡단면 PNG (벽체 해칭, 슬라브, 계단 단면, 창문/문, GL/FL 마커)
- **입면도**: 4방향(전면/후면/좌측/우측) 외관 투영 PNG (외벽 재질, 창문/문, 지붕, 층 레벨선)
- **도면 출력**: PDF(다중 페이지, 제목란, 면적표), SVG(벡터), DXF(AutoCAD 호환)
- **프로젝트 정보**: 설계자, 회사명, 도면 자동 번호 등 전문 도면 규격
- **면적표/물량 산출**: 면적 일람표, 건폐율/용적률, 벽체/창호/바닥재 물량표, 종합 보고서
- **치수 강화**: 다각형 방 각 변 치수, 연속 치수 체인, 사용자 지정 치수선, FL 레벨 마커
- **벽 시스템**: 수동 벽 추가/삭제/이동/분할, 커스텀 두께, 원호 벽, 이중벽(단열)
- **레이어 관리**: 요소별 가시성/스타일 제어, 프리셋 (structure_only, presentation 등)
- **Undo/Redo**: 모든 수정 작업 되돌리기/다시하기 (최대 50단계)
- **스냅샷**: 설계 상태를 명명 스냅샷으로 저장/복원/비교

### v4.2 추가 기능
- **나선형/Winder 계단**: spiral(원형), winder(꺾임) 계단 타입 추가
- **좌표 기반 문/창문**: 좌표로 문/창문 배치, 가장 가까운 벽에 자동 스냅
- **창문 연속 배치**: `add_window_batch`로 등간격 창문 일괄 추가
- **개구부 검증**: `validate_openings`로 문/창문 겹침 자동 검사
- **축선 그리드**: 구조 축선(X1,X2.../Y1,Y2...) 설정, 축선 교차점에 기둥 자동 배치
- **방 마감재**: 방별 바닥재/벽마감/천장마감/천장고 설정, 2D에서 바닥재 해칭 표시
- **복사/미러/배열**: 방 복사, 미러 복사, 배열 복사, 층 복사
- **지붕 평면도**: 최상층 2D 평면도에 용마루선/경사 방향 화살표 표시
- **내력벽**: 벽에 `is_load_bearing` 속성 설정 가능

## 기본 워크플로우

1. **요구사항 파악**: 규모, 층수, 용도, 원하는 스타일 파악
2. **설계 생성**: `create_house_design`으로 기본 구조 생성
3. **방 배치**: `add_room`으로 방 추가 (직사각형 또는 다각형)
4. **벽 자동 생성**: `auto_walls` 호출
5. **구조 요소**: 필요시 `add_column`, `add_beam` 추가
6. **계단**: 다층 건물이면 `add_stairs`로 계단 추가
7. **문/창문**: `add_door`, `add_window` 추가 (또는 `add_window_batch`로 연속 배치)
8. **마감재 설정**: `set_room_finishes`로 바닥재/벽/천장 마감 설정
9. **재질 설정**: `set_wall_material`, `set_facade_defaults`
10. **지붕 설정**: `set_roof`
11. **가구 배치**: `add_furniture`
12. **수동 벽**: 필요시 `add_wall`로 커스텀/원호/이중벽 추가
13. **축선 그리드**: 필요시 `set_column_grid` + `auto_place_columns_on_grid`
14. **레이어 설정**: `set_layer_visibility`, `apply_layer_preset`로 출력 제어
15. **시각화**: `generate_floor_plan` (2D) / `generate_3d_view` (3D)
16. **단면도/입면도**: `generate_section_view`, `generate_elevation_view`
17. **물량 확인**: `generate_quantity_report`로 면적표/물량 산출
18. **프로젝트 정보**: `set_project_info`로 설계자/회사명 입력 (도면 출력 시 제목란에 표시)
19. **도면 출력**: `export_drawing`으로 PDF/SVG/DXF 출력
20. **반복 수정**: 사용자 피드백 반영 (실수 시 `undo`로 되돌리기, `copy_floor`로 층 복사)

## 좌표계

- (0,0)이 좌하단, x는 오른쪽, y는 위쪽
- 단위: 미터(m)
- 방이 같은 변을 공유하면 자동으로 내벽 생성

## 방 배치

### 직사각형 방 (기존 호환)
```json
{"name": "거실", "type": "living", "x": 0, "y": 0, "width": 6, "depth": 5}
```

### 다각형 방
`vertices`로 꼭짓점을 시계/반시계 방향으로 나열:
```json
{"name": "L자형 거실", "type": "living", "vertices": [[0,0],[8,0],[8,3],[4,3],[4,6],[0,6]]}
```
- 삼각형, L자, 사다리꼴 등 자유 형태 가능
- 최소 3개 꼭짓점 필요
- 면적은 자동 계산 (Shoelace formula)

### 예시: 일반 주택 배치
```
거실: x=0, y=0, width=6, depth=5
주방: x=6, y=0, width=4, depth=5
침실1: x=0, y=5, width=5, depth=4
침실2: x=5, y=5, width=5, depth=4
```

## 방 타입
living(거실), bedroom(침실), kitchen(주방), bathroom(욕실), dining(식당), garage(차고), hallway(복도), closet(수납), office(서재), laundry(세탁실), balcony(발코니), entrance(현관), stairs(계단), storage(창고)

## 계단

다층 건물의 층간 이동을 위한 계단:

```json
{"action": "add_stairs", "floor_id": "floor_1", "element": {
  "name": "메인 계단", "type": "straight",
  "start": [8, 2], "direction": 0, "width": 1.0,
  "num_treads": 15, "tread_depth": 0.28,
  "handrail": "both", "connects_to": "floor_2"
}}
```

### 계단 타입
- **straight** - 직선 계단. 가장 기본적인 형태
- **l_shape** - L자 계단. 중간에 90도 꺾임 + 랜딩
- **u_turn** - U턴 계단. 180도 되돌아감 + 랜딩
- **spiral** - 나선형 계단. 원형으로 회전하며 올라감
- **winder** - Winder 계단. 직선 + 부채꼴 꺾임 + 직선

### 계단 옵션
- `start`: [x, y] 시작점 좌표
- `direction`: 진행 방향. 0(+Y), 90(+X), 180(-Y), 270(-X)
- `width`: 계단 폭 (최소 0.8m, 기본 1.0m)
- `num_treads`: 디딤판 수 (최소 3, 기본 15)
- `tread_depth`: 디딤판 깊이 (최소 0.22m, 기본 0.28m)
- `riser_height`: 챌면 높이 (미지정 시 층고/디딤판수로 자동 계산)
- `landing_depth`: 랜딩 깊이 (L자/U턴용, 기본 1.0m)
- `turn_direction`: 꺾이는 방향 "left" 또는 "right" (L자/U턴용)
- `handrail`: "both", "left", "right", "none"
- `connects_to`: 연결 층 ID (예: "floor_2")

### 나선형 계단 (spiral)
```json
{"action": "add_stairs", "floor_id": "floor_1", "element": {
  "name": "나선 계단", "type": "spiral",
  "center": [5, 5], "radius": 1.5, "inner_radius": 0.2,
  "num_treads": 12, "total_angle": 360,
  "rotation": "cw", "handrail": "outer", "connects_to": "floor_2"
}}
```
- `center`: [x, y] 중심점 좌표
- `radius`: 외경 반지름 (최소 0.8m, 기본 1.5m)
- `inner_radius`: 내경 반지름 (기본 0.15m, radius보다 작아야 함)
- `total_angle`: 회전 각도 (90~720도, 기본 360)
- `rotation`: 회전 방향 "cw"(시계) 또는 "ccw"(반시계)
- 외측 디딤판 폭이 0.22m 이상이어야 합니다

### Winder 계단
```json
{"action": "add_stairs", "floor_id": "floor_1", "element": {
  "name": "Winder 계단", "type": "winder",
  "start": [2, 0], "direction": 0, "width": 1.0,
  "num_treads": 12, "tread_depth": 0.28,
  "winder_count": 3, "turn_angle": 90,
  "turn_direction": "left", "connects_to": "floor_2"
}}
```
- `winder_count`: 꺾임부 부채꼴 디딤판 수 (2~4, 기본 3)
- `turn_angle`: 꺾임 각도 (90 또는 180, 기본 90)
- 직선 구간 + 부채꼴 꺾임 + 직선 구간으로 구성됩니다
- 랜딩 없이 부채꼴 디딤판으로 방향 전환

## 발코니 난간

방 타입이 `balcony`이면 자동으로 난간이 추가됩니다:

```json
{"action": "add_room", "element": {
  "name": "발코니", "type": "balcony", "x": 0, "y": 8, "width": 4, "depth": 2,
  "railing": {"height": 1.1, "type": "glass"}
}}
```

### 난간 타입
- **metal** - 금속 난간 (기본값). 수평 레일 + 수직 발루스터
- **glass** - 유리 난간. 투명 패널 + 금속 캡
- **wood** - 목재 난간. 수평 레일 + 수직 발루스터

## 구조 요소

### 기둥
```json
{"action": "add_column", "element": {"x": 2, "y": 2, "width": 0.4, "depth": 0.4, "shape": "round"}}
```

### 보
```json
{"action": "add_beam", "element": {"start": [2, 2], "end": [10, 2], "width": 0.3, "depth": 0.5}}
```

## 축선 그리드 (v4.2 신규)

구조 축선(Grid Line)을 설정하고, 축선 교차점에 기둥을 자동 배치합니다. 2D 평면도에 빨간 점선 축선과 원형 번호가 표시됩니다.

### 축선 설정 (간격 기반)
X/Y 방향 간격 배열로 축선을 자동 생성합니다:
```json
{"action": "set_column_grid", "design_id": "design_xxx", "element": {
  "x_spacings": [6, 6, 6],
  "y_spacings": [4, 4],
  "origin": [0, 0]
}}
```
- `x_spacings`: X방향 간격 배열 → X1(0), X2(6), X3(12), X4(18) 축선 생성
- `y_spacings`: Y방향 간격 배열 → Y1(0), Y2(4), Y3(8) 축선 생성
- `origin`: 기준점 (기본 [0,0])

### 축선 설정 (직접 지정)
축선을 직접 지정할 수도 있습니다:
```json
{"action": "set_column_grid", "design_id": "design_xxx", "element": {
  "x_axes": [{"label": "A", "value": 0}, {"label": "B", "value": 6}, {"label": "C", "value": 12}],
  "y_axes": [{"label": "1", "value": 0}, {"label": "2", "value": 5}]
}}
```

### 축선 교차점에 기둥 자동 배치
```json
{"action": "auto_place_columns_on_grid", "floor_id": "floor_1", "element": {
  "size": [0.4, 0.4], "shape": "rect", "material": "concrete",
  "exclude_intersections": ["X3-Y2"]
}}
```
- `size`: 기둥 크기 [폭, 깊이] (기본 [0.4, 0.4])
- `shape`: "rect" 또는 "round" (기본 "rect")
- `exclude_intersections`: 제외할 교차점 목록 (예: "X1-Y1")

### 내력벽 지정
```json
{"action": "set_load_bearing_wall", "floor_id": "floor_1", "element": {
  "wall_ids": ["wall_1", "wall_3"], "is_load_bearing": true
}}
```

## 벽 시스템 (v4 신규)

`auto_walls` 외에 수동으로 벽을 추가/관리할 수 있습니다.

### 커스텀 벽 추가
```json
{"action": "add_wall", "floor_id": "floor_1", "element": {
  "start": [0, 0], "end": [6, 0], "thickness": 0.2,
  "wall_type": "custom", "material": "brick", "is_load_bearing": true
}}
```

### 원호 벽 (곡선)
```json
{"action": "add_wall", "floor_id": "floor_1", "element": {
  "wall_type": "curved",
  "curve": {"center": [5, 5], "radius": 3, "start_angle": 0, "end_angle": 90},
  "thickness": 0.2, "material": "concrete"
}}
```
- `center`: 원호 중심점
- `radius`: 반경 (m)
- `start_angle`/`end_angle`: 시작/끝 각도 (도, 반시계 방향)
- 원호 벽은 여러 직선 세그먼트로 근사됩니다

### 이중벽 (단열)
```json
{"action": "add_wall", "floor_id": "floor_1", "element": {
  "wall_type": "double",
  "start": [0, 0], "end": [10, 0],
  "outer_thickness": 0.1, "inner_thickness": 0.1,
  "insulation": {"thickness": 0.05, "material": "insulation"}
}}
```

### 벽 삭제
```json
{"action": "remove_wall", "floor_id": "floor_1", "element": {"id": "wall_5"}}
```
> 해당 벽에 문/창문이 있으면 경고 메시지가 표시됩니다

### 벽 이동
좌표 직접 지정 또는 오프셋 이동:
```json
{"action": "move_wall", "floor_id": "floor_1", "element": {
  "id": "wall_3", "dx": 1.0, "dy": 0
}}
```
또는:
```json
{"action": "move_wall", "floor_id": "floor_1", "element": {
  "id": "wall_3", "new_start": [1, 0], "new_end": [7, 0]
}}
```

### 벽 수정
```json
{"action": "modify_wall", "floor_id": "floor_1", "element": {
  "id": "wall_3", "thickness": 0.25, "material": "concrete", "is_load_bearing": true
}}
```

### 벽 분할
벽을 특정 위치에서 두 개로 나눕니다:
```json
{"action": "split_wall", "floor_id": "floor_1", "element": {
  "id": "wall_3", "split_position": 0.5
}}
```
- `split_position`: 0.0~1.0 비율 (벽 시작에서 끝까지)
- 또는 `split_point: [3, 0]`으로 좌표 직접 지정

## 레이어 관리 (v4 신규)

도면의 요소별 가시성과 스타일을 제어합니다. 2D 평면도에서 특정 요소를 숨기거나 강조할 수 있습니다.

### 기본 레이어
| 레이어 ID | 이름 | 설명 |
|-----------|------|------|
| walls | 벽 | 외벽/내벽 |
| doors | 문 | 문 심볼 |
| windows | 창문 | 창문 심볼 |
| furniture | 가구 | 가구 심볼 |
| dimensions | 치수 | 치수선/치수 텍스트 |
| labels | 라벨 | 방 이름/면적 라벨 |
| structure | 구조 | 기둥/보 |
| stairs | 계단 | 계단 심볼 |
| grid | 그리드 | 배경 격자 |
| rooms | 방 (배경색) | 방 배경 채우기 |

### 레이어 조회
```json
{"action": "get_layers", "design_id": "design_xxx"}
```

### 레이어 가시성 설정
단일 레이어:
```json
{"action": "set_layer_visibility", "design_id": "design_xxx", "element": {
  "layer_id": "furniture", "visible": false
}}
```

여러 레이어 한번에:
```json
{"action": "set_layer_visibility", "design_id": "design_xxx", "element": {
  "layer_ids": ["furniture", "dimensions", "grid"], "visible": false
}}
```

### 레이어 스타일 설정
```json
{"action": "set_layer_style", "design_id": "design_xxx", "element": {
  "layer_id": "grid", "color": "#AAAAAA", "lineweight": 0.5, "opacity": 0.2
}}
```
- `color`: hex 색상 (해당 레이어 전체에 적용)
- `lineweight`: 선 두께
- `opacity`: 투명도 (0.0 투명 ~ 1.0 불투명)

### 레이어 프리셋
자주 쓰는 레이어 조합을 한번에 적용:
```json
{"action": "apply_layer_preset", "design_id": "design_xxx", "element": {
  "preset": "presentation"
}}
```

| 프리셋 | 설명 |
|--------|------|
| all_on | 모든 레이어 표시 |
| structure_only | 벽+기둥+보+계단만 (구조 검토용) |
| presentation | 가구+라벨+방 포함, 치수/그리드 숨김 (프레젠테이션용) |
| dimensions_only | 벽+치수+라벨만 (치수 검토용) |

### 레이어 활용 팁
- **시공 도면**: `structure_only` → 구조 요소만 표시하여 시공사에 전달
- **인테리어**: 가구와 방 배경만 보이게 → 인테리어 배치 검토
- **치수 검토**: `dimensions_only` → 치수와 벽만 표시하여 깔끔한 치수 도면
- **프레젠테이션**: `presentation` → 클라이언트에게 보여줄 깔끔한 도면

## 재질 시스템

### 사용 가능한 벽 재질
brick(벽돌), concrete(콘크리트), wood(목재), glass(유리), stone(석재), stucco(스터코), metal(금속), tile(타일)

### 벽 재질 설정
```json
{"action": "set_wall_material", "element": {"wall_type": "exterior", "material": "brick"}}
```

### 외벽 기본 재질
```json
{"action": "set_facade_defaults", "element": {"material": "brick", "color": "#B85C38"}}
```

## 방 마감재 (v4.2 신규)

방별로 바닥재, 벽마감, 천장마감, 천장고를 설정할 수 있습니다. 2D 평면도에서 바닥재 해칭이 표시됩니다.

### 방 추가 시 자동 기본값
방 타입에 따라 기본 마감재가 자동 적용됩니다:
| 방 타입 | 바닥재 | 벽마감 | 천장마감 | 천장고 |
|---------|--------|--------|----------|--------|
| bedroom/living_room/hallway | wood | paint | paint | 2.4m |
| kitchen/bathroom | tile | tile | paint | 2.3~2.4m |
| balcony | tile | paint | paint | 2.4m |
| storage/other | concrete | paint | paint | 2.4m |

### 방 추가 시 마감재 지정
```json
{"action": "add_room", "element": {
  "name": "거실", "type": "living_room", "x": 0, "y": 0, "width": 6, "depth": 5,
  "floor_material": "marble", "wall_finish": "wallpaper", "ceiling_height": 2.7
}}
```

### 마감재 일괄 설정
특정 방 또는 전체 방에 마감재를 한번에 설정합니다:
```json
{"action": "set_room_finishes", "floor_id": "floor_1", "element": {
  "room_ids": ["room_1", "room_2"],
  "floor_material": "wood", "wall_finish": "paint"
}}
```
`room_ids`를 생략하면 해당 층 전체 방에 적용됩니다.

### 바닥재 해칭 (2D)
2D 평면도에서 바닥재별 해칭 패턴이 표시됩니다:
- **wood** - 사선 빗금 (//)
- **tile** - 격자 (++)
- **marble** - X자 (xx)
- **stone** - 점 (..)
- **carpet** - 원형 (oo)
- **concrete** - 패턴 없음

## 지붕

```json
{"action": "set_roof", "element": {"type": "gable", "height": 2.5, "direction": "x", "overhang": 0.3}}
```

### 지붕 타입
- **hip** - 사방 경사 (기본값)
- **gable** - 박공 지붕
- **flat** - 평지붕
- **mansard** - 맨사드 지붕
- **gable_glass** - 유리 박공

## 필로티

```json
{"action": "set_floor_piloti", "floor_id": "floor_1", "element": {"is_piloti": true, "piloti_height": 3.5}}
```

## 건물 프로파일

```json
{"action": "set_floor_profile", "floor_id": "floor_3", "element": {"offset_x": 1.0, "offset_y": 0}}
```

## 문/창문

- `wall_id`: `auto_walls` 후 `get_house_design`으로 벽 ID 확인
- `position`: 벽 시작점에서의 거리 (미터)
- 문 타입: single(기본), double(양개), sliding(미닫이)
- 창문: `width`, `height`, `sill_height` 지정 가능

### 좌표 기반 문/창문 배치 (v4.2)
`wall_id` 대신 좌표로 문/창문을 배치할 수 있습니다. 가장 가까운 벽을 자동으로 찾아 스냅합니다:
```json
{"action": "add_door", "floor_id": "floor_1", "element": {
  "x": 3, "y": 0, "width": 0.9, "type": "single", "swing": "in"
}}
```
- `x`, `y`: 배치 좌표 (가장 가까운 벽에 자동 스냅)
- `swing`: 열림 방향 "in"(안쪽), "out"(바깥), "left", "right"

### 창문 연속 배치 (v4.2)
한 벽에 등간격으로 여러 창문을 한번에 추가합니다:
```json
{"action": "add_window_batch", "floor_id": "floor_1", "element": {
  "wall_id": "wall_3", "count": 4, "width": 1.2, "height": 1.5,
  "sill_height": 0.9, "spacing": 0.5
}}
```
- `count`: 창문 수
- `spacing`: 창문 간 간격 (미터)
- 벽 길이가 부족하면 오류 반환

### 개구부 검증 (v4.2)
문/창문 겹침을 자동으로 검사합니다:
```json
{"action": "validate_openings", "floor_id": "floor_1"}
```
겹치는 개구부가 있으면 경고를 반환합니다.

## 가구 타입
sofa, bed_single, bed_double, bed_queen, bed_king, dining_table, desk, wardrobe, bookshelf, tv_stand, toilet, bathtub, shower, sink, kitchen_sink, stove, refrigerator, washing_machine, chair, coffee_table

## 복사/미러/배열 (v4.2 신규)

방과 층을 효율적으로 복제하는 기능입니다.

### 방 복사
```json
{"action": "copy_room", "floor_id": "floor_1", "element": {
  "source_id": "room_1", "dx": 6, "dy": 0, "new_name": "침실2"
}}
```
- `source_id`: 원본 방 ID
- `dx`, `dy`: 이동 거리 (기본 0)
- `new_name`: 새 이름 (생략 시 원본명 + " (복사)")

### 미러 복사
지정 축을 기준으로 방들을 대칭 복사합니다:
```json
{"action": "mirror_rooms", "floor_id": "floor_1", "element": {
  "room_ids": ["room_1", "room_2"],
  "axis": "x", "axis_value": 10,
  "new_names": ["침실3", "침실4"]
}}
```
- `axis`: "x"(수직축) 또는 "y"(수평축)
- `axis_value`: 대칭축 위치 (미터)
- `new_names`: 새 이름 목록 (생략 시 자동 생성)

### 배열 복사
한 방을 일정 간격으로 반복 복사합니다:
```json
{"action": "array_copy", "floor_id": "floor_1", "element": {
  "source_id": "room_1", "dx": 5, "dy": 0, "count": 3,
  "naming": "number"
}}
```
- `count`: 복사 수 (원본 제외)
- `dx`, `dy`: 각 복사본 간 간격
- `naming`: "number"(1,2,3) 또는 "letter"(A,B,C) 접미사

### 층 복사
```json
{"action": "copy_floor", "design_id": "design_xxx", "element": {
  "source_floor_id": "floor_1", "new_level": 2, "new_name": "2층",
  "include_furniture": false
}}
```
- `source_floor_id`: 원본 층 ID
- `new_level`: 새 층 레벨 (기본: 원본+1)
- `include_furniture`: 가구 포함 여부 (기본 true)

## 단면도 (v4 신규)

`generate_section_view` 도구로 건물 횡단면을 생성합니다.

### 사용법
절단선의 시작점과 끝점을 평면 좌표로 지정합니다:
```json
{"tool": "generate_section_view", "params": {
  "design_id": "design_xxx",
  "cut_start": [5, 0],
  "cut_end": [5, 10],
  "view_direction": "right",
  "show_dimensions": true
}}
```

### 절단선 지정 팁
- 건물 중앙을 Y축 방향으로 자르기: `cut_start: [5, 0], cut_end: [5, 15]`
- 건물 중앙을 X축 방향으로 자르기: `cut_start: [0, 5], cut_end: [20, 5]`
- 대각선 절단도 가능

### 표시 항목
- 절단된 벽체 (재질별 해칭)
- 층 슬라브 (두꺼운 선)
- 계단 단면 (디딤판/챌판 지그재그)
- 창문 (sill height/head height 표시)
- 문 개구부
- 지붕 프로파일
- GL(지반선)/FL(층 레벨) 마커
- 층고 치수

## 입면도 (v4 신규)

`generate_elevation_view` 도구로 건물 외관 투영도를 생성합니다.

### 사용법
4방향 중 하나를 선택합니다:
```json
{"tool": "generate_elevation_view", "params": {
  "design_id": "design_xxx",
  "direction": "front",
  "show_dimensions": true
}}
```

### 방향
- **front** - 정면도 (전면, -Y 방향에서 봄)
- **rear** - 배면도 (후면, +Y 방향에서 봄)
- **left** - 좌측면도 (-X 방향에서 봄)
- **right** - 우측면도 (+X 방향에서 봄)

### 표시 항목
- 외벽 윤곽선 + 재질 해칭
- 창문 (십자 분할선 포함)
- 문 (패널 표현)
- 지붕 프로파일
- 지반선 (GL)
- 층 레벨선 (점선)
- 전체 폭/높이 치수
- FL 레벨 마커

## 사용자 지정 치수선 (v4 신규)

평면도에 직접 치수선을 추가할 수 있습니다:

### 치수선 추가
```json
{"action": "add_dimension", "floor_id": "floor_1", "element": {
  "start": [0, 0], "end": [6, 0], "offset": 0.5, "label": ""
}}
```
- `start`/`end`: 측정할 두 점의 좌표
- `offset`: 치수선이 측정선에서 떨어진 거리 (기본 0.5m)
- `label`: 커스텀 텍스트 (비우면 자동 길이 표시)

### 치수선 제거
```json
{"action": "remove_dimension", "floor_id": "floor_1", "element": {"id": "dim_1"}}
```

## 면적표/물량 산출

`generate_quantity_report` 도구로 다양한 보고서를 생성합니다:

### 보고서 타입
- **full_report** - 종합 보고서 (면적표 + 건폐율/용적률 + 벽체/창호/바닥 물량)
- **area_schedule** - 층별 방 면적 일람표
- **coverage_ratio** - 건폐율 (1층 바닥면적 / 대지면적 x 100)
- **floor_area_ratio** - 용적률 (연면적 / 대지면적 x 100)
- **wall_schedule** - 벽 타입별 길이/면적 물량표
- **door_schedule** - 문 일람표 (타입, 폭, 수량)
- **window_schedule** - 창호 일람표 (규격, 수량)
- **flooring** - 바닥재별 소요량

### 예시
```json
{"tool": "generate_quantity_report", "params": {
  "design_id": "design_xxx", "report_type": "full_report"
}}
```

특정 층만:
```json
{"tool": "generate_quantity_report", "params": {
  "design_id": "design_xxx", "report_type": "area_schedule", "floor_id": "floor_1"
}}
```

## 프로젝트 정보 (v4 신규)

도면 출력 시 제목란에 표시될 프로젝트 정보를 설정합니다:

```json
{"action": "set_project_info", "design_id": "design_xxx", "element": {
  "project_name": "강남 주택 프로젝트",
  "designer": "홍길동",
  "company": "좋은건축사무소"
}}
```

### 설정 가능 항목
- `project_name` - 프로젝트명
- `designer` - 설계자 이름
- `company` - 회사/사무소명
- `north_direction` - 북향 방향 (각도, 기본 0)

## 도면 출력 (v4 신규)

`export_drawing` 도구로 설계를 PDF, SVG, DXF 파일로 출력합니다.

### PDF 출력 (다중 페이지)

평면도, 단면도, 입면도를 한 PDF에 모아 출력합니다:
```json
{"tool": "export_drawing", "params": {
  "design_id": "design_xxx",
  "format": "pdf",
  "paper_size": "A3",
  "scale": "1:100",
  "include_title_block": true,
  "include_area_table": true,
  "include_sections": true,
  "section_cuts": [[[5, 0], [5, 15]]],
  "include_elevations": true,
  "elevation_directions": ["front", "right"]
}}
```

#### PDF 옵션
- `paper_size`: "A4", "A3", "A2", "A1" (기본 A3)
- `scale`: "1:50", "1:100", "1:200" (기본 1:100)
- `include_title_block`: 제목란 포함 (기본 true)
- `include_area_table`: 면적표 포함 (기본 true)
- `floor_ids`: 출력할 층 목록 (생략 시 전체)
- `include_sections`: 단면도 포함 (기본 false)
- `section_cuts`: 절단선 목록 `[[[x1,y1],[x2,y2]], ...]`
- `include_elevations`: 입면도 포함 (기본 false)
- `elevation_directions`: 입면 방향 목록 ["front", "rear", "left", "right"]

### SVG 출력 (벡터)

단일 도면을 벡터 SVG로 출력합니다:
```json
{"tool": "export_drawing", "params": {
  "design_id": "design_xxx",
  "format": "svg",
  "drawing_type": "floor_plan",
  "floor_id": "floor_1"
}}
```

`drawing_type`으로 `floor_plan`, `section`, `elevation` 선택 가능.

### DXF 출력 (AutoCAD 호환)

AutoCAD에서 열 수 있는 DXF 파일로 출력합니다:
```json
{"tool": "export_drawing", "params": {
  "design_id": "design_xxx",
  "format": "dxf",
  "floor_id": "floor_1"
}}
```

#### DXF 레이어
- WALLS (외벽), WALLS_INT (내벽), DOORS (문), WINDOWS (창문)
- ROOMS (방 윤곽), FURNITURE (가구), COLUMNS (기둥)
- DIMENSIONS (치수), TEXT (텍스트)

> DXF 출력에는 `ezdxf` 라이브러리가 필요합니다: `pip install ezdxf`

### 제목란

PDF/SVG 출력 시 도면 하단에 제목란이 포함됩니다:
- 프로젝트명, 회사명
- 도면명, 설계자명
- 도면번호 (A-01, A-02... 자동 생성), 축척
- 날짜, 용지 크기

`set_project_info`로 프로젝트 정보를 설정해야 제목란이 올바르게 표시됩니다.

## Undo/Redo

모든 수정 작업은 자동으로 Undo 스택에 저장됩니다 (최대 50단계).

### 되돌리기
```json
{"action": "undo", "design_id": "design_xxx"}
```

### 다시 실행
```json
{"action": "redo", "design_id": "design_xxx"}
```

### 히스토리 확인
```json
{"action": "list_history", "design_id": "design_xxx"}
```

## 스냅샷

설계 상태를 명명 스냅샷으로 저장하여 나중에 복원하거나 비교할 수 있습니다.

### 스냅샷 저장
```json
{"action": "create_snapshot", "design_id": "design_xxx", "element": {"name": "1차 검토안"}}
```

### 스냅샷 복원
```json
{"action": "restore_snapshot", "design_id": "design_xxx", "element": {"name": "1차 검토안"}}
```

### 스냅샷 비교
```json
{"action": "compare_snapshots", "design_id": "design_xxx", "element": {"name_a": "1차 검토안", "name_b": "2차 수정안"}}
```

## 지붕 평면도 (v4.2)

`generate_floor_plan`으로 최상층 평면도를 생성하면, 설정된 지붕이 자동으로 평면도에 표시됩니다:
- 용마루선 (점선)
- 경사 방향 화살표
- 처마 돌출선
- 평지붕의 경우 옥상 이용 공간 표시

별도 호출 없이 `set_roof` 설정 후 최상층 평면도를 생성하면 자동 표시됩니다.

## 다층 건물 설계 팁

1. `create_house_design`에서 `floors` 파라미터로 층수 설정
2. 각 층은 `floor_1`, `floor_2`, ... ID 사용
3. `floor_id` 지정하여 특정 층에 방/기둥 추가
4. 1층 필로티 -> 기둥만, 2층부터 방 배치 패턴이 일반적
5. 계단은 1층에 `add_stairs` 호출 (connects_to로 연결 층 지정)
6. 좁은 공간에는 나선형(`spiral`), 랜딩 없이 꺾이려면 winder 계단 사용
7. 각 층마다 벽 자동 생성 (`auto_walls` 호출)
8. 발코니는 `type: "balcony"`로 추가하면 난간 자동 생성
9. 특수 벽(원호, 이중벽)은 `add_wall`로 수동 추가
10. 대규모 건물은 `set_column_grid` → `auto_place_columns_on_grid`로 구조 설정
11. 반복 방 배치는 `copy_room`/`array_copy`/`mirror_rooms` 활용
12. 비슷한 층은 `copy_floor`로 복사 후 수정
13. `set_room_finishes`로 방 마감재 일괄 설정
14. `add_window_batch`로 등간격 창문 빠르게 배치
15. `apply_layer_preset`으로 용도별 도면 출력 (구조, 프레젠테이션 등)
16. 설계 중간 중간 `create_snapshot`으로 상태 저장 권장
17. 완성 후 `generate_quantity_report`로 면적/물량 확인
18. `generate_section_view`로 단면 확인 (계단, 층고, 창문 위치)
19. `generate_elevation_view`로 4면 외관 확인 (재질, 지붕, 창문 배치)
20. `set_project_info`로 프로젝트 정보 설정
21. `export_drawing`으로 PDF/DXF 출력 (제목란+면적표 포함)

## 실제 건물 반영 팁

사용자가 실제 건물 사진을 제공할 때:
1. 층수, 대략적 크기 파악
2. 1층 필로티 여부 확인
3. 외벽 재질 판단 (벽돌/콘크리트/유리 등)
4. 지붕 형태 판단 (평지붕/박공/사방경사)
5. 특이 형태 방은 다각형 vertices로 표현
6. 구조 기둥이 보이면 add_column으로 추가
7. 층별 돌출/세트백은 set_floor_profile로 표현
8. 발코니가 있으면 balcony 타입 방 추가 (난간 자동)
9. 계단 위치 파악 후 add_stairs (좁은 공간에 나선형 계단 고려)
10. 마감재 설정: `set_room_finishes`로 바닥재/벽/천장 지정
11. 단면도로 층고/계단/창문 위치 검증
12. 입면도로 외관 재질/창문 배치 검증
13. PDF 도면 출력으로 납품/검토 자료 생성
