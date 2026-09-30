"""Compiler diagnostics and bounded, non-executing expression observations."""
from urllib.parse import quote

from ibl_v2_ir import Fault, Node, digest, span
from ibl_v2_types import Type, UNKNOWN, NUMBER, TEXT, BOOL, join, alternatives
from ibl_v2_expr import number


HINTS = {
    "NOT_FOUND": "요청한 파일·디렉토리가 없습니다. 경로를 확인하거나 원천을 다시 요청하세요. 선택 자료라면 catch로 부재를 명시하세요.",
    "LITERAL_DOLLAR": "일반 문자열은 치환하지 않습니다. 값 참조 또는 f 문자열의 ${표현식}으로 옮기거나, 문자 그대로 의도했다면 경고를 무시하세요.",
    "RECORD_LENGTH": "len(Record)는 필드 수입니다. items 목록의 행 수는 len(값.items), 목록 자체는 len(값)을 쓰세요. 내부 목록 필드는 반환 계약으로 확인하세요. 필드 수를 의도했다면 현재 결과가 맞습니다.",
    "INPUTS": 'inputs는 {입력:값}이며 코드는 $입력을 사용합니다. 결과 참조는 inputs:{입력:{"$ref":"결과 id"}}처럼 이름의 값 자리에 둡니다.',
    "UNBOUND": "이 위치 전에 값을 정의하거나 함수의 명시 인자로 전달하세요.",
    "UNORDERED": "정렬 콜백은 Number·Text처럼 순서가 있는 값을 반환해야 합니다. 여러 키는 뒤 키부터 안정 정렬하고 Bool은 조건 값으로 0/1로 바꾸세요.",
    "MISSING_FIELD": "입력·반환 필드를 확인하세요. 선택 필드는 has/get으로 처리하세요.",
    "FIELD_TYPE": "실제 반환 타입을 확인하세요. List는 직접 인덱싱하고, Record는 행 목록이 있는 필드를 선택한 뒤 인덱싱합니다.",
    "RESUME_CHANGED": "resume은 원래 소스·입력·의존성·권한이 같은 실행에만 씁니다. 고친 프로그램은 같은 문맥의 reuse를 사용하거나 새로 실행하세요. 외부 쓰기를 반복하기 전 실행 기록을 확인하세요.",
    "RESUME_NOT_FOUND": "현재 주체·프로젝트에서 반환받은 실행 핸들인지 확인하세요. 없거나 정리된 기록으로는 재개할 수 없습니다.",
    "REUSE_NOT_FOUND": "현재 주체·프로젝트의 이전 실행 핸들을 사용하세요. 기록이 없으면 reuse를 빼고 새로 조회하세요.",
    "REUSE_ARGUMENT": "고친 프로그램은 reuse:{run_id:이전_핸들}, 같은 프로그램은 resume:{run_id:핸들} 중 하나만 지정하세요.",
    "RESUME_ARGUMENT": "resume에는 해당 실행이 반환한 run_id만 지정하세요.",
    "RESUME_BUSY": "원 실행이 끝날 때까지 기다린 뒤 같은 핸들로 재개하세요. 동시에 실행하지 마세요.",
    "REUSE_BUSY": "원 실행이 끝난 뒤 읽기 영수증을 재사용하세요.",
    "JOURNAL_IO": "실행 기록 저장소의 접근·상태를 확인하세요. 영수증을 확인하기 전 외부 쓰기를 반복하지 마세요.",
    "VALUE_PROTOCOL": "값 전송 경계에서 지원하지 않는 타입입니다. 기존 실행 여부는 실행 기록을 확인하세요. 같은 오류가 반복되면 문법을 바꾸며 재시도하지 말고 실행 기반 오류로 보고하세요.",
    "TYPE": "기대 타입과 실제 타입을 비교하고 값을 만드는 호출부터 확인하세요.",
    "NUMBER_REQUIRED": "숫자로 관측할 수 있는 값인지 확인하세요. 구조·산문은 숫자가 아닙니다.",
    "MISSING_ARGUMENT": "함수·도구 서명의 필수 인자를 명시하세요.",
    "UNKNOWN_ARGUMENT": "현재 판본의 서명에 선언된 인자 이름을 사용하세요.",
    "PIPE_COLLISION": "파이프 입력 자리와 같은 명시 인자를 함께 주지 마세요.",
    "REPEAT_COUNT": "반복 횟수에는 0 이상의 정수를 사용하세요.",
    "SYNTAX": "표시된 구문 경계를 수정한 뒤 프로그램 전체를 다시 검사하세요.",
    "STRING_LITERAL": '줄바꿈은 \\n 또는 삼중 따옴표로 쓰세요. 긴 본문은 inputs:{본문:"…"}로 전달해 $본문을 사용하거나 기존 파일·결과를 참조하세요.',
    "UNOBSERVED_FIELD": "describe로 계약을 조회하거나 작은 입력으로 한 번 실행해 실제 필드 이름을 확인하세요. 선택 필드는 has/get을 쓰세요.",
    # 컴파일 진단은 코드마다 고치는 법을 말한다 — 범용 문구로 떨어지는 코드는 가드가 막는다(70회차 F70-1).
    "ARGUMENT_CONTRACT": "describe로 이 액션의 인자 관계(함께 필요한 인자·택일·범위)를 확인하고 호출 인자를 맞추세요.",
    "ARITHMETIC": "산술은 Number끼리만 합니다. 글자로 된 숫자는 number(...)로 바꾸고, 목록·레코드는 필드를 골라 계산하세요.",
    "ARITY": "내장 함수의 인자 개수를 확인하세요. 선택 인자는 뒤에서부터 생략합니다.",
    "RATE_LIMITED": "원천의 요청 한도입니다(원천 장애·결과 없음이 아님). $error.details.retry_after 초 뒤 같은 원천을 다시 부르거나, 급하면 ?? 로 다른 원천을 쓰세요. 같은 호출을 즉시 반복하지 마세요.",
    "BUILTIN": "문법 전문의 내장 함수 이름을 쓰세요. 지역·저장 함수는 값으로 넘기지 않고 [fn:이름]{인자:값}으로 부르며, 목록의 원소마다 부를 때는 [table:each]{ [fn:이름]{인자:$it} }입니다.",
    "CONCURRENCY": "each의 parallel은 1~8 사이의 정수 리터럴입니다.",
    "DUPLICATE_LIBRARY": "저장 정의·관용구 가운데 이 이름이 둘 이상입니다. [self:workflow]{op:\"list\"}로 같은 이름의 저장본을 찾아 하나를 새 이름으로 다시 저장하거나 지우세요. 겹친 이름만 부를 수 없고 다른 함수는 영향이 없습니다.",
    "DUPLICATE_FUNCTION": "같은 범위의 정의 이름은 하나만 둡니다. 역할이 다르면 이름을 바꾸고, 고친 정의라면 옛 정의를 지우세요.",
    "EACH_COLLECT": "on_error:\"collect\"는 기본 map 모드에서만 씁니다. flat_map·effect에서 실패를 모으려면 본문을 [try]로 감싸세요.",
    "EACH_MODE": "each mode는 map·flat_map·effect, on_error는 stop·collect 중 하나의 리터럴입니다.",
    "FINALLY_RETURN": "finally는 정리만 합니다. 반환은 try 본문이나 catch에서 하세요.",
    "FORMAT_TYPE": "보간에는 Text·Number·Bool만 넣습니다. 목록은 join(\", \", 목록), 레코드는 필드를 골라 넣고, Unit·null일 수 있는 값은 먼저 분기하세요.",
    "FUNCTION": "같은 프로그램에 [def:이름]으로 정의하거나 저장된 함수 이름을 확인하세요. 도구 액션은 [node:action]으로 부릅니다.",
    "IR": "지원하지 않는 구문입니다. 같은 뜻을 현재 문법(문법 전문)의 문장으로 다시 쓰고, 반복되면 실행 기반 오류로 보고하세요.",
    "PARALLEL_WRITE_CONFLICT": "병렬 가지·each 병렬 반복이 같은 자원에 쓰면 최종 내용이 실행마다 달라집니다. 순차로 쓰거나(;·기본 each) 가지마다 다른 파일에 쓴 뒤 합치세요.",
    "PARAMETERS": "람다 인자 이름은 서로 다르고 예약 이름($it·$i·$error)이 아니어야 합니다.",
    "PIPE_TARGET": "파이프 오른쪽에는 앞 값을 첫 입력으로 받는 호출 하나를 둡니다. 식으로 가공하려면 앞 값을 $이름에 받은 뒤 쓰세요.",
    "PURE_EXPRESSION": "산술·비교·조건·람다·보간·기본값·내장 함수 인자에는 호출을 넣지 않습니다. 호출 결과를 먼저 $이름=[...]으로 받고 그 변수를 쓰세요.",
    "READONLY": "$it·$i·$error와, each 본문에서 본 바깥 변수는 다시 대입하지 않습니다. 새 이름에 받거나 결과를 each의 반환으로 모으세요.",
    "RECURSION": "재귀 대신 반복을 쓰세요: 횟수는 [repeat:n]{...}, 누적은 reduce(목록,초기값,($acc,$x)=>...), 원소별 처리는 [table:each]입니다.",
    "RESERVED": "함수 인자 이름에 $it·$i·$error를 쓰지 마세요. 다른 이름으로 받으세요.",
    "SLICE_BOUND": "슬라이스 경계는 정수(음수는 끝에서부터), 간격은 0이 아닌 정수입니다. 예: $목록[0:3], $글[-2:].",
    "STATIC_OPTION": "each의 mode·on_error·parallel은 실행 전에 정해져야 합니다. 변수 대신 리터럴로 명시하세요.",
    "UNSUPPORTED_ADAPTER": "현재 판본 계약이 있는 액션만 부를 수 있습니다. describe로 사용 가능한 액션과 계약을 확인하세요.",
    "VALUE_EXPRESSION": "객체·목록의 값에는 식·호출·조합만 씁니다. if·try·repeat 같은 제어 블록은 앞 문장에서 $이름에 받거나 함수 본문에 두세요.",
    "UNIT_RETURN_PATH": "값을 돌려주는 경로와 아무것도 돌려주지 않는 경로가 섞였습니다. [else] 가지나 마지막 return을 두세요. 효과만 하는 함수라면 값 return을 빼세요.",
}


def constant_value(node, depth=0):
    """Observe literal containers without executing code or inventing dynamic values."""
    from ibl_callable_contract import UNRESOLVED
    if depth > 16:
        return UNRESOLVED
    if node.kind == 'literal':
        return node.data['value']
    if node.kind == 'list':
        values = [constant_value(v, depth + 1) for v in node.data['values']]
        return UNRESOLVED if any(v is UNRESOLVED for v in values) else values
    if node.kind == 'record':
        # 레코드 리터럴도 관측한다(75회차 후속): 옛 판은 `config:{repeat:"매일"}` 을 미상으로 봐 check 가
        # 값 검사를 건너뛰었다 — 등록 런타임은 같은 값을 거절했다. 모르는 전개(...$x)가 섞이면 미상.
        from ibl_v2_ir import record_fields
        fields = {k: constant_value(v, depth + 1) for k, v in record_fields(node).items()}
        return UNRESOLVED if any(v is UNRESOLVED for v in fields.values()) else fields
    return UNRESOLVED


def location(source, source_map, node):
    """Local coordinates in the submitted source or the linked definition.

    Keep source_span's combined offsets for existing consumers. location is the
    human/AI-facing source identity; offsets are Unicode code points, not UTF-16.
    """
    entry = next((s for s in reversed(source_map)
                  if s['start'] <= node.start <= s['end']), source_map[0])
    text = source[entry['start']:entry['end']]
    start = max(0, node.start - entry['start'])
    end = min(len(text), max(start, node.end - entry['start']))
    pos = span(text, Node('location', start, end))
    name = entry['name']
    return {**pos, 'source': name,
            'uri': 'ibl://program' if name == '<program>' else 'ibl://function/' + quote(name, safe=''),
            'end_line': text.count('\n', 0, end) + 1,
            'end_column': end - text.rfind('\n', 0, end),
            'offset_encoding': 'unicode-codepoints'}


def pipe_collision_message(callee, receiver):
    """PIPE_COLLISION 은 처방이 다른 두 경우다 — 받는 자리가 없는 호출, 받는 자리를 명시로도 채운 호출.
    어느 자리인지 말하지 않으면 고칠 방향이 안 읽힌다(72회차 후속: 예약 do 의 notify_user message)."""
    if receiver is None:
        return (f"{callee or '이 호출'}은(는) 파이프 입력을 받지 않습니다. 앞 단계 값은 $x = … 로 받아 "
                f"필요한 인자에 넘기세요(예: {{인자: $x.text}}).")
    where = f"{callee}의 " if callee else ""
    return (f"파이프 값은 {where}`{receiver}` 자리로 들어가는데 `{receiver}` 를 명시로도 주었습니다. "
            f"명시 `{receiver}` 를 빼거나, 파이프를 끊고 $x = … 로 받아 필드로 넘기세요.")


def rejection_message(prefix, issues):
    """거절 봉투의 error 는 스스로 설명한다 — 문자열만 읽는 소비자(알림·이력·예약 결과·
    중첩 실행의 바깥)가 많다 (71회차 B71-3). 첫 진단과 남은 수."""
    if not issues:
        return prefix
    first = issues[0]
    more = f" 외 {len(issues) - 1}건" if len(issues) > 1 else ""
    return f"{prefix}: {first.get('message', '')} ({first.get('code', '')}){more}"


def finish_diagnostics(compiler):
    for entries, severity in ((compiler.issues, 'error'), (compiler.guards, 'information')):
        for entry in entries:
            old = entry['source_span']
            node = Node('diagnostic', old['start'], old['end'])
            entry['source_span'] = span(compiler.source, node)
            entry['location'] = location(compiler.source, compiler.source_map, node)
            entry.setdefault('code', 'RUNTIME_GUARD')
            entry.setdefault('rule', entry['code'])
            entry.setdefault('severity', severity)
            entry.setdefault('message', f"실행 중 {entry.get('expected', '값')} 계약을 확인합니다."
                             if severity == 'information' else entry.get('expected', '계약 확인이 필요합니다.'))
            entry.setdefault('hint', HINTS.get(entry['code'], '해당 위치의 계약과 호출 인자를 확인하세요.'))
            if (entry['code'] == 'TYPE' and entry.get('expected') == 'List<Record>'
                    and str(entry.get('actual', '')).startswith('List<')):
                entry['hint'] = ('이 입력은 객체 행 목록을 요구합니다. zip/enumerate의 행은 목록입니다. '
                                 '각 원소를 table:each로 명시적 필드의 레코드로 변환하거나, '
                                 '원소를 그대로 거를 때는 table:each 안에서 조건에 따라 '
                                 '[$it] 또는 []를 반환하고 mode:"flat_map"을 사용하세요.')
            for frame in entry.get('call_path', []):
                for key in ('call', 'definition'):
                    if frame.get(key):
                        p = frame[key]
                        frame[key] = location(compiler.source, compiler.source_map,
                                              Node('frame', p['start'], p['end']))


def syntax_report(exc, source):
    diagnostic = exc.view(source)
    fallback = {'compile': '호출 인자·타입·해당 위치의 계약을 확인하세요.',
                'permission': '현재 주체와 프로젝트의 접근 권한 및 기록 범위를 확인하세요.',
                'protocol': '실행 기록과 요청 프로토콜을 확인하세요. 완료 여부가 불명확한 외부 작업은 반복하지 마세요.'}
    diagnostic.update(rule=exc.code, severity='error',
                      hint=HINTS.get(exc.code, fallback.get(exc.kind, '오류 원인과 실행 상태를 확인하세요.')))
    if exc.node:
        diagnostic['location'] = location(source, [{'name': '<program>', 'start': 0, 'end': len(source)}], exc.node)
    return {'edition': 2, 'ok': False, 'success': False, 'executed': False,
            'status': 'invalid' if exc.kind == 'compile' else 'failed',
            'error': str(exc), 'diagnostic': diagnostic,
            'issues': [diagnostic] if exc.kind == 'compile' else [],
            'guards': [], 'source_hash': digest(source)}


def compact_check(plan):
    """Keep error diagnostics inline and preserve information guards for inspection."""
    import json
    from supervision_store import current_evidence_store
    from result_read_contract import DEFAULT_LIMIT

    report = plan.report()
    report['execution_note'] = '검사만 수행했습니다. 도구 실행·파일 생성은 하지 않았습니다.'
    report['next_action'] = ('진단 위치를 수정한 뒤 다시 검사하세요.' if plan.issues else
                             '실행하려면 같은 code·inputs·budget으로 check를 제거하거나 false로 호출하세요. '
                             '실행 결과의 success·executed와 쓰기 영수증을 확인한 뒤 산출물을 읽으세요.')
    if not plan.guards:
        return report
    useful = [g for g in plan.guards
              if g.get('expected') != 'Unknown' or g.get('actual') != 'Unknown']
    try:
        ref = current_evidence_store().evidence(json.dumps({'guards': plan.guards}, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        report.update(guards=plan.guards, guards_omitted=0)
        return report
    report.update(guards=[], guards_omitted=len(plan.guards),
                  runtime_checks={'total': len(plan.guards), 'informative': len(useful)},
                  guards_ref={'id': ref['id'], 'chars': ref['chars'],
                              'read_args': {'id': ref['id'], 'path': ['guards'],
                                            'offset': 0, 'limit': DEFAULT_LIMIT}})
    return report


def numeric_operand(compiler, node, typ):
    """Use exactly the runtime number observation for literal operands."""
    if typ.kind == 'Never':
        return
    if node.kind == 'literal':
        try:
            number(node.data['value'])
        except Fault as exc:
            compiler.issue(node, exc.code, str(exc), expected='Number', actual=str(typ))
        return
    if typ.kind == 'Union':
        for member in alternatives(typ):
            numeric_operand(compiler, node, member)
    elif typ.kind in ('Text', 'Unknown'):
        compiler.need(node, UNKNOWN, NUMBER)
    elif typ.kind != 'Number':
        compiler.issue(node, 'ARITHMETIC', f'산술로 관측할 수 없는 타입: {typ}',
                       expected='Number', actual=str(typ))


def access_type(compiler, node, base, key, key_type=None):
    """Check each possible receiver shape, retaining its projected type."""
    if base.kind == 'Never':
        return base
    if base.kind == 'Union':
        values = [access_type(compiler, node, member, key, key_type)
                  for member in alternatives(base)]
        result = values[0]
        for value in values[1:]:
            result = join(result, value)
        return result
    if base.kind == 'Record' and isinstance(key, str):
        fields = dict(base.fields)
        if key in fields:
            return fields[key]
        if not base.open:
            compiler.issue(node, 'MISSING_FIELD',
                           f'선언된 필드가 없습니다: {key}. 선택 필드는 has/get을 쓰세요.')
        else:
            if base.observed:
                observed = [k for k, _ in base.fields]
                compiler.warn(node, 'UNOBSERVED_FIELD',
                              f'관측된 반환 필드에 없는 이름입니다: {key}. 관측 필드: {", ".join(observed)}',
                              field=key, observed=observed)
            compiler.need(node, UNKNOWN, UNKNOWN)
        return UNKNOWN
    if base.kind == 'Record' and key is None and node.kind == 'index':
        compiler.need(node, key_type, TEXT)
        compiler.need(node, UNKNOWN, UNKNOWN)
        return UNKNOWN
    if base.kind in ('List', 'Text') and node.kind == 'index':
        compiler.need(node, key_type, NUMBER)
        if (base.kind == 'List' and base.positions is not None
                and type(key) is int and -len(base.positions) <= key < len(base.positions)):
            return base.positions[key]
        return base.item if base.kind == 'List' else TEXT
    if base.kind == 'Unknown':
        compiler.need(node, UNKNOWN, Type('Record') if node.kind == 'field' else UNKNOWN)
    else:
        hint = HINTS['FIELD_TYPE']
        if base.kind == 'Record' and 'items' in dict(base.fields):
            hint = '반환값은 items 행 목록을 가진 Record입니다. 값.items[0]처럼 목록 필드를 먼저 선택하세요.'
        elif base.kind == 'List':
            hint = '반환값은 List입니다. .items/.value를 붙이지 말고 값[0]처럼 직접 인덱싱하세요.'
        compiler.issue(node, 'FIELD_TYPE', f'{base}에 해당 필드 접근을 할 수 없습니다.', hint=hint)
    return UNKNOWN


def row_flow_type(compiler, node, contract, args, fields, values, result, env, names, readonly):
    """Preserve row observations using the vocabulary's existing flow contract."""
    flow = contract.get('analysis', {}).get('flow', {})
    source = args.get(contract.get('pipe_input'), UNKNOWN)
    if source.kind == 'Record':
        source = dict(source.fields).get('items', UNKNOWN)
    schema_param = flow.get('schema_param') or contract.get('analysis', {}).get('schema_param')
    if schema_param:
        from common.record_schema import schema_fields
        from ibl_callable_contract import UNRESOLVED
        inspect_param = contract.get('analysis', {}).get('ai_inspect_param')
        inspecting = values.get(inspect_param) if inspect_param else None
        if inspecting is not None:
            # Inspection returns the original rows, or is dynamic at runtime.
            if inspecting is not UNRESOLVED and source.kind == 'List':
                return Type('Record', fields=(('items', source),), open=True)
            return result
        try:
            columns = schema_fields(values.get(schema_param))
            from common.record_schema import hidden_schema_fields, hidden_schema_message
            input_param = contract.get('analysis', {}).get('schema_input_fields_param')
            known_fields = set()
            from ibl_v2_types import alternatives
            for variant in alternatives(source):
                if variant.kind == 'List':
                    for row_variant in alternatives(variant.item):
                        known_fields.update(dict(row_variant.fields))
            collisions = hidden_schema_fields(values.get(schema_param), values.get(input_param), known_fields)
            if collisions:
                compiler.issue(node, 'ARGUMENT_CONTRACT', hidden_schema_message(collisions))
        except ValueError as exc:
            compiler.issue(node, 'ARGUMENT_CONTRACT', str(exc))
            return result
        projection = values.get(flow.get('columns_param'))
        if columns or isinstance(projection, list) and projection:
            # The schema declares names, not types; unknown values may be null.
            # Models can replace visible input fields, so never retain their types.
            known = dict(source.item.fields) if source.kind == 'List' and source.item.kind == 'Record' else {}
            keys = list(projection) if isinstance(projection, list) and projection else list(dict.fromkeys([*known, *(columns or [])]))
            if all(isinstance(k, str) for k in keys):
                row = Type('Record', fields=tuple((k, UNKNOWN) for k in keys), open=False)
                return Type('Record', fields=tuple({**dict(result.fields), 'items': Type('List', item=row)}.items()), open=True)
    if source.kind != 'List' or flow.get('accepts') != 'items':
        return result
    row = source.item or UNKNOWN
    projected = None
    checked = set(flow.get('reads_fields', []))
    if flow.get('columns_param'):
        checked.add(flow['columns_param'])
    for param in sorted(checked):
        field = fields.get(param)
        if field is None:
            continue
        if field.kind == 'lambda' and len(field.data['params']) == 1:
            local = {**env, field.data['params'][0]: row if row.observed else UNKNOWN}
            value = compiler.visit(field.data['body'], local, names, readonly)
            if param == flow.get('columns_param'):
                projected = value
        elif param not in flow.get('row_condition_params', []):
            value = values.get(param)
            columns = [value] if isinstance(value, str) else value if isinstance(value, list) else []
            selected = []
            for name in columns:
                if isinstance(name, str):
                    # Flow observations are advisory. Sparse/declared input rows
                    # keep the tool's runtime field checks (and catch/?? recovery).
                    current = (access_type(compiler, field, row, name) if row.observed
                               else dict(row.fields).get(name, UNKNOWN) if row.kind == 'Record'
                               else UNKNOWN)
                    selected.append((name, current))
            if flow.get('columns') == 'subset' and selected:
                projected = Type('Record', fields=tuple(selected), open=False)
    mode = flow.get('columns')
    if mode == 'keep':
        output = row
        from ibl_v2_narrow import narrow
        for param in flow.get('row_condition_params', []):
            predicate = fields.get(param)
            if predicate is not None and predicate.kind == 'lambda' and len(predicate.data['params']) == 1:
                name = predicate.data['params'][0]
                output = narrow({name: row}, predicate.data['body'])[name]
                break
    elif mode == 'subset' and projected and projected.kind == 'Record':
        output = projected
    elif mode == 'add' and projected and projected.kind == 'Record' and row.kind == 'Record':
        output = Type('Record', fields=tuple({**dict(row.fields), **dict(projected.fields)}.items()),
                      open=row.open, observed=row.observed)
    else:
        return result
    rows = Type('List', item=output)
    if result.kind == 'List':
        return rows
    if result.kind == 'Record' and flow.get('emits') == 'items':
        return Type('Record', fields=tuple({**dict(result.fields), 'items': rows}.items()),
                    open=result.open, observed=result.observed)
    return result


def builtin_type(compiler, node, name, types, env=None, names=None, readonly=None):
    """Structural obligations only; never invoke a callback or external tool."""
    from common.expression_functions import CONTRACTS
    from ibl_v2_types import declared
    if name in CONTRACTS:
        spec = CONTRACTS[name]
        for i, typ in enumerate(types):
            expected = spec[2][min(i, len(spec[2]) - 1)]
            before = len(compiler.issues)
            compiler.need(node.data['args'][i], typ, declared(expected))
            for issue in compiler.issues[before:]:
                issue['hint'] = f"{name}({', '.join(spec[2])})의 인자 순서를 확인하세요. {i + 1}번째는 {expected}입니다."
        result = declared(spec[3])
        if name == 'sorted' and types and types[0].kind == 'List':
            key_type = types[0].item or UNKNOWN
            key_node = node.data['args'][0]
            if len(types) > 1:
                key_node = node.data['args'][1]
                if key_node.kind == 'lambda' and len(key_node.data['params']) == 1:
                    local = {**(env or {}), key_node.data['params'][0]: key_type}
                    key_type = compiler.visit(key_node.data['body'], local, names, readonly)
                elif key_node.kind == 'literal' and isinstance(key_node.data['value'], str):
                    # Field-name sorting uses the table's heterogeneous buckets,
                    # including textual fallback for structures and booleans.
                    key_type = UNKNOWN
                elif types[1].kind != 'Null':
                    key_type = UNKNOWN
            if any(t.kind in ('List', 'Record', 'Bool', 'Unit', 'Callable', 'Result') for t in alternatives(key_type)):
                from common.expression_functions import _MULTI_KEY_HINT
                compiler.issue(key_node, 'UNORDERED', 'sorted의 키는 순서 비교 가능한 값이어야 합니다. ' + _MULTI_KEY_HINT)
        if name in ('unique', 'intersection', 'difference', 'sorted') and types and types[0].kind == 'List':
            return Type('List', item=types[0].item or UNKNOWN)
        if name == 'union' and types:
            result = types[0]
            for typ in types[1:]:
                result = join(result, typ)
        return result
    nodes = node.data['args']
    def need(i, typ):
        if i < len(types):
            compiler.need(nodes[i], types[i], typ)
    if name == 'len':
        need(0, join(join(TEXT, Type('List', item=UNKNOWN)), Type('Record')))
        if types and any(t.kind == 'Record' for t in alternatives(types[0])):
            compiler.warn(node, 'RECORD_LENGTH',
                          'Record에 적용한 len은 내부 목록의 행 수가 아니라 필드 수를 셉니다.')
        return NUMBER
    if name in ('has', 'get'):
        need(0, Type('Record'))
        need(1, TEXT)
        # has/get are deliberately the dynamic/optional-field escape hatch.
        return BOOL if name == 'has' else UNKNOWN
    if name in ('number', 'abs', 'round'):
        if types:
            numeric_operand(compiler, nodes[0], types[0])
        if name == 'round':
            need(1, NUMBER)
        return NUMBER
    if name in ('is_ok', 'unwrap', 'error_of'):
        need(0, Type('Result', item=UNKNOWN))
        if name == 'is_ok':
            return BOOL
        if name != 'unwrap' or not types:
            return UNKNOWN
        # Union.item is a tuple of types, whereas Result.item is one type.
        # Invalid operands already have a diagnostic; never propagate that tuple.
        members = list(alternatives(types[0]))
        if any(t.kind != 'Result' for t in members):
            return UNKNOWN
        result = members[0].item or UNKNOWN
        for member in members[1:]:
            result = join(result, member.item or UNKNOWN)
        return result
    if name == 'reduce':
        need(0, Type('List', item=UNKNOWN))
        need(2, Type('Callable'))
        return UNKNOWN  # callback may change accumulator shape
    if name == 'text':
        need(0, join(join(TEXT, NUMBER), BOOL))
        return TEXT
    if name == 'json':
        return TEXT
    if name == 'evidence':
        return Type('Record')
    return UNKNOWN


def assigned_names(node):
    """Potential mutations in a repeat frame, excluding nested value frames."""
    result = set()
    def visit(value):
        if isinstance(value, Node):
            if value.kind in ('def', 'lambda', 'parallel', 'fallback'):
                return
            if value.kind == 'call':
                return
            if value.kind == 'bind':
                result.add(value.data['name'])
            for child in value.data.values():
                visit(child)
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
    visit(node)
    return result
