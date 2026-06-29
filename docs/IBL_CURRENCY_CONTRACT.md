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
