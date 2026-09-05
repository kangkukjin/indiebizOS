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
    atomic_write_text,
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
    GUARD_INPUT_PATTERNS,
    guard_inputs_regex,
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
    check_self_image,
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
from iblbuild_params_check import validate_declared_params, validate_impl_reads
from iblbuild_validators import (  # noqa: E402,F401
    _extract_op_dispatchers,
    _extract_op_defaults,
    _check_action,
    _load_corpus_param_keys,
    validate_corpus_params,
    validate_corpus_vocab,
    validate_runs_on,
    validate_transform_contract,
    validate_phone_reachability,
    validate_fixture_coverage,
    validate_node_guides,
    validate_guide_wiring,
    guide_staleness_warnings,
    validate_enum_handler_branches,
    STANDARD_CORE_NODES,
    validate_standard_core,
    validate_always_on,
    validate,
    compression_warnings,
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

        # --- B35-3 2조각: param 타입 선언 완전성 (2026-08-24 #repair) ---
        # 위 정합 검사는 "핸들러가 이 키를 읽나" 만 묻는다. 타입 관문(ibl_routing)이 보는
        # 진실 소스는 tool.json input_schema 인데 거기 없는 자리는 관문이 원리적으로 눈감고,
        # 그 자리에서 파이썬 예외가 그대로 샜다. 세지 말고 닫는다 — 빌드 실패로.
        dissues = validate_declared_params(data, root)
        if dissues is None:
            print("[build_ibl_nodes] 코퍼스/파서 미가용 — param 선언 완전성 검사 건너뜀",
                  file=sys.stderr)
        elif dissues:
            corpus_failed = True
            print(f"[build_ibl_nodes] param 선언 완전성 실패: {len(dissues)}건", file=sys.stderr)
            for issue in dissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] param 선언 완전성 통과 ✓ (미선언 0)")

        # --- 구현-읽기 감사 (2026-08-29 #repair) ---
        # 위 두 검사는 코퍼스 앵커라 코퍼스가 안 쓰는 param 자리를 원리적으로 못 본다.
        # 그 틈으로 web-builder checks(구현 O·가이드 O·선언 X)가 런타임 컨테이너
        # 관문에 거절돼 죽어 있었다. 앵커를 구현 자신에 둔다 — 컨테이너 기대 미선언은
        # 즉시, 스칼라 미선언은 동결 대장(IMPL_READ_BASELINE) 밖 신규만 빌드 실패.
        rissues = validate_impl_reads(data, root)
        if rissues:
            corpus_failed = True
            print(f"[build_ibl_nodes] 구현-읽기 감사 실패: {len(rissues)}건", file=sys.stderr)
            for issue in rissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 구현-읽기 감사 통과 ✓ (죽은 컨테이너 자리 0 · 신규 미선언 0)")

        # 코퍼스 어휘 생존 검사 (2026-08-22) — param 정합은 "핸들러가 이 키를 읽나" 만 묻고
        # "이 액션이 아직 있나" 는 묻지 않았다. 그 틈으로 은퇴 어휘 20여 종 208항목이
        # 학습 파일에 3개월간 남아 있었다(트레이너는 DB 와 data/training/*.json 을 둘 다 읽는다).
        vissues = validate_corpus_vocab(data, root)
        if vissues is None:
            print("[build_ibl_nodes] 코퍼스/파서 미가용 — 어휘 생존 검사 건너뜀", file=sys.stderr)
        elif vissues:
            corpus_failed = True
            print(f"[build_ibl_nodes] 코퍼스 어휘 생존 실패: {len(vissues)}건", file=sys.stderr)
            for issue in vissues[:15]:
                print(f"  ✗ {issue}", file=sys.stderr)
            if len(vissues) > 15:
                print(f"  … 외 {len(vissues) - 15}건 (원인 어휘는 소수 — 위 목록으로 충분)",
                      file=sys.stderr)
            print("  → 은퇴 어휘는 라이브 코퍼스(ibl_usage.db)의 이관본을 권위로 고친다: "
                  "scripts/repair_training_dead_vocab.py", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 코퍼스 어휘 생존 통과 ✓ (죽은 어휘·파싱 불가 0)")

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

    # --- flow 선언 완전성 (--check/--validate 전용, 2026-09-05 정적 통화 검사) ---
    flow_failed = False
    if data is not None and (check or validate_only):
        from iblbuild_validators import validate_flow_coverage
        fissues = validate_flow_coverage(data, root)
        if fissues:
            flow_failed = True
            print(f"[build_ibl_nodes] flow 선언 완전성 실패: {len(fissues)}건 "
                  f"(returns: transform 액션은 flow: {{accepts, emits}} 필수 — 검사기가 이 선언만 읽는다)",
                  file=sys.stderr)
            for issue in fissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] flow 선언 완전성 통과 ✓ (모든 transform 액션이 flow 보유)")

    # --- enum-가드: 파라미터 enum ↔ handler 분기 리터럴 정합 (--check/--validate 전용) ---
    # 드리프트 부류: handler 가 지원하는 discriminator 값(예 realty source=naver)이
    # 파생 스키마 enum 에 빠져 desc 산문만 진실을 아는 상태 (2026-07-28 메모 감사에서 발굴).
    enum_failed = False
    if check or validate_only:
        eissues = validate_enum_handler_branches(root)
        if eissues:
            enum_failed = True
            print(
                f"[build_ibl_nodes] enum-가드 실패: {len(eissues)}건 "
                f"(handler 분기 리터럴이 enum 에 없음)",
                file=sys.stderr,
            )
            for issue in eissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] enum-가드 통과 ✓ (handler 분기 리터럴 ⊆ 파라미터 enum)")

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

    # --- 자기상 가드: system_structure.md '현 상태' 줄 ↔ 레지스트리 (--check/--validate 전용) ---
    # 그 줄은 세 에이전트에 항상 주입되는 정체성 코어라, 낡으면 시스템이 자기 몸 크기를
    # 틀리게 안다(2026-08-06 수리 후 9일 만에 재발 — 손 수정으론 안 잡힌다).
    selfimg_failed = False
    if check or validate_only:
        siissues = check_self_image(root, data)
        if siissues:
            selfimg_failed = True
            print(
                f"[build_ibl_nodes] 자기상 가드 실패: {len(siissues)}건 "
                f"(system_structure.md 의 '현 상태' 줄이 레지스트리와 불일치 — "
                f"이 줄은 실행·의식·평가 에이전트에 항상 주입된다)",
                file=sys.stderr,
            )
            for issue in siissues:
                print(f"  ✗ {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 자기상 가드 통과 ✓ (system_structure.md 현 상태 줄 = 레지스트리)")

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

    # --- 가이드 배선 가드 (--check/--validate 전용) ---
    # 가이드는 절차 기억이라 낡는다. 어휘 은퇴 절차엔 코퍼스 이관 의무는 있어도
    # 가이드 정리 의무가 없어서 2026-08-17 에 81KB 를 손으로 걷어냈다 — 그 의무를 여기 둔다.
    # 사실 관계(유령 등재·끊긴 코드 경로)만 하드 실패, 판단이 필요한 건 아래 경고로.
    guidewire_failed = False
    if check or validate_only:
        gwissues = validate_guide_wiring(root)
        if gwissues:
            guidewire_failed = True
            print(
                f"[build_ibl_nodes] 가이드 배선 가드 실패: {len(gwissues)}건 "
                f"(유령 등재는 침묵 주입 실패, 끊긴 경로는 잘못된 코드 지도)",
                file=sys.stderr,
            )
            for issue in gwissues:
                print(f"  \u2717 {issue}", file=sys.stderr)
        else:
            print("[build_ibl_nodes] 가이드 배선 가드 통과 \u2713 (guide_db 실존 + 코드 경로 유효)")

    # --- 압축 경고 (--check/--validate 전용, ★비차단) ---
    # 개념중복 상설 감시(핸드오프 (5)): desc 면책 과다 + 같은 group op 닮음.
    # 경고만 출력하고 종료코드에 안 섞는다 — 병합 판단은 사람 몫.
    if check or validate_only:
        cwarns = compression_warnings(data) if data is not None else []
        if cwarns:
            print(f"[build_ibl_nodes] 압축 경고(비차단): {len(cwarns)}건 — 개념중복 후보, 병합 판단은 docs/VOCAB_DEDUP_HANDOFF.md")
            for w in cwarns:
                print(f"  ⚠ {w}")
        else:
            print("[build_ibl_nodes] 압축 경고 없음 ✓ (desc 면책·op 닮음 신호 0)")

    # --- 가이드 부패 경고 (--check/--validate 전용, ★비차단) ---
    # 검출은 시스템, 결정은 사람 — 묘비로 남길지 지울지는 기계가 못 정한다(2026-08-17 실증).
    if check or validate_only:
        gwarns = guide_staleness_warnings(data, root) if data is not None else []
        if gwarns:
            print(f"[build_ibl_nodes] 가이드 부패 경고(비차단): {len(gwarns)}건")
            for w in gwarns:
                print(f"  \u26a0 {w}")
        else:
            print("[build_ibl_nodes] 가이드 부패 경고 없음 \u2713 (죽은 참조·고아 0)")

    if validate_only:
        return 1 if (validation_failed or corpus_failed or fixture_failed or flow_failed
                     or enum_failed
                     or profile_failed or os_failed or launcher_failed
                     or textbook_failed or appvocab_failed or selfimg_failed
                     or renderer_failed or appparam_failed or guidewire_failed) else 0

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
        # ── 파생물 불일치 시 *무엇이* 다른지 (2026-07-25) ──────────────────────
        # "불일치 — 재생성 필요"만 찍고 마는 검사는 약하다: 내 기계에서 재생성하면
        # 사라지는 차이일 때(= 환경 의존 파생) 원인을 영영 못 본다. 실제로 CI 첫
        # 실행에서 package_meta 가 리눅스에서만 어긋났고, 그 메시지만으로는 진단이
        # 불가능했다. 파생물은 전부 JSON 이므로 키 단위로 갈라 보여준다.
        def _print_derived_diff(label: str, on_disk_text, built_text) -> None:
            print(f"  ↳ {label} 차이:", file=sys.stderr)
            if on_disk_text is None:
                print("     · 디스크에 파일 없음 (커밋 누락?)", file=sys.stderr)
                return
            try:
                a = json.loads(on_disk_text)
                b = json.loads(built_text)
            except Exception:
                import difflib
                d = list(difflib.unified_diff(on_disk_text.splitlines(), built_text.splitlines(),
                                              "on-disk", "built", lineterm="", n=0))
                for line in d[:40]:
                    print(f"     {line}", file=sys.stderr)
                return

            def walk(x, y, path=""):
                out = []
                if isinstance(x, dict) and isinstance(y, dict):
                    for k in sorted(set(x) | set(y)):
                        p = f"{path}.{k}" if path else k
                        if k not in x:
                            out.append(f"+ {p} = {y[k]!r}")
                        elif k not in y:
                            out.append(f"- {p} = {x[k]!r}")
                        else:
                            out += walk(x[k], y[k], p)
                elif x != y:
                    out.append(f"~ {path}: 디스크={x!r} → 빌드={y!r}")
                return out

            diffs = walk(a, b)
            if not diffs:
                # ★JSON 은 같은데 바이트가 다르다 = 값이 아니라 표현의 차이
                # (키 순서·개행·인코딩·후행 개행). 이걸 안 보여주면 "차이:" 헤더만
                # 찍히고 아무것도 안 나온다 — CI 첫 진단에서 실제로 그랬다.
                print("     · 값은 동일 — 표현(바이트)만 다름", file=sys.stderr)
                print(f"     · 길이 {len(on_disk_text)} → {len(built_text)}"
                      f" / 후행개행 {on_disk_text.endswith(chr(10))} → {built_text.endswith(chr(10))}"
                      f" / CR 포함 {chr(13) in on_disk_text} → {chr(13) in built_text}",
                      file=sys.stderr)
                ka, kb = list(a), list(b)
                if isinstance(a, dict) and ka != kb:
                    print(f"     · 최상위 키 순서 다름: {ka} → {kb}", file=sys.stderr)
                import difflib
                for line in list(difflib.unified_diff(
                        on_disk_text.splitlines(), built_text.splitlines(),
                        "on-disk", "built", lineterm="", n=0))[:30]:
                    print(f"     {line}", file=sys.stderr)
                return
            for line in diffs[:40]:
                print(f"     {line}", file=sys.stderr)
            if len(diffs) > 40:
                print(f"     … 외 {len(diffs) - 40}건", file=sys.stderr)

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
                _print_derived_diff("phone_manifest.json", on_disk, manifest_text)
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
            _print_derived_diff("package_meta.json", pkg_meta_on_disk, pkg_meta_text)
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
                _print_derived_diff("ibl_fixtures.json", fx_on_disk, fixtures_text)
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
        # 문서 파생 신선도 (README·system_docs 의 마커 구간 ↔ 레지스트리 실측)
        # — 자기상 가드의 확장: 검사에서 재생성으로 승격(빌드가 고치고, check 가 대조).
        docs_ok = True
        try:
            import iblbuild_docs as _docs
            _doc_issues = _docs.check_docs(root, data)
            if _doc_issues:
                docs_ok = False
                print(f"[build_ibl_nodes] check: 문서 파생 불일치 {len(_doc_issues)}건",
                      file=sys.stderr)
                for _di in _doc_issues:
                    print(f"  ✗ {_di}", file=sys.stderr)
            else:
                print(f"[build_ibl_nodes] check: 문서 파생 일치 ✓ "
                      f"({len(dict.fromkeys(t[0] for t in _docs.DOC_TARGETS))}개 문서)")
        except Exception as _e:
            print(f"[build_ibl_nodes] check: 문서 파생 검사 건너뜀 ({_e})")

        # ── 프롬프트 예산 계측 (판정하지 않음 — 숫자만 보인다) ────────────────
        # 어휘 카탈로그는 매 요청 프롬프트에 통째로 들어간다. 액션을 하나 늘리는 비용이
        # 로컬에선 yaml 몇 줄로 보이지만 실제로는 *전 요청 과금*이라, 그 청구서가
        # 커밋 시점에 안 보이면 어휘만 늘고 줄어들 힘이 없다.
        #
        # ★스코핑으로도 못 줄이는 바닥이 있다: always_on 기능어 코어(self·others·table)는
        #   IBL 헌법상 항상 켜져 있어 어떤 노드 스코핑을 걸어도 남는다. 이건 버그가 아니라
        #   헌법의 청구서다 — 상한을 걸려면 언어 개정 사안이므로 지금은 계측만 한다.
        try:
            _pb_prev = sys.path[:]
            if str(root / "backend") not in sys.path:
                sys.path.insert(0, str(root / "backend"))
                import boot_paths  # noqa: F401 — 층 디렉토리 등재

            from ibl_access import build_environment as _be   # type: ignore
            _full = len(_be(allowed_nodes=None))
            _core = len(_be(allowed_set=set(STANDARD_CORE_NODES)))
            _pct = (_core / _full * 100) if _full else 0.0
            print(f"[build_ibl_nodes] 프롬프트 예산: 카탈로그 {_full:,}자 · "
                  f"always_on 코어({'·'.join(sorted(STANDARD_CORE_NODES))}) {_core:,}자 "
                  f"= {_pct:.1f}% (스코핑 최대 절감 {100 - _pct:.1f}%)")
            sys.path[:] = _pb_prev
        except Exception as _e:
            print(f"[build_ibl_nodes] 프롬프트 예산 계측 건너뜀 ({_e.__class__.__name__})")

        return 0 if (bytes_ok and manifest_ok and pkg_meta_ok and fixtures_ok
                     and tool_json_ok and core_manifest_ok and dist_filter_ok
                     and docs_ok
                     and not validation_failed
                     and not corpus_failed and not fixture_failed and not flow_failed
                     and not enum_failed
                     and not profile_failed and not os_failed
                     and not launcher_failed and not textbook_failed
                     and not appvocab_failed and not selfimg_failed
                     and not renderer_failed and not appparam_failed
                     and not guidewire_failed) else 1

    if validation_failed:
        print(
            "[build_ibl_nodes] 빌드는 수행했지만 검증 실패 — "
            "ibl_nodes.yaml 작성 보류. --validate 로 재확인하세요.",
            file=sys.stderr,
        )
        return 1

    # 라이브 백엔드가 부분 파일을 읽지 않도록 tmp+rename (2026-08-22)
    atomic_write_text(target, output)
    print(f"[build_ibl_nodes] 작성: {target}")
    if manifest_text is not None:
        atomic_write_text(manifest_path, manifest_text)
        print(f"[build_ibl_nodes] 작성: {manifest_path} "
              f"(폰 패키지 {len(PHONE_VERIFIED_PACKAGES)}, runnable {manifest_text.count(':')})")
    atomic_write_text(pkg_meta_path, pkg_meta_text)
    print(f"[build_ibl_nodes] 작성: {pkg_meta_path}")
    if fixtures_text is not None:
        atomic_write_text(fixtures_path, fixtures_text)
        print(f"[build_ibl_nodes] 작성: {fixtures_path}")
    tj_written = 0
    for tj_path, tj_text in sorted(tool_json_docs.items()):
        current = tj_path.read_text(encoding="utf-8") if tj_path.is_file() else None
        if current != tj_text:
            atomic_write_text(tj_path, tj_text)
            tj_written += 1
    if tool_json_docs:
        print(
            f"[build_ibl_nodes] tool.json 파생: {len(tool_json_docs)}개 패키지 "
            f"(갱신 {tj_written}개)"
        )
    # 표준 코어 매니페스트 재생성 (git 추적 패키지/앱/어휘 집합 파생 — 코어/사용자 경계)
    try:
        import build_core_manifest as _bcm
        atomic_write_text(_bcm.MANIFEST_PATH, _bcm._serialize(_bcm.build_manifest()))
        print(f"[build_ibl_nodes] 작성: {_bcm.MANIFEST_PATH} (표준 코어 매니페스트)")
    except Exception as _e:
        print(f"[build_ibl_nodes] core_manifest 재생성 건너뜀 ({_e})")
    # 문서 파생 재기입 (README·system_docs 마커 구간 ← 레지스트리 실측 — 사건 시점 갱신:
    # 어휘·코드를 바꾼 행위자가 빌드를 돌리는 순간 문서가 같은 커밋에 실린다)
    try:
        import iblbuild_docs as _docs
        _written, _doc_issues = _docs.apply_docs(root, data)
        if _written:
            print(f"[build_ibl_nodes] 문서 파생 재기입: {', '.join(_written)}")
        for _di in _doc_issues:
            print(f"[build_ibl_nodes] 문서 파생 경고: {_di}", file=sys.stderr)
    except Exception as _e:
        print(f"[build_ibl_nodes] 문서 파생 건너뜀 ({_e})")
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
    ap.add_argument(
        "--inputs-regex",
        action="store_true",
        help="가드가 읽는 파일들의 ERE 한 줄 출력 (pre-commit 훅 트리거용 — 빌드 안 함)",
    )
    ap.add_argument(
        "--inputs",
        action="store_true",
        help="가드가 읽는 파일 패턴을 한 줄에 하나씩 출력 (사람 확인용 — 빌드 안 함)",
    )
    args = ap.parse_args(argv)
    if args.inputs_regex:
        print(guard_inputs_regex())
        return 0
    if args.inputs:
        for p in GUARD_INPUT_PATTERNS:
            print(p)
        return 0
    return build(check=args.check, validate_only=args.validate)


if __name__ == "__main__":
    raise SystemExit(main())
