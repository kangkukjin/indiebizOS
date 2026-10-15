"""원격 기기 쪽 처리 부품(표준 라이브러리만). 입력 12행을 2배로, 이름 원문 보존, 기기 신원 포함.
사용: python3 process.py <입력 sample.json> <출력 result.json> <device_id>
설치·판정·보고 로직 없음. 어느 기기에서든 같은 바이트로 실행된다."""
import json, sys, socket, platform, datetime, io

src, dst, device_id = sys.argv[1], sys.argv[2], sys.argv[3]
with io.open(src, "r", encoding="utf-8", newline="") as f:
    data = json.load(f)
rows = [{"id": r["id"], "result": r["value"] * 2, "name": r["name"]} for r in data["rows"]]
out = {
    "identity": {
        "device_id": device_id,
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processed_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    },
    "sum": sum(r["result"] for r in rows),
    "count": len(rows),
    "rows": rows,
}
with io.open(dst, "w", encoding="utf-8", newline="") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("OK", out["sum"], out["count"])
