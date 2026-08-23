"""
건강 기록 도구 핸들러 - AI 에이전트가 호출하는 도구 실행 로직
다중 사용자(환자) 지원
"""
import os
import sys
import json
import shutil
from datetime import datetime
from typing import Dict, Any

# 패키지 디렉토리를 path에 추가하여 storage 모듈 import 가능하게 함
_package_dir = os.path.dirname(os.path.abspath(__file__))
if _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)

# ★모듈명은 패키지 고유로 (finance-record 와의 sys.modules 'storage' 충돌 실측, 2026-08-14 —
#   패키지 서브모듈은 notebook_core/music_core 처럼 반드시 고유 이름)
import health_storage as storage


# 통화 규율(2026-08-05 감사 ②): returns:items 액션이라 맨 문자열 반환 금지 —
# 에러=_err, 효과·빈 결과=_ok(빈 결과는 items:[] 동봉해 파이프가 안 깨지게).
def _err(msg: str) -> str:
    return json.dumps({"success": False, "error": msg}, ensure_ascii=False)


def _ok(msg: str, items: list = None) -> str:
    out = {"success": True, "message": msg}
    if items is not None:
        out["items"] = items
    return json.dumps(out, ensure_ascii=False)


# ── 공용 정규화 지도 (save/query/delete 공용 — 함수 안 중복 정의 금지) ──
_VALID_INFO_TYPES = {'measurement', 'symptom', 'medication', 'document'}
_KO_INFO_TYPE_MAP = {
    '측정': 'measurement', '측정값': 'measurement',
    '증상': 'symptom',
    '투약': 'medication', '약': 'medication', '약물': 'medication',
    '문서': 'document', '검사': 'document',
}
# ★ _KO_CATEGORY_MAP 의 값은 전부 여기에도 있어야 한다 — 비대칭이면
#   한국어(심박수)는 통하는데 영어(heart_rate)는 저장 실패하는 버그가 된다.
_KNOWN_CATEGORIES = {
    'blood_pressure', 'blood_sugar', 'blood_glucose', 'weight',
    'blood_count', 'body_composition', 'kidney_function', 'liver_function',
    'cholesterol', 'thyroid', 'hemoglobin',
    'heart_rate', 'temperature', 'oxygen_saturation',
}
_KO_CATEGORY_MAP = {
    '혈압': 'blood_pressure', '혈당': 'blood_sugar', '체중': 'weight',
    '혈액검사': 'blood_count', '콜레스테롤': 'cholesterol',
    '심박수': 'heart_rate', '체온': 'temperature', '산소포화도': 'oxygen_saturation',
}
_VALID_QUERY_TYPES = {'summary', 'measurements', 'symptoms', 'medications', 'documents', 'search', 'list_persons'}
_KO_QUERY_TYPE_MAP = {
    '요약': 'summary', '전체': 'summary',
    '측정기록': 'measurements', '측정': 'measurements', '측정값': 'measurements',
    '증상': 'symptoms',
    '투약': 'medications', '약': 'medications', '약물': 'medications',
    '문서': 'documents', '검사': 'documents',
    '검색': 'search',
    '목록': 'list_persons', '사람목록': 'list_persons',
}


def execute(tool_input: dict, context) -> str:
    """도구 실행 엔트리포인트 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name

    # 통합 도구 — IBL 어휘에 노출 (_OP_DISPATCHERS 는 함수 정의 뒤, 파일 하단)
    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.get("op") or "").strip()
        fn = _OP_DISPATCHERS[tool_name].get(op)
        if fn is None:
            return json.dumps({"success": False, "error": f"알 수 없는 op '{op}'. (save|query|delete)"}, ensure_ascii=False)
        return fn(tool_input)
    return _err(f"알 수 없는 도구: {tool_name}")


def save_health_info(input_data: dict) -> str:
    """건강 정보 저장"""
    info_type = input_data.get('info_type')
    data = input_data.get('data', {})
    if not isinstance(data, dict):
        data = {}
    measured_at = input_data.get('measured_at')
    note = input_data.get('note')
    person = input_data.get('person')  # 대상자

    # AI가 data 없이 최상위에 category/value/name 등을 평탄화하여 넘기는 경우 보정
    # (예: {info_type: measurement, category: blood_sugar, value: 128})
    _TOPLEVEL_DATA_KEYS = (
        'category', 'value', 'name', 'description', 'severity',
        'started_at', 'ended_at', 'dosage', 'frequency',
        'image_path', 'extracted_data',
        'systolic', 'diastolic', 'unit', 'type',
    )
    for _k in _TOPLEVEL_DATA_KEYS:
        if _k in input_data and _k not in data:
            data[_k] = input_data[_k]

    # AI가 info_type에 한국어나 카테고리명을 넣는 경우 자동 보정 (지도=모듈 상단 공용)
    if info_type and info_type not in _VALID_INFO_TYPES:
        if info_type in _KO_INFO_TYPE_MAP:
            info_type = _KO_INFO_TYPE_MAP[info_type]
        elif info_type in _KNOWN_CATEGORIES:
            if 'category' not in data:
                data['category'] = info_type
            info_type = 'measurement'
        elif info_type in _KO_CATEGORY_MAP:
            if 'category' not in data:
                data['category'] = _KO_CATEGORY_MAP[info_type]
            info_type = 'measurement'

    # info_type 누락 시 data.category로부터 추론
    # (학습 코퍼스가 {category: "혈압", value: ...} 형태로 가르치기 때문)
    if not info_type:
        _raw_cat = data.get('category')
        if _raw_cat in _KO_CATEGORY_MAP:
            data['category'] = _KO_CATEGORY_MAP[_raw_cat]
            info_type = 'measurement'
        elif _raw_cat in _KNOWN_CATEGORIES:
            info_type = 'measurement'
        elif _raw_cat in _KO_INFO_TYPE_MAP:
            info_type = _KO_INFO_TYPE_MAP[_raw_cat]
            # category 자리에 '투약' 같은 info_type이 들어온 경우 제거
            data.pop('category', None)
        elif data.get('name') or data.get('dosage'):
            info_type = 'medication'
        elif data.get('description') or data.get('severity'):
            info_type = 'symptom'

    try:
        if info_type == 'measurement':
            # 측정값 저장 (혈압, 혈당, 체중 등)
            category = data.get('category', 'unknown')
            value = data.get('value', {})

            # 스칼라 value 정규화: 128 → {"value": 128}
            if not isinstance(value, dict):
                value = {'value': value}

            # 혈압: data 평면에 systolic/diastolic 왔을 때 value로 합치기
            if category == 'blood_pressure':
                if 'systolic' in data and 'systolic' not in value:
                    value['systolic'] = data['systolic']
                if 'diastolic' in data and 'diastolic' not in value:
                    value['diastolic'] = data['diastolic']

            # 보조 필드(unit/type) 값에 병합
            for _aux in ('unit', 'type'):
                if _aux in data and _aux not in value:
                    value[_aux] = data[_aux]

            # 혈압 자유 입력 "128/85" → systolic/diastolic (계기 '기록' 탭 등)
            _raw = value.get('value')
            if category == 'blood_pressure' and isinstance(_raw, str) and '/' in _raw:
                _parts = [p.strip() for p in _raw.split('/', 1)]
                if all(_p.replace('.', '', 1).isdigit() for _p in _parts):
                    value.setdefault('systolic', _parts[0])
                    value.setdefault('diastolic', _parts[1])
                    value.pop('value', None)

            # 숫자 문자열은 숫자로 (표·points 통화가 수치를 기대)
            for _num_k in ('value', 'systolic', 'diastolic'):
                if _num_k in value:
                    value[_num_k] = _to_number(value[_num_k])

            # 빈 value 방어 — 조용한 손실 방지
            _meaningful = {k: v for k, v in value.items() if v not in (None, '')}
            if not _meaningful:
                return _err(
                    "저장 실패: 측정값이 비어 있습니다. "
                    "data.value에 수치를 넣어주세요 "
                    "(예: {info_type: measurement, data: {category: blood_sugar, value: {value: 128, unit: 'mg/dL', type: fasting}}})"
                )

            record_id = storage.save_measurement(
                category=category,
                value=value,
                measured_at=measured_at,
                note=note,
                person=person
            )

            # 사용자 친화적 응답 생성
            value_str = format_measurement_value(category, value)
            person_str = f"[{person}] " if person and person != "나" else ""
            return _ok(f"✓ {person_str}{category_to_korean(category)} 기록 저장됨 (#{record_id}): {value_str}")

        elif info_type == 'symptom':
            # 증상/이벤트 저장
            category = data.get('category', 'unknown')
            description = data.get('description')
            severity = data.get('severity')
            started_at = data.get('started_at') or measured_at
            ended_at = data.get('ended_at')

            record_id = storage.save_symptom(
                category=category,
                description=description,
                severity=severity,
                started_at=started_at,
                ended_at=ended_at,
                note=note,
                person=person
            )

            severity_str = f" ({severity_to_korean(severity)})" if severity else ""
            person_str = f"[{person}] " if person and person != "나" else ""
            return _ok(f"✓ {person_str}증상 기록 저장됨 (#{record_id}): {category_to_korean(category)}{severity_str}")

        elif info_type == 'medication':
            # 투약 기록 저장
            name = data.get('category') or data.get('name', 'unknown')
            dosage = data.get('dosage')
            frequency = data.get('frequency')
            reason = data.get('description')
            started_at = data.get('started_at') or measured_at
            ended_at = data.get('ended_at')

            record_id = storage.save_medication(
                name=name,
                dosage=dosage,
                frequency=frequency,
                reason=reason,
                started_at=started_at,
                ended_at=ended_at,
                note=note,
                person=person
            )

            freq_str = f", {frequency}" if frequency else ""
            person_str = f"[{person}] " if person and person != "나" else ""
            return _ok(f"✓ {person_str}투약 기록 저장됨 (#{record_id}): {name} {dosage or ''}{freq_str}")

        elif info_type == 'document':
            # 문서/이미지 저장
            doc_type = data.get('category', 'unknown')
            image_path = data.get('image_path')
            extracted_data = data.get('extracted_data')
            description = data.get('description')
            recorded_at = data.get('started_at') or measured_at

            # 이미지 파일이 있으면 복사
            saved_image_path = None
            if image_path and os.path.exists(image_path):
                saved_image_path = copy_image_to_storage(image_path, doc_type, person)

            record_id = storage.save_document(
                doc_type=doc_type,
                image_path=saved_image_path,
                extracted_data=extracted_data,
                description=description,
                recorded_at=recorded_at,
                note=note,
                person=person
            )

            person_str = f"[{person}] " if person and person != "나" else ""
            result = f"✓ {person_str}문서 기록 저장됨 (#{record_id}): {doc_type_to_korean(doc_type)}"
            if extracted_data:
                result += f"\n  추출된 데이터: {len(extracted_data)}개 항목"
            return _ok(result)

        else:
            return _err(f"알 수 없는 정보 유형: {info_type}")

    except Exception as e:
        return _err(f"저장 실패: {str(e)}")


def get_health_context(input_data: dict) -> str:
    """건강 컨텍스트 조회"""
    # query_type 명시 여부 구분 — default 처리 전에 확인
    query_type_given = input_data.get('query_type') is not None
    query_type = input_data.get('query_type', 'summary')
    category = input_data.get('category')
    days = input_data.get('days', 365)
    # ★정본 query(별칭 keyword — ibl_actions.yaml aliases). 관문이 keyword→query 로
    #   정규화하지만 직접 호출도 있으니 둘 다 읽는다.
    keyword = input_data.get('query') or input_data.get('keyword')
    include_images = input_data.get('include_images', False)
    person = input_data.get('person')  # 대상자

    # AI가 query_type에 한국어나 카테고리명을 넣는 경우 자동 보정 (지도=모듈 상단 공용)
    if query_type not in _VALID_QUERY_TYPES:
        if query_type in _KO_QUERY_TYPE_MAP:
            # 한국어 query_type → 영어 변환
            query_type = _KO_QUERY_TYPE_MAP[query_type]
        elif query_type in _KNOWN_CATEGORIES:
            # 영어 카테고리명 → measurements로 보정
            if not category:
                category = query_type
            query_type = 'measurements'
        elif query_type in _KO_CATEGORY_MAP:
            # 한국어 카테고리명 → 영어 변환 + measurements
            if not category:
                category = _KO_CATEGORY_MAP[query_type]
            query_type = 'measurements'
        else:
            # 알 수 없는 값 → 키워드 검색으로 폴백
            if not keyword:
                keyword = query_type
            query_type = 'search'

    # query_type 미지정 + category에 카테고리/조회유형이 들어온 경우 재해석
    # (학습 코퍼스가 [self:health]{op: "query", category: "혈당"} 형태로 가르치기 때문)
    if not query_type_given and category and query_type == 'summary':
        if category in _KO_QUERY_TYPE_MAP:
            query_type = _KO_QUERY_TYPE_MAP[category]
            category = None
        elif category in _KO_CATEGORY_MAP:
            category = _KO_CATEGORY_MAP[category]
            query_type = 'measurements'
        elif category in _KNOWN_CATEGORIES:
            query_type = 'measurements'

    try:
        if query_type == 'list_persons':
            # 등록된 사람 목록
            persons = storage.list_persons()
            if not persons:
                return _ok("등록된 사람이 없습니다.", items=[])
            lines = ["👥 등록된 사람 목록:", ""]
            for p in persons:
                note = f" - {p['note']}" if p.get('note') else ""
                lines.append(f"  • {p['name']}{note}")
            # 통화 규율: 맨 문자열 금지 — records 동봉
            records = [{"title": p['name'], "meta": "", "summary": p.get('note') or "", "url": ""}
                       for p in persons]
            return json.dumps({"text": "\n".join(lines), "items": records}, ensure_ascii=False)

        elif query_type == 'summary':
            # 전체 요약 — text(사람용) + blocks(계기 렌더 IR)
            summary = storage.get_health_summary(days=days, person=person)
            text = format_health_summary(summary, include_images)
            return json.dumps({"text": text, "blocks": _summary_to_blocks(summary)},
                              ensure_ascii=False)

        elif query_type == 'measurements':
            # 측정값 조회
            measurements = storage.get_measurements(category=category, days=days, person=person)
            if not measurements:
                cat_str = category_to_korean(category) if category else "측정"
                person_str = f"{person}의 " if person and person != "나" else ""
                return _ok(f"{person_str}최근 {days}일간 {cat_str} 기록이 없습니다.", items=[])
            text = format_measurements(measurements, category, person)
            # 표준 테이블 통화 — 시계열 측정값을 table로 (>> chart/spreadsheet/document)
            # 사람용 텍스트는 text 키로 보존하고 table만 ADD (world_bank 선례).
            # blocks/points 는 🩺 계기 렌더용 (blocks=표 IR, points=첫 시리즈 sparkline).
            table = _measurements_to_table(measurements)
            payload = {"text": text, "count": len(measurements)}
            if table:
                payload["table"] = table
                payload["blocks"] = [{"type": "table",
                                      "columns": table["columns"], "rows": table["rows"]}]
                payload["points"] = _table_to_points(table)
                if payload["points"]:
                    payload["series_label"] = table["columns"][1]
            return json.dumps(payload, ensure_ascii=False)

        elif query_type == 'symptoms':
            # 증상 조회
            symptoms = storage.get_symptoms(category=category, days=days, person=person)
            if not symptoms:
                person_str = f"{person}의 " if person and person != "나" else ""
                return _ok(f"{person_str}최근 {days}일간 증상 기록이 없습니다.", items=[])
            text = format_symptoms(symptoms, person)
            # 레코드 통화(비파괴) — 증상 목록 >> [table:filter/document]. 사람용은 text(measurements 선례).
            records = [{
                "title": category_to_korean(s.get("category", "")) or s.get("category", ""),
                "meta": " · ".join(x for x in [str(s.get("severity") or ""), s.get("started_at", "")] if x),
                "summary": s.get("description", ""),
                "url": "",
            } for s in symptoms]
            return json.dumps({"text": text, "items": records}, ensure_ascii=False)

        elif query_type == 'medications':
            # 투약 기록 조회
            active_only = input_data.get('active_only', False)
            medications = storage.get_medications(days=days, active_only=active_only, person=person)
            if not medications:
                person_str = f"{person}의 " if person and person != "나" else ""
                return _ok(f"{person_str}투약 기록이 없습니다.", items=[])
            text = format_medications(medications, person)
            records = [{
                "title": m.get("name", ""),
                "meta": " · ".join(x for x in [m.get("dosage", ""), m.get("frequency", "")] if x),
                "summary": m.get("reason", ""),
                "url": "",
            } for m in medications]
            return json.dumps({"text": text, "items": records}, ensure_ascii=False)

        elif query_type == 'documents':
            # 문서 조회
            documents = storage.get_documents(doc_type=category, days=days, person=person)
            if not documents:
                person_str = f"{person}의 " if person and person != "나" else ""
                return _ok(f"{person_str}최근 {days}일간 문서 기록이 없습니다.", items=[])
            text = format_documents(documents, include_images, person)
            records = [{
                "title": d.get("doc_type", "") or "문서",
                "meta": d.get("recorded_at", ""),
                "summary": d.get("description", ""),
                "url": d.get("image_path", "") or "",
            } for d in documents]
            return json.dumps({"text": text, "items": records}, ensure_ascii=False)

        elif query_type == 'search':
            # 키워드 검색
            if not keyword:
                return _err("검색 키워드를 입력해주세요.")
            results = storage.search_records(keyword, person=person)
            text = format_search_results(results, keyword, person)
            records = _search_to_records(results)
            if not records:
                return _ok(text, items=[])
            return json.dumps({"text": text, "items": records}, ensure_ascii=False)

        else:
            return _err(f"알 수 없는 조회 유형: {query_type}")

    except Exception as e:
        return _err(f"조회 실패: {str(e)}")


def delete_health_record(input_data: dict) -> str:
    """건강 기록 삭제 (soft-delete tombstone → 동기화 전파).

    파라미터: record_type(measurement|symptom|medication|document) + record_id(정수).
    person 지정 시 해당 사용자 기록만(오삭제 방지). 조회 출력의 (#id) 가 record_id."""
    # record_type 정규화 (한국어/조회유형 별칭 수용)
    _RT_MAP = {
        '측정': 'measurement', '측정값': 'measurement', 'measurements': 'measurement',
        '증상': 'symptom', 'symptoms': 'symptom',
        '투약': 'medication', '약': 'medication', '약물': 'medication', 'medications': 'medication',
        '문서': 'document', '검사': 'document', 'documents': 'document',
    }
    record_type = (input_data.get('record_type') or input_data.get('info_type')
                   or input_data.get('query_type') or '').strip()
    record_type = _RT_MAP.get(record_type, record_type)

    # record_id 수용 (id/record_id, 문자열 정수 허용)
    raw_id = input_data.get('record_id', input_data.get('id'))
    person = input_data.get('person')

    _VALID = {'measurement', 'symptom', 'medication', 'document'}
    if record_type not in _VALID:
        return _err("삭제 실패: record_type 을 지정하세요 "
                    "(measurement|symptom|medication|document). "
                    "예: {op: delete, record_type: measurement, record_id: 5}")
    if raw_id in (None, ''):
        return _err("삭제 실패: record_id(삭제할 기록 번호)를 지정하세요. 조회 결과의 (#번호)를 사용하세요.")
    try:
        record_id = int(raw_id)
    except (TypeError, ValueError):
        return _err(f"삭제 실패: record_id '{raw_id}' 가 정수가 아닙니다.")

    try:
        ok = storage.soft_delete_record(record_type, record_id, person=person)
    except Exception as e:
        return _err(f"삭제 실패: {str(e)}")

    if not ok:
        person_str = f"[{person}] " if person and person != "나" else ""
        return _err(f"삭제할 기록을 찾지 못했습니다: {person_str}{record_type} #{record_id}")

    type_ko = {'measurement': '측정', 'symptom': '증상',
               'medication': '투약', 'document': '문서'}.get(record_type, record_type)
    person_str = f"[{person}] " if person and person != "나" else ""
    return _ok(f"🗑 {person_str}{type_ko} 기록 #{record_id} 삭제됨")


_INGEST_KIND_MAP = {
    'measurement': 'measurement', '측정': 'measurement',
    'symptom': 'symptom', '증상': 'symptom',
    'medication': 'medication', '투약': 'medication',
    'document': 'document', '문서': 'document',
}
_INGEST_KIND_KO = {'measurement': '측정', 'symptom': '증상',
                   'medication': '투약', 'document': '문서'}
_DATE_RE = None  # 지연 컴파일


def ingest_health_info(input_data: dict) -> str:
    """다형 입력(텍스트/파일 — 이미지·PDF·엑셀·텍스트)을 AI로 구조화해 일괄 저장.

    공용 ingest_engine(backend/services) 첫 소비자 — 이 함수는 ④적재만 도메인 몫:
    스키마 프롬프트 + 결정론 검증(수치·날짜·kind) + 기존 save 경로 재사용."""
    global _DATE_RE
    import re as _re
    if _DATE_RE is None:
        _DATE_RE = _re.compile(r'^\d{4}-\d{2}-\d{2}')

    file_path = (input_data.get('file') or input_data.get('path') or '').strip()
    free_text = (input_data.get('text') or input_data.get('content') or '').strip()
    person = input_data.get('person')

    try:
        import ingest_engine
    except ImportError as e:
        return _err(f"ingest_engine 임포트 불가(백엔드 밖 실행?): {e}")

    source = ingest_engine.extract_source(path=file_path or None, text=free_text or None)
    if not source.get('ok'):
        return _err(source.get('error') or '원문 추출 실패')

    today = datetime.now().strftime('%Y-%m-%d')
    schema = (
        f"오늘 날짜: {today} (원문의 '오늘/어제' 같은 상대 날짜는 이것 기준으로 환산)\n"
        "출력 스키마 — 배열의 각 원소는 다음 중 하나:\n"
        '- 측정: {"kind":"measurement","category":"blood_pressure|blood_sugar|weight|heart_rate|'
        'temperature|oxygen_saturation","value":수치,"systolic":수축기,"diastolic":이완기,'
        '"unit":"단위","date":"YYYY-MM-DD","note":"짧은 메모"} — 혈압만 systolic/diastolic, 그 외 value 하나\n'
        '- 증상: {"kind":"symptom","category":"두통 등 짧은 이름","severity":"mild|moderate|severe",'
        '"description":"설명","date":"시작일"}\n'
        '- 투약: {"kind":"medication","name":"약 이름","dosage":"용량","frequency":"복용 횟수",'
        '"description":"사유","date":"시작일"}\n'
        '- 문서: {"kind":"document","category":"blood_test|urine_test|health_checkup|prescription|'
        'xray|ct|mri","description":"한 줄 요약","extracted_data":{"항목":"값"},"date":"검사일"}\n'
        "검사지·건강검진처럼 수치가 여럿이면: 표준 카테고리(혈압·혈당·체중·심박수 등)는 측정으로 "
        "낱개 추출하고, 나머지 세부 수치는 문서 하나의 extracted_data 에 모은다."
    )

    records, err = ingest_engine.extract_records(source, schema, domain_label="건강기록")
    if err:
        return _err(f"추출 실패: {err}")
    if not records:
        return _ok(f"{source.get('label', '입력')}: 저장할 건강 기록을 찾지 못했습니다.", items=[])

    saved_items, skipped = [], []
    doc_original_attached = bool(file_path) and (source.get('kind') == 'image' or file_path.lower().endswith('.pdf'))
    first_doc_seen = False

    for r in records:
        kind = _INGEST_KIND_MAP.get(str(r.get('kind') or '').strip().lower())
        if not kind:
            skipped.append(f"kind 불명: {str(r)[:80]}")
            continue
        date = str(r.get('date') or '').strip()
        measured_at = date if _DATE_RE.match(date) else None

        data = {}
        if kind == 'measurement':
            cat = str(r.get('category') or '').strip()
            cat = _KO_CATEGORY_MAP.get(cat, cat)
            if not cat:
                skipped.append(f"측정 카테고리 없음: {str(r)[:80]}")
                continue
            sys_v, dia_v = _to_number(r.get('systolic')), _to_number(r.get('diastolic'))
            val = _to_number(r.get('value'))
            if isinstance(sys_v, (int, float)) and isinstance(dia_v, (int, float)):
                data.update({'category': cat, 'systolic': sys_v, 'diastolic': dia_v})
            elif isinstance(val, (int, float)):
                data.update({'category': cat, 'value': val})
                if r.get('unit'):
                    data['unit'] = str(r['unit'])
            else:
                skipped.append(f"{cat}: 수치 없음 — 지어내지 않고 건너뜀")
                continue
        elif kind == 'symptom':
            if not (r.get('category') or r.get('description')):
                skipped.append(f"증상 내용 없음: {str(r)[:80]}")
                continue
            data = {'category': str(r.get('category') or 'unknown'),
                    'description': r.get('description'), 'started_at': measured_at}
            if str(r.get('severity') or '') in ('mild', 'moderate', 'severe'):
                data['severity'] = r['severity']
        elif kind == 'medication':
            if not r.get('name'):
                skipped.append(f"약 이름 없음: {str(r)[:80]}")
                continue
            data = {'name': str(r['name']), 'dosage': r.get('dosage'),
                    'frequency': r.get('frequency'), 'description': r.get('description'),
                    'started_at': measured_at}
        else:  # document
            data = {'category': str(r.get('category') or 'health_checkup'),
                    'description': r.get('description'),
                    'extracted_data': r.get('extracted_data') if isinstance(r.get('extracted_data'), dict) else None,
                    'started_at': measured_at}
            # 원본 보존 — 이미지/PDF 업로드면 첫 문서 레코드에 원본 파일을 붙인다
            if doc_original_attached and not first_doc_seen:
                data['image_path'] = file_path
                first_doc_seen = True

        result_raw = save_health_info({'info_type': kind, 'data': data,
                                       'measured_at': measured_at,
                                       'note': r.get('note'), 'person': person})
        try:
            result = json.loads(result_raw)
        except ValueError:
            result = {'success': False, 'error': str(result_raw)[:120]}
        if result.get('success'):
            title = (category_to_korean(data.get('category', '')) if kind == 'measurement'
                     else data.get('name') or category_to_korean(data.get('category', '')) or doc_type_to_korean(data.get('category', '')))
            summary = result.get('message', '')
            saved_items.append({'title': title or _INGEST_KIND_KO[kind],
                                'meta': f"{_INGEST_KIND_KO[kind]} · {measured_at or today}",
                                'summary': summary.split(': ', 1)[-1], 'url': ''})
        else:
            skipped.append(result.get('error', '저장 실패'))

    # 문서 레코드 없이 이미지/PDF 가 온 경우 — 원본만이라도 문서로 보존
    if doc_original_attached and not first_doc_seen and saved_items:
        save_health_info({'info_type': 'document', 'person': person,
                          'data': {'category': 'health_checkup', 'image_path': file_path,
                                   'description': f"업로드 원본({source.get('label', '')})"}})

    head = f"✓ {source.get('label', '입력')}에서 {len(saved_items)}건 저장"
    if skipped:
        head += f", {len(skipped)}건 건너뜀"
    lines = [head] + [f"  • {it['title']} — {it['summary']}" for it in saved_items]
    if skipped:
        lines += ["  건너뜀:"] + [f"  ⚠ {s}" for s in skipped[:5]]
    return json.dumps({"success": True, "message": head, "text": "\n".join(lines),
                       "items": saved_items, "saved": len(saved_items),
                       "skipped": len(skipped)}, ensure_ascii=False)


# 2026-05-28 dispatcher 표준화 → 2026-08-05 진짜 함수 참조 테이블로 전환.
# --check 가 이 dict 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "health_op": {"save": save_health_info, "query": get_health_context,
                  "delete": delete_health_record, "ingest": ingest_health_info},
}
# health_op는 op 필수 — _OP_DEFAULTS 항목 없음.


# ===== 유틸리티 함수들 =====

def copy_image_to_storage(source_path: str, doc_type: str, person: str = None) -> str:
    """이미지를 저장소로 복사"""
    os.makedirs(storage.IMAGES_DIR, exist_ok=True)

    ext = os.path.splitext(source_path)[1]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    person_prefix = f"{person}_" if person and person != "나" else ""
    filename = f"{person_prefix}{doc_type}_{timestamp}{ext}"
    dest_path = os.path.join(storage.IMAGES_DIR, filename)

    shutil.copy2(source_path, dest_path)
    return dest_path


def category_to_korean(category: str) -> str:
    """카테고리 한글 변환"""
    mapping = {
        'blood_pressure': '혈압',
        'blood_sugar': '혈당',
        'weight': '체중',
        'heart_rate': '심박수',
        'temperature': '체온',
        'oxygen_saturation': '산소포화도',
        'headache': '두통',
        'stomachache': '복통',
        'cold': '감기',
        'fever': '발열',
        'fatigue': '피로',
        'insomnia': '불면',
        'allergy': '알레르기',
    }
    return mapping.get(category, category)


def severity_to_korean(severity: str) -> str:
    """심각도 한글 변환"""
    mapping = {
        'mild': '경미',
        'moderate': '보통',
        'severe': '심각'
    }
    return mapping.get(severity, severity) if severity else ''


def doc_type_to_korean(doc_type: str) -> str:
    """문서 유형 한글 변환"""
    mapping = {
        'blood_test': '혈액검사',
        'urine_test': '소변검사',
        'xray': 'X-ray',
        'ct': 'CT',
        'mri': 'MRI',
        'prescription': '처방전',
        'health_checkup': '건강검진',
        'skin_photo': '피부 사진',
        'wound_photo': '상처 사진',
    }
    return mapping.get(doc_type, doc_type)


def format_measurement_value(category: str, value: dict) -> str:
    """측정값 포맷팅"""
    if category == 'blood_pressure':
        return f"{value.get('systolic', '?')}/{value.get('diastolic', '?')} mmHg"
    elif category == 'blood_sugar':
        return f"{value.get('value', '?')} mg/dL"
    elif category == 'weight':
        unit = value.get('unit', 'kg')
        return f"{value.get('value', value.get('weight', '?'))} {unit}"
    elif category == 'heart_rate':
        return f"{value.get('value', '?')} bpm"
    elif category == 'temperature':
        return f"{value.get('value', '?')}°C"
    else:
        return json.dumps(value, ensure_ascii=False)


def format_health_summary(summary: dict, include_images: bool = False) -> str:
    """건강 요약 포맷팅"""
    person = summary.get('person', '나')
    person_str = f"[{person}] " if person != "나" else ""
    lines = [f"📋 {person_str}건강 기록 요약 ({summary['period']})", ""]

    # 측정값 요약
    if summary['measurements']:
        lines.append("📊 최근 측정값:")
        for cat, info in summary['measurements'].items():
            latest = info['latest']
            value_str = format_measurement_value(cat, latest['value'])
            date_str = latest['measured_at'][:10]
            lines.append(f"  • {category_to_korean(cat)}: {value_str} ({date_str}, 총 {info['count']}회)")
        lines.append("")

    # 진행 중인 증상
    if summary['active_symptoms']:
        lines.append("🤒 현재 증상:")
        for s in summary['active_symptoms']:
            sev = f" ({severity_to_korean(s['severity'])})" if s['severity'] else ""
            lines.append(f"  • {category_to_korean(s['category'])}{sev} - {s['started_at']}부터")
        lines.append("")

    # 현재 복용 약물
    if summary['current_medications']:
        lines.append("💊 복용 중인 약물:")
        for m in summary['current_medications']:
            freq = f", {m['frequency']}" if m['frequency'] else ""
            lines.append(f"  • {m['name']} {m['dosage'] or ''}{freq}")
        lines.append("")

    # 최근 검사
    if summary['recent_documents']:
        lines.append("📄 최근 검사/문서:")
        for d in summary['recent_documents']:
            lines.append(f"  • {doc_type_to_korean(d['doc_type'])} ({d['recorded_at']})")
        lines.append("")

    if len(lines) <= 2:
        return f"{person_str}기록된 건강 정보가 없습니다."

    return "\n".join(lines)


def _to_number(v):
    """가능하면 float/int로 변환, 아니면 원값 유지."""
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        try:
            f = float(s)
            return int(f) if f.is_integer() else f
        except (ValueError, TypeError):
            return v
    return v


def _measurements_to_table(measurements: list):
    """측정값 목록 → 표준 table 통화.

    첫 열=날짜(x축), 나머지=수치 시리즈.
    혈압은 수축기/이완기 2 시리즈, 그 외는 단일 값.
    여러 카테고리가 섞이면 카테고리별 열로 피벗(날짜 = 행).
    """
    # 카테고리별 시리즈 키 정의: (열라벨, value dict에서 뽑는 함수)
    def _series_for(cat):
        if cat == 'blood_pressure':
            return [
                ("수축기(mmHg)", lambda val: _to_number(val.get('systolic'))),
                ("이완기(mmHg)", lambda val: _to_number(val.get('diastolic'))),
            ]
        unit_map = {
            'blood_sugar': 'mg/dL', 'weight': 'kg',
            'heart_rate': 'bpm', 'temperature': '℃',
            'oxygen_saturation': '%',
        }
        unit = unit_map.get(cat, '')
        label = category_to_korean(cat)
        if unit:
            label = f"{label}({unit})"
        return [(label, lambda val: _to_number(val.get('value', val.get('weight'))))]

    # 등장 카테고리 수집 (등장 순서 보존)
    cats = []
    for m in measurements:
        c = m.get('category')
        if c and c not in cats:
            cats.append(c)
    if not cats:
        return None

    # 각 카테고리의 시리즈 목록
    cat_series = {c: _series_for(c) for c in cats}
    # 열 헤더: 날짜 + 모든 시리즈
    columns = ["날짜"]
    series_order = []  # (cat, label, getter)
    for c in cats:
        for label, getter in cat_series[c]:
            columns.append(label)
            series_order.append((c, label, getter))

    # 날짜별 행으로 피벗 (날짜 = measured_at[:10])
    by_date = {}
    for m in measurements:
        date = (m.get('measured_at') or '')[:10]
        if not date:
            continue
        val = m.get('value') or {}
        row = by_date.setdefault(date, {})
        for c, label, getter in series_order:
            if m.get('category') == c:
                try:
                    row[label] = getter(val)
                except Exception:
                    pass

    if not by_date:
        return None

    rows = []
    for date in sorted(by_date.keys()):  # 시간 오름차순
        r = [date]
        for c, label, getter in series_order:
            r.append(by_date[date].get(label))
        rows.append(r)

    return {"columns": columns, "rows": rows}


def _table_to_points(table: dict) -> list:
    """table 통화의 첫 수치 시리즈 → sparkline points [{date, value}] (시간 오름차순 유지)."""
    rows = table.get("rows") or []
    points = []
    for r in rows:
        if len(r) >= 2 and isinstance(r[1], (int, float)):
            points.append({"date": r[0], "value": r[1]})
    return points


def _summary_to_blocks(summary: dict) -> list:
    """건강 요약 dict → 계기 blocks IR (heading/list). 렌더는 표면 공용 blocks 프리미티브."""
    blocks = []

    def _section(title, items):
        if items:
            blocks.append({"type": "heading", "level": 3, "text": title})
            blocks.append({"type": "list", "items": items})

    meas = []
    for cat, info in (summary.get('measurements') or {}).items():
        latest = info['latest']
        meas.append(f"{category_to_korean(cat)}: {format_measurement_value(cat, latest['value'])}"
                    f" ({latest['measured_at'][:10]}, 총 {info['count']}회)")
    _section("📊 최근 측정값", meas)

    _section("🤒 현재 증상", [
        f"{category_to_korean(s['category'])}"
        f"{' (' + severity_to_korean(s['severity']) + ')' if s.get('severity') else ''}"
        f" - {s['started_at']}부터"
        for s in (summary.get('active_symptoms') or [])])

    _section("💊 복용 중인 약물", [
        f"{m['name']} {m.get('dosage') or ''}{', ' + m['frequency'] if m.get('frequency') else ''}"
        for m in (summary.get('current_medications') or [])])

    _section("📄 최근 검사/문서", [
        f"{doc_type_to_korean(d['doc_type'])} ({d['recorded_at']})"
        for d in (summary.get('recent_documents') or [])])

    return blocks


def _search_to_records(results: dict) -> list:
    """검색 결과 dict → records 통화 (종류 라벨을 meta 앞에)."""
    records = []
    for m in results.get('measurements', []):
        records.append({
            "title": category_to_korean(m['category']),
            "meta": f"측정 · {m['measured_at'][:10]}",
            "summary": format_measurement_value(m['category'], m['value']),
            "url": "",
        })
    for s in results.get('symptoms', []):
        records.append({
            "title": category_to_korean(s['category']),
            "meta": f"증상 · {s['started_at']}",
            "summary": s.get('description') or '',
            "url": "",
        })
    for m in results.get('medications', []):
        records.append({
            "title": m['name'],
            "meta": f"투약 · {m['started_at']}",
            "summary": " ".join(x for x in [m.get('dosage') or '', m.get('frequency') or ''] if x),
            "url": "",
        })
    for d in results.get('documents', []):
        records.append({
            "title": doc_type_to_korean(d['doc_type']),
            "meta": f"문서 · {d['recorded_at']}",
            "summary": d.get('description') or '',
            "url": "",
        })
    return records


def format_measurements(measurements: list, category: str = None, person: str = None) -> str:
    """측정값 목록 포맷팅"""
    cat_str = category_to_korean(category) if category else "측정값"
    person_str = f"[{person}] " if person and person != "나" else ""
    lines = [f"📊 {person_str}{cat_str} 기록 ({len(measurements)}건)", ""]

    for m in measurements[:20]:  # 최대 20개
        value_str = format_measurement_value(m['category'], m['value'])
        date_str = m['measured_at'][:16].replace('T', ' ')
        note_str = f" - {m['note']}" if m['note'] else ""
        lines.append(f"  (#{m['id']}) {date_str}: {value_str}{note_str}")

    return "\n".join(lines)


def format_symptoms(symptoms: list, person: str = None) -> str:
    """증상 목록 포맷팅"""
    person_str = f"[{person}] " if person and person != "나" else ""
    lines = [f"🤒 {person_str}증상 기록 ({len(symptoms)}건)", ""]

    for s in symptoms:
        status = "진행중" if not s['ended_at'] else f"~{s['ended_at']}"
        sev = f" [{severity_to_korean(s['severity'])}]" if s['severity'] else ""
        desc = f": {s['description']}" if s['description'] else ""
        lines.append(f"  • (#{s['id']}) {category_to_korean(s['category'])}{sev} ({s['started_at']} {status}){desc}")

    return "\n".join(lines)


def format_medications(medications: list, person: str = None) -> str:
    """투약 기록 포맷팅"""
    active = [m for m in medications if m['is_active']]
    inactive = [m for m in medications if not m['is_active']]

    person_str = f"[{person}] " if person and person != "나" else ""
    lines = [f"💊 {person_str}투약 기록", ""]

    if active:
        lines.append("▶ 복용 중:")
        for m in active:
            freq = f", {m['frequency']}" if m['frequency'] else ""
            reason = f" (사유: {m['reason']})" if m['reason'] else ""
            lines.append(f"  • (#{m['id']}) {m['name']} {m['dosage'] or ''}{freq}{reason}")
            lines.append(f"    시작: {m['started_at']}")
        lines.append("")

    if inactive:
        lines.append("▷ 과거 복용:")
        for m in inactive[:10]:  # 최대 10개
            lines.append(f"  • (#{m['id']}) {m['name']} ({m['started_at']} ~ {m['ended_at']})")

    return "\n".join(lines)


def format_documents(documents: list, include_images: bool = False, person: str = None) -> str:
    """문서 목록 포맷팅"""
    person_str = f"[{person}] " if person and person != "나" else ""
    lines = [f"📄 {person_str}문서/검사 기록 ({len(documents)}건)", ""]

    for d in documents:
        lines.append(f"  • (#{d['id']}) {doc_type_to_korean(d['doc_type'])} ({d['recorded_at']})")
        if d['description']:
            lines.append(f"    설명: {d['description']}")
        if d['extracted_data']:
            lines.append(f"    추출 데이터: {len(d['extracted_data'])}개 항목")
        if include_images and d['image_path']:
            lines.append(f"    이미지: {d['image_path']}")

    return "\n".join(lines)


def format_search_results(results: dict, keyword: str, person: str = None) -> str:
    """검색 결과 포맷팅"""
    total = sum(len(v) for v in results.values())
    person_str = f"[{person}] " if person and person != "나" else ""

    if total == 0:
        return f"{person_str}'{keyword}'에 대한 검색 결과가 없습니다."

    lines = [f"🔍 {person_str}'{keyword}' 검색 결과 ({total}건)", ""]

    if results['measurements']:
        lines.append(f"📊 측정값 ({len(results['measurements'])}건):")
        for m in results['measurements'][:5]:
            value_str = format_measurement_value(m['category'], m['value'])
            lines.append(f"  • {m['measured_at'][:10]}: {value_str}")
        lines.append("")

    if results['symptoms']:
        lines.append(f"🤒 증상 ({len(results['symptoms'])}건):")
        for s in results['symptoms'][:5]:
            lines.append(f"  • {s['started_at']}: {category_to_korean(s['category'])}")
        lines.append("")

    if results['medications']:
        lines.append(f"💊 투약 ({len(results['medications'])}건):")
        for m in results['medications'][:5]:
            lines.append(f"  • {m['name']} ({m['started_at']})")
        lines.append("")

    if results['documents']:
        lines.append(f"📄 문서 ({len(results['documents'])}건):")
        for d in results['documents'][:5]:
            lines.append(f"  • {doc_type_to_korean(d['doc_type'])} ({d['recorded_at']})")

    return "\n".join(lines)
