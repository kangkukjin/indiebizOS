"""repair_verdict_distill.py — 수리 판정 증류 (커밋 메시지 → 포식 기억 다리).

'새로운 도약' 1번(자기 수정의 완성)의 배선: 자기수정의 *판정*(무엇이 문제였고,
무엇이 오진이었으며, 진범이 무엇이고, 어디를 고쳤나)은 커밋 메시지에 훌륭하게
남는데(사람이 읽는 자리), AI 가 회상하는 자리(포식 기억 code 지도)에는 닿지
않았다 — 같은 부류 문제를 다시 만난 세션이 처음부터 재진단하는 낭비가 실측됨.
이 모듈이 그 다리다.

정착점이 REPAIR 훅이 아니라 *커밋*인 이유: 인프로세스 REPAIR 경로는 라이브
실사용이 드물고, 실제 수리 대부분은 아웃오브프로세스 세션(Claude Code)이 한다 —
그 손은 프로세스 밖이라 훅으로는 원리적으로 못 잡는다. 커밋은 두 경로가 합류하는
유일한 원장이다(원장은 git — check_red_drift 와 같은 원칙).

설계(forage_consolidation 과 동형):
- 기계 단계(새 커밋 열거·단서 게이트·상태 전진)는 git+forage_meta 로 무LLM
- 판정 추출만 경량 AI(role=background) — 커밋당 1회, 수리 단서 없는 커밋은
  LLM 호출 없이 스킵
- run_maintenance_bundle 합류, 상태=forage_meta("repair_verdict_last_commit")
  (커밋 하나 처리할 때마다 전진 — 중단돼도 다음 사이클이 이어받는다)
- ★locus 는 레포 *상대경로*(절대경로 금지) — 판정은 파일 내용이 아니라 *사건에
  대한 지식*이라 mtime 부패 모델이 안 맞는다(절대경로면 이후 편집마다 stale
  노이즈). 상대경로는 freshness 면제(_stale_of)이면서 query 필터엔 그대로 걸린다.
- ★★locus 에 판정 슬러그를 붙인다("경로#슬러그") — forage_map 의 upsert 키
  (body,locus,kind)는 공간 지식(폴더당 정체 하나) 설계라, 한 파일에 같은 kind
  판정이 여럿이면 서로를 *조용히 덮어쓴다*(실측: base.py substrate 판정 4건이
  마지막 것만 남음). 슬러그가 키를 판정 단위로 가른다. 표현이 갈린 근접중복은
  forage_consolidation 의 의미 병합이 청소한다(그게 그 기관의 일).
- 상한 초과분은 남긴 개수를 정직하게 보고(조용한 깎기 금지 — silent-clamp 규약).
"""
import json
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

# 한 사이클 LLM 처리 커밋 상한(비용 가드). 초과분은 remaining 으로 신고하고 다음 사이클.
MAX_COMMITS_PER_RUN = 10
# 첫 가동(상태 없음) 백필 창 — 최근 판정들이 즉시 회상 가능해지도록.
BACKFILL_COMMITS = 15
# LLM 에 넘기는 커밋 메시지 길이 상한
MAX_MSG_CHARS = 4000
# 커밋당 지도 항목 상한 — 이 레포 커밋은 수리 여러 절(■)을 한 커밋에 싣는 관습이라
# 4 로는 밀도 높은 커밋(예: 수리 5절)에서 핵심 판정이 밀려난다(실측). 포식 증류의
# map 상한(6)과 정합.
MAX_ITEMS_PER_COMMIT = 6

_META_KEY = "repair_verdict_last_commit"

# 싼 게이트: 수리 판정 냄새가 나는 커밋만 LLM 으로. (기능 신설 커밋 오포함은
# LLM 단계가 빈 배열로 거른다 — 이 게이트의 일은 명백한 비수리를 공짜로 버리는 것.)
_REPAIR_CUES = (
    "수리", "진범", "오진", "봉합", "함정", "드리프트", "버그", "거짓",
    "레이스", "교착", "고아", "오발", "브릭", "사고", "침묵", "오염",
    "fix", "bug", "regression",
)


def _repo_root() -> Optional[str]:
    """backend 의 부모 = 레포 루트. .git 없으면(폰 몸 등) None."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return root if os.path.isdir(os.path.join(root, ".git")) else None


def _git(root: str, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", root, *args],
                           capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _pending_commits(root: str, last: Optional[str]) -> List[str]:
    """마지막 처리 커밋 이후의 새 커밋들(오래된 것부터). 상태가 없거나 낡았으면
    (리베이스 등으로 해시 실종) 최근 BACKFILL_COMMITS 창으로 폴백."""
    if last:
        out = _git(root, "rev-list", "--reverse", "--no-merges", f"{last}..HEAD")
        if out is not None:
            return [h for h in out.split() if h]
    out = _git(root, "rev-list", "--reverse", "--no-merges",
               "-n", str(BACKFILL_COMMITS), "HEAD")
    return [h for h in (out or "").split() if h]


def _commit_detail(root: str, h: str) -> Tuple[str, List[str]]:
    """커밋 메시지 전문 + 만진 파일 목록(레포 상대경로)."""
    msg = _git(root, "log", "-1", "--format=%B", h) or ""
    files_out = _git(root, "show", "--name-only", "--format=", h) or ""
    files = [f for f in files_out.split("\n") if f.strip()][:30]
    return msg.strip(), files


def _has_repair_cue(msg: str) -> bool:
    low = msg.lower()
    return any(c in low for c in _REPAIR_CUES)


def _known_map_text(body: str) -> str:
    import forage_memory as FM
    lines = []
    for m in FM.recall(body=body, limit=30).get("map", []):
        lines.append(f'- [{m["kind"]}] {m["locus"]}: {m["claim"]}')
    return "\n".join(lines) if lines else "(아직 없음)"


def _distill_commit(body: str, repo_name: str, h: str, msg: str,
                    files: List[str], known_text: str) -> Optional[int]:
    """커밋 하나의 수리 판정을 경량 AI 로 추출해 forage_map 에 적재.

    반환: 적재 건수. ★None = LLM 판정 불가(키 부재·응답 못 읽음) — '판정 없음'(0)과
    구별해야 호출측이 상태를 전진시키지 않는다(판정 불가를 소비로 치면 조용한 유실)."""
    from consciousness_agent import oneshot_ai_call
    from runtime_utils import parse_first_json
    import forage_memory as FM

    title = msg.split("\n", 1)[0][:80]
    files_text = "\n".join(f"- {f}" for f in files) if files else "(없음)"
    prompt = f"""아래는 코드레포 '{repo_name}' 의 커밋 메시지다. 이 커밋이 *수리*(버그·오진·
드리프트·함정의 판정과 교정)를 담고 있다면, 미래의 진단을 싸게 만들 **일반화 가능한
판정 지식**만 추출하라. 다음 세션이 같은 부류의 증상을 만났을 때 재진단 없이 직행하게
하는 것이 목적이다.

kind 는 이렇게 고른다:
- substrate: 결함 부류 — "X 하면 Y 가 깨진다"는 기질 취약성(예 "compaction 이 도구
  호출-결과 쌍을 인덱스로 가르면 고아 tool 메시지가 남아 400 이 난다").
- dead_branch: 오진 기록 — "Z 는 원인이 아니었다"(prune_reason 에 진범을 적어라).
- convention: 수리에서 얻은 관습 — "이 부류를 고칠 땐 선언과 호출 양쪽을 다 확인할 것".
- identity: 모듈·파일의 정체가 새로 판명된 경우만(드물다).

규칙:
- locus 는 커밋이 만진 파일의 레포 상대경로(아래 목록에서 골라라). 특정 파일에 못
  붙는 교훈이면 "__repair__" 를 써라. 절대경로 금지.
- slug: 판정마다 짧은 식별 슬러그(한글·영문 2~4단어, 하이픈 연결 — 예
  "고아-tool-400", "프루닝-압축-굶김"). 같은 판정을 다시 보면 같은 슬러그가
  나오도록 내용을 요약하는 이름으로.
- 이미 아는 것과 같으면 내지 마라(새롭거나 교정된 판정만).
- 새 기능 소개·변경 나열은 판정이 아니다 — 수리 판정이 없으면 빈 배열을 내라.
- 시스템 철학·자기 서술 금지. 결함 부류와 진범과 고친 자리의 *사실*만.
- claim 은 한 문장: 무엇이 문제였고 진범이 무엇이며 어떻게 고쳤나. 커밋 해시는
  넣지 마라(출처는 따로 기록된다).
- 최대 {MAX_ITEMS_PER_COMMIT}건. 그보다 많으면 가장 재발 가능성 높은 부류만 골라라.
- 커밋이 여러 절(■ 등)로 나뉘어 있으면 절마다 *별개의 수리*일 수 있다 — 한 절에
  몰리지 말고 절들을 고루 훑어라.
- JSON 으로만 응답.

이미 아는 지도(이 레포):
{known_text[:1500]}

커밋이 만진 파일:
{files_text}

커밋 메시지:
{msg[:MAX_MSG_CHARS]}

응답 형식(빈 배열 허용):
{{"map":[{{"locus":"backend/…(상대경로)|__repair__","slug":"판정-슬러그","kind":"substrate|dead_branch|convention|identity",
 "claim":"...","prior_class":"structural|semantic","prune_reason":"(dead_branch면 진범)"}}]}}"""

    resp = oneshot_ai_call(
        prompt=prompt,
        system_prompt="수리 판정 증류기. 커밋에서 일반화 가능한 결함 부류·오진·수리 관습만 JSON으로. 판정 없으면 빈 배열.",
        role="background")
    if not resp:
        return None  # LLM 불가 — 판정 없음이 아니다
    data = parse_first_json(resp)
    if not isinstance(data, dict):
        return None  # 응답을 못 읽음 — 위와 동류

    noted = 0
    prov = {"query": f"commit {h[:10]} {title}"}
    for m in (data.get("map") or [])[:MAX_ITEMS_PER_COMMIT]:
        locus, kind, claim = m.get("locus"), m.get("kind"), m.get("claim")
        if not locus or not kind or not claim:
            continue
        # 절대경로로 왔으면 상대로 강등(레포 밖 경로는 __repair__ 로) — mtime 부패 면제 유지.
        if str(locus).startswith(("/", "~")):
            locus = "__repair__"
        # ★키 분리: 경로#슬러그 — 같은 파일·같은 kind 의 서로 다른 판정이 upsert 키에서
        # 충돌해 덮어쓰지 않게. 슬러그 없으면 claim 해시로(결정론 폴백).
        slug = str(m.get("slug") or "").strip().replace(" ", "-")[:48]
        if not slug:
            import hashlib
            slug = hashlib.sha1(str(claim).encode("utf-8")).hexdigest()[:8]
        locus = f"{locus}#{slug}"
        r = FM.note_map(
            body=body, locus=str(locus), kind=str(kind), claim=str(claim),
            prior_class=m.get("prior_class") or "structural",
            confidence=0.7, provenance=dict(prov),
            prune_reason=m.get("prune_reason"), generalizes=True)
        if r.get("success"):
            noted += 1
            print(f"[수리판정] {r['action']} map[{kind}] {locus}: \"{str(claim)[:60]}\"")
    return noted


def run_repair_verdict_distill(limit: int = MAX_COMMITS_PER_RUN) -> Dict[str, Any]:
    """수리 판정 증류 한 사이클 — 새 커밋 열거 → 단서 게이트 → 판정 추출 → 상태 전진.

    run_maintenance_bundle 합류. 새 커밋이 없으면 git 스캔 한 번으로 끝(무LLM·무비용).
    """
    import forage_memory as FM

    root = _repo_root()
    if not root:
        return {"skipped": "no_git"}
    repo_name = os.path.basename(root)
    body = f"code:{repo_name}"

    last = FM.get_meta(_META_KEY)
    pending = _pending_commits(root, last)
    if not pending:
        return {"scanned": 0, "distilled": 0, "noted": 0, "remaining": 0}

    stats = {"scanned": 0, "skipped_no_cue": 0, "distilled": 0, "noted": 0,
             "remaining": 0, "llm_unavailable": False}
    known_text = _known_map_text(body)
    halted_at = None
    for h in pending[:limit]:
        msg, files = _commit_detail(root, h)
        stats["scanned"] += 1
        advance = True
        try:
            if msg and _has_repair_cue(msg):
                n = _distill_commit(body, repo_name, h, msg, files, known_text)
                if n is None:
                    # ★판정 불가(LLM 키 부재·응답 불가독) ≠ 판정 없음 — 상태를 전진시키면
                    # 이 커밋의 판정이 조용히 유실된다. 사이클 중단, 다음 사이클이 재시도.
                    stats["llm_unavailable"] = True
                    advance = False
                    halted_at = h
                else:
                    stats["distilled"] += 1
                    stats["noted"] += n
            else:
                stats["skipped_no_cue"] += 1
        except Exception as e:
            # 커밋 고유의 예외(추출 오류 등)는 전진 — 한 커밋이 사이클을 영구 볼모로 잡지 않게.
            print(f"[수리판정] 커밋 {h[:10]} 증류 실패 (건너뜀): {e}")
        if not advance:
            break
        FM.set_meta(_META_KEY, h)

    if halted_at:
        print(f"[수리판정] LLM 판정 불가 — 커밋 {halted_at[:10]} 에서 중단, 다음 사이클에 재시도")
    stats["remaining"] = max(0, len(pending) - stats["scanned"] + (1 if halted_at else 0))
    if stats["remaining"]:
        print(f"[수리판정] 상한 {limit} 도달 — 남은 커밋 {stats['remaining']}건은 다음 사이클에")
    if stats["noted"]:
        print(f"[수리판정] 커밋 {stats['distilled']}건에서 판정 {stats['noted']}건 적재")
    return stats


if __name__ == "__main__":
    import sys
    lim = MAX_COMMITS_PER_RUN
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            lim = int(a.split("=", 1)[1])
    print(json.dumps(run_repair_verdict_distill(limit=lim), ensure_ascii=False, indent=2))
