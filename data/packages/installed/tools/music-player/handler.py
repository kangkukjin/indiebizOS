"""music-player/handler.py — 내 음악 라이브러리 ([self:music]).

소스 폴더 등록 → 백그라운드 스캔(mutagen 태그) → 라이브러리 질의 + 플레이리스트.
재생은 핸들러가 하지 않는다 — 통화의 stream 필드(/music/stream)를 보는 표면의
<audio>(media_player 프리미티브)가 문다. [limbs:music](유튜브뮤직)과 다른 개념:
그쪽은 유튜브 스트림 재생, 이쪽은 내 파일 라이브러리 (sense:radio/limbs:radio 공존 선례).

로직은 music_core.py — api_music.py(스트리밍·앨범아트)와 sys.modules 공유 키로
같은 인스턴스를 쓴다(bulletin_core 선례).
"""

import sys
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from common.currency import items  # IBL 단일 통화 생성자

_CORE = None


def _core():
    """music_core 를 sys.modules 공유 키로 로드 — api_music 과 같은 인스턴스(락 공유)."""
    global _CORE
    if _CORE is not None:
        return _CORE
    key = "indiebiz_music_core"
    if key in sys.modules:
        _CORE = sys.modules[key]
        return _CORE
    p = Path(__file__).resolve().parent / "music_core.py"
    spec = importlib.util.spec_from_file_location(key, str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[key] = mod
    _CORE = mod
    return mod


_EMPTY_HINT = "라이브러리가 비어 있습니다. 보관함 탭에서 음악 폴더를 등록하고 스캔하세요."


# ── 라이브러리 질의 ──────────────────────────────────────────────────────

def _library(params: dict) -> dict:
    c = _core()
    rows = c.query_tracks(
        q=(params.get("q") or "").strip(),
        path=(params.get("path") or "").strip(),
        folder=(params.get("folder") or "").strip(),
        limit=params.get("limit") or 300,
    )
    if not rows:
        return items([], message=_EMPTY_HINT if not c.load_sources() else "조건에 맞는 곡이 없습니다.")
    return items(rows, count=len(rows))


def _track(params: dict) -> dict:
    """곡 하나 상세 — 재생 + 태그 + '플레이리스트에 담기' 드릴용 (playlists 에 track_path 동봉)."""
    c = _core()
    path = (params.get("path") or "").strip()
    rows = c.query_tracks(path=path, limit=1)
    if not rows:
        return items([], success=False, message="곡을 찾을 수 없습니다 (스캔이 오래됐을 수 있어요).")
    t = rows[0]
    pls = [{"name": p["name"], "meta": f"{len(p.get('tracks', []))}곡",
            "track_path": t["path"],
            "has_track": t["path"] in p.get("tracks", [])}
           for p in c.load_playlists()]
    return items([t], track=t, playlists=pls,
                 playlists_note="" if pls else "플레이리스트가 아직 없습니다. 플레이리스트 탭에서 만드세요.")


# 폴더 하나를 열 때 함께 싣는 재생 목록 상한. 표면이 곡마다 <audio> 를 하나씩 그리므로
# 무제한이면 큰 폴더에서 화면이 죽는다. 넘치면 앞에서부터 이만큼만 재생 대상.
_PLAY_CAP = 500


def _folders(params: dict) -> dict:
    """파인더식 한 단계 탐색 — 바로 아래 폴더 + '이 폴더 전부 재생'용 곡 목록.

    폴더를 하나 열면 (a) 그 안의 하위 폴더(더 들어갈 수 있게)와 (b) 그 폴더 **아래
    전체**(하위 폴더 포함) 곡을 함께 돌려준다. 표면은 (a)로 계속 파고들다가 원하는
    단계에서 (b)를 재생하면 된다 — "폴더 선택을 마치면 그 안 음악을 다 재생".
    """
    c = _core()
    folder = (params.get("folder") or "").strip()
    br = c.browse_folders(folder)
    if not br["items"]:
        return items([], message=_EMPTY_HINT if not c.load_sources() else "하위 폴더가 없습니다.")

    out = items(br["items"], count=len(br["items"]),
                folder=br["folder"], parent=br["parent"], n_tracks=br["n_tracks"])
    if folder:
        # direct — 이 폴더에 **직접** 든 곡. 파인더가 그러듯 폴더와 파일을 같은 화면에 보인다
        # (폴더만 있는 곳엔 안 보이고, 곡이 든 곳엔 그 자리에서 바로 재생).
        direct = c.direct_tracks(br["folder"])
        out["direct"] = direct
        out["direct_note"] = "" if direct else "이 폴더에 직접 든 곡은 없습니다."
        # tracks — 하위 폴더까지 포함한 전체(별도 탭에서 '다 골랐을 때' 재생).
        tracks = c.query_tracks(folder=br["folder"], limit=_PLAY_CAP)
        out["tracks"] = tracks
        out["folder_label"] = c._rel_folder(br["folder"])
        out["play_note"] = (
            f"{br['n_tracks']}곡 중 앞 {len(tracks)}곡" if br["n_tracks"] > len(tracks)
            else f"{len(tracks)}곡"
        ) + " — 하위 폴더 곡까지 이어서 재생합니다."
    return out


# ── 플레이리스트 ─────────────────────────────────────────────────────────

def _playlists(params: dict) -> dict:
    c = _core()
    rows = [{"name": p["name"], "title": p["name"], "n": len(p.get("tracks", [])),
             "meta": f"{len(p.get('tracks', []))}곡", "created_at": p.get("created_at", "")}
            for p in c.load_playlists()]
    if not rows:
        return items([], message="플레이리스트가 없습니다. 이름을 넣어 만들어 보세요.")
    return items(rows, count=len(rows))


def _playlist(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    pl = c.find_playlist(c.load_playlists(), name)
    if pl is None:
        return items([], success=False, message=f"플레이리스트가 없습니다: {name}")
    rows = c.playlist_tracks(pl)
    return items(rows, name=pl["name"], count=len(rows),
                 message="" if rows else "빈 플레이리스트입니다. 전곡 탭에서 곡을 눌러 담으세요.")


def _playlist_create(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    if not name:
        return items([], success=False, message="플레이리스트 이름을 입력해 주세요.")
    pls = c.load_playlists()
    if c.find_playlist(pls, name):
        return items([], success=False, message=f"같은 이름의 플레이리스트가 이미 있습니다: {name}")
    from datetime import datetime
    pls.append({"name": name, "created_at": datetime.now().isoformat(timespec="seconds"), "tracks": []})
    c.save_playlists(pls)
    return items([{"name": name, "title": name, "n": 0, "meta": "0곡"}],
                 success=True, message=f"플레이리스트 '{name}' 생성. 전곡 탭에서 곡을 눌러 담으세요.")


def _playlist_delete(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    pls = c.load_playlists()
    kept = [p for p in pls if p["name"] != name]
    if len(kept) == len(pls):
        return items([], success=False, message=f"플레이리스트가 없습니다: {name}")
    c.save_playlists(kept)
    return items([], success=True, message=f"플레이리스트 '{name}' 삭제.")


def _playlist_add(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    path = c.norm_path(params.get("path") or "")
    pls = c.load_playlists()
    pl = c.find_playlist(pls, name)
    if pl is None:
        return items([], success=False, message=f"플레이리스트가 없습니다: {name}")
    if not c.query_tracks(path=path, limit=1):
        return items([], success=False, message="라이브러리에 없는 곡입니다.")
    if path in pl.setdefault("tracks", []):
        return items([], success=False, message=f"이미 '{name}'에 있는 곡입니다.")
    pl["tracks"].append(path)
    c.save_playlists(pls)
    return items([], success=True, message=f"'{name}'에 담았습니다 ({len(pl['tracks'])}곡).")


def _playlist_remove(params: dict) -> dict:
    c = _core()
    name = (params.get("name") or "").strip()
    path = c.norm_path(params.get("path") or "")
    pls = c.load_playlists()
    pl = c.find_playlist(pls, name)
    if pl is None:
        return items([], success=False, message=f"플레이리스트가 없습니다: {name}")
    if path not in pl.get("tracks", []):
        return items([], success=False, message="이 플레이리스트에 없는 곡입니다.")
    pl["tracks"] = [p for p in pl["tracks"] if p != path]
    c.save_playlists(pls)
    return items([], success=True, message=f"'{name}'에서 뺐습니다 ({len(pl['tracks'])}곡).")


def _stop(params: dict) -> dict:
    """재생 중지 — 소리를 내는 건 서버가 아니라 표면의 <audio> 라, 표면에 '멈춰라'를 돌려준다.

    라디오의 client 모드와 같은 규약(`stop_in_client`): 서버가 스피커를 잡고 있으면 서버가
    끄고(mpv), 표면이 물고 있으면 표면이 끈다. 음악 파일은 늘 후자다.
    한 폴더가 수백 곡이면 재생 중인 <audio> 를 눈으로 찾아 누르는 게 사실상 불가능하므로
    계기 상단에 라디오와 같은 자리의 '■ 정지' 버튼이 이 op 를 부른다.
    """
    return items([], success=True, stop_in_client=True, message="재생을 멈췄습니다.")


# ── 소스 폴더 · 스캔 ─────────────────────────────────────────────────────

def _sources(params: dict) -> dict:
    """보관함 탭 한 화면 — 소스 목록 + 라이브러리 통계 + 스캔 상태."""
    c = _core()
    st = c.stats()
    rows = [{"path": s["path"], "title": s["path"], "n": st["per_source"].get(s["path"], 0),
             "meta": f"{st['per_source'].get(s['path'], 0)}곡", "added_at": s.get("added_at", "")}
            for s in c.load_sources()]
    return items(rows, stats=st, scan={"label": c.scan_label(), **c.scan_state()},
                 message="" if rows else "등록된 음악 폴더가 없습니다. 폴더를 등록하면 스캔이 시작됩니다.")


def _add_source(params: dict) -> dict:
    c = _core()
    r = c.add_source(params.get("path") or "")
    if not r["ok"]:
        return items([], success=False, message=r["error"])
    c.start_scan([r["path"]])  # 등록 즉시 그 폴더만 백그라운드 스캔
    return items([], success=True,
                 message=f"폴더 등록 — 스캔을 시작했습니다: {r['path']} (보관함 탭에서 진행 상태 확인)")


def _remove_source(params: dict) -> dict:
    c = _core()
    r = c.remove_source(params.get("path") or "")
    if not r["ok"]:
        return items([], success=False, message=r["error"])
    return items([], success=True, message=f"폴더 제거 — 라이브러리에서 {r['removed']}곡을 내렸습니다.")


def _scan(params: dict) -> dict:
    c = _core()
    r = c.start_scan()
    if not r["ok"]:
        return items([], success=False, message=r["error"], scan=r.get("scan", {}))
    return items([], success=True, queued=True,
                 message=f"전체 스캔을 시작했습니다 ({len(r['roots'])}개 폴더, 백그라운드). 보관함 탭에서 진행 상태를 확인하세요.")


# ── 디스패치 (--check 가 AST 로 키 정확 비교) ────────────────────────────

_OP_DISPATCHERS = {
    "music_library_op": {
        "library": _library,
        "track": _track,
        "folders": _folders,
        "playlists": _playlists,
        "playlist": _playlist,
        "playlist_create": _playlist_create,
        "playlist_delete": _playlist_delete,
        "playlist_add": _playlist_add,
        "playlist_remove": _playlist_remove,
        "sources": _sources,
        "add_source": _add_source,
        "remove_source": _remove_source,
        "scan": _scan,
        "stop": _stop,
    }
}
_OP_DEFAULTS = {"music_library_op": "library"}


def execute(tool_input: dict, context):
    tool_name = context.tool_name
    try:
        if tool_name in _OP_DISPATCHERS:
            op = tool_input.get("op") or _OP_DEFAULTS.get(tool_name)
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if fn is None:
                return items([], success=False,
                             message=f"알 수 없는 op: {op} (가능: {', '.join(_OP_DISPATCHERS[tool_name])})")
            return fn(tool_input)
        return items([], success=False, message=f"알 수 없는 도구: {tool_name}")
    except Exception as e:
        return items([], success=False, message=f"music-player 오류: {e}")
