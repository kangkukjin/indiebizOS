"""CLI 프로바이더의 세션 저장소 — CLI 세션 매핑과 세션 크기 기록, 그 둘을 읽고 지우는 함수.

cli_provider.py 에서 분리(2026-11-17, 1500줄 규칙). 기존 import 경로(providers.cli_provider 의
CliSessionStore·_SESSION_STORES·clear_sessions_for_agent)는 재수출로 유지된다.

저장 위치는 cli_provider._data_dir 이 정한다(패키지 앱의 userData 해석·시험의 경로 바꿔치기가 그 이름에 걸려 있다).
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _data_dir() -> Path:
    from . import cli_provider
    return cli_provider._data_dir()


_SESSION_STORES: List["CliSessionStore"] = []


class CliSessionStore:
    """`data/<prefix>_sessions.json` · `data/<prefix>_session_sizes.json` 한 쌍.

    생성만 하면 전역 목록에 등록되어 `clear_sessions_for_agent()`(프로바이더 무관
    '새 대화')가 이 저장소도 함께 비운다 — 새 CLI 프로바이더를 추가할 때 UI 리셋
    배선을 따로 기억하지 않아도 되도록.
    """

    def __init__(self, prefix: str, label: str):
        self.prefix = prefix
        self.label = label
        _SESSION_STORES.append(self)

    # --- 경로 ---
    def map_path(self) -> Path:
        return _data_dir() / f"{self.prefix}_sessions.json"

    def size_path(self) -> Path:
        return _data_dir() / f"{self.prefix}_session_sizes.json"

    # --- 공통 입출력 ---
    @staticmethod
    def _load(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, path: Path, m: Dict[str, Any], what: str):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[{self.label}] {what} 저장 실패: {e}")

    # --- 세션 매핑 ---
    def load_map(self) -> Dict[str, str]:
        return self._load(self.map_path())

    def save_map(self, m: Dict[str, str]):
        self._save(self.map_path(), m, "세션 매핑")

    def clear_agent(self, session_key: str):
        """특정 agent의 세션 매핑 제거. UI '새 대화' 등에서 호출.

        ★접두 스윕: 프로바이더가 세션 키를 파생시켜 쓸 수 있다(예: codex 는 시스템 프롬프트
        해시를 `키#해시` 로 붙인다 — CodexProvider._get_session_key 참조). 호출부는 그
        파생을 모르고 평범한 registry_key 를 넘기므로, 정확히 같은 키 + `키#…` 파생분을
        함께 지운다. 안 그러면 '새 대화'가 파생 키를 못 찾아 옛 스레드가 살아남는다.
        """
        return self._clear(self.map_path(), session_key)

    def _clear(self, path, session_key):
        # 초기화는 실패를 삼키는 캐시 읽기/쓰기를 사용하지 않는다.
        from restart_protocol import atomic_json
        try:
            mapping = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0
        if not isinstance(mapping, dict):
            raise ValueError("세션 저장소가 객체가 아닙니다")
        victims = [k for k in mapping if k == session_key or k.startswith(session_key + "#")]
        if victims:
            atomic_json(path, {k: v for k, v in mapping.items() if k not in victims})
            observed = json.loads(path.read_text(encoding="utf-8"))
            if any(k in observed for k in victims):
                raise OSError("세션 매핑 삭제 후 재독 불일치")
        return len(victims)

    # --- 컨텍스트 크기 ---
    def load_sizes(self) -> Dict[str, int]:
        return self._load(self.size_path())

    def save_sizes(self, m: Dict[str, int]):
        self._save(self.size_path(), m, "세션 크기")

    def record_size(self, session_key: str, size: int):
        """직전 턴의 실측 컨텍스트 토큰 수를 기록 (다음 턴 리셋 판단용)."""
        if not session_key or size <= 0:
            return
        m = self.load_sizes()
        m[session_key] = int(size)
        self.save_sizes(m)

    def clear_size(self, session_key: str):
        return self._clear(self.size_path(), session_key)


def session_context_size(suffix: str, note: Optional[dict] = None) -> Optional[dict]:
    """대화 세션 하나의 CLI 세션 크기 — 마지막 라운드의 문맥 토큰. 없으면 None.

    suffix = 세션 열쇠에서 대화 세션을 가리키는 부분(`@session:<id>` 와 되감기 판 표식). 열쇠는
    `<자아>@session:<id>[@revision:N][#지문]` 꼴이다. note = 대화 세션 곁의 표식(공급자·열쇠). 표식이
    가리키는 열쇠가 크기 기록에 그대로 있으면 그 값이다. 표식이 없거나(표식이 생기기 전의 세션) 가리키는
    기록이 지워졌으면(세션 초기화·되감기) 같은 대화 세션의 열쇠를 크기 기록에서 찾아 가장 나중 것을 쓴다.
    예행 세션은 세지 않는다.
    """
    def of_session(key):
        return "@rehearsal" not in key and key.split("#", 1)[0].endswith(suffix)

    stores = {store.prefix: store for store in _SESSION_STORES}
    if note and note.get("provider") in stores and of_session(note.get("key") or ""):
        size = stores[note["provider"]].load_sizes().get(note["key"])
        if isinstance(size, int) and size > 0:
            return {"tokens": size, "provider": note["provider"]}
    for prefix, store in stores.items():
        found = [(key, size) for key, size in store.load_sizes().items()
                 if of_session(key) and isinstance(size, int) and size > 0]
        if found:
            return {"tokens": found[-1][1], "provider": prefix}
    return None


def clear_sessions_for_agent(session_key: str):
    """해당 세션과 파생 키만 제거하고 재독한 결과를 반환한다. 다른 세션·기록은 유지한다."""
    removed, errors = 0, []
    for store in _SESSION_STORES:
        try:
            removed += store.clear_agent(session_key) or 0
            store.clear_size(session_key)
        except Exception as exc:
            errors.append(f"{store.label}: {exc}")
    message = ("CLI 세션 매핑을 제거했습니다. 다음 호출은 새 컨텍스트로 시작합니다."
               if removed else "제거할 CLI 세션 매핑이 없습니다.")
    return {"ok": not errors, "key": session_key, "removed": removed,
            "message": message if not errors else "세션 매핑 정리를 완료하지 못했습니다.",
            "error": "; ".join(errors)}
