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
