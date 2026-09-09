"""Frozen tasks and artifact oracles for the 2026-09-09 exposure experiment.

Task text never includes the preferred alias or reference program. Data vary by seed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401

import json
import os
import random
from idiom_value_cases import final_value, content

CASES = [
    dict(
        id="direct_latest",
        group="direct",
        relevant="최신범위읽기",
        task="drafts/*.md의 문서 중 가장 최근에 수정된 문서에서 11~22줄 본문을 반환해 줘. 파일명의 날짜가 아니라 수정시각 기준이다. 후보는 4개, 수정시각 동률은 없고 모두 80줄이다.",
    ),
    dict(
        id="direct_context",
        group="direct",
        relevant="위치마다읽기",
        task="locations.json은 파일·줄번호 열이 있는 위치 목록이다. 목록 순서대로 세 위치에서 각각 지정 줄부터 5줄씩 본문을 읽어 줘. 파일·줄번호·본문을 반환하고, 없는 파일은 해당 위치와 오류를 남겨 줘. 한 곳이 없어도 나머지는 읽어야 한다.",
    ),
    dict(
        id="direct_ledger",
        group="direct",
        relevant="원장에누적",
        task="existing.json과 arrivals.json의 행을 합쳐 outputs/archive.json에 JSON으로 보관해 줘. id와 kind가 모두 같아야 같은 항목이고, 중복이면 먼저 있던 행 전체를 보존한다. 기존 목록 뒤에 새로운 고유 행을 붙이는 순서다. 입력 파일은 변경하지 마.",
    ),
    dict(
        id="embedded_latest",
        group="embedded",
        relevant="최신범위읽기",
        task="인수인계 자료 두 개를 준비해 줘. drafts/*.md 네 문서 중 수정시각이 가장 최근인 문서의 11~22줄을 outputs/excerpt.txt에 저장하고, queue.json에서 state가 open이고 priority가 3 이상인 항목을 id 오름차순으로 outputs/pending.json에 저장해 줘. 문서들은 모두 80줄이고 수정시각 동률은 없다. JSON은 원래 행의 모든 필드를 보존한다. 입력 파일은 변경하지 마.",
    ),
    dict(
        id="embedded_context",
        group="embedded",
        relevant="위치마다읽기",
        task="수정 검토 자료를 준비해 줘. review_locations.json에는 파일·줄번호·state·priority 열이 있다. state=open, priority>=3인 위치를 파일명 오름차순으로 정렬한 앞 세 곳의 지정 줄부터 5줄씩 본문을 수집해서 outputs/snippets.json에 저장해 줘. 각 결과에는 파일·줄번호·본문이 필요하고 읽을 수 없는 곳은 위치와 오류를 남긴다. 별도로 state=closed인 원래 행 전부를 파일명 오름차순으로 outputs/closed.json에 저장해 줘. 입력 파일은 변경하지 마.",
    ),
    dict(
        id="embedded_ledger",
        group="embedded",
        relevant="원장에누적",
        task="자료 반입을 정리해 줘. submissions.json에서 approved=true인 행의 id·kind·value만 취해 existing.json에 있던 행들과 함께 outputs/archive.json에 저장한다. id와 kind가 모두 같으면 기존 행 전체를 보존하고, 새 고유 행은 원래 제출 순서로 뒤에 붙인다. approved=false인 원래 행은 모두 outputs/rejected.json에 따로 보관한다. 입력 파일은 변경하지 마.",
    ),
    dict(
        id="counter_latest",
        group="counter",
        relevant=None,
        task="drafts/*.md에서 파일명에 적힌 YYYY-MM-DD 날짜가 가장 늦은 문서의 11~22줄 본문을 반환해 줘. 수정시각은 선정 기준이 아니다. 후보는 report_YYYY-MM-DD.md 형식의 네 파일이며 모두 80줄이다.",
    ),
    dict(
        id="counter_context",
        group="counter",
        relevant=None,
        task="notes/*.txt에서 NEEDLE이 나타나는 모든 위치와 그 일치 줄만 반환해 줘. 파일·줄번호·일치 내용을 보존한다. 주변 본문을 별도로 읽거나 위치 개수를 줄이지 마.",
    ),
    dict(
        id="counter_ledger",
        group="counter",
        relevant=None,
        task="registry.json의 records 목록에 updates.json의 행들을 id 기준으로 반영해 줘. 같은 id는 새로 온 필드 값으로 갱신하되 새 행에 없는 기존 필드는 보존하고, 없는 id는 추가한다. records 이외의 메타데이터도 유지해야 한다. updates.json은 변경하지 마. 결과는 registry.json에 저장해 줘.",
    ),
]
BY_ID = {x["id"]: x for x in CASES}


def put(root, name, value):
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def setup(root, seed=0):
    rng = random.Random(seed)
    (root / "drafts").mkdir()
    (root / "notes").mkdir()
    (root / "outputs").mkdir()
    for i, date in enumerate(
        ["2026-08-03", "2026-08-11", "2026-08-19", "2026-08-27"]
    ):
        p = root / "drafts" / f"report_{date}.md"
        p.write_text(
            "".join(
                f"DOCUMENT-{rng.randrange(10000,99999)} LINE-{n}\n"
                for n in range(1, 81)
            )
        )
        stamp = 1600000000 + [900, 2700, 1800, 0][i]
        os.utime(p, (stamp, stamp))
    for i in range(6):
        p = root / "notes" / f"{i:02d}.txt"
        p.write_text(
            "".join(
                f'{"NEEDLE " if n in (4,13) else ""}N{i}-{rng.randrange(10000,99999)}-{n}\n'
                for n in range(1, 26)
            )
        )
    put(
        root,
        "locations.json",
        [
            {"파일": "notes/01.txt", "줄번호": 4},
            {"파일": "notes/missing.txt", "줄번호": 2},
            {"파일": "notes/04.txt", "줄번호": 8},
        ],
    )
    reviews = [
        {
            "파일": f"notes/{i:02d}.txt",
            "줄번호": 4 + i,
            "state": "open" if i < 4 else "closed",
            "priority": 3 + i % 2,
        }
        for i in range(6)
    ]
    rng.shuffle(reviews)
    put(root, "review_locations.json", reviews)
    old = [
        {
            "id": i,
            "kind": k,
            "value": rng.randrange(100, 900),
            "original": True,
        }
        for i, k in [(1, "a"), (2, "a"), (1, "b"), (4, "a")]
    ]
    incoming = [
        {"id": i, "kind": k, "value": rng.randrange(900, 1900)}
        for i, k in [
            (1, "a"),
            (3, "a"),
            (2, "b"),
            (3, "a"),
            (4, "a"),
            (5, "b"),
        ]
    ]
    put(root, "existing.json", old)
    put(root, "arrivals.json", incoming)
    put(
        root,
        "submissions.json",
        [dict(x, approved=i not in (1, 4)) for i, x in enumerate(incoming)],
    )
    put(
        root,
        "queue.json",
        [
            {
                "id": i,
                "state": "open" if i % 3 else "closed",
                "priority": i % 5,
                "title": f"T-{rng.randrange(99999)}",
            }
            for i in range(1, 10)
        ],
    )
    put(
        root,
        "registry.json",
        {
            "owner": "retain-this",
            "revision": 7,
            "records": [
                {"id": i, "value": rng.randrange(100), "keep": f"K{i}"}
                for i in range(1, 5)
            ],
        },
    )
    put(
        root,
        "updates.json",
        [{"id": i, "value": rng.randrange(1000, 2000)} for i in [2, 4, 6]],
    )


def read_rows(path):
    obj = json.loads(path.read_text())
    return (
        obj.get("items")
        if isinstance(obj, dict) and isinstance(obj.get("items"), list)
        else obj
    )


def accumulated(old, incoming):
    result = []
    seen = set()
    for row in old + incoming:
        key = (row["id"], row["kind"])
        if key not in seen:
            result.append(row)
            seen.add(key)
    return result


def judge(case_id, result, root, observed, initial):
    if not isinstance(result, dict) or not result.get("success"):
        return (
            False,
            "runtime: "
            + str(result.get("error") if isinstance(result, dict) else result)[
                :1800
            ],
        )
    mutable = {"registry.json"} if case_id == "counter_ledger" else set()
    for name, raw in initial.items():
        if name not in mutable and (
            not (root / name).exists() or (root / name).read_bytes() != raw
        ):
            return False, "입력 파일이 변경됐습니다: " + name
    final = final_value(result)
    original = lambda name: json.loads(initial[name])
    latest = "drafts/report_2026-08-11.md"
    by_date = "drafts/report_2026-08-27.md"

    def expected_lines(name, start=11, width=12):
        return (
            initial[name].decode().splitlines()[start - 1 : start - 1 + width]
        )

    if case_id in ("direct_latest", "counter_latest"):
        ok = content(final) == expected_lines(
            latest if case_id == "direct_latest" else by_date
        )
    elif case_id == "embedded_latest":
        ok = content(
            (root / "outputs/excerpt.txt").read_text()
        ) == expected_lines(latest)
        expected = sorted(
            [
                r
                for r in original("queue.json")
                if r["state"] == "open" and r["priority"] >= 3
            ],
            key=lambda x: x["id"],
        )
        ok = ok and read_rows(root / "outputs/pending.json") == expected
    elif case_id in ("direct_context", "embedded_context"):
        if case_id == "direct_context":
            targets = original("locations.json")
            rows = final.get("items", []) if isinstance(final, dict) else []
        else:
            reviews = original("review_locations.json")
            targets = sorted(
                [
                    r
                    for r in reviews
                    if r["state"] == "open" and r["priority"] >= 3
                ],
                key=lambda r: r["파일"],
            )[:3]
            rows = read_rows(root / "outputs/snippets.json")
        ok = isinstance(rows, list) and len(rows) == len(targets)
        if ok:
            for row, target in zip(rows, targets):
                ok = (
                    ok
                    and isinstance(row, dict)
                    and row.get("파일") == target["파일"]
                    and row.get("줄번호") == target["줄번호"]
                )
                if target["파일"] not in initial:
                    ok = ok and bool(row.get("_error") or row.get("error"))
                else:
                    expected = expected_lines(
                        target["파일"], target["줄번호"], 5
                    )
                    ok = ok and any(
                        content(v) == expected for v in row.values()
                    )
        if case_id == "embedded_context":
            ok = ok and read_rows(root / "outputs/closed.json") == sorted(
                [r for r in reviews if r["state"] == "closed"],
                key=lambda r: r["파일"],
            )
    elif case_id in ("direct_ledger", "embedded_ledger"):
        if case_id == "direct_ledger":
            incoming = original("arrivals.json")
        else:
            submissions = original("submissions.json")
            incoming = [
                {k: r[k] for k in ("id", "kind", "value")}
                for r in submissions
                if r["approved"]
            ]
        ok = read_rows(root / "outputs/archive.json") == accumulated(
            original("existing.json"), incoming
        )
        if case_id == "embedded_ledger":
            ok = ok and read_rows(root / "outputs/rejected.json") == [
                r for r in submissions if not r["approved"]
            ]
    elif case_id == "counter_context":
        expected = []
        for name in sorted(initial):
            if name.startswith("notes/"):
                for n, line in enumerate(
                    initial[name].decode().splitlines(), 1
                ):
                    if "NEEDLE" in line:
                        expected.append((name, n, line))
        rows = final.get("items", []) if isinstance(final, dict) else []
        ok = (
            sorted(
                (r.get("파일"), r.get("줄번호"), r.get("내용")) for r in rows
            )
            == expected
            and "self:read" not in observed["leaf_calls"]
        )
    elif case_id == "counter_ledger":
        expected = original("registry.json")
        by_id = {r["id"]: dict(r) for r in expected["records"]}
        for row in original("updates.json"):
            by_id[row["id"]] = {**by_id.get(row["id"], {}), **row}
        actual = json.loads((root / "registry.json").read_text())
        ok = {k: v for k, v in actual.items() if k != "records"} == {
            k: v for k, v in expected.items() if k != "records"
        } and sorted(actual["records"], key=lambda r: r["id"]) == sorted(
            by_id.values(), key=lambda r: r["id"]
        )
    else:
        raise ValueError(case_id)
    return bool(ok), (
        "품질 기준 통과"
        if ok
        else "요구한 본문·행·보존 조건과 결과가 다릅니다. "
        + BY_ID[case_id]["task"]
    )


GOLD = {
    "direct_latest": '[fn:최신범위읽기]{폴더:"drafts",패턴:"*.md",시작줄:11,줄수:12}',
    "direct_context": '[self:read]{path:"locations.json"} >> [fn:위치마다읽기]{개수:3,줄수:5}',
    "direct_ledger": '$old=[self:read]{path:"existing.json"}\n$new=[self:read]{path:"arrivals.json"}\n[fn:원장에누적]{옛것:$old,새것:$new,키:["id","kind"],원장:"outputs/archive.json"}',
    "embedded_latest": '[fn:최신범위읽기]{폴더:"drafts",패턴:"*.md",시작줄:11,줄수:12} >> [self:write]{path:"outputs/excerpt.txt"}\n[self:read]{path:"queue.json"} >> [table:filter]{where:"state == \'open\' and priority >= 3"} >> [table:sort]{by:"id"} >> [self:write]{path:"outputs/pending.json",format:"json"}',
    "embedded_context": '$r=[self:read]{path:"review_locations.json"}\n$r >> [table:filter]{where:"state == \'open\' and priority >= 3"} >> [table:sort]{by:"파일"} >> [fn:위치마다읽기]{개수:3,줄수:5} >> [self:write]{path:"outputs/snippets.json",format:"json"}\n$r >> [table:filter]{where:"state == \'closed\'"} >> [table:sort]{by:"파일"} >> [self:write]{path:"outputs/closed.json",format:"json"}',
    "embedded_ledger": '$o=[self:read]{path:"existing.json"}\n$s=[self:read]{path:"submissions.json"}\n$n=$s >> [table:filter]{where:{field:"approved",op:"eq",value:true}} >> [table:select]{columns:["id","kind","value"]}\n[fn:원장에누적]{옛것:$o,새것:$n,키:["id","kind"],원장:"outputs/archive.json"}\n$s >> [table:filter]{where:{field:"approved",op:"eq",value:false}} >> [self:write]{path:"outputs/rejected.json",format:"json"}',
    "counter_latest": '[self:file_find]{path:"drafts",pattern:"*.md"} >> [table:sort]{by:"name",desc:true} >> [table:take]{n:1} >> [self:read]{start_line:11,limit:12}',
    "counter_context": '[self:grep]{path:"notes",pattern:"NEEDLE",file_pattern:"*.txt",limit:100}',
    "counter_ledger": '[self:ledger]{op:"upsert",path:"registry.json",target:"records",key:"id",items_file:"updates.json"}',
}

# Independent inline solutions establish that the control condition is executable.
INLINE = dict(GOLD)
LATEST = '[self:file_find]{path:"drafts",pattern:"*.md"} >> [table:filter]{where:{field:"is_dir",op:"eq",value:false}} >> [table:sort]{by:"mtime",desc:true} >> [table:take]{n:1} >> [self:read]{start_line:11,limit:12}'
CONTEXT = '[table:take]{n:3} >> [table:each]{keep:["파일","줄번호"],limit:3,collect:true,on_error:"keep"} {[self:read]{path:$it.파일,start_line:$it.줄번호,limit:5}}'
for key in INLINE:
    INLINE[key] = (
        INLINE[key]
        .replace(
            '[fn:최신범위읽기]{폴더:"drafts",패턴:"*.md",시작줄:11,줄수:12}',
            LATEST,
        )
        .replace("[fn:위치마다읽기]{개수:3,줄수:5}", CONTEXT)
    )
INLINE["direct_ledger"] = INLINE["direct_ledger"].replace(
    '[fn:원장에누적]{옛것:$old,새것:$new,키:["id","kind"],원장:"outputs/archive.json"}',
    '$old & $new >> [table:union] >> [table:dedup]{by:["id","kind"]} >> [self:write]{path:"outputs/archive.json",format:"json"}',
)
INLINE["embedded_ledger"] = INLINE["embedded_ledger"].replace(
    '[fn:원장에누적]{옛것:$o,새것:$n,키:["id","kind"],원장:"outputs/archive.json"}',
    '$o & $n >> [table:union] >> [table:dedup]{by:["id","kind"]} >> [self:write]{path:"outputs/archive.json",format:"json"}',
)

# Preflight found that the current scalar fn result keeps an execution envelope.
# Preserve the task and engine; a legal named solution must explicitly select it.
# This reference is never shown to the generation model.
GOLD["embedded_latest"] = GOLD["embedded_latest"].replace(
    '[fn:최신범위읽기]{폴더:"drafts",패턴:"*.md",시작줄:11,줄수:12} >> [self:write]{path:"outputs/excerpt.txt"}',
    '$part=[fn:최신범위읽기]{폴더:"drafts",패턴:"*.md",시작줄:11,줄수:12}\n[self:write]{path:"outputs/excerpt.txt",content:$part.final_result}',
)
