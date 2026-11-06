"""Editor draft synchronization and managed toolchain; analysis itself uses workspace."""
import subprocess
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_coding import owner
from code_analysis_drivers import TOOLCHAIN, inventory
from workspace_sessions import Workspace

router = APIRouter(prefix='/coding/analysis', tags=['coding'], dependencies=[Depends(owner)])
_INSTALL = Lock()


class DraftRequest(BaseModel):
    client: str
    view: str | None = None
    path: str | None = None
    text: str | None = None
    expected: int | None = None
    action: str = 'update'


@router.post('/{resource}/draft')
def draft(resource: str, body: DraftRequest):
    app = Workspace().code()
    try:
        return app.analysis.draft(app.project(resource), **body.model_dump())
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/servers')
def servers():
    return {'items': inventory(), 'managed': True}


@router.post('/servers/install')
def install():
    import shutil
    npm = shutil.which('npm')
    if not npm:
        raise HTTPException(409, 'Node.js 20 이상과 npm이 필요합니다')
    with _INSTALL:
        from code_analysis import shutdown
        try:
            shutdown(require_idle=True)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        result = subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund', '--prefix', str(TOOLCHAIN)],
                                capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise HTTPException(409, result.stderr[-4000:])
    return {'items': inventory(), 'installed': True}
