"""보존 산출물의 명시 좌표와 따옴표 구절을 각각 검사한다(모델 호출 없음).

같은 출력 줄의 유효한 D1 L12-15 / R2 L30 좌표를 구절마다 후보로 대조한다.
D1 L7, L101 및 D1 §5(L82)도 읽는다. 문서 ID는 줄을 넘어 계승하지 않는다.
각 구절은 독립 판정하며 다른 구절의 일치로 통과시키지 않는다. ±2줄 후보 일치는
인접 근거 발견일 뿐 정확한 귀속·의미의 증명이 아니다. 따옴표는 용어/요약일 수도
있으므로 불일치는 수동 검토 대상으로 남긴다. 좌표 없는 구절도 생략하지 않는다.
사용: PYTHONPATH=backend python3 verify_coords.py <inputs> <산출물...>
JSON 전체 결과를 stdout에 출력. 종료 0=기계 검토 항목 없음, 1=검토 필요, 2=입력 오류.
어떤 종료 코드도 문서의 의미 정확성이나 과제 달성을 보증하지 않는다.
"""

import boot_paths  # noqa: F401

import argparse
from collections import Counter
import json
from pathlib import Path
import re


COORD = re.compile(r"\b(?P<doc>[DR]\d+)\b|\bL\s*(?P<start>\d+)(?:\s*[-~–]\s*L?(?P<end>\d+))?")
QUOTE = re.compile(r'"([^"\n]+)"|“([^”\n]+)”|「([^」\n]+)」|『([^』\n]+)』')


def norm(text):
    """공백과 Markdown 강조 표지만 정규화하며 문구를 요약하거나 생략하지 않는다."""
    return re.sub(r"[\s`*_]+", "", text)


def load_docs(folder):
    docs = {}
    for path in sorted(Path(folder).glob("*.md")):
        did = path.stem.split("_")[0]
        if not re.fullmatch(r"[DR]\d+", did):
            continue
        if did in docs:
            raise ValueError(f"중복 문서 ID: {did}")
        docs[did] = path.read_text(encoding="utf-8").splitlines()
    if not docs:
        raise ValueError("D/R 문서 ID를 가진 입력 사본이 없습니다")
    return docs


def verify_text(text, docs, margin=2):
    coordinates = []
    quotes = []
    for line_number, line in enumerate(text.splitlines(), 1):
        candidates = []
        did = None
        for match in COORD.finditer(line):
            if match.group("doc"):
                did = match.group("doc")
                continue
            start = int(match.group("start"))
            end = int(match.group("end") or start)
            row = {"line": line_number, "column": match.start() + 1,
                   "coord": f"{did or '?'} {match.group(0)}", "doc": did,
                   "start": start, "end": end}
            source = docs.get(did)
            if source is None:
                row["status"] = "unknown_doc"
            elif end < start:
                row["status"] = "invalid_range"
            elif start < 1 or end > len(source):
                row["status"] = "out_of_range"
                row["max"] = len(source)
            else:
                row["status"] = "in_range"
                exact = norm("".join(source[start - 1:end]))
                nearby = norm("".join(source[max(0, start - 1 - margin):end + margin]))
                candidates.append((row, exact, nearby))
            coordinates.append(row)

        for match in QUOTE.finditer(line):
            value = next(group for group in match.groups() if group is not None)
            normalized = norm(value)
            matches = []
            for row, exact, nearby in candidates:
                if normalized and normalized in nearby:
                    matches.append({"coord": row["coord"], "column": row["column"],
                                    "scope": "exact" if normalized in exact else "nearby"})
            if not normalized:
                status = "empty_quote"
            elif any(item["scope"] == "exact" for item in matches):
                status = "matched_candidate"
            elif matches:
                status = "nearby_only"
            elif candidates:
                status = "unmatched"
            else:
                status = "no_valid_coordinate"
            quotes.append({"line": line_number, "column": match.start() + 1,
                           "quote": value, "status": status, "matches": matches})

    invalid = [row for row in coordinates if row["status"] != "in_range"]
    pending = [row for row in quotes if row["status"] != "matched_candidate"]
    return {
        "coords": len(coordinates),
        "coordinate_status": dict(Counter(row["status"] for row in coordinates)),
        "quote_count": len(quotes),
        "quote_status": dict(Counter(row["status"] for row in quotes)),
        "needs_review": bool(invalid or pending),
        "semantic_validated": False,
        "coordinates": coordinates,
        "quotes": quotes,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        docs = load_docs(args.inputs)
        result = {str(path): verify_text(path.read_text(encoding="utf-8"), docs)
                  for path in args.artifacts}
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(any(item["needs_review"] for item in result.values()))


if __name__ == "__main__":
    raise SystemExit(main())
