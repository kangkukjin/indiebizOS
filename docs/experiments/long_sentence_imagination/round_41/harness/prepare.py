"""41회차 합성 실험 자료·변형·독립 oracle. IBL 과제 계산은 하지 않는다(oracle 은 대조용, AI 입력 사본에서 제외).

사용: prepare.py generate — source/ 생성, trainer/·agent/ 사본: base, v1(정정: B 참가자 7명 세션 파일 재전송), v2(B×T3 결손 → n=6), v3(값 품질: 음수·"NA"·중복 id)
      prepare.py oracle   — oracle/expected.json (base·v1·v2·v3)
사전등록(design.json) 규칙과 oracle 수식은 같다:
  제외: duration_s <= 0 또는 > 600, errors 가 수가 아님, 같은 파일 안 중복 trial_id 는 첫 것만(중복 수 보고)
  분석 단위: 참가자×과제별 유효 trial 평균. 조건 = 인터페이스(A/B)×과제(T1~T3). 조건당 n<8 이면 검정 불가
  CI: 평균 ± t(.05, n-1)·sd/√n (표본 sd). Welch t, df 내림, 임계값 = t_critical.json 의 p0125 (Bonferroni 4)
  Cohen's d = (mB-mA)/pooled sd. 판정: |t|>임계 and 방향 일치 → 지지 / 유의하지만 반대 → 불지지(반대 방향) / 비유의 → 불지지(차이 없음 입증 아님) / n<8 → 검정 불가
  설문: Q3·Q6 역문항(6-x), 참가자 만족도 = 7문항 평균, 응답 없는 참가자 제외. H4 = 만족도 B>A
"""
import csv
import hashlib
import json
import math
import random
import shutil
import sys
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_41회차'
TASKS = ["T1", "T2", "T3"]
MEANS = {("A", "T1"): 60, ("B", "T1"): 50, ("A", "T2"): 90, ("B", "T2"): 100, ("A", "T3"): 120, ("B", "T3"): 121}
SD = 12
HYP = [{"id": "H1", "measure": "duration", "task": "T1", "direction": "B<A", "text": "과제 T1 완료시간은 B 가 A 보다 짧다"},
       {"id": "H2", "measure": "duration", "task": "T2", "direction": "B<A", "text": "과제 T2 완료시간은 B 가 A 보다 짧다"},
       {"id": "H3", "measure": "duration", "task": "T3", "direction": "B<A", "text": "과제 T3 완료시간은 B 가 A 보다 짧다"},
       {"id": "H4", "measure": "satisfaction", "task": None, "direction": "B>A", "text": "만족도는 B 가 A 보다 높다"}]


# ---------- t 분위수(표 생성용, scipy 없이) ----------
def betacf(a, b, x):
    MAXIT, EPS, FPMIN = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > FPMIN else FPMIN); h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2)); d = 1 + aa * d; d = 1 / (d if abs(d) > FPMIN else FPMIN); c = 1 + aa / c; c = c if abs(c) > FPMIN else FPMIN; h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2)); d = 1 + aa * d; d = 1 / (d if abs(d) > FPMIN else FPMIN); c = 1 + aa / c; c = c if abs(c) > FPMIN else FPMIN
        de = d * c; h *= de
        if abs(de - 1) < EPS:
            break
    return h


def betai(a, b, x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    return bt * betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1 - bt * betacf(b, a, 1 - x) / b


def t_two_sided_p(t, df):
    x = df / (df + t * t)
    return betai(df / 2, 0.5, x)


def t_crit(df, p):
    lo, hi = 0.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_two_sided_p(mid, df) > p: lo = mid
        else: hi = mid
    return round((lo + hi) / 2, 4)


# ---------- 생성 ----------
def generate():
    rng = random.Random(41)
    if OUT.exists():
        shutil.rmtree(OUT)
    src = OUT / 'source'; (src / 'trials').mkdir(parents=True); (OUT / 'oracle').mkdir()
    design = {"title": "인터페이스 A/B 사용자 실험", "alpha": 0.05, "correction": {"method": "Bonferroni", "tests": 4, "alpha_adjusted": 0.0125},
              "unit_of_analysis": "참가자×과제별 유효 trial 평균", "min_n_per_condition": 8,
              "exclusion": {"duration_min_exclusive": 0, "duration_max_inclusive": 600, "errors_must_be_numeric": True, "duplicate_trial_id": "첫 trial 만 유효, 나머지 제외·보고"},
              "ci": "평균 ± t(0.05, n-1) × sd/√n, 표본 표준편차", "test": "Welch t, 자유도 Welch–Satterthwaite 내림, 양측 임계값 t_critical.json p0125",
              "effect_size": "Cohen's d, pooled sd", "survey": {"items": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"], "reverse": ["Q3", "Q6"], "scale": [1, 5]},
              "hypotheses": HYP}
    (src / 'design.json').write_text(json.dumps(design, ensure_ascii=False, indent=1))
    parts = []
    for i in range(1, 61):
        pid = f"P{i:02d}"; grp = "A" if i <= 30 else "B"
        parts.append({"id": pid, "group": grp, "age_band": rng.choice(["20대", "30대", "40대", "50대"]), "experience": "" if i in (9, 44) else rng.choice(["초급", "중급", "고급"])})
    with open(src / 'participants.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=["id", "group", "age_band", "experience"]); w.writeheader(); w.writerows(parts)
    for p in parts:
        rows = []; k = 0
        for t in TASKS:
            for rep in range(4):
                k += 1
                if p["id"] == "P23" and t == "T3" and rep == 3:
                    continue  # trial 11개
                d = round(rng.gauss(MEANS[(p["group"], t)], SD), 1)
                rows.append({"trial_id": f"{p['id']}-{k:02d}", "task_type": t, "rep": rep + 1, "duration_s": max(5.0, d), "errors": max(0, int(rng.gauss(1.5, 1.2))), "completed": True})
        if p["id"] == "P05": rows[2]["duration_s"] = 0
        if p["id"] == "P12": rows[7]["duration_s"] = 650.0
        if p["id"] == "P31": rows[4]["errors"] = "NA"
        if p["id"] == "P48": rows[10]["errors"] = "NA"
        (src / 'trials' / f"{p['id']}.json").write_text(json.dumps({"participant": p["id"], "group": p["group"], "trials": rows}, ensure_ascii=False, indent=1))
    with open(src / 'survey.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(["participant"] + design["survey"]["items"])
        for p in parts:
            if p["id"] == "P17": continue
            base = 3.4 if p["group"] == "A" else 4.0
            vals = []
            for q in design["survey"]["items"]:
                v = round(rng.gauss(base, 0.6)); v = min(5, max(1, v))
                if q in design["survey"]["reverse"]: v = 6 - v
                vals.append(v)
            w.writerow([p["id"]] + vals)
    (src / 't_critical.json').write_text(json.dumps({"two_sided": True, "columns": ["df", "p05", "p0125"], "rows": [[df, t_crit(df, 0.05), t_crit(df, 0.0125)] for df in range(1, 121)]}, indent=0))
    # ---- 사본·변형 ----
    for who in ("trainer", "agent"):
        shutil.copytree(src, OUT / who / 'base')
        v1 = OUT / who / 'v1'; shutil.copytree(src, v1)
        for pid in ("P33", "P35", "P37", "P39", "P41", "P43", "P45"):   # 정정: T1 완료시간 +15
            fp = v1 / 'trials' / f"{pid}.json"; d = json.loads(fp.read_text())
            for r in d["trials"]:
                if r["task_type"] == "T1": r["duration_s"] = round(r["duration_s"] + 15, 1)
            d["revision"] = "2026-10-09 재전송"; fp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        v2 = OUT / who / 'v2'; shutil.copytree(src, v2)
        for i in range(31, 55):   # B 24명의 T3 trial 결손 → B×T3 n=6
            fp = v2 / 'trials' / f"P{i:02d}.json"; d = json.loads(fp.read_text()); d["trials"] = [r for r in d["trials"] if r["task_type"] != "T3"]; fp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        v3 = OUT / who / 'v3'; shutil.copytree(src, v3)
        fp = v3 / 'trials' / 'P50.json'; d = json.loads(fp.read_text())
        d["trials"][1]["duration_s"] = -12.5; d["trials"][3]["errors"] = "NA"; d["trials"].append(dict(d["trials"][5]))  # 중복 trial_id
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        for o in ('out', 'out1', 'out2', 'out3'):
            (OUT / who / o).mkdir(parents=True, exist_ok=True)
    print("generated participants 60, trial files 60")


# ---------- oracle ----------
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(folder):
    design = json.loads((folder / 'design.json').read_text())
    parts = list(csv.DictReader(open(folder / 'participants.csv', encoding='utf-8')))
    tcrit = {r[0]: {"p05": r[1], "p0125": r[2]} for r in json.loads((folder / 't_critical.json').read_text())["rows"]}
    trials = {p.name: json.loads(p.read_text()) for p in sorted((folder / 'trials').glob('*.json'))}
    survey = list(csv.DictReader(open(folder / 'survey.csv', encoding='utf-8')))
    return design, parts, tcrit, trials, survey


def analyze(folder):
    design, parts, tcrit, trials, survey = load(folder)
    grp = {p["id"]: p["group"] for p in parts}
    excluded, dup_count, valid = [], 0, {}   # valid[(pid, task)] = [durations]
    per_participant_valid = {}
    for fname, d in trials.items():
        seen = set()
        for r in d["trials"]:
            reason = None
            if r["trial_id"] in seen:
                reason = "duplicate_trial_id"; dup_count += 1
            seen.add(r["trial_id"])
            dur = r["duration_s"]
            if reason is None and (not isinstance(dur, (int, float)) or dur <= 0 or dur > 600): reason = "duration_out_of_range"
            if reason is None and not isinstance(r["errors"], (int, float)): reason = "errors_non_numeric"
            if reason:
                excluded.append({"file": fname, "trial_id": r["trial_id"], "reason": reason}); continue
            valid.setdefault((d["participant"], r["task_type"]), []).append(dur)
            per_participant_valid[d["participant"]] = per_participant_valid.get(d["participant"], 0) + 1
    cond = {}
    for g in ("A", "B"):
        for t in TASKS:
            xs = [mean(v) for (pid, tt), v in valid.items() if tt == t and grp[pid] == g]
            n = len(xs); m = mean(xs) if xs else None; s = stdev(xs) if n > 1 else None
            half = tcrit[n - 1]["p05"] * s / math.sqrt(n) if n > 1 else None
            cond[f"{g}-{t}"] = {"group": g, "task": t, "n": n, "mean": round(m, 3) if m is not None else None, "sd": round(s, 3) if s is not None else None,
                                "ci_low": round(m - half, 3) if half is not None else None, "ci_high": round(m + half, 3) if half is not None else None, "values": xs}
    # 설문
    sat = {}
    for row in survey:
        vals = []
        for q in design["survey"]["items"]:
            v = float(row[q]); vals.append(6 - v if q in design["survey"]["reverse"] else v)
        sat[row["participant"]] = mean(vals)
    sat_g = {g: [v for pid, v in sat.items() if grp[pid] == g] for g in ("A", "B")}
    def welch(xa, xb):
        na, nb = len(xa), len(xb)
        if na < 8 or nb < 8: return None
        ma, mb, sa, sb = mean(xa), mean(xb), stdev(xa), stdev(xb)
        se2 = sa * sa / na + sb * sb / nb; t = (mb - ma) / math.sqrt(se2)
        df = math.floor(se2 * se2 / ((sa * sa / na) ** 2 / (na - 1) + (sb * sb / nb) ** 2 / (nb - 1)))
        pooled = math.sqrt(((na - 1) * sa * sa + (nb - 1) * sb * sb) / (na + nb - 2)); d = (mb - ma) / pooled
        crit = tcrit[min(df, 120)]["p0125"]
        return {"n_a": na, "n_b": nb, "mean_a": round(ma, 3), "mean_b": round(mb, 3), "t": round(t, 4), "df": df, "t_crit_0125": crit, "significant": abs(t) > crit, "cohen_d": round(d, 4)}
    hyps = []
    for h in HYP:
        if h["measure"] == "duration":
            xa, xb = cond[f"A-{h['task']}"]["values"], cond[f"B-{h['task']}"]["values"]
        else:
            xa, xb = sat_g["A"], sat_g["B"]
        w = welch(xa, xb)
        if w is None: verdict = "검정 불가"
        else:
            diff_dir = "B<A" if w["mean_b"] < w["mean_a"] else "B>A"
            verdict = ("지지" if diff_dir == h["direction"] else "불지지(반대 방향 유의)") if w["significant"] else "불지지(비유의 — 차이 없음 입증 아님)"
        hyps.append({"id": h["id"], "direction": h["direction"], "verdict": verdict, **(w or {})})
    sat_stats = {g: {"n": len(v), "mean": round(mean(v), 3), "sd": round(stdev(v), 3)} for g, v in sat_g.items()}
    low_n = [k for k, c in cond.items() if c["n"] < design["min_n_per_condition"]]
    return {"quality": {"excluded": excluded, "excluded_count": len(excluded), "duplicate_count": dup_count, "participants_valid_trials": per_participant_valid,
                        "low_n_conditions": low_n, "survey_missing": sorted(set(grp) - set(sat))},
            "conditions": {k: {kk: vv for kk, vv in c.items() if kk != "values"} for k, c in cond.items()},
            "satisfaction": sat_stats, "hypotheses": hyps,
            "input_sha256": {str(p.relative_to(folder)): sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}}


def oracle():
    result = {v: analyze(OUT / 'trainer' / v) for v in ("base", "v1", "v2", "v3")}
    (OUT / 'oracle' / 'expected.json').write_text(json.dumps(result, ensure_ascii=False, indent=1))
    b = result["base"]
    print(json.dumps({"excluded": b["quality"]["excluded_count"], "low_n": b["quality"]["low_n_conditions"], "survey_missing": b["quality"]["survey_missing"],
                      "conditions": {k: (c["n"], c["mean"], c["ci_low"], c["ci_high"]) for k, c in b["conditions"].items()},
                      "sat": b["satisfaction"], "hyps": [(h["id"], h["verdict"], h.get("t"), h.get("df"), h.get("cohen_d")) for h in b["hypotheses"]],
                      "v1_hyps": [(h["id"], h["verdict"], h.get("t")) for h in result["v1"]["hypotheses"]], "v1_B-T1": result["v1"]["conditions"]["B-T1"]["mean"],
                      "v2_lowN": result["v2"]["quality"]["low_n_conditions"], "v2_H3": result["v2"]["hypotheses"][2]["verdict"],
                      "v3_excluded": result["v3"]["quality"]["excluded_count"], "v3_dup": result["v3"]["quality"]["duplicate_count"]}, ensure_ascii=False))


if __name__ == '__main__':
    {"generate": generate, "oracle": oracle}[sys.argv[1]]()
