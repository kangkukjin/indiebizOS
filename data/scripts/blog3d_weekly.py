"""3D 마을 블로그 주간 갱신(사용자 확정 2026-11-08: 매주 일요일 06:00, 새 블로그 글 + 유튜브 영상 목록).
선행: 트리거가 [self:blog]{op:"check_new"} 로 RSS 새 글을 DB 에 먼저 수집한다(이 스크립트는 DB 를 읽기만 한다).
순서: 영상 목록 → 글 내보내기(layout.lock 으로 기존 배치 고정, 새 글만 추가) → 바뀐 게 없으면 종료
      → 글꼴 서브셋 → 빌드 → 조감 지도 굽기(새 집이 없으면 건너뜀, 2026-11-09 P0-7) → 검사(파일 수·크기·기존 배치 불변)
      → 배포 → 실서버 확인 → 3d-blog 저장소 자동 커밋(데이터 파일만, 메시지에 Version ID) → 기록.
실패하면 0 이 아닌 코드로 끝나며 배포 전 실패는 운영 사이트를 건드리지 않는다.
args: {"force": false}  — force=true 면 바뀐 게 없어도 빌드·배포."""
import hashlib, json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "outputs/3d-blog"
ENVF = Path(__file__).resolve().parents[2] / ".env"
SITE = "https://blog3d.kangkukjin.workers.dev"
NODE = "/opt/homebrew/opt/node@24/bin"
PY = sys.executable
args = {}
try:
    raw = sys.stdin.read()
    args = json.loads(raw) if raw.strip() else {}
except Exception:
    args = {}
rec = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": {}}

def env():
    e = dict(os.environ); e["PATH"] = NODE + ":" + e.get("PATH", "")
    if ENVF.exists():
        for line in ENVF.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1); k = k.strip()
                if k in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"): e[k] = v.strip().strip('"').strip("'")
    return e

def run(name, cmd, timeout=900, ok_codes=(0,)):
    t = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env())
    rec["steps"][name] = {"code": p.returncode, "secs": round(time.time() - t, 1), "tail": (p.stdout + p.stderr)[-600:]}
    if p.returncode not in ok_codes: fail(f"{name} 실패(code {p.returncode})")
    return p

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def finish(code=0):
    rec["ended"] = time.strftime("%Y-%m-%d %H:%M:%S")
    d = ROOT / "measure/weekly"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{time.strftime('%Y-%m-%d_%H%M')}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    print(json.dumps({k: rec[k] for k in rec if k != "steps"} | {"failed_step": rec.get("failed_step")}, ensure_ascii=False))
    sys.exit(code)

def fail(msg):
    rec["ok"] = False; rec["error"] = msg; rec["failed_step"] = list(rec["steps"])[-1] if rec["steps"] else None
    finish(1)

videos = ROOT / "src/data/videos.json"
v_before = sha(videos)
run("videos", [PY, "scripts/export_videos.py"], timeout=400, ok_codes=(0, 2))   # 2 = 실패했지만 이전 목록 유지
rec["videos_changed"] = sha(videos) != v_before
lock = ROOT / "layout.lock.json"
lock_before = json.loads(lock.read_text())["posts"] if lock.exists() else {}
p = run("posts", [PY, "scripts/export_posts.py"])
summary = json.loads(p.stdout.strip().splitlines()[-1])
rec["new_posts"] = summary["new"]; rec["total_posts"] = summary["posts"]; rec["houses"] = summary["houses"]
lock_after = json.loads(lock.read_text())["posts"]
moved = [k for k, v in lock_before.items() if lock_after.get(k) != v]
if moved: fail(f"기존 배치가 바뀜 {moved[:5]}")
if not summary["new"] and not rec["videos_changed"] and not args.get("force"):
    rec["ok"] = True; rec["deployed"] = False; rec["note"] = "새 글·영상 변화 없음 — 배포 생략"; finish(0)

run("font", [PY, "scripts/make_font.py"], timeout=300)
run("build", ["npm", "run", "build"], timeout=900)          # NODE_ENV=production 고정(README) — npx astro build 는 셸 NODE_ENV 를 따른다
mp = run("map", [PY, "scripts/bake_map.py"], timeout=400)
try: rec["map"] = json.loads(mp.stdout.strip().splitlines()[-1])
except Exception: rec["map"] = None
files = [f for f in (ROOT / "dist").rglob("*") if f.is_file()]
big = [str(f) for f in files if f.stat().st_size > 25 * 1024 * 1024]
rec["dist_files"] = len(files)
if len(files) > 18000: fail(f"배포 파일 {len(files)}개 — 한도 20,000 에 가까움")
if big: fail(f"25 MiB 초과 파일 {big[:3]}")
dp = run("deploy", ["npx", "wrangler", "deploy", "--message", f"weekly {time.strftime('%Y-%m-%d')}"], timeout=900)
vid = re.search(r"Current Version ID:\s*([0-9a-f-]{36})", dp.stdout + dp.stderr)
rec["version_id"] = vid.group(1) if vid else None

# 실서버 확인: 가장 최근 글 페이지·본문, 뉴스 API
new_ids = sorted(set(lock_after) - set(lock_before))
probe = new_ids[-1] if new_ids else next(iter(lock_after))
checks = {}
time.sleep(5)
for path in [f"/p/{probe}/", f"/b/{probe}.json", "/api/news", "/"]:
    try:
        with urllib.request.urlopen(urllib.request.Request(SITE + path, headers={"User-Agent": "blog3d-weekly"}), timeout=20) as r: checks[path] = r.status
    except Exception as e: checks[path] = str(e)[:80]
rec["live_checks"] = checks
if any(v != 200 for v in checks.values()): fail(f"실서버 확인 실패 {checks}")
rec["ok"] = True; rec["deployed"] = True; rec["new_ids"] = new_ids

# 3d-blog 전용 로컬 저장소에 이번 갱신이 바꾼 데이터 파일만 커밋한다(소스 코드·다른 미커밋 변경은 건드리지 않는다).
# 커밋 실패는 배포 성공을 뒤집지 않고 기록·알림 대상으로만 남긴다(배포는 이미 끝났으므로).
DATA_PATHS = ["layout.lock.json", "video.lock.json", "src/data", "public/d", "public/fonts", "public/map", "public/hall.json"]
def git(*a): return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=60)
try:
    paths = [x for x in DATA_PATHS if (ROOT / x).exists()]
    git("add", "--", *paths)
    staged = git("diff", "--cached", "--name-only").stdout.split()
    if staged:
        msg = f"주간 갱신 {time.strftime('%Y-%m-%d')}: 새 글 {len(new_ids)}편{' · 영상 목록 갱신' if rec.get('videos_changed') else ''}{' · 지도 다시 구움' if (rec.get('map') or {}).get('baked') else ''}\n\nwrangler version {rec.get('version_id')}"
        c = git("commit", "-m", msg, "--", *paths)
        rec["git"] = {"committed": c.returncode == 0, "files": len(staged), "head": git("rev-parse", "--short", "HEAD").stdout.strip(), "err": c.stderr[-300:] if c.returncode else None}
    else:
        rec["git"] = {"committed": False, "files": 0, "note": "바뀐 데이터 파일 없음"}
    rec["git"]["dirty_other"] = [l for l in git("status", "--porcelain").stdout.splitlines() if l][:20]
except Exception as e:
    rec["git"] = {"committed": False, "err": str(e)[:200]}
finish(0)
