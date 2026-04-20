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

import storage


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """도구 실행 엔트리포인트"""

    if tool_name == "save_health_info":
        return save_health_info(tool_input, project_path)
    elif tool_name == "get_health_context":
        return get_health_context(tool_input)
    else:
        return f"알 수 없는 도구: {tool_name}"


def save_health_info(input_data: dict, project_path: str = ".") -> str:
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

    # AI가 info_type에 한국어나 카테고리명을 넣는 경우 자동 보정
    _VALID_INFO_TYPES = {'measurement', 'symptom', 'medication', 'document'}

    # 한국어 info_type → 영어 매핑
    _KO_INFO_TYPE_MAP = {
        '측정': 'measurement', '측정값': 'measurement',
        '증상': 'symptom',
        '투약': 'medication', '약': 'medication', '약물': 'medication',
        '문서': 'document', '검사': 'document',
    }

    # 카테고리명 매핑 (영어/한국어)
    _KNOWN_CATEGORIES = {
        'blood_pressure', 'blood_sugar', 'blood_glucose', 'weight',
        'blood_count', 'body_composition', 'kidney_function', 'liver_function',
        'cholesterol', 'thyroid', 'hemoglobin',
    }
    _KO_CATEGORY_MAP = {
        '혈압': 'blood_pressure', '혈당': 'blood_sugar', '체중': 'weight',
        '혈액검사': 'blood_count', '콜레스테롤': 'cholesterol',
        '심박수': 'heart_rate', '체온': 'temperature', '산소포화도': 'oxygen_saturation',
    }

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

            # 빈 value 방어 — 조용한 손실 방지
            _meaningful = {k: v for k, v in value.items() if v not in (None, '')}
            if not _meaningful:
                return (
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
            return f"✓ {person_str}{category_to_korean(category)} 기록 저장됨 (#{record_id}): {value_str}"

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
            return f"✓ {person_str}증상 기록 저장됨 (#{record_id}): {category_to_korean(category)}{severity_str}"

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
            return f"✓ {person_str}투약 기록 저장됨 (#{record_id}): {name} {dosage or ''}{freq_str}"

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
            return result

        else:
            return f"알 수 없는 정보 유형: {info_type}"

    except Exception as e:
        return f"저장 실패: {str(e)}"


def get_health_context(input_data: dict) -> str:
    """건강 컨텍스트 조회"""
    # query_type 명시 여부 구분 — default 처리 전에 확인
    query_type_given = input_data.get('query_type') is not None
    query_type = input_data.get('query_type', 'summary')
    category = input_data.get('category')
    days = input_data.get('days', 365)
    keyword = input_data.get('keyword')
    include_images = input_data.get('include_images', False)
    person = input_data.get('person')  # 대상자

    # AI가 query_type에 한국어나 카테고리명을 넣는 경우 자동 보정
    _VALID_QUERY_TYPES = {'summary', 'measurements', 'symptoms', 'medications', 'documents', 'search', 'list_persons'}

    # 한국어 query_type → 영어 query_type 매핑
    _KO_QUERY_TYPE_MAP = {
        '요약': 'summary', '전체': 'summary',
        '측정기록': 'measurements', '측정': 'measurements', '측정값': 'measurements',
        '증상': 'symptoms',
        '투약': 'medications', '약': 'medications', '약물': 'medications',
        '문서': 'documents', '검사': 'documents',
        '검색': 'search',
        '목록': 'list_persons', '사람목록': 'list_persons',
    }

    # 영어/한국어 카테고리명 매핑
    _KNOWN_CATEGORIES = {
        'blood_pressure', 'blood_sugar', 'blood_glucose', 'weight',
        'blood_count', 'body_composition', 'kidney_function', 'liver_function',
        'cholesterol', 'thyroid', 'hemoglobin',
    }
    _KO_CATEGORY_MAP = {
        '혈압': 'blood_pressure', '혈당': 'blood_sugar', '체중': 'weight',
        '혈액검사': 'blood_count', '콜레스테롤': 'cholesterol',
        '심박수': 'heart_rate', '체온': 'temperature', '산소포화도': 'oxygen_saturation',
    }

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
    # (학습 코퍼스가 [self:health_query]{category: "혈당"} 형태로 가르치기 때문)
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
                return "등록된 사람이 없습니다."
            lines = ["👥 등록된 사람 목록:", ""]
            for p in persons:
                note = f" - {p['note']}" if p.get('note') else ""
                lines.append(f"  • {p['name']}{note}")
            return "\n".join(lines)

        elif query_type == 'summary':
            # 전체 요약
            summary = storage.get_health_summary(days=days, person=person)
            return format_health_summary(summary, include_images)

        elif query_type == 'measurements':
            # 측정값 조회
            measurements = storage.get_measurements(category=category, days=days, person=person)
            if not measurements:
                cat_str = category_to_korean(category) if category else "측정"
                person_str = f"{person}의 " if person and person != "나" else ""
                return f"{person_str}최근 {days}일간 {cat_str} 기록이 없습니다."
            return format_measurements(measurements, category, person)

        elif query_type == 'symptoms':
            # 증상 조회
            symptoms = storage.get_symptoms(category=category, days=days, person=person)
            if not symptoms:
                person_str = f"{person}의 " if person and person != "나" else ""
                return f"{person_str}최근 {days}일간 증상 기록이 없습니다."
            return format_symptoms(symptoms, person)

        elif query_type == 'medications':
            # 투약 기록 조회
            active_only = input_data.get('active_only', False)
            medications = storage.get_medications(days=days, active_only=active_only, person=person)
            if not medications:
                person_str = f"{person}의 " if person and person != "나" else ""
                return f"{person_str}투약 기록이 없습니다."
            return format_medications(medications, person)

        elif query_type == 'documents':
            # 문서 조회
            documents = storage.get_documents(doc_type=category, days=days, person=person)
            if not documents:
                person_str = f"{person}의 " if person and person != "나" else ""
                return f"{person_str}최근 {days}일간 문서 기록이 없습니다."
            return format_documents(documents, include_images, person)

        elif query_type == 'search':
            # 키워드 검색
            if not keyword:
                return "검색 키워드를 입력해주세요."
            results = storage.search_records(keyword, person=person)
            return format_search_results(results, keyword, person)

        else:
            return f"알 수 없는 조회 유형: {query_type}"

    except Exception as e:
        return f"조회 실패: {str(e)}"


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


def format_measurements(measurements: list, category: str = None, person: str = None) -> str:
    """측정값 목록 포맷팅"""
    cat_str = category_to_korean(category) if category else "측정값"
    person_str = f"[{person}] " if person and person != "나" else ""
    lines = [f"📊 {person_str}{cat_str} 기록 ({len(measurements)}건)", ""]

    for m in measurements[:20]:  # 최대 20개
        value_str = format_measurement_value(m['category'], m['value'])
        date_str = m['measured_at'][:16].replace('T', ' ')
        note_str = f" - {m['note']}" if m['note'] else ""
        lines.append(f"  {date_str}: {value_str}{note_str}")

    return "\n".join(lines)


def format_symptoms(symptoms: list, person: str = None) -> str:
    """증상 목록 포맷팅"""
    person_str = f"[{person}] " if person and person != "나" else ""
    lines = [f"🤒 {person_str}증상 기록 ({len(symptoms)}건)", ""]

    for s in symptoms:
        status = "진행중" if not s['ended_at'] else f"~{s['ended_at']}"
        sev = f" [{severity_to_korean(s['severity'])}]" if s['severity'] else ""
        desc = f": {s['description']}" if s['description'] else ""
        lines.append(f"  • {category_to_korean(s['category'])}{sev} ({s['started_at']} {status}){desc}")

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
            lines.append(f"  • {m['name']} {m['dosage'] or ''}{freq}{reason}")
            lines.append(f"    시작: {m['started_at']}")
        lines.append("")

    if inactive:
        lines.append("▷ 과거 복용:")
        for m in inactive[:10]:  # 최대 10개
            lines.append(f"  • {m['name']} ({m['started_at']} ~ {m['ended_at']})")

    return "\n".join(lines)


def format_documents(documents: list, include_images: bool = False, person: str = None) -> str:
    """문서 목록 포맷팅"""
    person_str = f"[{person}] " if person and person != "나" else ""
    lines = [f"📄 {person_str}문서/검사 기록 ({len(documents)}건)", ""]

    for d in documents:
        lines.append(f"  • {doc_type_to_korean(d['doc_type'])} ({d['recorded_at']})")
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
