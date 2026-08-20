# IBL 통화 계약 (Producer Contract) — 새 어휘를 추가하는 사람을 위한 한 장

indiebizOS를 가져가 **자기 어휘(액션)·앱을 추가**할 때 읽는 단 하나의 규약. 이 한 장만
지키면 당신의 어휘가 변환자(`>>` filter/sort/…)·렌더러(앱/원격/폰)·수동/자율 모드 전부와
자동으로 맞물린다. 통화는 당신이 자주 쓰는 어휘에 기초하지 않는다 — 그래서 남이 받아 써도
기본이 흔들리지 않는다.

> 설계 근거: 통화는 인터넷의 IP, Unix의 파일처럼 **좁은 허리(narrow waist)**다. 허리가
> *논리적으로 약할수록*(약속이 적을수록) 위(어휘)도 아래(소비자)도 독립적으로 늘어난다.
> (Beck, "On The Hourglass Model", CACM 2019 — Deployment Scalability Trade-off.)

---

## 1. 계약은 하나뿐 — 컬렉션은 `items` 목록이다

목록·표·검색결과·매물 등 **무엇이든 돌려주는 액션**은 이렇게 낸다:

```python
from common.currency import items
return items(rows, message="...", success=True)   # → {"items": [ {…}, … ], ...}
```

- **구조적으로 강제되는 것은 바깥 한 겹 — `{"items": [ … ]}` 가 목록이라는 사실 — 뿐이다.**
- **항목(item) 내부는 전부 열린 관습이다.** title·meta·url 같은 표준 필드는 *권장*일 뿐
  강제가 아니다. 도메인마다 필드가 달라도 된다 — 소비자는 아는 필드만 읽고 모르면 건너뛴다.
- 필수 필드 레지스트리·스키마 강제는 **두지 않는다.** 그것이 통화가 N개로 늘며 더러워지던
  병의 뿌리였다. (Postel의 법칙 / Tolerant Reader: "받을 땐 관대하게, 낼 땐 엄격하게.")

`table`(columns/rows)이나 단일값을 내고 싶어도 **별도 통화를 만들지 마라.** table은 items의
파생 뷰이고(소비자가 items→table 재구성), 단일값은 길이 1 items다.

## 2. 기계가 읽을 값은 *평평한 필드*에 둔다

변환자(filter/sort/groupby/…)는 도메인을 모른 채 `item.get("필드명")`으로 값을 직접 짚는다.
그러니 **걸러지거나 정렬될 값은 item의 평평한 필드로 노출하라.**

```python
{"title": "신현대12차", "법정동": "압구정동", "거래금액": "1,100,000", "전용면적": "182.95"}
#  →  >> filter{where:"거래금액 >= 500000"} >> sort{by:"거래금액"} >> take{n:3}  이 그냥 동작
```

값을 문장(summary) 속에 묻으면 변환자가 못 짚는다. 이것이 통화가 보장하는 것의 경계다:
**구조적 상호운용(어떤 변환자든 어떤 items 위에서 돈다)은 보장하나, 의미적 상호운용
(한 사람의 `price`와 다른 사람의 `거래금액`이 같은 뜻인지)은 보장하지 않는다.** 후자를 강제하면
다시 N개 통화의 병으로 돌아간다. 필드명 드리프트는 자유 확장의 *받아들인 비용*이다.

## 3. 통화가 *아닌 것* — 손대지 마라

| 종류 | `returns` | 통화? | 규칙 |
|---|---|---|---|
| 컬렉션(목록·표·검색결과) | `items` | ✅ 유일한 통화 | `items(rows)` 로 감싼다 |
| 단일 효과(저장·전송·토글) | `effect` | ❌ | 통화 아님. items로 위장하지 마라 |
| 단일 스칼라(시각·가격 하나) | `scalar` | ❌ | 통화 아님 |
| 변환자 자신(filter/sort/…) | `transform` | — | 같은 통화 in→out |

**`returns` enum은 닫혀 있다: `{items, transform, scalar, effect}`.** 새 액션은 이 넷 중
하나를 선언만 하면 되고, 새 통화 *종류*를 더할 길은 없다(그게 안정성의 핵심).

### ★ map_data / route geometry = 통화가 아니다 (의도적 제외)

지도(부동산 매물 위치, 길찾기 경로, CCTV 핀)는 **통화로 접지 않는다.** 봉투 구조가 생산자마다
다르고(위치=markers / 경로=origin·destination·route geometry / center·zoom), 균일한 item
구조로 환원되지 않으며, **지도 위젯이 봉투를 직접 읽는다.** 그래서 `derive_items`는 map_data를
일부러 건드리지 않는다(`backend/common/currency.py` 참조).

> **이것은 미완성 마이그레이션이 아니다 — 정직한 평면 분리다.** 데이터 평면과 상호작용/지리
> 평면은 다른 평면이고, 어떤 단일 데이터 통화(items든 HTML이든)로도 접히지 않는다. map_data를
> items로 "고치려" 들지 마라. 지도를 내는 액션은 `returns: scalar`(또는 items)를 선언하고
> 봉투에 `map_data` 필드를 함께 실으면 된다 — 지도 위젯이 그 필드를 읽는다.

## 3-2. 거울 키는 변환을 따라간다 (2026-08-20, B15-1)

생산자가 `items` 와 **같은 리스트**를 도메인 이름으로도 병기하는 관행이 있다(`items 병행 방출`
— `[self:trigger]{op:"list"}` 의 `triggers`, `self:switch` 의 `switches`, `others:agents`,
`[limbs:guestpc]` 의 `limbs` 등). 그래야 `>> [table:*]` 가 통화를 찾는다.

**규약: 변환자는 그 거울 키를 변환 결과로 함께 갱신한다.** 구현은 생산자마다가 아니라
병목 하나 — `data-ops` 의 `_reproject_mirrors`(`_emit_items`/`_emit_table`) — 에 있고,
판정은 이름 목록이 아니라 **동일성**(객체 is → 값 == 폴백)이다. 그러므로 **새 병행 방출은
아무것도 안 해도 이 규약을 상속한다**(생산자 7곳을 각각 고치면 8번째가 다시 감염된다).

- 종류가 다른 형제 원장(trigger list 의 `existing_schedules`)은 원본과 다른 리스트이므로
  손대지 않는다 — 합치는 것은 통화 수리가 아니라 의미 결정이다.
- 재투영이 일어나면 봉투에 `_mirrored: [키…]` 표식이 남는다. 자가점검 §1C-3 이 이 계수를
  압력계로 읽는다 — **재투영은 거울 키를 마음껏 만들어도 된다는 면허가 아니다**(하우스
  교리는 여전히 단일 통화 `{items}`).
- 사건: `[self:trigger]{op:"list"} >> [table:take]{n:1}` 이 `items` 는 1건으로 줄이면서
  `triggers` 에 3건을 남겨 "take(1) 했는데 전 건이 나온다"로 읽혔다. 변환자는 일했고
  **봉투가 거짓말을 했다**. 배터리=`backend/test_table_mirror_keys.py`.

**재투영이 못 미치는 형제 컬렉션은 `_untransformed` 로 자백한다** (2026-08-20 판정).
두 부류가 있고 둘 다 기계가 대신 정할 수 없다 — ①종류가 다른 형제 원장(`existing_schedules`)은
애초에 변환 대상이 아니고 ②**파생 원천**(`others:agents` 의 `projects` 트리 — items 는 이걸
*펼쳐서* 만든 것)은 평평한 items 로 되돌릴 수 없어 재투영이 원리적으로 불가능하다.

> 그래서 드롭도 재투영도 아닌 **세 번째 답**을 쓴다: 봉투가 "이 키들은 변환 전 상태"라고
> 적는다. B15-1 의 실제 피해는 데이터가 아니라 **오독**(도메인 이름을 통화로 읽는 것)이었고,
> 자백은 그 오독만 막으면서 데이터는 하나도 안 버린다. 드롭은 표면 소비자를 깨뜨리고,
> 침묵은 거짓말을 남긴다. 조건=비어 있지 않고 dict 를 담은 리스트(스칼라 리스트·빈 리스트는
> 통화로 오독될 일이 없어 자백하지 않는다 — 자백이 잡음이 되면 아무도 안 읽는다).

## 4. 틀려도 안전하다 — 실패는 국소적·시끄럽다

- **정의 시점**: `python3 scripts/build_ibl_nodes.py --check` 가 src↔tool.json↔handler의
  삼각 정합(op enum·`_OP_DISPATCHERS`·`returns` 누락)을 AST로 검사. 어긋나면 RED + 
  `ibl_nodes.yaml` 작성 **보류**. pre-commit 훅 + 12시간 self-check 양쪽에 걸린다.
- **실행 시점**: 잘못된 통화는 조용히 빈 결과로 퍼지지 않고 **호출 단위 에러 dict**로 끝난다
  (예: `{"error": "filter: 입력에서 records/table 통화를 찾지 못했습니다."}`). 공유 시스템은
  안 죽는다.

## 5. 새 어휘 추가 = 순수 추가형

1. `data/packages/installed/tools/<패키지>/` 폴더 드롭 (`tool.json` + `handler.py`)
2. `data/ibl_nodes_src/<node>.yaml` 에 액션 블록 추가 (`returns:` 포함; 앱이 필요하면 `app:` 블록)
3. `python3 scripts/build_ibl_nodes.py` 로 `ibl_nodes.yaml` 재생성 → `--check`
4. `/packages/reload` (핸들러 라이브) — backend/*.py 는 안 건드린다

**backend의 enum·switch·레지스트리를 편집할 일이 없다.** 런타임은 yaml을 동적 lookup하고,
빌드는 노드 파일을 바이트 단위로 이어 붙이므로 — *당신의 어휘 추가가 남의 기본 어휘 바이트를
흔들지 않는다.* 렌더 프리미티브 12종(card_list·kv·metric·image_grid·thread·form·map…)은
도메인 무관이라 **새 렌더러를 만들 필요도 없다** — `app.view`에서 선언만 하면 전 표면에 등장한다.

---
*단일 통화 이행은 2026-06-27 컷오버 완료(records 생산자 0). 이 문서는 그 종착의 생산자측 계약이다.
관련: `backend/common/currency.py`(생성자·derive_items), `docs/SINGLE_CURRENCY_MIGRATION_HANDOFF.md`(이행 이력).*
