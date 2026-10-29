"""수집 관용구의 결정론적 URL 정리·본문 검색·결과 취합."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_honesty import truncation_evidence  # noqa: E402


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            detail = value if value.startswith("$") and len(value) < 80 else type(value).__name__
            raise ValueError(f"JSON 통화 대신 해소되지 않은 입력: {detail}") from exc
    return value


def rows(value):
    value = decode(value)
    if isinstance(value, dict):
        if value.get("success") is False or value.get("error"):
            raise ValueError("실패한 입력을 수집 자료로 사용할 수 없습니다.")
        value = value.get("items")
    if not isinstance(value, list) or any(not isinstance(r, dict) for r in value):
        raise ValueError("items 행 목록이 필요합니다.")
    return value


def integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name}은 0 이상의 정수여야 합니다.")
    return value


def selection_markers(result, total, selected):
    """의도한 선택을 원천 절단과 구별한다. 기존 원천 표지는 지우지 않는다."""
    markers = list(truncation_evidence(result).get("truncations", []))
    if selected < total:
        markers.append({"scope": "selection", "total": total,
                        "selected": selected, "omitted": total - selected})
        result["truncated"] = True
    if markers:
        result["truncations"] = markers


def urls(args):
    """URL은 주소 문자열 그대로 비교한다. 일반 텍스트의 느슨한 동등성을 쓰지 않는다."""
    original = decode(args["source"])
    source = rows(original)
    seen, unique, failures, ordered = set(), [], [], []
    for row in source:
        if row.get("_error"):
            failures.append(row)
            ordered.append(row)
            continue
        url = row.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("수집 후보에는 비어 있지 않은 url이 필요합니다.")
        if url not in seen:
            seen.add(url)
            unique.append(row)
            ordered.append(row)
    out = dict(original) if isinstance(original, dict) else {}
    out.pop("text", None)
    out.update(items=ordered, count=len(ordered), total=len(ordered))
    out["error_count"] = max(out.get("error_count") or 0, len(failures))
    if out["error_count"]:
        out["partial"] = True
    if "limit" not in args:
        return out
    limit = integer(args["limit"], "개수")
    chosen = unique[:limit]
    selection_markers(out, len(unique), len(chosen))
    out.update(items=chosen, count=len(chosen), total=len(chosen),
               source_error_items=failures,
               selection_info={"source_count": len(source), "unique_urls": len(unique),
                               "duplicates": len(source) - len(failures) - len(unique),
                               "selected": len(chosen), "omitted_by_limit": len(unique) - len(chosen)})
    return {**out, "collection": out}


def finish(args):
    selection = decode(args["selection"])
    result = decode(args["result"])
    rows(result)
    # each의 크롤 실패·원문 잘림 신고와 상류 검색의 실패·잘림을 함께 보존.
    out = {k: v for k, v in result.items() if v is not None}
    out["items"] = rows(result) + selection.get("source_error_items", [])
    out["count"] = len(out["items"])
    out["total"] = len(out["items"])
    # 원천 실패 행을 붙이면서 새 크롤의 error_count=0을 그대로 두면
    # 하류가 부분 실패를 정상 수집으로 오해한다. 두 단계의 실패를 합산한다.
    source_errors = max(selection.get("error_count") or 0,
                        len(selection.get("source_error_items", [])))
    crawl_errors = max(result.get("error_count") or 0,
                       sum(bool(row.get("_error")) for row in rows(result)))
    out["error_count"] = source_errors + crawl_errors
    if out["error_count"] or selection.get("partial") or result.get("partial"):
        out["partial"] = True
    out.update(selection_info=selection["selection_info"],
               source_markers={k: v for k, v in selection.items()
                               if k not in ("items", "selection_info", "success", "count", "total")},
               truncated=bool(result.get("truncated") or selection.get("truncated")))
    # source_markers는 현재 판본의 정직 표지 탐색 경로가 아니다. 최상위에도 명시한다.
    markers = []
    for origin in (selection, result):
        markers.extend(truncation_evidence(origin).get("truncations", []))
    if markers:
        out["truncations"] = markers
    return out


def match_context(args):
    """본문 문맥 선택은 값 연산이다. 구판 IBL 프로그램을 실행하지 않는다."""
    from common.row_conditions import _match
    from common.pkg_utils import load_sibling
    package = Path(__file__).resolve().parents[1] / 'packages/installed/tools/data-ops'
    context_module = load_sibling(str(package / 'handler.py'), 'dataops_filter_context')
    source = decode(args['source'])
    records = rows(source)
    context = integer(args.get('context', 0), '문맥')
    limit = integer(args['limit'], '개수')
    where = {'field': 'text', 'op': 'matches', 'value': args['pattern']}
    # Validate even empty input; malformed patterns must not become empty success.
    _match({'text': ''}, where)
    kept, info = context_module.select_context(records, where,
        {'before': context, 'after': context, 'by': 'url', 'limit': limit}, _match)
    # 일반 표 변환과 같은 출구를 쓴다. 선택 전 text/table을 남기면
    # 발췌 30행 옆에 PDF 전문이 붙고 자료실에 JSON 전체가 다시 색인된다.
    handler = load_sibling(str(package / 'handler.py'), 'handler')
    envelope = handler._emit_items(source, kept, population=True)
    envelope['match_info'] = info
    if info['omitted_matches']:
        envelope['truncations'] = list(envelope.get('truncations') or []) + [{
            'scope': 'selection', 'source': 'filter.context', 'unit': 'matches',
            'retained': info['selected_matches'], 'total': info['total_matches']}]
    return envelope


def collect_values(args):
    """명시적으로 수집한 행 결과를 펼친다. 실행·재시도·구문 해석은 하지 않는다."""
    collected = rows(args['results'])
    items, failures, markers, displays, row_markers = [], [], [], [], []
    renamed = {}
    for row in collected:
        origin = row.get('source') or {}
        keep = {key: origin[key] for key in args.get('keep', []) if key in origin}
        if row.get('ok') is not True:
            failure = {**keep, '_error': row.get('error')}
            items.append(failure)
            failures.append(failure)
            continue
        value = row['value']
        if isinstance(value, list):
            children = value
        elif isinstance(value, dict) and isinstance(value.get('items'), list):
            children = value['items']
            markers.extend(truncation_evidence(value).get('truncations', []))
        else:
            # 읽기·심사처럼 Record를 반환하는 생산자는 행 하나로 보존한다.
            children = [value]
        from ibl_honesty import markers_of
        if isinstance(value, dict):
            honesty = markers_of(value)
            if honesty:
                row_markers.append({'row': len(displays) + 1, 'markers': honesty})
        displays.append(value.get('_display') if isinstance(value, dict) and isinstance(value.get('items'), list) else None)
        for child in children:
            if not isinstance(child, dict):
                raise ValueError('수집 결과의 행은 Record여야 합니다.')
            merged = dict(keep)
            for key, value in child.items():
                target = key
                while target in merged:
                    target += '_2'
                if target != key:
                    renamed[key] = target
                merged[target] = value
            items.append(merged)
    out = {'items': items, 'count': len(items), 'total': len(items),
           'error_count': len(failures), 'errors': failures,
           'ok_count': len(collected) - len(failures),
           'rows_requested': len(collected), 'rows_processed': len(collected),
           'partial': bool(failures)}
    if markers:
        out.update(truncated=True, truncations=markers)
    from common.currency import collected_item_display
    display = collected_item_display(displays)
    if display:
        out['_display'] = display
    if row_markers:
        out['row_honesty'] = row_markers
    if renamed:
        out['collect_renamed'] = renamed
    return out


def run(args):
    return {"urls": urls,
            "finish": finish, "match": match_context,
            "collect": collect_values}[args["op"]](args)


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin)), ensure_ascii=False, allow_nan=False))
    except (KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
