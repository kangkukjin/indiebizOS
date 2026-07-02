# ibl_nodes_src/ — 편집용 소스

`data/ibl_nodes.yaml`(4,300+줄) 편집을 쉽게 하려고 7개 파일로 나눠둔 곳이다.
**런타임은 이 디렉토리를 보지 않는다** — 항상 단일 `data/ibl_nodes.yaml`만 읽는다.

## 워크플로

```bash
# 1) 여기서 편집 (또는 패키지 자기완결 어휘 — 아래 참조)
vi data/ibl_nodes_src/sense.yaml

# 2) 병합 (단일 yaml 갱신)
python scripts/build_ibl_nodes.py
```

## 파일 구성

| 파일 | 내용 | 표준 yaml? |
|---|---|---|
| `meta.yaml` | `meta:` 블록 (IBL 문법 설명, 파이프라인, 예시) | yes |
| `sense.yaml` | sense 노드 (감각·외부 인터페이스) | yes (root indent=2) |
| `self.yaml` | self 노드 (자아·내부 데이터) | yes |
| `limbs.yaml` | limbs 노드 (사지·바깥 손길) | yes |
| `others.yaml` | others 노드 (위임·채널) | yes |
| `engines.yaml` | engines 노드 (생성 엔진 — 슬라이드·영상·이미지·신문·웹) | yes |
| `table.yaml` | table 노드 (표·통화 변환 문법 — filter/sort/take/…/chart/spreadsheet/document/structure, 2026-06-30 engines에서 분리) | yes |

소스 파일들은 모두 단독 yaml로 파싱 가능하다 (PyYAML/IDE/lint 모두 OK).
노드 파일들은 root key가 column 2에 위치하지만 YAML 스펙상 유효하다.

## 패키지 자기완결 어휘 (`ibl_actions.yaml`, 2026-07-01 — 능력 자기완결화)

패키지가 소유하는 액션은 이제 이 중앙 소스가 아니라 **패키지 폴더 자신**에 정의할 수 있다:
`data/packages/installed/tools/<pkg>/ibl_actions.yaml`(단일노드 `{node, actions}` 또는 다중노드 `{nodes: {...}}` 형식,
템플릿=`data/packages/not_installed/tools/house-designer/ibl_actions.yaml`).

`build_ibl_nodes.py`가 **중앙 7파일 + 설치된 패키지들의 fragment**를 병합해 `ibl_nodes.yaml`을 만든다
(`collect_package_fragments`→`merge_fragments`→fragment가 있으면 `serialize_nodes_document`로 재직렬화,
없으면 기존처럼 바이트 동일). 패키지를 철거하면(폴더 이동) 그 어휘도 다음 빌드에서 카탈로그에서 사라진다(좀비 없음).

기존 패키지를 이 방식으로 옮기려면 `scripts/migrate_package_vocab.py <package_name>`(마이그레이션 하네스) —
중앙 src에서 그 패키지 소유 액션을 추출→패키지 `ibl_actions.yaml`에 기록→중앙 src에서 텍스트 수술로 제거→
재빌드→의미 동일(파싱된 dict deep-equal) 단언→`--check`. 실패 시 자동 롤백. **이름은 절대 바꾸지 않는다**(해마 코퍼스 무손상).
2026-07-01 기준 35개 패키지가 이미 이 방식으로 자기완결화됐다 — 중앙 src는 backend-native 액션(workflow/trigger/
delegate/world/self_check 등, 특정 패키지 없이 엔진 자체에 속하는 것)만 남아있다.

상세: `docs/CAPABILITY_SELF_CONTAINMENT_PLAN.md`, `docs/CAPABILITY_SELF_CONTAINMENT_HANDOFF.md`.

## tool.json 파생 (2026-07-03 — 정합성을 검증에서 구조로)

패키지 `tool.json` 은 이제 **빌드 산출물**이다 (`_generated` 마커): 각 패키지
`ibl_actions.yaml` 의 `tool_json:` 블록(header + tools)이 원본이고, op-bearing
도구의 op enum/default 는 저장하지 않는다 — 빌드가 그 액션의 `ops:` 블록에서
**주입**한다. 예전 삼각검증의 src↔tool.json op 비교가 "어긋남 검출"이었다면,
이제는 어긋남이 **구조적으로 불가능**하다 (fixture: 필드 → ibl_fixtures.json 파생과 같은 수).

- 검증: `--check` 가 파생 결과 ↔ 디스크 tool.json 바이트 일치를 확인 (손편집 검출 → 빌드로 재생성/치유)
- 액션 미소유 도구(내부 배관 — world_pulse_collectors 등이 이름으로 직접 디스패치)는 `tools:` 에 원문 그대로 보존
- 이관 하네스: `scripts/migrate_tool_schema.py` (이관→재파생→deep-equal 단언→실패 시 롤백)
- 미이관 패키지(`tool_json:` 블록 없음, 예: ibl-core)는 손수 유지 그대로

## 선택 필드: `app:` 블록 (앱 표면 노출)

액션 정의에 `app:{icon,name,order,inputs,action,view,…}` 블록을 달면 그 액션이
데스크탑·원격 런처의 **앱 모드 계기(GUI)**로 자동 등장한다 (`GET /launcher/instruments`가 파생).
정합성은 `--check`의 `validate_app_blocks`가 검증한다 (참조 액션 실존·$key↔inputs·view 어휘 10종(metric/kv/kv_list/card_list/image_grid/sparkline/list_action/thread/form/editable_list)+보조어휘(form.actions·compose.channels·master_detail)·계기 그룹).
어휘 명세: `docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md`, 요약: `data/system_docs/ibl.md`의 "앱 표면 노출" 절.

- **`phone_render: false`** (선택, 기본 true): 폰 프로파일에서 이 계기를 숨긴다. 실행 위치(`runs_on`)와 **직교** — 폰서 못 도는 액션도 기본은 노출(실행은 맥에 라우팅, 아래 참조)되지만, 출력을 폰서 보여줄 수 없으면(맥 브라우저·네이티브창) 또는 미검증 보류(예: ytmusic 오디오) 이 플래그로 숨긴다. PC엔 영향 없음.

## 선택 필드: `runs_on` (어디서 도는가 — 폰 네이티브 #3)

액션에 `runs_on: anywhere|mac_only|phone_only`를 달아 실행 환경을 선언한다 (미지정=`anywhere`).
- `anywhere` (기본): 이식 가능 로직/HTTP. handler/driver 라우터면 **검증된 폰 패키지**(`build_ibl_nodes.PHONE_VERIFIED_PACKAGES`)일 때만 폰서 실행.
- `mac_only`: 집 PC 하드웨어·무거운 의존·미검증 패키지. **폰서 직접 실행 못 함 → 맥(연합 두뇌)에 단건 라우팅**(예: `limbs:os_open`/`open_window`=데스크탑 GUI, `self:manage_events`=무거운 api_system_ai 의존).
- `phone_only`: 폰 하드웨어 전용. 입력=`sense:phone`(알림 피드)·`sense:here`(현재위치 온디맨드 1회 조회 — 상시 추적 아님), 출력=`limbs:phone`(알림·진동·토스트·복사·TTS·앱실행 + 문자·전화 스테이징, Chaquopy→Kotlin PhoneActions). PC선 graceful 거부(또는 INDIEBIZ_PHONE_URL 설정 시 분산 IBL 로 폰에 포워드).

**분산 IBL 라우팅 (액션이 실행 단위)**: 폰 프로파일에서 엔진(`ibl_engine.execute_ibl`)은 폰서 못 도는 액션(`runnable_actions` 밖)을 거부하지 않고 **맥에 단건 위임**한다(`_forward_to_mac`, `_forward_to_phone`의 대칭). 이 chokepoint를 합성 code(`&`/`>>`/`??`)의 각 leaf가 거치므로, **혼합 code도 액션별로 쪼개져** 일부는 폰서·일부는 맥서 실행되고 결과가 한 봉투로 결합된다(예: `[sense:weather] & [sense:world_bank]` → weather=폰·world_bank=맥). 맥 도달=`INDIEBIZ_MAC_URL`+`INDIEBIZ_MAC_PASSWORD`(원격 런처 세션), 미설정이면 graceful 에러. 추상화 의도=라우팅은 "맥에 프록시"가 아니라 "신뢰 노드(신원)에 위임" — 미래 피어(허가한 친구)가 같은 뼈대에 슬롯인(허가 층만 미구현).

빌드가 `runs_on` + 검증 패키지에서 `data/phone_manifest.json`(packages + runnable_actions)을 파생한다 —
폰 번들(Gradle `bundleIndiebizBase`)·앱 계기 필터(`_derive_instruments`)·엔진 라우팅(`ibl_engine._phone_runnable`)의 **단일 진실 소스**.
`--check`가 enum + 매니페스트 정합을 검증. **패키지를 폰서 검증하면 `PHONE_VERIFIED_PACKAGES`에 추가**.

## 주의

- **단일 yaml을 직접 편집하지 말 것.** 다음 빌드에서 덮어쓴다.
  - 실수 방지: pre-commit/CI에서 `python scripts/build_ibl_nodes.py --check`로 검증.
- 노드 추가/제거 시 `scripts/build_ibl_nodes.py`의 `NODE_ORDER`도 갱신.
- 라인 끝(LF/CRLF)은 소스 파일과 통일.

## 런타임 영향 없음

다음 백엔드 코드가 단일 yaml을 직접 로드한다 — 이 분할 작업에서는 건드리지 않음:
- `backend/ibl_access.py` (`_load_nodes_data`) — 1차 로더, 캐시 보유
- `backend/tool_loader.py`
- `backend/bootstrap_ibl_actions.py`
- `backend/api_xray.py` (2곳)
- `backend/world_pulse_health.py`
- `backend/ibl_usage_generator.py`

이 코드들은 모두 같은 단일 파일을 본다 — 빌드 스크립트가 그 파일을 유지하므로
원본 코드는 영향 없음.
