"""관계 결합. 기존 inner 의미론을 보존하며 보존/존재 결합을 제공한다."""
import copy


def _invalid_rows(left, right):
    """Validate both consumed sources before matching can hide malformed rows."""
    invalid = {side: [i for i, row in enumerate(rows) if not isinstance(row, dict)]
               for side, rows in (("left", left), ("right", right))}
    invalid = {side: indices for side, indices in invalid.items() if indices}
    if invalid:
        return {'success': False, 'error': f'join: 입력은 객체 행이어야 합니다(0 기반 행 위치: {invalid}). 행을 제외한 결합을 만들지 않았습니다.',
                'invalid_row_indices': invalid}
    return None


def join(prev, params, h):
    how = params.get('how', 'inner')
    if not isinstance(how, str) or how not in ('inner', 'left', 'right', 'full', 'semi', 'anti'):
        return {'success': False, 'error': 'join: how는 inner/left/right/full/semi/anti 중 하나입니다.'}
    defaults = params.get('defaults', {})
    if not isinstance(defaults, dict):
        return {'success': False, 'error': 'join: defaults는 결과 열 이름→기본값 객체입니다.'}
    if defaults and how in ('inner', 'semi', 'anti'):
        return {'success': False, 'error': 'join: defaults는 left/right/full의 빈 쪽 열에만 적용합니다.'}
    if how == 'inner':
        return inner_join(prev, params, h)
    keys, err = h['_key_names'](params.get('on') if 'on' in params else params.get('key'), 'join', 'on')
    if err:
        return err
    if not keys:
        return {'success': False, 'error': 'join: on 키가 필요합니다.'}
    if params.get('left') is not None and params.get('right') is not None:
        prev = [params['left'], params['right']]
    if not isinstance(prev, list) or len(prev) != 2:
        return {'success': False, 'error': 'join: & 또는 left/right로 정확히 두 입력이 필요합니다.'}
    a, b = h['_extract_two'](prev)
    if a is None or b is None:
        return {'success': False, 'error': 'join: 두 입력의 통화를 찾지 못했습니다.'}
    ra, _ = h['_get_items'](a)
    rb, _ = h['_get_items'](b)
    table_mode = ra is None and rb is None
    ca, cb = None, None
    if table_mode:
        ta, _ = h['_get_table'](a)
        tb, _ = h['_get_table'](b)
        if ta is None or tb is None:
            return {'success': False, 'error': 'join: 두 입력이 items/table 통화여야 합니다.'}
        ra, rb = h['_row_dicts'](ta), h['_row_dicts'](tb)
        ca, cb = list(ta['columns']), list(tb['columns'])
    elif ra is None or rb is None:
        return {'success': False, 'error': 'join: 두 입력이 같은 통화여야 합니다.'}
    row_error = _invalid_rows(ra, rb)
    if row_error:
        return row_error
    ca = ca if ca is not None else list(dict.fromkeys(k for r in ra for k in r))
    cb = cb if cb is not None else list(dict.fromkeys(k for r in rb for k in r))
    for side, rows, cols in [('좌', ra, ca), ('우', rb, cb)]:
        missing = [k for k in keys if k not in cols]
        if missing and (rows or table_mode):
            return {'success': False, 'error': f'join: {side}측에 키 {missing}가 없습니다. 실제 열: {cols}'}
    # 빈 items는 스키마가 없다. defaults에 적은 새 열이 빈 쪽의 열을 선언한다.
    if not cb and how in ('left', 'full'):
        cb = list(keys) + [k for k in defaults if k not in ca and k not in keys]
    if not ca and how in ('right', 'full'):
        ca = list(keys) + [k for k in defaults if k not in cb and k not in keys]
    extra = [c for c in cb if c not in keys]
    mapped = h['_suffix_collisions'](ca, extra)
    cols = ca if how in ('semi', 'anti') else ca + mapped
    if any(k not in cols for k in defaults):
        return {'success': False, 'error': f'join: defaults에 결과에 없는 열이 있습니다. 실제 열: {cols}'}
    index = {}
    for i, row in enumerate(rb):
        key = h['_join_keys'](row, keys)
        if key is not None:
            index.setdefault(key, []).append(i)
    used, out = set(), []

    def emit(left, right):
        row = {c: copy.deepcopy(left.get(c) if left is not None else defaults.get(c)) for c in ca}
        if left is None and right is not None:
            row.update({k: copy.deepcopy(right.get(k)) for k in keys})
        row.update({dest: copy.deepcopy(right.get(src) if right is not None else defaults.get(dest))
                    for src, dest in zip(extra, mapped)})
        out.append(row)

    for left in ra:
        matches = index.get(h['_join_keys'](left, keys), [])
        if how in ('semi', 'anti'):
            if bool(matches) == (how == 'semi'):
                out.append(copy.deepcopy(left))
            continue
        for i in matches:
            used.add(i)
            emit(left, rb[i])
        if not matches and how in ('left', 'full'):
            emit(left, None)
    if how in ('right', 'full'):
        for i, right in enumerate(rb):
            if i not in used:
                emit(None, right)
    env = h['_carry_flags']([a, b], with_total=False)
    result = (h['_emit_table']({**env, 'table': {}}, {'columns': cols, 'rows': [[r.get(c) for c in cols] for r in out]})
              if table_mode else h['_emit_items'](env, out))
    return h['_attach_branch_warning'](result, [a, b])


def inner_join(prev, params, h):
    """두 table을 키 열로 inner join. params.on(양쪽 공통 키 열명 또는 복합키 목록, 필수).

    결과 열 = 좌측 전체 + 우측(키 제외). 서로 다른 소스를 한 키로 묶어 분석.
    on 이 목록이면 복합키 조인(2026-09-07 언어 개정) — 키 일부가 빈 행은 조인 밖.
    예: [sense:stock]{op:history} & [sense:world_bank]{...} >> [table:join]{on: "연도"}.
    """
    keys, kerr = h['_key_names'](params.get("on") or params.get("key"), "join", "on")
    if kerr:
        return kerr
    if not keys:
        return {"success": False, "error": "join: on(조인 키 열 이름)이 필요합니다."}
    # left/right 직접 공급(& 병렬 대신 — $변수 참조로 파이프 낀 가지를 먹일 때).
    # 명시 파라미터가 파이프 입력보다 우선한다. (리터럴 get = 코퍼스-param 가드 가시성)
    if params.get("left") is not None and params.get("right") is not None:
        prev = [params.get("left"), params.get("right")]
    if isinstance(prev, list) and len(prev) > 2:
        # 셋째 분기를 조용히 버리지 않는다(⑧′ 부류) — join 은 이항 연산
        return {"success": False,
                "error": f"join: 입력이 {len(prev)}개 — join 은 두 입력만 받습니다. 여러 개는 [table:union/merge]로 합치거나 둘씩 나눠 join 하세요."}
    if not isinstance(prev, list) or len(prev) < 2:
        return {"success": False, "error": "join: & 병렬 또는 left/right로 두 입력이 필요합니다. 예: [A] & [B] >> [table:join]{on: \"연도\"}"}
    a, b = h['_extract_two'](prev)
    if a is None or b is None:
        # 입력 개수 탓으로 돌리면 자가교정 단서가 틀린다 — 진짜 원인은 분기 출력이 통화가 아님.
        _sides = "·".join(s for s, o in (("첫째", a), ("둘째", b)) if o is None)
        return {"success": False,
                "error": f"join: {_sides} 분기의 출력이 통화(items/table)로 파싱되지 않습니다"
                         f"(스칼라·평문 반환 등) — 통화를 내는 액션·op 으로 바꾸세요."}
    # B38-2(2026-08-25): items 봉투도 _get_table 이 투영할 수 있으므로 table 을 먼저
    # 물으면 직접 병렬 items 만 table 경로를 타고, 변수 raw list 는 items 경로를 탔다.
    # 공개 통화 모양을 **강제 투영 전에** 판별해 문장 경계가 의미를 바꾸지 않게 한다.
    ra, _ = h['_get_items'](a)
    rb, _ = h['_get_items'](b)
    if ra is not None or rb is not None:
        if ra is None or rb is None:
            return {"success": False, "error": "join: 두 입력이 같은 통화여야 합니다(둘 다 table 또는 둘 다 items)."}
        row_error = _invalid_rows(ra, rb)
        if row_error:
            return row_error
        # 두 입력이 items 통화면 items inner join (table 분기와 대칭).
        # items 행도 dict 라 키 필드로 조인 가능 — merge/union 이 items 를 받는 것과 일관.
        # ★키 실존은 표 경로처럼 **먼저** 본다(2026-09-07): 없는 키는 전 행에서 키 없음이 되어
        #   0행이 success 로 나갔다 — 복합키에서는 오타 하나가 조용히 빈 표가 된다(⑧′ 부류).
        for _side, _rows in (("좌", ra), ("우", rb)):
            _dicts = _rows
            if not _dicts:
                continue
            _missing = [k for k in keys if not any(k in r for r in _dicts)]
            if _missing:
                missing_fields = "', '".join(_missing)
                return {"success": False,
                        "error": f"join: 키 '{missing_fields}' 이(가) {_side}측 items 의 "
                                 f"어느 행에도 없습니다. 실제 필드: {list(_dicts[0].keys())}"}
        index = {}
        for r in rb:
            key = h['_join_keys'](r, keys)
            if key is not None:
                index.setdefault(key, []).append(r)
        out = []
        for l in ra:
            key = h['_join_keys'](l, keys)
            if key is None:
                continue
            lkeys = list(l.keys())
            for r in index.get(key, []):
                add = [k for k in r.keys() if k not in keys]
                disp = h['_suffix_collisions'](lkeys, add)  # 동명 필드 _2 (침묵 오선택 방지)
                merged = dict(l)
                for orig, name in zip(add, disp):
                    merged[name] = r[orig]
                out.append(merged)
        return h['_attach_branch_warning'](h['_emit_items'](h['_carry_flags']([a, b], with_total=False), out), [a, b])
    ta, _ = h['_get_table'](a)
    tb, _ = h['_get_table'](b)
    if ta is None or tb is None:
        return {"success": False, "error": "join: 두 입력이 같은 통화여야 합니다(둘 다 table 또는 둘 다 items)."}
    ca = [str(c) for c in (ta.get("columns") or [])]
    cb = [str(c) for c in (tb.get("columns") or [])]
    missing = [k for k in keys if k not in ca or k not in cb]
    if missing:
        missing_fields = "', '".join(missing)
        return {"success": False,
                "error": f"join: 키 '{missing_fields}'이(가) 양쪽 table 열에 "
                         f"모두 있어야 합니다(좌:{ca} 우:{cb})."}
    lki = [ca.index(k) for k in keys]
    rki = [cb.index(k) for k in keys]
    # 우측을 키로 인덱싱
    index = {}
    for r in tb.get("rows") or []:
        key = h['_join_row_key']([(r[i] if i < len(r) else None) for i in rki])
        if key is not None:
            index.setdefault(key, []).append(r)
    extra = [c for c in cb if c not in keys]  # 우측에서 가져올 열(키 제외, 읽기는 원본 이름)
    out_cols = ca + h['_suffix_collisions'](ca, extra)  # 표시 이름만 충돌 회피
    out_rows = []
    for r in ta.get("rows") or []:
        key = h['_join_row_key']([(r[i] if i < len(r) else None) for i in lki])
        if key is None:
            continue
        for rb_row in index.get(key, []):
            rbd = {cb[i]: (rb_row[i] if i < len(rb_row) else None) for i in range(len(cb))}
            out_rows.append(list(r) + [rbd.get(c) for c in extra])
    return h['_attach_branch_warning'](
        h['_emit_table']({**h['_carry_flags']([a, b], with_total=False), "table": {}},
                    {"columns": out_cols, "rows": out_rows}), [a, b])
