# 다중 노드 토폴로지 설계 (MULTINODE_TOPOLOGY_DESIGN)

> 작성 2026-06-17. **여러 대의 기기(특히 폰 2대 이상)에서 indiebizOS가 돌 때**의 노드 정체성·라우팅·주소지정·동기화 설계. 사용자 제기("폰 2대를 깔면?")에 대한 확정 설계. 구현 전 합의 문서.
>
> 관련 메모: substrate/superstructure 이음매(헌법1조) · 폰-맥 라우팅(chokepoint 빌림) · 두 독립 자아(detect_body) · 네 번째 문제의식(두 번째 노드=병목).

---

## 0. 범위 (이번 설계 = Stage 1)

- **소유자 1명 가정.** 한 사용자가 기기를 여러 대(맥 + 폰1 + 폰2 …) 쓰는 경우.
- **다중 사용자(나 + 아내, 2+ npub)는 Stage 2로 명시 연기.** 다른 npub = 신뢰 경계 발생 → 허가/grant 층, 노드 간 프롬프트 인젝션 방어, 결과 신뢰, 책임·비용. 전부 Stage 2. 단일 사용자는 전부 **self-trust**라 이 층을 통째로 건너뜀 = 완벽한 시작점.
- **목표**: 기기가 늘어도 (a) 서로 구분되고 (b) 능력 라우팅이 올바른 기기를 고르고 (c) 모호하면 사용자에게 묻고 (d) 한쪽 폰이 다른 폰의 액션(예: 위치)을 명시적으로 호출할 수 있다.

---

## 1. 현재 상태 (코드 검증, 2026-06-17)

**결론: 능력 기반 단일-피어 점대점(point-to-point).** 기기가 1대씩이라는 가정이 코드 전반에 박혀 있음.

### 1.1 라우팅은 능력(`runs_on`) 축, 주소는 단수 env
- 라우팅 결정 단일 지점 = `backend/ibl_engine.py:538`.
  - `if not _phone_runnable(node, action): return _forward_to_mac(...)` — 폰서 못 도는 액션 → **그** 맥.
  - `ibl_engine.py:560` `if runs_on=="phone_only" and PROFILE!="phone": _forward_to_phone(INDIEBIZ_PHONE_URL, ...)` — 폰 전용 → **그** 폰.
- 주소는 방향당 **단수 환경변수**:
  - 맥→폰: `INDIEBIZ_PHONE_URL`(단수) — `ibl_engine.py:562`
  - 폰→맥: `INDIEBIZ_MAC_URL`(단수) — `ibl_engine.py:206`
- 포워드 함수: `_forward_to_phone(phone_url, ...)`(`:142`) · `_forward_to_mac(...)`(`:194`, env 직접 read). 둘 다 **단일 대상** 전제.
- `_phone_runnable`(`:124`)은 `data/phone_manifest.json`의 `runnable_actions` 화이트리스트만 봄 — 능력 판정이지 기기 판정 아님.
- `runs_on` 분포(컴파일된 `data/ibl_nodes.yaml`): `anywhere` 14 · `mac_only` 32 · `phone_only` 4. (값은 `data/ibl_nodes_src/`가 정본.)

### 1.2 인증·신원 메커니즘
- 기기 간 인증: 맥→폰 `X-Phone-Token`(대칭키 `INDIEBIZ_PHONE_TOKEN`, hmac, `ibl_engine.py:163`) / 폰→맥 런처세션 비번.
- 행위 주체: `agent_id` 문자열을 페이로드에 전파(`ibl_engine.py:158, 216`). 빌림은 호출자가 주체(설계결정 §6.4).

### 1.3 `node_registry.py`는 물리 기기 노드가 아님
- "Everything is a Node"지만 여기서 노드 = **논리 노드**(sense/self/limbs/others/engines + 에이전트). 라우팅에 미참여(`_discover_nodes` 어휘 탐색만).

### 1.4 npub은 기기 조율에 무관 — *대외* 신원 전용
- `npub`/`pubkey` grep: `ibl_engine.py`·`api_ibl.py`·`ibl_routing.py`에서 **0건**.
- npub은 `backend/indienet.py`의 `identity.json {npub,nsec,private_key_hex}`로, **Nostr DM(NIP-17)·feed·board 서명**(대외 통신)에만 쓰임.
- **시스템 전체에 npub 1개, 맥에 위치.** 폰엔 nostr 키 없음 — `provision_phone_keys.py`가 데이터 API 키 + 맥 위임 설정만 주입, `nsec`/`npub` **의도적 제외**.

---

## 2. 핵심 설계 원칙

### 원칙 A — 노드는 하드웨어를 포함한다
능력 기반(`phone_only`)은 "한 능력 = 한 기기"가 당연하던 단일-HW 시절의 잔재. 기기가 늘면 서로 구분 필요.

### 원칙 B — 능력(capability)과 인스턴스(instance)는 직교 (★)
`phone_only`은 두 가지를 뭉쳐 있었다:
1. **능력 요구** — "GPS/마이크/카메라 같은 몸이 필요" (폰2도 GPS 있음 → 폰1 전용 아님)
2. **(암묵) 인스턴스** — "그런 몸이 1대뿐이라 곧 그 기기"

**위치 문의 예시가 이 분리를 증명**: "GPS 필요"(능력) ≠ "B폰의 위치"(인스턴스). A폰은 `sense:here`를 자기한테도, B한테도 호출 = 같은 액션, 다른 인스턴스. ∴ **기기 ID는 *액션 정의*가 아니라 *호출 지점*에 있어야 한다.** 액션 정의를 `폰1_only`로 바꾸면 어휘 폭증 + 기기 추가마다 정의 수정 = 포크 = 이음매(헌법1조) 위반.

### 원칙 C — 3층 분리
```
어휘층 (이음매 위, 하드웨어 중립)
  액션은 "능력 요구"만 선언. runs_on을 "기기명"이 아니라 "능력 클래스"로 재해석.
  → 136개 액션 정의 한 줄도 안 고침 (의미만 재해석)

기기 레지스트리 (이음매 아래, 하드웨어가 사는 곳)
  각 물리 기기 = {alias, device-id, owner, transport, capability, ...}

라우팅/주소지정
  능력 매칭 → 후보 선택(명시주소 > 자기-가능 > 주(主)기기 > 모호하면 되물음)
  _forward_to_node(device-id) 가 단수 _forward_to_phone/_forward_to_mac 대체
```

### 원칙 D — 2계층 정체성, npub 층은 휴면 슬롯
```
owner  (누구 — 주권 주체, = npub)     ← Stage 2(다중 사용자)에서 사람 경계
  └─ device-id (어느 몸)              ← Stage 1(내 기기 여러 대)에서 기기 구분
```
- 내 기기끼리는 owner가 다 "나"라 npub으로 구분 안 됨 → **device-id가 작업 층**.
- 노드 정체성을 내부적으로 `(owner, device-id)`로 표현하되 **Stage 1은 `owner=self` 고정**. Stage 2가 오면 `owner`가 진짜 npub 경계로 살아나고 **재작업 없이 끼워짐**. (슬롯만 비워둠)
- npub은 이번 설계에서 **건드리지 않음**(대외용 1개, 맥, 그대로).

---

## 3. 확정 결정

| # | 결정 | 근거 |
|---|------|------|
| 1 | **device-id 체계** = 사람용 별칭(`맥`/`폰1`/`폰2`)이 주소지정 이름 + provision 때 발급하는 안정 device-id가 내부 정본. npub은 device-id에 안 씀. | detect_body의 MODEL(SM-A366N)은 같은 기종 2대면 충돌 → provision 발급 ID 필요. 소유자 1명이라 npub 불필요. |
| 2 | **기본 선택 휴리스틱**(주소 생략 시) = ①자기가 능력 있으면 자기 → ②없으면 그 능력의 **주(主)기기**(레지스트리 1대 지정) → ③주 기기 미지정 & 후보 2+면 **"어느 폰?" 되물음**. | 조용히 아무거나 고르지 않음 = augmentation 원칙. 사용자 확정("부정확하면 어느 폰이냐고 묻고"). |
| 3 | **주소지정 문법** = `[sense:here]@폰2` 노드 접미사(1급 연산자). | `&`/`>>`/`??`처럼 합성 code의 leaf마다 노드 지정 가능. 사용자 확정("필요하면 문법을 만들어야지"). |
| 4 | **동기화 위상** = star, 허브=맥미니(상시가동). business.db CRDT를 각 기기↔맥 쌍방 머지. | 폰끼리 직접(mesh)은 NAT 도달성 문제 → Stage 2. |
| — | **능력 입도** = 거친 클래스(현 `runs_on` 재해석)로 시작. 세분화(gps/mic/cam 개별)는 기기가 정말 비대칭일 때 후속. | 처음부터 잘게 쪼개면 안 쓰는 추상화. |

---

## 4. 기기 레지스트리 = 동적 프레즌스 (★ 정적 설정 아님)

**★사용자 핵심 결정(2026-06-17)**: 폰 수를 *어디에도 고정하지 않는다.* 1대→2대→3대 늘 때마다 모든 폰/허브 설정을 고치고 싶지 않다. → **"지금 연결된 노드가 몇 대인지를 *연락(연결)으로* 확인한다."** 정적 `node_registry.json`에 폰1·폰2를 박는 설계는 폐기. 대신 **프레즌스(presence) 프로토콜**:

- 각 노드는 부팅 시 **허브(맥)에 자기를 등록**(`POST /nodes/register`) + 주기 **heartbeat**(`POST /nodes/heartbeat`, 60s). 허브가 라이브 테이블 유지(`last_seen` + TTL 150s).
- **폰 N대째 추가 = 그 폰만 켜면 끝.** 다른 폰·허브 설정 무수정. 폰이 알아야 할 정적 정보 = "허브가 어디냐(`INDIEBIZ_MAC_URL`)" **하나**(폰 수와 무관, 불변).
- "지금 몇 대?" = `GET /nodes/live`(라이브 테이블 조회 — `/nodes`는 api_packages 의 논리노드가 선점). 모호 시 **이 라이브 목록**에서 "어느 폰?" 되물음.
- 주(主)기기 지정 = `POST /nodes/primary {target|connected_phone}` (능력당 0~1, 같은 능력 노드만 해제). **primary 는 허브가 이 엔드포인트로만 정함** — 노드 재등록이 덮어쓰지 않게 register 는 기존 primary 보존.
- 폰 IP 변동 → 재등록으로 자동 갱신(별도 후속 불필요).
- 최종 도달성은 **포워드 시도 자체가 검증**(`_forward_*`이 `phone_unreachable` 반환) — 죽은 항목은 다음 후보로/되물음.

라이브 항목 모양(런타임, `data/device_registry.json` 영속):
```jsonc
{ "nodes": {
  "<device_id>": {
    "alias": "폰2",                 // 주소지정 이름 (등록 시 자기보고)
    "owner": "self",               // Stage1=self 고정. Stage2 슬롯(npub).
    "capabilities": ["phone-class"],// 자기보고 (detect_body 기반)
    "url": "http://192.0.2.14:8765",  // 허브가 이 노드에 닿는 주소(등록 시 보고)
    "auth": "x_phone_token",       // 포워드 인증 방식
    "primary": false,              // 그 능력의 주(主)기기 (주소 생략 시 자동선택 대상)
    "self": false,                 // 이 항목이 현재 프로세스 자신인가
    "last_seen": 1750000000.0      // heartbeat 시각 (TTL 판정)
  }
}}
```

- **능력 클래스(Stage 1, 거친 2종)**: `phone-class`(폰=센서·effector) / `compute-class`(맥=무거운 연산·네이티브). 매핑: `runs_on:phone_only`→요구 `phone-class` · `runs_on:mac_only`→요구 `compute-class` · `anywhere`→요구 없음. 세분(gps/cam 개별)은 후속.
- `capabilities`는 **각 노드 자기-보고**(detect_body) — 손작성 아님(헌법: 감지하되 적어주지 않음).
- `primary` = 결정②의 주(主)기기. 한 능력당 0~1.
- **레거시 호환(마이그레이션 다리)**: 레지스트리에 후보가 없으면 단수 env(`INDIEBIZ_PHONE_URL`/`MAC_URL`)로 폴백 → 폰이 자기등록 코드로 업데이트되기 전에도 현 단일-폰 셋업이 그대로 동작.

---

## 5. 라우팅 알고리즘 (의사코드)

현재 `ibl_engine.py:534~564`의 단수 분기를 아래로 교체.

```python
def resolve_target(node, action, explicit_node, params):
    req = required_capability(node, action)        # runs_on 재해석 (None=anywhere)
    me  = registry.self_node()

    # 1. 명시 주소 (@폰2) 최우선
    if explicit_node:
        tgt = registry.get(explicit_node)
        if not tgt: return ERROR(f"알 수 없는 노드: {explicit_node}", registry.aliases())
        # (Stage2) tgt.owner != self → 허가 게이트. Stage1은 self뿐이라 통과.
        return tgt

    # 2. 능력 불필요 → 로컬
    if req is None: return me

    # 3. 자기가 능력 있으면 자기 (빌림 불필요 = 최선)
    if req in me.capabilities: return me

    # 4. 후보 = 그 능력 가진 노드들
    cands = [n for n in registry.nodes if req in n.capabilities]
    if not cands: return ERROR(f"'{req}' 능력 가진 노드 없음")
    if len(cands) == 1: return cands[0]

    # 5. 주(主)기기 지정돼 있으면 그것
    primary = [n for n in cands if req in n.primary_for]
    if len(primary) == 1: return primary[0]

    # 6. 모호 → 되물음 (결정②③)
    return ASK_USER(f"{node}:{action}를 어느 기기에서 실행할까요?", options=[n.alias for n in cands])
```

실행:
```python
tgt = resolve_target(...)
if tgt is ERROR or ASK_USER: return tgt   # 되물음은 UI/에이전트 루프로 환류
if tgt is me:                return run_local(...)
return _forward_to_node(tgt, node, action, params, agent_id)   # 단수 forward 일반화
```

`_forward_to_node`는 기존 `_forward_to_phone`/`_forward_to_mac`을 흡수:
- 대상 URL = `tgt.transport.url` (단수 env 대체)
- 인증 = `tgt.transport.auth`로 분기(X-Phone-Token | 런처세션)
- 산출물 회수 = 기존 `_pull_remote_artifacts`(양방향 빌림) 재사용
- agent_id 전파 동일

### 되물음(ASK_USER) 환류
- **수동/자율 모드**: 에이전트가 "어느 폰?" 질문을 사용자에게 환류(평가 루프처럼). 또는 dry-run 검수 단계에서 노출.
- **결정 후 기억**: 같은 의도 반복 시 매번 묻지 않게, 직전 선택을 세션/해마에 결정화(후속).

---

## 6. 주소지정 문법 `@node`

- **형태**: `[sense:here]@폰2` — 액션 뒤 `@별칭`.
- **합성 code**: leaf마다 독립. 예 `[sense:here]@폰1 & [sense:here]@폰2` (두 폰 위치 동시) / `[sense:here]@폰2 >> [self:save]` (폰2 위치 받아 로컬 저장).
- **파서**: `ibl_parser.py`에 `@` 접미사 토큰 추가 → leaf의 `target_node` 필드로. `&`/`>>`/`??`와 우선순위 정의(액션에 가장 강하게 바인딩 = postfix).
- **생략 시**: §5 휴리스틱.
- **--check / 어휘 영향**: `@`는 노드 차원이라 액션 desc·해마 코퍼스에 영향 없음(렌더러/라우팅 어휘). build_ibl_nodes에 파서 라운드트립 검증만 추가.

---

## 7. 동기화 위상 (star)

- 허브 = 맥미니(always_on). 각 폰 ↔ 맥 **쌍방** CRDT 머지(business.db LWW+tombstone, 이미 구현). 폰1↔폰2는 맥 경유로 수렴.
- 공유 집합은 현 정책 유지: **business.db만**(연락처·비즈니스·일정 엔티티), opt-in. 각 자아의 체험(해마·일화)은 사적, 동기화 안 함.
- 폰끼리 직접(mesh)은 NAT 문제로 Stage 2.

---

## 8. 구현 변경 지점 (체크리스트)

**구현 상태 (2026-06-17): 백엔드 + 폰 온디바이스 종단까지 완료·검증(A36 실기기, 폰 1대). 2번째 폰 실험만 남음.**

**★온디바이스 종단(A36 DEVICE_SERIAL_REDACTED)**: 폰 자기등록→`/nodes/live`에 맥·폰 2노드(heartbeat 신선)→`POST /nodes/primary {connected_phone:true}`로 폰=주(主)→무주소 `[sense:here]` 맥서 호출→주(主)폰 자동 라우팅→실 GPS(`_forwarded_to:phone`)·`@폰-9f2b` 동일. 이번에 잡은 함정: ①`GET /nodes` 경로 충돌→`/nodes/live` ②`_phone_lan_ip`가 터널 경로의 셀룰러 IP를 잡던 것→인터페이스 열거(RFC1918·wlan0, `Collections.list`로 Chaquopy 추상 Enumeration 우회)로 WiFi LAN IP 등록 ③register가 주(主) 덮어쓰던 것→기존 primary 보존+`set_primary`.

| 영역 | 파일 | 상태 |
|------|------|------|
| 레지스트리 (동적 프레즌스) | `backend/device_registry.py` (신규) | ✅ register/heartbeat/list_live/live_with_capability/get_by_alias + self_device_id(영속)·self_alias·능력매핑. 논리-노드 `node_registry`와 별 모듈 |
| API | `backend/api_nodes.py` (신규) + `api.py` 마운트 | ✅ `POST /nodes/register`·`POST /nodes/heartbeat`·`GET /nodes`. 전역 remote_access_guard 로 인증 |
| 라우팅 | `backend/ibl_engine.py` `_resolve_and_maybe_forward` | ✅ 단수 분기 → 동적 후보 선택(@주소>자기>1대>주(主)>되물음). 레거시 env 폴백 |
| 포워드 일반화 | `backend/ibl_engine.py` `_forward_to_node` | ✅ `_forward_to_phone`/`_forward_to_mac` 흡수(auth로 분기). `_forward_to_mac(mac_url=)` 추가 |
| 능력 매핑 | `device_registry.required_capability` | ✅ runs_on→phone-class/compute-class (액션 정의 무수정) |
| 문법 `@node` | `backend/ibl_parser.py` `_parse_step` | ✅ `[node:action]{...}@별칭`→`target_node`. params 밖 tail서만(이메일 @충돌 없음). 한글 별칭·합성 leaf별 |
| 맥 자기등록 | `backend/api.py` lifespan | ✅ 부팅 시 ensure_self(compute-class·주(主)) |
| 폰 자기등록 | `phone-companion/.../phone_api.py` + `build.gradle` | ✅ **온디바이스 검증**(serve→/nodes/register+60s heartbeat, WiFi LAN IP 인터페이스 열거). device_registry 번들 |
| 주(主) 지정 | `device_registry.set_primary` + `POST /nodes/primary` | ✅ **온디바이스 검증**(connected_phone 자동·능력당 0~1·register 보존) |
| provision 별칭 | `phone-companion/scripts/provision_phone_keys.py` | ✅ `--alias 폰2` → INDIEBIZ_NODE_ALIAS 주입 |
| 되물음 환류 | `agent_cognitive` / 수동모드 | ⏳ 엔진은 `needs_node_choice` dict 반환 — 이를 사용자 질문으로 환류하는 UX는 후속(주(主) 있으면 안 뜸) |

**검증(백엔드)**: py_compile 전부 ✓ · 파서 @node 단위(한글·이메일 비충돌·합성 leaf별) ✓ · device_registry 라이브/능력후보 ✓ · `_resolve_and_maybe_forward` 7시나리오(로컬/명시/되물음/주(主)/단일/레거시폴백/폰빌림) ✓ · build_ibl_nodes `--check` 삼각정합+포크-가드 통과 ✓ · api_nodes 라우트·통합 배선 ✓.

---

## 9. 검증 계획 (2번째 폰)

1. 폰2 provision(별개 device-id, INDIEBIZ_PHONE_TOKEN, 맥 위임).
2. 맥 레지스트리에 폰1·폰2 등록(주(主)=폰1).
3. `[sense:here]` (주소 생략) → 맥서 호출 시 주(主)=폰1 도달 / 폰1·폰2 둘 다 후보지만 주(主) 있으니 안 물음.
4. `[sense:here]@폰2` → 폰2 GPS 실제 도달 + 결과 회수.
5. `[sense:here]@폰1 & [sense:here]@폰2` → 두 폰 위치 동시(합성 leaf별 라우팅).
6. 주(主) 미지정 상태로 모호 호출 → "어느 폰?" 되물음 발생.
7. 폰1↔폰2 위치 상호 문의(폰1서 `@폰2`) — 사용자 핵심 시나리오.
8. business.db star 머지: 폰2서 연락처 추가 → 맥 → 폰1 수렴.

---

## 10. Stage 2 슬롯 (비워둠, 구현 안 함)

- `owner != self` 노드 = 다른 사람(npub) → 허가 게이트(`resolve_target` 1번 분기에 자리 표시).
- 필요 층: 스코프·조건·취소·감사 / 노드 간 프롬프트 인젝션 방어(타인 요청=데이터지 명령 아님) / 결과 신뢰(검증) / 책임·비용.
- 전송: 같은 LAN 아니면 IndieNet(릴레이/DM) 경유 — npub이 그때 라우팅 신원으로 승격.

---

## 11. 미해결 / 후속

- 되물음 결정의 해마 결정화(반복 의도 시 자동 선택).
- 레지스트리 동적 갱신(기기 on/off, IP 변동) — 현재 정적 등록. mDNS/도달성 핑 후속.
- 능력 자기보고의 신선도(detect_body 캐시 vs 런타임 변화).
- 폰을 대외적으로도 독립 노드로 노출할지(폰 자기 npub provision) = Stage 2와 맞물림, 보류.
