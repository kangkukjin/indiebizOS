"""Isolated finite thread reproduces the service inheriting a request lease."""
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'backend'))
import boot_paths  # noqa: E402
import runtime_work as rw  # noqa: E402
import media_sessions as ms  # noqa: E402
reg=rw.install('round70-probe');reg.gate('ACTIVE');rw.install_worker_tracking()
stop=threading.Event();original=threading.Thread
ms.threading=SimpleNamespace(Thread=lambda **kw: original(target=lambda:stop.wait(3),name=kw['name'],daemon=True))
ms._sweeper=None;os.environ.pop('INDIEBIZ_MEDIA_NO_SWEEPER',None)
try:
    with rw.scope('synthetic-media-request'):ms._ensure_sweeper()
    snap=reg.snapshot()
    result={'phase':snap['phase'],'active_roots':snap['active_roots'],
            'active_children':snap['active_children'],'labels':[x['label'] for x in snap['owners']]}
finally:
    stop.set();ms._sweeper.join(3)
p=Path(__file__).resolve().parents[1]/'evidence'/f'sweeper-{sys.argv[1]}.json'
p.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result))
