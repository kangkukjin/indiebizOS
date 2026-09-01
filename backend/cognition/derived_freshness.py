"""derived_freshness.py — 파생물 신선도 순찰 (2026-09-01, ep2519 사슬).

world_pulse_health 에서 분가했다(1500줄 규칙). 자리는 여기가 옳기도 하다 —
이건 "건강을 재서 보고하는" 점검이 아니라 **집행**이다: 드리프트를 발견하면
재생성으로 닫고 초록을 낸다(파생물은 기계 소유물이라 사람 판단을 기다리지 않는다).
소스 자체가 깨져 재생성이 실패할 때만 빨강.

두 자리에서 부른다: 부팅(api.py — 백엔드가 죽어 있던 사이의 편집분)과
일일 건강점검(world_pulse_health.run_daily_health_check).
"""
import logging
import sys
import time as _time
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


def enforce_derived_freshness() -> Dict:
    """파생물(ibl_nodes.yaml·tool.json·문서 마커) 신선도 — 세서 보고하지 않고 **집행**한다.

    ★왜 (2026-09-01, ep2519 사슬 수리): 쓰기 초크포인트(vocab_write_gate)는 IBL 쓰기
    경로만 문다 — 아웃오브프로세스 편집자(Claude Code 세션·[self:script]·run_command·
    패키지 핸들러 자신의 open())는 그 문을 안 지난다(check_red_drift 가 적어둔 넷).
    이 순찰이 그 잔여를 덮는다: 부팅(백엔드가 죽어 있던 사이의 편집분) + 일일점검.
    드리프트 = 재생성으로 닫고 초록(파생물은 기계 소유물), 소스 결함 = 빨강."""
    import os as _os
    import subprocess as _sp
    root = Path(__file__).parent.parent.parent
    build = root / "scripts" / "build_ibl_nodes.py"
    t0 = _time.time()
    ev = {"node": "__static__", "action": "derived_freshness", "success": True,
          "response_ms": 0, "data_quality": "ok", "error_message": None}
    if not build.exists():
        return ev
    try:
        env = dict(_os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        chk = _sp.run([sys.executable, str(build), "--check"], cwd=str(root),
                      capture_output=True, text=True, timeout=300, env=env)
        if chk.returncode != 0:
            bld = _sp.run([sys.executable, str(build)], cwd=str(root),
                          capture_output=True, text=True, timeout=300, env=env)
            if bld.returncode != 0:
                ev.update(success=False, data_quality="error",
                          error_message=("파생물이 낡았는데 재생성도 실패 — 소스 결함: "
                                         + ((bld.stdout or "") + (bld.stderr or ""))
                                         .strip()[-400:]))
            else:
                logger.warning("[HealthCheck] 파생물 드리프트 발견 → 재생성으로 닫음(기계 소유물)")
        ev["response_ms"] = int((_time.time() - t0) * 1000)
    except Exception as e:
        ev.update(success=False, data_quality="error",
                  error_message=f"파생물 신선도 순찰 실패: {e}")
    return ev
