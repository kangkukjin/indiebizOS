# ibl_nodes_src/ — 편집용 소스

`data/ibl_nodes.yaml` (3,400+줄) 편집을 쉽게 하려고 6개 파일로 나눠둔 곳이다.
**런타임은 이 디렉토리를 보지 않는다** — 항상 단일 `data/ibl_nodes.yaml`만 읽는다.

## 워크플로

```bash
# 1) 여기서 편집
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
| `engines.yaml` | engines 노드 (생성·변환 엔진) | yes |

소스 파일들은 모두 단독 yaml로 파싱 가능하다 (PyYAML/IDE/lint 모두 OK).
노드 파일 4개는 root key가 column 2에 위치하지만 YAML 스펙상 유효하다.

## 선택 필드: `app:` 블록 (앱 표면 노출)

액션 정의에 `app:{icon,name,order,inputs,action,view,…}` 블록을 달면 그 액션이
데스크탑·원격 런처의 **앱 모드 계기(GUI)**로 자동 등장한다 (`GET /launcher/instruments`가 파생).
정합성은 `--check`의 `validate_app_blocks`가 검증한다 (참조 액션 실존·$key↔inputs·view 어휘 7종·계기 그룹).
어휘 명세: `docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md`, 요약: `data/system_docs/ibl.md`의 "앱 표면 노출" 절.

## 선택 필드: `runs_on` (어디서 도는가 — 폰 네이티브 #3)

액션에 `runs_on: anywhere|home_only|phone_only`를 달아 실행 환경을 선언한다 (미지정=`anywhere`).
- `anywhere` (기본): 이식 가능 로직/HTTP. handler/driver 라우터면 **검증된 폰 패키지**(`build_ibl_nodes.PHONE_VERIFIED_PACKAGES`)일 때만 폰서 실행.
- `home_only`: 집 PC 하드웨어·무거운 의존·미검증 패키지. 폰서 제외(예: `limbs:os_open`/`open_window`=데스크탑 GUI).
- `phone_only`: 폰 하드웨어 전용. 입력=`sense:phone`(알림·위치·걸음), 출력=`limbs:phone`(알림·진동·토스트·복사·TTS·앱실행 + 문자·전화 스테이징, Chaquopy→Kotlin PhoneActions). PC선 graceful 거부.

빌드가 `runs_on` + 검증 패키지에서 `data/phone_manifest.json`(packages + runnable_actions)을 파생한다 —
폰 번들(Gradle `bundleIndiebizBase`)·앱 계기 필터(`_derive_instruments`)·엔진 가드(`ibl_engine._phone_runnable`)의 **단일 진실 소스**.
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
