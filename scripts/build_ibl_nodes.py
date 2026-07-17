#!/usr/bin/env python3
"""ibl_nodes.yaml 빌드 — 편집용 소스 6개를 단일 yaml로 병합 + 삼각 검증.

편집 워크플로:
1) `data/ibl_nodes_src/<name>.yaml` 중 하나를 편집
2) `python scripts/build_ibl_nodes.py` 실행
3) `data/ibl_nodes.yaml`이 갱신됨 (런타임이 읽는 단일 파일)

런타임 코드는 단일 ibl_nodes.yaml만 읽는다 (ibl_access / tool_loader /
tool_selector / system_tools).

병합 방식: 바이트-단위 연결. 소스 파일들의 내용은 원본 yaml의 해당 span에서
잘라낸 바이트 그대로이므로, 정상 워크플로에서는 byte-identical 라운드트립이
보장된다 (소스 편집 후엔 그 부분만 달라짐).

검증 (2026-05-28 추가) — router:handler 액션에 대해 삼각 일치 확인:
  src.tool       ↔  packages/.../tool.json 의 name
  src.ops.values ↔  tool.json input_schema.properties.op.enum
  src.ops.default ↔ tool.json input_schema.properties.op.default
  src.ops.values ↔  handler.py 의 _OP_DISPATCHERS[tool_name] 키 (AST, 정확)
                       또는 _OP_DISPATCHERS 없으면 op 문자열 substring (폴백)
  src.ops.default ↔ handler.py 의 _OP_DEFAULTS[tool_name] (AST, _OP_DISPATCHERS 있을 때만)
실패하면 `--check`는 비0 종료, 일반 빌드는 경고만 출력.

코퍼스 param 정합 (2026-06-04 추가, --check/--validate 전용):
  학습 코퍼스의 액션별 param 키 ↔ (핸들러 읽기키 ∪ 액션 aliases 선언 ∪ 보편키 ∪ target_key).
  코퍼스가 자연어로 쓰는 키를 핸들러가 조용히 무시하는 신규 불일치를 검출 (silent-ignore 회귀 방지).
  의도된 노이즈는 CORPUS_PARAM_ALLOW 에 등록. 파서/코퍼스 미가용 시 건너뜀.

파라미터 별칭 (2026-07-03 데이터화):
  각 액션 정의처(src yaml / 패키지 ibl_actions.yaml)의 `aliases: {정규키: [별칭...]}` 블록이
  단일 소스 — 빌드가 ibl_nodes.yaml 로 병합하고, 런타임(ibl_routing._normalize_param_aliases)은
  레지스트리에서 읽는다. 옛 ibl_routing.ACTION_PARAM_ALIASES 하드코딩 테이블은 은퇴.

모듈화 (2026-07-18, 1500줄 규칙): 구현은 형제 모듈로 분할 — iblbuild_common(상수·
repo_root) / iblbuild_guards(포크·OS·launcher·교재 가드) / iblbuild_derive(tool 인덱스·
파생·병합) / iblbuild_appview(APP_* 뷰 어휘·앱 블록 검증) / iblbuild_validators(액션
삼각검증·validate). 이 파일은 진입점(build/main) + **기존 공개 이름 전부 재수출**
(migrate_*·apply_edition 등 spec-load 소비자 호환 — `build_ibl_nodes.<이름>` 불변).
"""
from __future__ import annotations
import argparse
import ast  # noqa: F401 (재수출 호환 — 구현은 iblbuild_validators 로 이동)
import hashlib
import json
import re  # noqa: F401 (재수출 호환)
import sys
from pathlib import Path

# 형제 모듈(iblbuild_*)을 spec-load(migrate_* 등) 경로에서도 찾을 수 있게.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from iblbuild_common import (  # noqa: E402,F401
    _BACKEND_DIR,
    UNIVERSAL_PARAM_KEYS,
    RUNTIME_META_KEYS,
    CORPUS_PARAM_ALLOW,
    _file_read_keys,
    _dir_read_keys,
    NODE_ORDER,
    PACKAGE_DIRS,
    NOT_INSTALLED_PACKAGE_DIRS,
    VALID_RUNS_ON,
    DEFAULT_RUNS_ON,
    PHONE_VERIFIED_PACKAGES,
    CORPUS_FILES,
    repo_root,
    _extract_action_param_aliases,
)
from iblbuild_guards import (  # noqa: E402,F401
    PROFILE_BRANCH_ALLOWLIST,
    PROFILE_SCAN_DIRS,
    check_profile_branches,
    _is_dormant_package_path,
    OS_SEAM_ALLOWLIST,
    OS_SCAN_DIRS,
    OS_MARKERS,
    check_os_branches,
    check_launcher_handlers,
    check_textbook,
)
from iblbuild_derive import (  # noqa: E402,F401
    build_tool_index,
    derive_phone_manifest,
    derive_fixtures,
    collect_package_fragments,
    _TOOL_JSON_MARKER,
    derive_tool_json_docs,
    collect_dormant_package_qualifiers,
    _KEY_ENV_SUFFIX_RE,
    _DIRECT_ENV_CALL_RE,
    _CHECK_API_KEY_RE,
    _META_KEY_EXCLUDE_ENV_VARS,
    _KR_LOCKED_AUTH_SERVICES,
    _KR_LOCKED_ENV_VARS,
    _HEAVY_DEP_MARKERS,
    _registry_env_vars,
    _load_auth_registry,
    derive_package_meta,
    merge_fragments,
    serialize_nodes_document,
)
from iblbuild_appview import (  # noqa: E402,F401
    APP_VIEW_TYPES,
    APP_VIEW_EVENTS,
    APP_EVENT_VARS,
    APP_INPUT_TYPES,
    APP_FORM_FIELD_TYPES,
    APP_AIDOCK_MODES,
    APP_KEYS,
    APP_TPL_FILTERS,
    _APP_VOCAB_DOC_PATHS,
    check_app_vocab_docs,
    check_view_renderers,
    _app_action_templates,
    _block_local_keys,
    _check_ai_dock,
    _check_compose_channels,
    _app_check_filter_block,
    _app_check_view,
    _app_check_filters,
    _validate_app_block,
    validate_standalone_instruments,
    validate_app_blocks,
    _template_param_keys,
    validate_app_template_params,
)
from iblbuild_validators import (  # noqa: E402,F401
    _extract_op_dispatchers,
    _extract_op_defaults,
    _check_action,
    _load_corpus_param_keys,
    validate_corpus_params,
    validate_runs_on,
    validate_transform_contract,
    validate_phone_reachability,
    validate_fixture_coverage,
    validate_node_guides,
    STANDARD_CORE_NODES,
    validate_standard_core,
    validate_always_on,
    validate,
)


def build(check: bool = False, validate_only: bool = False) -> int:
    root = repo_root()
    src_dir = root / "data" / "ibl_nodes_src"
    target = root / "data" / "ibl_nodes.yaml"

    if not src_dir.is_dir():
        print(f"[build_ibl_nodes] 소스 디렉토리 없음: {src_dir}", file=sys.stderr)
        return 2

    header = (
        "# GENERATED — DO NOT EDIT\n"
        "# Source : data/ibl_nodes_src/{meta,sense,self,limbs,others,engines,table}.yaml\n"
        "# Rebuild: python3 scripts/build_ibl_nodes.py\n"
        "# Check  : python3 scripts/build_ibl_nodes.py --check\n"
        "\n"
    )
    parts: list[str] = [header]

    meta_path = src_dir / "meta.yaml"
    if not meta_path.is_file():
        print(f"[build_ibl_nodes] 누락: {meta_path}", file=sys.stderr)
        return 2
    parts.append(meta_path.read_text(encoding="utf-8"))

    # `nodes:` 헤더를 명시적으로 삽입 (소스 파일 어디에도 두지 않는다).
    parts.append("nodes:\n")

    for node in NODE_ORDER:
        node_path = src_dir / f"{node}.yaml"
        if not node_path.is_file():
            print(f"[build_ibl_nodes] 누락: {node_path}", file=sys.stderr)
            return 2
        parts.append(node_path.read_text(encoding="utf-8"))

    merged = "".join(parts)

    # YAML 파싱으로 sanity check — 노드/액션 수가 정상인지 + 검증.
    try:
        import yaml as _yaml
    except ImportError:
        print(
            "[build_ibl_nodes] PyYAML 없음 — 검증 건너뜀 (sanity check 불가)",
            file=sys.stderr,
        )
        _yaml = None

    data: dict | None = None
    output = merged          # 기본: 설치된 fragment 가 없으면 바이트 동일(안전 착지)
    frag_issues: list = []
    if _yaml is not None:
        data = _yaml.safe_load(merged)
        # --- 설치된 패키지 어휘 fragment 병합 (Phase 0) ---
        fragments, collect_issues = collect_package_fragments(root, _yaml)
        merge_issues = merge_fragments(data, fragments) if fragments else []
        frag_issues = collect_issues + merge_issues
        frag_action_n = sum(len(a) for _, _, a in fragments)
        if fragments and not frag_issues:
            # fragment 가 있고 병합 성공 시에만 재직렬화(그 외엔 기존 텍스트 유지).
            output = serialize_nodes_document(header, data, _yaml)
        nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
        total_actions = sum(
            len(n.get("actions") or {}) for n in nodes.values() if isinstance(n, dict)
        )
        extra = (
            f", 패키지 fragment {len(fragments)}개(+{frag_action_n} 액션)"
            if fragments else ""
        )
        print(
            f"[build_ibl_nodes] 노드 {len(nodes)}개, 액션 {total_actions}개{extra} "
            f"({sum(1 for _ in output.splitlines())}줄, {len(output.encode('utf-8'))}바이트)"
        )

    # --- 삼각 검증 ---
    validation_failed = False
    if data is not None:
        issues = frag_issues + validate(data, root)
        if issues:
            validation_failed = True
            print(
                f"[build_ibl_nodes] 검증 실패: {len(issues)}건",
                file=sys.stderr,
            )
            for issue in issues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 검증 통과 ✓ (등록·op enum·default·handler 분기)")

    # --- 코퍼스 param 정합 검사 (--check/--validate 전용) ---
    # 코퍼스 드리프트가 평소 yaml 빌드를 막지 않도록, 게이트(check/validate)에서만 평가.
    corpus_failed = False
    if data is not None and (check or validate_only):
        cissues = validate_corpus_params(data, root)
        if cissues is None:
            print(
                "[build_ibl_nodes] 코퍼스/파서 미가용 — param 정합 검사 건너뜀",
                file=sys.stderr,
            )
        elif cissues:
            corpus_failed = True
            print(
                f"[build_ibl_nodes] 코퍼스 param 정합 실패: {len(cissues)}건",
                file=sys.stderr,
            )
            for issue in cissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 코퍼스 param 정합 통과 ✓")

    # --- 행동 건강 fixture 완전성 (--check/--validate 전용) ---
    # 실행 가능한(items/scalar) 액션은 ibl_fixtures.json 에 fixture 또는 exempt 가 있어야 한다.
    # 신규 어휘가 건강검사망을 조용히 빠져나가는 걸 *커밋 게이트*로 막는다.
    fixture_failed = False
    if data is not None and (check or validate_only):
        xissues = validate_fixture_coverage(data, root)
        if xissues:
            fixture_failed = True
            print(
                f"[build_ibl_nodes] fixture 완전성 실패: {len(xissues)}건 "
                f"(items/scalar 액션은 data/ibl_fixtures.json 에 fixture 또는 exempt 필수)",
                file=sys.stderr,
            )
            for issue in xissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] fixture 완전성 통과 ✓ (모든 items/scalar 액션이 fixture/exempt 보유)")

    # --- 포크-가드: INDIEBIZ_PROFILE 분기 위치 (--check/--validate 전용) ---
    profile_failed = False
    if check or validate_only:
        pissues = check_profile_branches(root)
        if pissues:
            profile_failed = True
            print(
                f"[build_ibl_nodes] 포크-가드 실패: {len(pissues)}건 "
                f"(이음매 위 INDIEBIZ_PROFILE 분기)",
                file=sys.stderr,
            )
            for issue in pissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print(
                f"[build_ibl_nodes] 포크-가드 통과 ✓ "
                f"(INDIEBIZ_PROFILE 분기 {len(PROFILE_BRANCH_ALLOWLIST)}개, 전부 이음매 아래)"
            )

    # --- OS-가드: platform/유닉스-바이너리 의존 위치 (--check/--validate 전용) ---
    os_failed = False
    if check or validate_only:
        oissues = check_os_branches(root)
        if oissues:
            os_failed = True
            print(
                f"[build_ibl_nodes] OS-가드 실패: {len(oissues)}건 "
                f"(몸 독립 코어에 OS 의존)",
                file=sys.stderr,
            )
            for issue in oissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print(
                f"[build_ibl_nodes] OS-가드 통과 ✓ "
                f"(OS 이음매 {len(OS_SEAM_ALLOWLIST)}개 파일 — 윈도우/리눅스 이식 점검 대상)"
            )

    # --- launcher-가드: 어휘→라우터→main.js 핸들러 계약 (--check/--validate 전용) ---
    launcher_failed = False
    if check or validate_only:
        lissues = check_launcher_handlers(root)
        if lissues:
            launcher_failed = True
            print(
                f"[build_ibl_nodes] launcher-가드 실패: {len(lissues)}건 "
                f"(라우팅된 창 명령에 main.js 핸들러 부재 — 침묵 실패)",
                file=sys.stderr,
            )
            for issue in lissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print(
                "[build_ibl_nodes] launcher-가드 통과 ✓ "
                "(라우팅된 창 명령 전부 main.js switch 에 핸들러 보유)"
            )

    # --- 교재-가드: 12_ibl_only.md ↔ 카탈로그 (--check/--validate 전용) ---
    textbook_failed = False
    if check or validate_only:
        tissues = check_textbook(root, data)
        if tissues:
            textbook_failed = True
            print(
                f"[build_ibl_nodes] 교재-가드 실패: {len(tissues)}건 "
                f"(12_ibl_only.md 스니펫/노드표가 카탈로그와 불일치)",
                file=sys.stderr,
            )
            for issue in tissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 교재-가드 통과 ✓ (스니펫 실존 + 노드 선택표 집합 일치)")

    # --- 뷰-어휘 문서-동기 가드: APP_* 선언 ↔ 교육 문서 어휘 줄 (--check/--validate 전용) ---
    appvocab_failed = False
    if check or validate_only:
        avissues = check_app_vocab_docs(root)
        if avissues:
            appvocab_failed = True
            print(
                f"[build_ibl_nodes] 뷰-어휘 가드 실패: {len(avissues)}건 "
                f"(교육 문서 어휘 줄이 APP_VIEW_TYPES/APP_FORM_FIELD_TYPES 와 불일치 — "
                f"뷰 어휘 변경은 문서 2곳 동시 갱신이 언어 개정 절차)",
                file=sys.stderr,
            )
            for issue in avissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print(
                "[build_ibl_nodes] 뷰-어휘 가드 통과 ✓ "
                "(ibl.md·new_action_checklist.md 어휘 줄 = 코드 선언)"
            )

    # --- 뷰-렌더러 가드: APP_VIEW_TYPES ↔ 렌더러 2곳 p.type 파리티 (--check/--validate 전용) ---
    renderer_failed = False
    if check or validate_only:
        rvissues = check_view_renderers(root)
        if rvissues:
            renderer_failed = True
            print(
                f"[build_ibl_nodes] 뷰-렌더러 가드 실패: {len(rvissues)}건 "
                f"(선언된 view 어휘를 렌더러가 안 그림 — 빈 화면(좀비) 또는 데스크탑/원격 파리티 깨짐)",
                file=sys.stderr,
            )
            for issue in rvissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print(
                "[build_ibl_nodes] 뷰-렌더러 가드 통과 ✓ "
                "(APP_VIEW_TYPES 전부 데스크탑·원격 렌더러에 p.type 케이스 보유)"
            )

    # --- 앱-템플릿 param 가드: app: 템플릿 리터럴 키 ↔ 액션 허용키 (--check/--validate 전용) ---
    # 선언형 앱이 핸들러가 안 읽는 키를 넘겨 조용히 무시되는 오답(성공처럼 보임)을
    # 저술 시점 하드 실패로 잡는다(런타임 soft 경고 → 빌드 hard 게이트).
    appparam_failed = False
    if check or validate_only:
        apissues = validate_app_template_params(data, root) if data is not None else []
        if apissues:
            appparam_failed = True
            print(
                f"[build_ibl_nodes] 앱-템플릿 param 가드 실패: {len(apissues)}건 "
                f"(app 템플릿이 핸들러 미인식 파라미터 전달 — 침묵 무시되는 오타)",
                file=sys.stderr,
            )
            for issue in apissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 앱-템플릿 param 가드 통과 ✓ (모든 app 템플릿 키가 액션 허용키)")

    if validate_only:
        return 1 if (validation_failed or corpus_failed or fixture_failed
                     or profile_failed or os_failed or launcher_failed
                     or textbook_failed or appvocab_failed
                     or renderer_failed or appparam_failed) else 0

    # 폰 매니페스트 파생 (runs_on + 검증된 폰 패키지). data 파싱 성공 시에만.
    manifest_path = root / "data" / "phone_manifest.json"
    manifest_text = None
    if data is not None:
        manifest = derive_phone_manifest(data, root)
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"

    # 능력 메타 파생 (Phase 4, needs_key/weight/locale — 코드 스캔, 손수 유지 아님).
    pkg_meta_path = root / "data" / "package_meta.json"
    pkg_meta_text = json.dumps(derive_package_meta(root), ensure_ascii=False, indent=2) + "\n"

    # 행동 건강 fixture 파생 (액션별 fixture:/exempt: 필드 → 중앙 파일). data 파싱 성공 시에만.
    fixtures_path = root / "data" / "ibl_fixtures.json"
    fixtures_text = None
    if data is not None:
        fixtures_text = json.dumps(derive_fixtures(data), ensure_ascii=False, indent=2) + "\n"

    # tool.json 파생 (tool_json 블록 보유 패키지만 — 정합성을 검증에서 구조로).
    # op-bearing 도구의 enum/default 는 저장이 아니라 액션 ops 에서 주입되므로
    # src ↔ tool.json 드리프트가 이관 패키지에선 구조적으로 불가능하다.
    tool_json_docs: dict = {}
    try:
        import yaml as _yaml_for_tj
        tool_json_docs, tj_issues = derive_tool_json_docs(root, _yaml_for_tj)
        if tj_issues:
            validation_failed = True
            print(
                f"[build_ibl_nodes] tool.json 파생 실패: {len(tj_issues)}건",
                file=sys.stderr,
            )
            for issue in tj_issues:
                print(f"  ✗ {issue}", file=sys.stderr)
    except ImportError:
        pass

    if check:
        if not target.is_file():
            print(f"[build_ibl_nodes] check: 타깃 부재 — {target}", file=sys.stderr)
            return 1
        current = target.read_text(encoding="utf-8")
        bytes_ok = current == output
        if not bytes_ok:
            h_cur = hashlib.sha256(current.encode("utf-8")).hexdigest()[:12]
            h_new = hashlib.sha256(output.encode("utf-8")).hexdigest()[:12]
            print(
                f"[build_ibl_nodes] check: 바이트 불일치 — 빌드 결과가 현재 yaml과 다름\n"
                f"  현재 {h_cur} / 빌드 {h_new}",
                file=sys.stderr,
            )
        else:
            print("[build_ibl_nodes] check: 바이트 일치 ✓")
        # 폰 매니페스트 정합 (드리프트 방지)
        manifest_ok = True
        if manifest_text is not None:
            on_disk = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else None
            manifest_ok = on_disk == manifest_text
            if not manifest_ok:
                print(
                    f"[build_ibl_nodes] check: phone_manifest.json 불일치 — "
                    f"`python3 scripts/build_ibl_nodes.py` 로 재생성 필요",
                    file=sys.stderr,
                )
            else:
                print("[build_ibl_nodes] check: phone_manifest.json 일치 ✓")
        # 능력 메타 정합 (드리프트 방지 — needs_key/weight/locale 은 코드가 유일한 소스)
        pkg_meta_on_disk = pkg_meta_path.read_text(encoding="utf-8") if pkg_meta_path.is_file() else None
        pkg_meta_ok = pkg_meta_on_disk == pkg_meta_text
        if not pkg_meta_ok:
            print(
                f"[build_ibl_nodes] check: package_meta.json 불일치 — "
                f"`python3 scripts/build_ibl_nodes.py` 로 재생성 필요",
                file=sys.stderr,
            )
        else:
            print("[build_ibl_nodes] check: package_meta.json 일치 ✓")
        # fixture 파생 정합 (드리프트 방지 — 소스는 액션별 fixture:/exempt: 필드)
        fixtures_ok = True
        if fixtures_text is not None:
            fx_on_disk = fixtures_path.read_text(encoding="utf-8") if fixtures_path.is_file() else None
            fixtures_ok = fx_on_disk == fixtures_text
            if not fixtures_ok:
                print(
                    f"[build_ibl_nodes] check: ibl_fixtures.json 불일치 — "
                    f"`python3 scripts/build_ibl_nodes.py` 로 재생성 필요",
                    file=sys.stderr,
                )
            else:
                print("[build_ibl_nodes] check: ibl_fixtures.json 일치 ✓")
        # tool.json 파생 정합 (드리프트 방지 — 소스는 ibl_actions.yaml tool_json 블록 + ops)
        tool_json_ok = True
        for tj_path, tj_text in sorted(tool_json_docs.items()):
            on_disk = tj_path.read_text(encoding="utf-8") if tj_path.is_file() else None
            if on_disk != tj_text:
                tool_json_ok = False
                print(
                    f"[build_ibl_nodes] check: {tj_path.parent.name}/tool.json 불일치 — "
                    f"`python3 scripts/build_ibl_nodes.py` 로 재생성 필요",
                    file=sys.stderr,
                )
        if tool_json_ok and tool_json_docs:
            print(f"[build_ibl_nodes] check: tool.json 파생 일치 ✓ ({len(tool_json_docs)}개 패키지)")
        # 표준 코어 매니페스트 신선도 (git 추적 패키지/앱/어휘 집합 파생) — 코어/사용자 경계 단일 진실
        core_manifest_ok = True
        try:
            import build_core_manifest as _bcm
            _expected = _bcm._serialize(_bcm.build_manifest())
            _cur = _bcm.MANIFEST_PATH.read_text(encoding="utf-8") if _bcm.MANIFEST_PATH.is_file() else None
            if _cur != _expected:
                core_manifest_ok = False
                print(
                    "[build_ibl_nodes] check: core_manifest.json 불일치 — "
                    "`python3 scripts/build_core_manifest.py` 로 재생성 필요",
                    file=sys.stderr,
                )
            else:
                print("[build_ibl_nodes] check: core_manifest.json 일치 ✓")
        except Exception as _e:
            print(f"[build_ibl_nodes] check: core_manifest 검사 건너뜀 ({_e})")
        # 설치 파일 필터 신선도 (매니페스트 주도 비-코어 제외가 package.json 에 반영됐나)
        dist_filter_ok = True
        try:
            import build_dist_filter as _bdf
            _pkg = json.loads(_bdf.PKG_JSON.read_text(encoding="utf-8"))
            _entry = _bdf._data_entry(_pkg.get("build", {}))
            _cur = list(_entry.get("filter", []))
            _want = _bdf._with_generated_filter(_cur, _bdf._generated_block())
            if _cur != _want:
                dist_filter_ok = False
                print(
                    "[build_ibl_nodes] check: package.json 설치필터 stale — "
                    "`python3 scripts/build_dist_filter.py` 재실행 필요",
                    file=sys.stderr,
                )
            else:
                print("[build_ibl_nodes] check: 설치필터(dist) 일치 ✓")
        except Exception as _e:
            print(f"[build_ibl_nodes] check: dist_filter 검사 건너뜀 ({_e})")
        return 0 if (bytes_ok and manifest_ok and pkg_meta_ok and fixtures_ok
                     and tool_json_ok and core_manifest_ok and dist_filter_ok
                     and not validation_failed
                     and not corpus_failed and not fixture_failed
                     and not profile_failed and not os_failed
                     and not launcher_failed and not textbook_failed
                     and not appvocab_failed
                     and not renderer_failed and not appparam_failed) else 1

    if validation_failed:
        print(
            "[build_ibl_nodes] 빌드는 수행했지만 검증 실패 — "
            "ibl_nodes.yaml 작성 보류. --validate 로 재확인하세요.",
            file=sys.stderr,
        )
        return 1

    target.write_text(output, encoding="utf-8")
    print(f"[build_ibl_nodes] 작성: {target}")
    if manifest_text is not None:
        manifest_path.write_text(manifest_text, encoding="utf-8")
        print(f"[build_ibl_nodes] 작성: {manifest_path} "
              f"(폰 패키지 {len(PHONE_VERIFIED_PACKAGES)}, runnable {manifest_text.count(':')})")
    pkg_meta_path.write_text(pkg_meta_text, encoding="utf-8")
    print(f"[build_ibl_nodes] 작성: {pkg_meta_path}")
    if fixtures_text is not None:
        fixtures_path.write_text(fixtures_text, encoding="utf-8")
        print(f"[build_ibl_nodes] 작성: {fixtures_path}")
    tj_written = 0
    for tj_path, tj_text in sorted(tool_json_docs.items()):
        current = tj_path.read_text(encoding="utf-8") if tj_path.is_file() else None
        if current != tj_text:
            tj_path.write_text(tj_text, encoding="utf-8")
            tj_written += 1
    if tool_json_docs:
        print(
            f"[build_ibl_nodes] tool.json 파생: {len(tool_json_docs)}개 패키지 "
            f"(갱신 {tj_written}개)"
        )
    # 표준 코어 매니페스트 재생성 (git 추적 패키지/앱/어휘 집합 파생 — 코어/사용자 경계)
    try:
        import build_core_manifest as _bcm
        _bcm.MANIFEST_PATH.write_text(_bcm._serialize(_bcm.build_manifest()), encoding="utf-8")
        print(f"[build_ibl_nodes] 작성: {_bcm.MANIFEST_PATH} (표준 코어 매니페스트)")
    except Exception as _e:
        print(f"[build_ibl_nodes] core_manifest 재생성 건너뜀 ({_e})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="작성하지 않고 현재 data/ibl_nodes.yaml과 일치 + 검증 통과 확인 (CI/pre-commit용)",
    )
    ap.add_argument(
        "--validate",
        action="store_true",
        help="삼각 검증만 수행 (yaml 작성·바이트 비교 없음)",
    )
    args = ap.parse_args(argv)
    return build(check=args.check, validate_only=args.validate)


if __name__ == "__main__":
    raise SystemExit(main())
