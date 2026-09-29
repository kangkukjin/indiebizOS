"""열린 인자 계약 전수 관문 (2026-09-29, 상상훈련 78회차 F78-2 밭 이관).

질문 하나: **판본 2 실행 관문이 인자 이름을 보지 않는(open_params) 액션마다, 그렇게 연 사유가 선언돼 있는가?**

왜 — 인자 선언이 비면 계약이 열리고(`ibl_v2_contracts.handler_contract` 의 `open_params: keys is None`),
열린 계약에서는 check 도 실행도 모르는 인자를 받아 준다. 78회차 T03 `[self:recent_chats]{days:7,
query:"전세", since:…}` 는 세 인자 모두 조용히 무시된 채 전체 대화를 돌려줬고 check 는 경고 0이었다.
80회차는 같은 틈으로 발신 어휘(publish·feed)의 미리보기 인자가 침묵했다. 열림은 선언이 *없어서* 생기는
기본값이었지 누가 고른 것이 아니었다 — 그래서 목록을 사람이 고르지 않고 계약 생성 함수로 기계 열거한다.

규칙:
  ① 계약이 열린 액션은 `open_params: true` 와 `open_params_reason`(왜 인자 집합을 닫을 수 없는가)을 선언한다.
     사유 없는 개방 = 빌드 실패. 처방은 둘 중 하나 — 구현이 실제로 읽는 인자를 `open_params: false` +
     `params` 로 적어 닫거나(권장), 정말 자유 키를 받는 액션이면 사유를 적는다.
  ② 닫힌 액션에 `open_params_reason` 이 남아 있으면 낡은 사유다 — 실패.
  ③ 구현 패키지가 이 저장소에 아예 없는 핸들러 액션은 대상 밖(계약을 만들 재료가 없어 열린 것 — 선언 문제가 아니다).

판정은 레지스트리(`ibl_v2_adapters.load_registry`)가 쓰는 **같은 함수**(declared_contract·handler_contract)에
빌드의 스키마 스냅숏을 넘겨 계산한다 — 기준 사본 없음.
"""
from __future__ import annotations

import sys
from pathlib import Path

from iblbuild_derive import build_tool_index


def open_contract_actions(data: dict, root: Path) -> list[tuple[str, dict]]:
    """계약이 열린 액션 전부 [(node:action, 선언)] — 구현 패키지가 없는 핸들러 액션은 뺀다."""
    backend = Path(__file__).resolve().parents[1] / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    import boot_paths  # noqa: F401
    from ibl_v2_contracts import declared_contract, handler_contract

    index = build_tool_index(root)
    out = []
    for node, body in (data.get("nodes") or {}).items():
        for action, cfg in ((body or {}).get("actions") or {}).items():
            if not isinstance(cfg, dict):
                continue
            tool = cfg.get("tool")
            if cfg.get("router") == "handler" and tool and tool not in index:
                continue                               # ③ 구현 부재 — 선언 문제가 아니다
            schema = ((index[tool][1].get("input_schema") or {}).get("properties") or {}) if tool in index else None
            contract = declared_contract(cfg) or handler_contract(node, action, cfg, schema)
            if contract and contract.get("open_params"):
                out.append((f"{node}:{action}", cfg))
    return out


def validate_open_params(data: dict, root: Path) -> tuple[list[str], list[str]]:
    """(문제 목록, 사유 있는 개방 목록)."""
    issues: list[str] = []
    opened = open_contract_actions(data, root)
    open_names = {name for name, _ in opened}
    reasoned = []
    for name, cfg in opened:
        reason = cfg.get("open_params_reason")
        if cfg.get("open_params") is True and isinstance(reason, str) and reason.strip():
            reasoned.append(name)
            continue
        issues.append(
            f"[{name}] 인자 계약이 열려 있다(check·실행이 모르는 인자를 조용히 받는다) — 구현이 실제로 읽는 인자를 "
            f"`open_params: false` + `params` 로 선언해 닫거나, 자유 키가 본질이면 `open_params: true` 와 "
            f"`open_params_reason` 을 적을 것")
    for node, body in (data.get("nodes") or {}).items():
        for action, cfg in ((body or {}).get("actions") or {}).items():
            name = f"{node}:{action}"
            if isinstance(cfg, dict) and cfg.get("open_params_reason") and name not in open_names:
                issues.append(f"[{name}] 계약이 닫혀 있는데 open_params_reason 이 남아 있다 — 낡은 사유를 지울 것")
    return issues, sorted(reasoned)


if __name__ == "__main__":
    import yaml
    ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    nodes = yaml.safe_load((ROOT / "data" / "ibl_nodes.yaml").read_text(encoding="utf-8"))
    found, ok = validate_open_params(nodes, ROOT)
    for line in found:
        print(line)
    print(f"사유 있는 개방 {len(ok)}: {', '.join(ok)}")
    print(f"{len(found)}건")
