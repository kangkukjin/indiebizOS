"""CLI 프로바이더 등록 관문 — 새 CLI 를 붙일 때 조용히 새는 자리들을 대조한다.

★왜 관문인가: 아웃오브프로세스 CLI 프로바이더는 **여러 곳에 자기 이름을 등록해야**
온전히 산다. 하나라도 빠지면 에러가 아니라 '조용한 반쪽 동작'이 된다 —
  · vocab_crystallization 의 라벨 목록에서 빠지면 그 프로바이더의 주행이 통째로
    어휘 결정화에 안 보인다(2026-07-21 claude_code 실사고: Bash 42·execute_ibl 162건/7일이
    불가시였다).
  · model_resolver._NO_KEY_PROVIDERS 에서 빠지면 "API 키가 설정되지 않았습니다"로 즉사한다
    (2026-08-17 claude_code 실사고).
  · 팩토리에서 빠지면 설정에 적어도 안 잡힌다.
사람이 고른 grep 범위는 반드시 샌다(pitfall_hand_picked_sweep_leaks) — 그래서 목록을
지우는 대신, 목록이 클래스 정의와 어긋나면 실패시킨다.
"""

import boot_paths  # noqa: F401


def _cli_provider_classes():
    """등록된 모든 CliSubprocessProvider 서브클래스 (재귀)."""
    from providers.cli_provider import CliSubprocessProvider

    seen = []

    def walk(cls):
        for sub in cls.__subclasses__():
            if sub not in seen:
                seen.append(sub)
            walk(sub)

    # 서브클래스가 등록되려면 모듈이 임포트돼 있어야 한다 — 패키지 __init__ 이 전부 올린다.
    import providers  # noqa: F401
    walk(CliSubprocessProvider)
    return seen


def test_labels_registered_in_vocab_crystallization():
    """모든 CLI 프로바이더의 CLI_LABEL 이 어휘 결정화 로그 파서에 등록돼 있는가."""
    from cognition.vocab_crystallization import _CLI_LABELS

    missing = [
        (cls.__name__, cls.CLI_LABEL)
        for cls in _cli_provider_classes()
        if cls.CLI_LABEL not in _CLI_LABELS
    ]
    assert not missing, (
        f"CLI_LABEL 미등록: {missing} — cognition/vocab_crystallization.py 의 "
        f"_CLI_LABELS 에 추가하십시오. 빠지면 그 프로바이더의 tool_use/tool_result 가 "
        f"어휘 결정화에 통째로 안 보입니다(2026-07-21 실사고)."
    )


def test_no_key_providers_covers_cli():
    """CLI 프로바이더는 자체 인증이라 api_key 를 요구하면 안 된다."""
    from model_resolver import provider_needs_api_key
    from providers import get_provider

    # 팩토리에 등록된 이름 중 CLI 프로바이더로 해소되는 것들을 실제로 물어본다.
    from providers.cli_provider import CliSubprocessProvider

    cli_names = []
    for name in ("claude_code", "claude-code", "claudecode",
                 "codex", "codex_cli", "codex-cli"):
        prov = get_provider(name, api_key="", model="x", system_prompt="")
        assert isinstance(prov, CliSubprocessProvider), f"{name} 이 CLI 프로바이더가 아님"
        cli_names.append(name)

    offenders = [n for n in cli_names if provider_needs_api_key(n)]
    assert not offenders, (
        f"키 불요여야 하는데 요구함: {offenders} — base/model_resolver.py 의 "
        f"_NO_KEY_PROVIDERS 에 추가하십시오. 빠지면 시스템 AI 진입점이 "
        f"'API 키가 설정되지 않았습니다'로 즉사합니다(2026-08-17 실사고)."
    )


def test_session_stores_are_distinct_and_registered():
    """프로바이더마다 세션 저장소가 따로여야 하고(세션 id 발급자가 다르다),
    전역 목록에 등록돼 '새 대화'가 함께 비울 수 있어야 한다."""
    from providers.cli_provider import _SESSION_STORES

    classes = _cli_provider_classes()
    prefixes = [c.SESSION_STORE.prefix for c in classes if c.SESSION_STORE]
    assert len(prefixes) == len(set(prefixes)), (
        f"세션 저장소 prefix 중복: {prefixes} — 한 파일을 나눠 쓰면 한 CLI 의 세션 id 를 "
        f"다른 CLI 에 먹이게 됩니다."
    )
    registered = {s.prefix for s in _SESSION_STORES}
    missing = [p for p in prefixes if p not in registered]
    assert not missing, f"세션 저장소 미등록: {missing} (CliSessionStore 로 생성할 것)"


def test_derived_session_keys_are_swept_on_reset():
    """파생 세션 키(`키#해시`)도 '새 대화'가 지운다.

    codex 는 시스템 프롬프트 해시를 키에 붙인다 — 호출부는 그 파생을 모르고 평범한
    registry_key 를 넘기므로, 접두 스윕이 없으면 옛 스레드가 살아남는다.
    """
    from providers.cli_provider import CliSessionStore

    store = CliSessionStore("__test_sweep", "TestStore")
    try:
        store.save_map({
            "proj:agent": "sid-plain",
            "proj:agent#abc12345": "sid-derived",
            "proj:agent#def67890": "sid-derived2",
            "other:agent": "sid-keep",
        })
        store.save_sizes({"proj:agent#abc12345": 123, "other:agent": 456})
        store.clear_agent("proj:agent")
        store.clear_size("proj:agent")

        left = store.load_map()
        assert left == {"other:agent": "sid-keep"}, f"스윕 후 잔재: {left}"
        assert store.load_sizes() == {"other:agent": 456}
    finally:
        for p in (store.map_path(), store.size_path()):
            try:
                p.unlink()
            except OSError:
                pass


def test_no_hand_copied_no_key_sets():
    """'키 불요 프로바이더' 집합을 model_resolver 밖에서 손으로 적지 않는다.

    ★부류 스윕은 관문을 먼저 세운다(pitfall_hand_picked_sweep_leaks): 이 집합의 손복사본이
    consciousness_agent 와 channel_poller 두 곳에 살아 있었고, codex 를 추가하며 하나는
    바로 눈에 띄었지만 다른 하나(channel_poller)는 grep 범위 밖이라 놓칠 뻔했다 —
    놓쳤다면 기어가 codex 인 동안 채널 수신이 통째로 "모델/키 없음"으로 조용히 죽었다.
    판정의 정본은 model_resolver.provider_needs_api_key 하나다.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent
    canon = root / "base" / "model_resolver.py"
    # `claude_code` 와 `ollama` 가 같은 리터럴 집합/튜플 안에 함께 나타나면 손복사본이다.
    pattern = re.compile(
        r"[{(\[][^{}()\[\]]*[\"']claude[_-]?code[\"'][^{}()\[\]]*[\"']ollama[\"'][^{}()\[\]]*[)}\]]"
    )
    offenders = []
    for path in root.rglob("*.py"):
        if path == canon or path.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            offenders.append(f"{path.relative_to(root)}:{line_no}")

    assert not offenders, (
        f"키 불요 프로바이더 집합의 손복사본: {offenders} — "
        f"model_resolver.provider_needs_api_key() 호출로 바꾸십시오. "
        f"집합을 두 벌 두면 새 프로바이더 추가 때 한쪽만 고쳐져 조용히 죽습니다."
    )


def test_turn_state_is_reset_between_turns():
    """턴-국소 캐시가 턴 시작마다 비워지는가.

    ★조용한 실패라 관문이 필요하다: Codex 는 아이템 id 를 `item_0`·`item_1` 로 **매 턴
    처음부터** 다시 매긴다. 지난 턴의 잔재가 남으면 이번 턴의 같은 id 가 '이미 헤더를 냈다'로
    오인돼 tool_start 가 통째로 사라지고, process_message 의 start↔result 페어링이 한 칸씩
    밀려 도구 결과가 엉뚱한 호출에 붙는다(에러 없이).
    """
    from providers import get_provider

    p = get_provider("codex", api_key="", model="x", system_prompt="")
    p._started_items.add("item_0")
    p._reset_turn_state()
    assert not p._started_items, "턴 상태가 안 비워짐 — 도구 페어링이 밀린다"

    # 상위 오케스트레이터가 실제로 이 훅을 부르는지도 확인한다(훅만 있고 호출이 없으면
    # 고친 게 아니다). 초기화 안 된 provider 는 곧장 error 이벤트로 빠지므로,
    # 그 직전에 턴 상태 초기화가 일어났는지 본다.
    p._client = None
    p._started_items.add("item_9")
    p._pending_map_tags.append("[MAP:{}]")
    events = list(p.process_message_stream("x"))
    assert events and events[0]["type"] == "error"
    assert not p._started_items, "process_message_stream 이 _reset_turn_state 를 안 부른다"
    assert not p._pending_map_tags, "지도 태그가 턴 사이에 남는다"


def test_codex_session_key_tracks_system_prompt():
    """시스템 프롬프트가 바뀌면 세션 키가 바뀌어 자동으로 fresh 로 끊긴다.

    Codex 는 시스템 프롬프트를 fresh 턴 프롬프트 머리로만 받으므로(--append-system-prompt
    등가물 없음), 키가 그대로면 옛 지침을 문 스레드가 영영 이어진다.
    """
    from providers import get_provider

    a = get_provider("codex", api_key="", model="x", system_prompt="지침 A", agent_id="ag")
    b = get_provider("codex", api_key="", model="x", system_prompt="지침 B", agent_id="ag")
    c = get_provider("codex", api_key="", model="x", system_prompt="지침 A", agent_id="ag")
    ka, kb, kc = a._get_session_key(), b._get_session_key(), c._get_session_key()
    assert ka != kb, "프롬프트가 바뀌었는데 세션 키가 같다 — 옛 지침 스레드가 이어진다"
    assert ka == kc, "같은 프롬프트인데 키가 다르다 — 세션이 매번 끊긴다"
    assert ka.startswith("ag#"), f"키 형식이 접두 스윕과 안 맞는다: {ka}"


def test_codex_model_carries_reasoning_effort():
    """`슬러그:강도` 표기가 -m 과 model_reasoning_effort 두 인자로 갈린다.

    ★강도가 `model` 칸에 사는 이유는 편의가 아니라 캐시 정합이다: 프로바이더 캐시 키가
    `bucket|provider|model|keyhash` 라, 강도가 그 문자열 밖에 있으면 같은 슬러그를 쓰는
    두 티어(고급=sol:max · 중급=sol:low)가 캐시에서 충돌해 **에러 없이 강도가 뒤바뀐다**.
    """
    from providers import get_provider

    def cmd_for(model):
        p = get_provider("codex", api_key="", model=model, system_prompt="")
        p._binary_path = "/fake/codex"
        return p._build_command(stream=True)

    # 강도 명시 → 두 인자로 갈린다
    c = cmd_for("gpt-5.6-sol:high")
    assert "-m" in c and c[c.index("-m") + 1] == "gpt-5.6-sol", f"슬러그가 안 갈렸다: {c}"
    assert 'model_reasoning_effort="high"' in c, f"강도 오버라이드가 없다: {c}"

    # 강도 없음 → 오버라이드를 보내지 않는다(사용자 config.toml 을 따른다)
    c = cmd_for("gpt-5.6-sol")
    assert c[c.index("-m") + 1] == "gpt-5.6-sol"
    assert not any("model_reasoning_effort" in str(x) for x in c), \
        f"강도를 안 적었는데 오버라이드가 실렸다: {c}"

    # 철자 오류 → 무시하고 원문 유지(모르는 값을 흘리면 codex 가 턴을 통째로 거절한다)
    c = cmd_for("gpt-5.6-sol:extreme")
    assert not any("model_reasoning_effort" in str(x) for x in c), \
        f"알 수 없는 강도가 그대로 흘렀다: {c}"

    # 캐시 키 정합: 강도가 다르면 model 문자열이 달라야 한다(= 캐시 키가 갈린다)
    a = get_provider("codex", api_key="", model="gpt-5.6-sol:max", system_prompt="")
    b = get_provider("codex", api_key="", model="gpt-5.6-sol:low", system_prompt="")
    assert a.model != b.model, "강도가 캐시 키에 안 실린다 — 두 티어가 프로바이더를 나눠 쓴다"


def test_codex_oneshot_does_not_drop_user_config():
    """원샷이 `--ignore-user-config` 로 추론강도를 조용히 떨어뜨리지 않는다.

    2026-08-31 실측: 그 플래그는 17,222→16,270(5.5%)만 아끼면서 사용자의
    model_reasoning_effort 를 빼앗아 **원샷만 모델 기본 강도로** 돌게 만든다.
    경로마다 강도가 다르면 비용도 품질도 재현되지 않는다.
    """
    from providers import get_provider

    p = get_provider("codex", api_key="", model="gpt-5.6-sol", system_prompt="")
    p._binary_path = "/fake/codex"
    p.no_tools = True
    c = p._build_command(stream=True, tools_mode="none")
    assert "--ignore-user-config" not in c, (
        "원샷이 사용자 config 를 버린다 — 추론강도가 경로마다 갈린다 "
        "(절감 5.5% 대가로는 비싸다, 2026-08-31 실측)"
    )


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 로 위임한다(두 번째 러너는 드리프트한다).
    import sys

    import pytest

    raise SystemExit(pytest.main([__file__, "-v"] + sys.argv[1:]))
