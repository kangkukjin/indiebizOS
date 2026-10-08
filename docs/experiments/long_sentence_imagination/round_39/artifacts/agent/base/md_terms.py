#!/usr/bin/env python3
"""마크다운 문서 묶음 용어 치환 + 제목 앵커 재매핑 + 깨진 링크 점검.

사용: python3 -I md_terms.py --docs DIR --out DIR [--dry-run]

- 코드 펜스(```) 안, 인라인 코드(백틱) 안, 링크 대상 `](...)` 괄호 안은 치환하지 않는다.
- 제목이 바뀌어 앵커가 달라지면 그 앵커를 가리키는 링크 대상만 새 앵커로 고친다.
- 하나라도 읽기 실패면 어떤 문서도 쓰지 않는다. 바뀐 파일만 제자리에 원자 교체한다.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile

TERMS = [("구독 플랜", "요금제"), ("워크스페이스", "작업 공간")]
ANCHOR_DROP = set(".,:()!?`")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")


def anchor(text):
    t = "".join(c for c in text.lower() if c not in ANCHOR_DROP)
    return t.strip().replace(" ", "-")


def is_fence(line):
    return line.lstrip().startswith("```")


def tokenize(line):
    """펜스 밖 한 줄 → [(kind, text)], kind = prose | code | target."""
    segs, buf, i, n = [], [], 0, len(line)

    def flush():
        if buf:
            segs.append(("prose", "".join(buf)))
            buf.clear()
    while i < n:
        c = line[i]
        if c == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            run = j - i
            # 같은 길이의 백틱 런으로 닫힌다(CommonMark). 없으면 문자 그대로.
            k = j
            close = -1
            while k < n:
                if line[k] == "`":
                    m = k
                    while m < n and line[m] == "`":
                        m += 1
                    if m - k == run:
                        close = m
                        break
                    k = m
                else:
                    k += 1
            if close != -1:
                flush()
                segs.append(("code", line[i:close]))
                i = close
            else:
                buf.append(line[i:j])
                i = j
            continue
        if line.startswith("](", i):
            end = line.find(")", i + 2)
            if end != -1:
                buf.append("](")
                flush()
                segs.append(("target", line[i + 2:end]))
                buf.append(")")
                i = end + 1
                continue
        buf.append(c)
        i += 1
    flush()
    return segs


def split_nl(raw_line):
    if raw_line.endswith("\r\n"):
        return raw_line[:-2], "\r\n"
    if raw_line.endswith("\n") or raw_line.endswith("\r"):
        return raw_line[:-1], raw_line[-1]
    return raw_line, ""


def analyze(text):
    """문서 → 줄 목록 [{body, nl, fenced, segs, heading}]."""
    out, fence = [], False
    for raw in text.splitlines(keepends=True):
        body, nl = split_nl(raw)
        if is_fence(body):
            out.append({"body": body, "nl": nl, "fenced": True, "segs": None, "heading": None})
            fence = not fence
            continue
        if fence:
            out.append({"body": body, "nl": nl, "fenced": True, "segs": None, "heading": None})
            continue
        m = HEADING_RE.match(body)
        out.append({"body": body, "nl": nl, "fenced": False, "segs": tokenize(body),
                    "heading": m.group(2) if m else None})
    return out, fence


def replace_prose(s):
    cnt = {}
    for old, new in TERMS:
        k = s.count(old)
        if k:
            cnt[old] = k
            s = s.replace(old, new)
    return s, cnt


def links(lines):
    for no, ln in enumerate(lines, 1):
        if ln["fenced"]:
            continue
        for kind, t in ln["segs"]:
            if kind == "target":
                yield no, t


def split_target(t, cur):
    if "#" in t:
        f, a = t.split("#", 1)
        return (f or cur), a
    return t, None


def broken(docs, anchors_of):
    res = []
    for name in sorted(docs):
        for no, t in links(docs[name]):
            f, a = split_target(t, name)
            if f not in anchors_of:
                res.append({"file": name, "line": no, "target": t, "reason": "없는 파일"})
            elif a is not None and a not in anchors_of[f]:
                res.append({"file": name, "line": no, "target": t, "reason": "그 파일에 없는 앵커"})
    return res


def heading_anchors(lines):
    return {anchor(ln["heading"]) for ln in lines if ln["heading"] is not None}


def render(lines):
    return "".join(ln["body"] + ln["nl"] for ln in lines)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def atomic_write(path, data):
    d = os.path.dirname(path)
    mode = os.stat(path).st_mode & 0o7777 if os.path.exists(path) else 0o644
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true", help="문서를 쓰지 않고 보고만")
    a = ap.parse_args()
    started = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    names = sorted(n for n in os.listdir(a.docs)
                   if n.endswith(".md") and os.path.isfile(os.path.join(a.docs, n)))
    raw, failed = {}, []
    for n in names:
        try:
            with open(os.path.join(a.docs, n), "rb") as f:
                b = f.read()
            raw[n] = (b, b.decode("utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            failed.append({"file": n, "reason": f"{type(e).__name__}: {e}"})

    report = {"started_at": started, "docs": a.docs, "dry_run": a.dry_run,
              "files_total": len(names), "failed": failed}
    os.makedirs(a.out, exist_ok=True)
    if failed:
        report.update({"applied": False, "files_changed": [], "files_written": 0,
                       "note": "읽기 실패 파일이 있어 어떤 문서도 쓰지 않았다"})
        write_outputs(a.out, report)
        print(json.dumps({"ok": False, "applied": False, "failed": failed}, ensure_ascii=False))
        return 2

    old_docs, new_docs, unclosed = {}, {}, []
    replacements, repl_by_term = 0, {o: 0 for o, _ in TERMS}
    for n in names:
        lines, open_fence = analyze(raw[n][1])
        if open_fence:
            unclosed.append(n)
        old_docs[n] = lines
        nl = []
        for ln in lines:
            if ln["fenced"]:
                nl.append(dict(ln))
                continue
            segs = []
            for kind, t in ln["segs"]:
                if kind == "prose":
                    t, cnt = replace_prose(t)
                    for k, v in cnt.items():
                        repl_by_term[k] += v
                        replacements += v
                segs.append((kind, t))
            body = "".join(t for _, t in segs)
            m = HEADING_RE.match(body)
            nl.append({"body": body, "nl": ln["nl"], "fenced": False, "segs": segs,
                       "heading": m.group(2) if m else None})
        new_docs[n] = nl

    old_anchors = {n: heading_anchors(old_docs[n]) for n in names}
    new_anchors = {n: heading_anchors(new_docs[n]) for n in names}

    # 제목 변경 → 파일별 옛 앵커 → 새 앵커 대응표
    headings_changed, remap = [], {n: {} for n in names}
    for n in names:
        for o, w in zip(old_docs[n], new_docs[n]):
            if o["heading"] is not None and o["heading"] != w["heading"]:
                headings_changed.append({"file": n, "old": o["heading"], "new": w["heading"]})
                oa, na = anchor(o["heading"]), anchor(w["heading"])
                if oa != na:
                    remap[n].setdefault(oa, set()).add(na)

    anchors_remapped, ambiguous = 0, []
    for n in names:
        for no, ln in enumerate(new_docs[n], 1):
            if ln["fenced"]:
                continue
            segs, touched = [], False
            for kind, t in ln["segs"]:
                if kind == "target" and "#" in t:
                    f_part, a_part = t.split("#", 1)
                    dest = f_part or n
                    cand = remap.get(dest, {}).get(a_part)
                    if cand:
                        if a_part in new_anchors[dest] or len(cand) > 1:
                            # 옛 앵커가 여전히 있거나 새 후보가 여럿이면 모호 — 고치지 않고 보고
                            ambiguous.append({"file": n, "line": no, "target": t,
                                              "candidates": sorted(cand)})
                        else:
                            t = f"{f_part}#{next(iter(cand))}"
                            anchors_remapped += 1
                            touched = True
                segs.append((kind, t))
            if touched:
                ln["segs"] = segs
                ln["body"] = "".join(t for _, t in segs)

    broken_before = broken(old_docs, old_anchors)
    broken_after = broken(new_docs, new_anchors)

    files_changed, lines_changed = [], {}
    new_bytes = {}
    for n in names:
        nb = render(new_docs[n]).encode("utf-8")
        if nb != raw[n][0]:
            files_changed.append(n)
            lines_changed[n] = sum(1 for o, w in zip(old_docs[n], new_docs[n]) if o["body"] != w["body"])
            new_bytes[n] = nb

    if not a.dry_run:
        for n in files_changed:
            atomic_write(os.path.join(a.docs, n), new_bytes[n])

    # 쓰기 뒤 디스크 재독: 지문 + 의도한 본문 일치 + 디스크 기준 깨진 링크 재계산
    disk, mismatch = {}, []
    for n in names:
        with open(os.path.join(a.docs, n), "rb") as f:
            disk[n] = f.read()
        expect = new_bytes.get(n, raw[n][0]) if not a.dry_run else raw[n][0]
        if disk[n] != expect:
            mismatch.append(n)
    disk_docs = {n: analyze(disk[n].decode("utf-8"))[0] for n in names}
    broken_disk = broken(disk_docs, {n: heading_anchors(disk_docs[n]) for n in names})

    report.update({
        "applied": True,
        "files_changed": files_changed,
        "files_written": 0 if a.dry_run else len(files_changed),
        "lines_changed_by_file": lines_changed,
        "replacements": replacements,
        "replacements_by_term": {f"{o}→{w}": repl_by_term[o] for o, w in TERMS},
        "headings_changed": headings_changed,
        "anchors_remapped": anchors_remapped,
        "anchor_remap_ambiguous": ambiguous,
        "broken_links": broken_before,
        "broken_links_after": broken_after,
        "broken_links_count": {"before": len(broken_before), "after": len(broken_after),
                               "after_on_disk": len(broken_disk),
                               "increased": len(broken_after) > len(broken_before)},
        "unclosed_fence_files": unclosed,
        "verify": {"disk_matches_intended": not mismatch, "mismatch_files": mismatch,
                   "idempotent_recheck": None},
        "sha256": {n: sha(disk[n]) for n in names},
    })
    # 멱등성 자가 점검: 디스크 내용에 같은 치환을 다시 걸면 바뀔 것이 없어야 한다(쓰기 안 함)
    if not a.dry_run:
        again = [n for n in names if any(
            replace_prose(t)[1] for ln in disk_docs[n] if not ln["fenced"]
            for kind, t in ln["segs"] if kind == "prose")]
        report["verify"]["idempotent_recheck"] = {"files_still_with_terms": again, "ok": not again}
    write_outputs(a.out, report)
    print(json.dumps({"ok": not mismatch, "files_changed": len(files_changed),
                      "written": report["files_written"], "replacements": replacements,
                      "headings_changed": len(headings_changed), "anchors_remapped": anchors_remapped,
                      "ambiguous": len(ambiguous), "broken": report["broken_links_count"],
                      "verify": report["verify"]}, ensure_ascii=False))
    return 0 if not mismatch else 1


def write_outputs(out, r):
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
        f.write("\n")
    L = [f"# 용어 치환 보고 — {r['started_at']}", "", f"- 대상: `{r['docs']}` (문서 {r['files_total']}개)"]
    if not r.get("applied"):
        L += ["- **적용 안 함** — 읽기에 실패한 파일이 있어 어떤 문서도 쓰지 않았다.", "", "## 실패 파일"]
        L += [f"- `{x['file']}`: {x['reason']}" for x in r["failed"]]
    else:
        bc = r["broken_links_count"]
        L += [f"- 모드: {'드라이런(문서 쓰기 없음)' if r['dry_run'] else '적용'}",
              f"- 바뀐 파일: {len(r['files_changed'])}개, 실제로 쓴 파일: {r['files_written']}개"
              + (" — 바뀔 것이 없어 아무 문서도 쓰지 않았다" if not r["files_changed"] else ""),
              f"- 산문 용어 치환: {r['replacements']}곳 ({', '.join(f'{k} {v}' for k, v in r['replacements_by_term'].items())})",
              f"- 바뀐 제목: {len(r['headings_changed'])}개, 새 앵커로 고친 링크: {r['anchors_remapped']}개",
              f"- 깨진 링크: 바꾸기 전 {bc['before']}개 → 바꾼 뒤 {bc['after']}개 (디스크 재독 기준 {bc['after_on_disk']}개)"
              + (" — **늘었음**" if bc["increased"] else " — 늘지 않음"),
              f"- 쓰기 뒤 검증: 디스크=의도 {r['verify']['disk_matches_intended']}, 재치환 점검 {r['verify']['idempotent_recheck']}",
              "", "## 바뀐 파일(바뀐 줄 수)"]
        L += [f"- {k}: {v}" for k, v in r["lines_changed_by_file"].items()] or ["- 없음"]
        L += ["", "## 바뀐 제목"]
        L += [f"- {h['file']}: `{h['old']}` → `{h['new']}`" for h in r["headings_changed"]] or ["- 없음"]
        L += ["", "## 깨진 링크(바꾸기 전 기준)"]
        L += [f"- {x['file']}:{x['line']} → `{x['target']}` ({x['reason']})" for x in r["broken_links"]] or ["- 없음"]
        L += ["", "## 깨진 링크(바꾼 뒤)"]
        L += [f"- {x['file']}:{x['line']} → `{x['target']}` ({x['reason']})" for x in r["broken_links_after"]] or ["- 없음"]
        if r["anchor_remap_ambiguous"]:
            L += ["", "## 앵커 재매핑 보류(모호)"]
            L += [f"- {x['file']}:{x['line']} `{x['target']}` 후보 {x['candidates']}" for x in r["anchor_remap_ambiguous"]]
        L += ["", "## 적용 규칙",
              "- 코드 펜스: 줄 앞 공백을 뗄 뒤 ``` 로 시작하는 줄이 열고 닫는다. 펜스 안(구분 줄 포함)은 치환하지 않고, # 으로 시작해도 제목이 아니며, 그 안의 `[..](..)` 도 링크로 세거나 고치지 않는다.",
              "- 인라인 코드: 같은 길이의 백틱 런으로 닫히는 구간(닫히지 않은 백틱은 문자). 제목 안의 인라인 코드도 치환하지 않는다(예: api_03 `### `구독 플랜` 객체` 는 그대로).",
              "- 링크 대상: `](` 부터 다음 `)` 까지. 치환하지 않고 앵커 재매핑으로만 고친다. 링크 표시 텍스트 `[...]` 와 링크가 아닌 대괄호는 산문.",
              "- 제목: 펜스 밖에서 `#`1~6개 + 공백으로 시작하는 줄. 앵커 = 제목 텍스트 소문자 → . , : ( ) ! ? 백틱 삭제 → 앞뒤 공백 제거 → 공백을 - 로.",
              "- 중복 제목: 주어진 규칙에 번호 붙이기가 없으므로 같은 앵커로 본다(plans.md 의 두 '구독 플랜 비교' → 모두 '요금제-비교').",
              "- 앵커 재매핑: 제목이 바뀜 파일의 옛 앵커→새 앵커 대응표로 `파일.md#앵커`·`#앵커` 대상을 고친다. 바꾸기 전부터 깨져 있던 링크는 고치지 않는다. 옛 앵커가 바꾼 뒤에도 남거나 새 후보가 여럿이면 고치지 않고 보류로 보고한다.",
              "- 깨진 링크: docs 에 없는 파일, 또는 그 파일의 제목 앵커 집합에 없는 앵커.",
              "- 쓰기: 모든 파일을 먼저 읽고(UTF-8 엄격), 하나라도 실패하면 어떤 문서도 쓰지 않는다. 바이트가 달라진 파일만 임시 파일→rename 으로 제자리 교체(권한 유지, 줄바꿈 보존). 나머지 파일은 열기만 한다.",
              "- sha256: 쓰기 뒤 디스크에서 다시 읽은 모든 문서의 지문."]
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
