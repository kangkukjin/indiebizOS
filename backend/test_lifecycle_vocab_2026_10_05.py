"""⑩ 몸의 명사 생애주기 어휘(2026-10-05): 런처 항목(self:project/folder/trash)·스위치·에이전트·채팅방·창고·채널·미디어·즐겨찾기.

docs/APP_COMMON_FOUNDATION_GAPS_2026_10_05.md §1-⑩. 구현은 조종실 HTTP 라우트와 **같은 서비스 함수**(한 벌)이고, 라우터는 이름만 안다
(조립 루트가 능력 주입). 쓰기 op 는 사전의 requires(owner·파괴적이면 human_confirm)가 관문에서 집행한다.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import yaml

import principal as P
import thread_context as tc


@pytest.fixture
def world(tmp_path, monkeypatch):
    """임시 기본 경로 — projects.json·switches.json·multi_chat.db·공유창고 전부 tmp 아래."""
    import os
    real = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    (tmp_path / "templates" / "기본").mkdir(parents=True)
    (tmp_path / "templates" / "기본" / "agents.yaml").write_text(yaml.safe_dump({"agents": [], "common": {}}), encoding="utf-8")
    (tmp_path / "data").mkdir(exist_ok=True)
    # 어휘 원장·파생물은 기본 경로에서 읽는다 — 저장소만 격리하고 사전은 실물을 복사(패키지 폴더는 링크, 읽기만)
    for name in ("ibl_nodes.yaml", "core_manifest.json", "member_manifest.json", "phone_manifest.json", "ibl_fixtures.json", "package_meta.json",
                 "vocabulary_policy.yaml", "lifecycle_policy.yaml", "shell_shadow.json"):
        if (real / "data" / name).exists():
            shutil.copy(real / "data" / name, tmp_path / "data" / name)
    os.symlink(real / "data" / "packages", tmp_path / "data" / "packages")
    (tmp_path / "data" / "vocabulary").mkdir()
    if (real / "data" / "vocabulary" / "activation.json").exists():
        shutil.copy(real / "data" / "vocabulary" / "activation.json", tmp_path / "data" / "vocabulary" / "activation.json")
    from ibl_routing import register_system_capabilities
    import launcher_ops, chat_room_ops, warehouse_ops, warehouse_admin, channel_settings_ops, media_ops
    from multi_chat_manager import MultiChatManager
    chat_room_ops.set_manager(MultiChatManager(base_path=tmp_path))
    register_system_capabilities({"project_op": launcher_ops.project_op, "folder_op": launcher_ops.folder_op,
                                  "trash_op": launcher_ops.trash_op, "switch_manage_op": launcher_ops.switch_manage_op,
                                  "chat_room_op": chat_room_ops.chat_room_op, "warehouse_op": warehouse_ops.warehouse_op,
                                  "my_warehouse_op": warehouse_admin.my_warehouse_op, "channel_op": channel_settings_ops.channel_op,
                                  "media_op": media_ops.media_op})
    import routing_system
    routing_system.register_all()
    tok = P.set_transport(P.OWNER)
    prev = tc.snapshot(); tc.clear_all_context()
    yield SimpleNamespace(tmp=tmp_path)
    tc.restore(prev); P.reset_transport(tok)


def _run(code, pp, inputs=None, approval=None):
    from ibl_v2_entry import handle_request
    import approval_tokens as T
    from thread_context import set_approval
    digest = T.request_digest(code, inputs or {}, sorted(inputs or []))
    set_approval(approval, digest)
    try:
        return handle_request({"code": code, "edition": 2, "inputs": inputs or {}, "declared_inputs": sorted(inputs or [])}, pp, None)
    finally:
        set_approval(None, None)


def _approve(r):
    import approval_tokens as T
    ask = (r.get("diagnostic") or {}).get("details", {}).get("approval_required")
    assert ask, r
    return T.issue(ask["challenge"])["token"]


# ── 런처 항목: 프로젝트·폴더·휴지통 ─────────────────────────────────────────

def test_project_folder_trash_lifecycle_and_requires(world):
    import launcher_ops as L
    pp = str(world.tmp)
    r = L.project_op({"op": "create", "name": "연구"})
    assert r["success"] and r["project"]["id"] == "연구" and (world.tmp / "projects" / "연구").is_dir()
    assert any(p["id"] == "연구" for p in L.project_op({"op": "list"})["items"])
    assert L.project_op({"op": "templates"})["count"] >= 1
    f = L.folder_op({"op": "create", "name": "묶음"})
    assert f["success"]
    fid = f["folder"]["id"]
    assert L.project_op({"op": "move", "project_id": "연구", "folder_id": fid})["success"]
    assert [i["id"] for i in L.folder_op({"op": "items", "folder_id": fid})["items"]] == ["연구"]
    assert L.project_op({"op": "rename", "project_id": "연구", "new_name": "연구2"})["success"]
    assert L.project_op({"op": "trash", "project_id": "연구2"})["success"]
    trash = L.trash_op({"op": "list"})["items"]
    assert any(i["id"] == "연구2" and i["item_type"] == "project" for i in trash)
    assert L.trash_op({"op": "restore", "item_id": "연구2", "item_type": "project"})["success"]
    assert any(p["id"] == "연구2" for p in L.project_op({"op": "list"})["items"])
    # 관문: 영구 삭제는 사람 승인 — 토큰 없이는 approval_required, 승인 뒤 삭제
    r = _run('[self:project]{op: "delete", project_id: "연구2"}', pp)
    assert r["success"] is False
    token = _approve(r)
    r = _run('[self:project]{op: "delete", project_id: "연구2"}', pp, approval=token)
    assert r["success"] is True and r["value"]["permanent"] is True, r.get("error")
    assert not any(p["id"] == "연구2" for p in L.project_op({"op": "list"})["items"])
    # 회원 주체는 list 조차 거절(주인 자원)
    with P.narrow(P.member("m1", 4, "d")):
        r = _run('[self:project]{op: "list"}', pp)
        assert r["success"] is False
    # 휴지통 비우기도 사람 승인
    r = _run('[self:trash]{op: "empty"}', pp)
    assert r["success"] is False and _approve(r)


# ── 스위치 ───────────────────────────────────────────────────────────────────

def test_switch_lifecycle_and_run_receipt(world, monkeypatch):
    import launcher_ops as L
    pp = str(world.tmp)
    L.project_op({"op": "create", "name": "P1"})
    (world.tmp / "projects" / "P1" / "agents.yaml").write_text(yaml.safe_dump({
        "agents": [{"id": "agent_a", "name": "비서", "role": "돕는다", "allowed_nodes": ["sense"]}],
        "common": {"common_prompt": "공통"}}), encoding="utf-8")
    r = L.switch_manage_op({"op": "create", "name": "아침", "command": "뉴스 요약", "project_id": "P1", "agent_name": "비서"})
    assert r["success"], r
    sw = r["switch"]
    assert sw["config"]["agent_role"] == "돕는다" and sw["config"]["allowed_nodes"] == ["sense"] and sw["config"]["common_prompt"] == "공통"
    sid = sw["id"]
    assert L.switch_manage_op({"op": "info", "switch_id": sid})["switch"]["name"] == "아침"
    assert L.switch_manage_op({"op": "rename", "switch_id": sid, "new_name": "아침2"})["switch"]["name"] == "아침2"
    assert L.switch_manage_op({"op": "update", "switch_id": sid, "icon": "☀️"})["switch"]["icon"] == "☀️"
    copy = L.switch_manage_op({"op": "copy", "switch_id": sid})["switch"]
    assert copy["id"] != sid
    assert L.switch_manage_op({"op": "trash", "switch_id": copy["id"]})["success"]
    assert any(i["id"] == copy["id"] and i["item_type"] == "switch" for i in L.trash_op({"op": "list"})["items"])
    assert L.trash_op({"op": "restore", "item_id": copy["id"], "item_type": "switch"})["success"]
    assert L.switch_manage_op({"op": "bogus", "switch_id": sid})["success"] is False
    # run → 접수증(③) — 러너 대역
    class FakeRunner:
        def __init__(self, switch):
            self.switch = switch
        def run_async(self, callback=None):
            callback({"success": True, "response": "끝"})
    monkeypatch.setitem(sys.modules, "switch_runner", SimpleNamespace(SwitchRunner=FakeRunner))
    r = _run(f'[self:switch]{{op: "run", switch_id: "{sid}"}}', pp)
    assert r["success"] is True, r.get("error")
    rc = r["value"]
    assert rc["accepted"] and rc["task_ref"]["kind"] == "switch_run"
    import task_receipts as T
    v = T.status(rc["task_ref"])
    assert v["state"] == "succeeded" and v["result"]["response"] == "끝"
    # delete 는 사람 승인
    r = _run(f'[self:switch]{{op: "delete", switch_id: "{sid}"}}', pp)
    assert r["success"] is False and _approve(r)


# ── 에이전트 생애주기 ────────────────────────────────────────────────────────

def test_agents_lifecycle_ops(world, monkeypatch):
    import launcher_ops as L
    import agent_lifecycle as AL
    pp = str(world.tmp)
    L.project_op({"op": "create", "name": "P2"})
    r = AL.agents_op("create", {"project_id": "P2", "name": "조사원", "role": "조사한다", "allowed_nodes": ["sense"]})
    assert r["success"], r
    aid = r["agent"]["id"]
    data = yaml.safe_load((world.tmp / "projects" / "P2" / "agents.yaml").read_text())
    assert data["agents"][0]["ibl_only"] is True and (world.tmp / "projects" / "P2" / "agent_조사원_role.txt").read_text() == "조사한다"
    assert AL.agents_op("role", {"agent_id": f"P2/{aid}"})["role"] == "조사한다"
    assert AL.agents_op("note", {"agent_id": f"P2/{aid}", "text": "메모"})["note"] == "메모"
    assert AL.agents_op("update", {"project_id": "P2", "agent_id": aid, "name": "조사원2"})["agent"]["name"] == "조사원2"
    assert not (world.tmp / "projects" / "P2" / "agent_조사원_role.txt").exists()
    started = []
    class FakeAgentRunner:
        def __init__(self, cfg, common):
            self.config, self.running = cfg, False
        def start(self):
            self.running = True; started.append(self.config["name"])
        def stop(self):
            self.running = False
    monkeypatch.setitem(sys.modules, "agent_runner", SimpleNamespace(AgentRunner=FakeAgentRunner))
    import agent_registry
    monkeypatch.setattr(agent_registry, "agent_runners", {})
    assert AL.agents_op("start", {"project_id": "P2", "agent_id": aid})["status"] == "started" and started == ["조사원2"]
    assert AL.agents_op("start", {"project_id": "P2", "agent_id": aid})["status"] == "already_running"
    assert AL.agents_op("stop", {"project_id": "P2", "agent_id": aid})["status"] == "stopped"
    assert AL.agents_op("delete", {"project_id": "P2", "agent_id": "nope"})["success"] is False
    # 관문을 지나는 호출 — 회원은 create 거절, delete 는 사람 승인
    with P.narrow(P.member("m1", 4, "d")):
        r = _run('[others:agents]{op: "create", project_id: "P2", name: "x"}', pp)
        assert r["success"] is False
    r = _run(f'[others:agents]{{op: "delete", project_id: "P2", agent_id: "{aid}"}}', pp)
    assert r["success"] is False
    r = _run(f'[others:agents]{{op: "delete", project_id: "P2", agent_id: "{aid}"}}', pp, approval=_approve(r))
    assert r["success"] is True and r["value"]["deleted"] == aid


# ── 채팅방 ───────────────────────────────────────────────────────────────────

def test_chat_room_ops(world, monkeypatch):
    import launcher_ops as L
    import chat_room_ops as C
    L.project_op({"op": "create", "name": "P3"})
    (world.tmp / "projects" / "P3" / "agents.yaml").write_text(yaml.safe_dump({
        "agents": [{"id": "agent_b", "name": "토론자", "role": "토론"}], "common": {}}), encoding="utf-8")
    r = C.chat_room_op({"op": "create", "name": "회의"})
    assert r["success"]
    rid = r["room"]["id"]
    assert any(x["id"] == rid for x in C.chat_room_op({"op": "list"})["items"])
    assert C.chat_room_op({"op": "add", "room_id": rid, "agent_id": "P3/agent_b"})["success"]
    assert [p["agent_name"] for p in C.chat_room_op({"op": "participants", "room_id": rid})["items"]] == ["토론자"]
    monkeypatch.setattr(C.get_manager(), "send_message", lambda **kw: [{"agent_name": "토론자", "response": "네"}])
    say = C.chat_room_op({"op": "say", "room_id": rid, "message": "@토론자 안녕"})
    assert say["success"] and say["items"][0]["response"] == "네"
    assert C.chat_room_op({"op": "remove", "room_id": rid, "agent_name": "토론자"})["success"]
    assert C.chat_room_op({"op": "trash", "room_id": rid})["success"]
    assert any(i["id"] == rid and i["item_type"] == "chat_room" for i in L.trash_op({"op": "list"})["items"])
    assert L.trash_op({"op": "restore", "item_id": rid, "item_type": "chat_room"})["success"]
    assert C.chat_room_op({"op": "delete", "room_id": rid})["success"]
    assert C.chat_room_op({"op": "info", "room_id": rid})["success"] is False


# ── 내 창고·이웃 창고 ─────────────────────────────────────────────────────────

def test_my_warehouse_admin_ops(world):
    import warehouse_admin as W
    src = world.tmp / "사진.txt"; src.write_text("x")
    assert W.my_warehouse_op({"op": "mkdir", "level": 1, "name": "앨범"})["created"] == "앨범"
    r = W.my_warehouse_op({"op": "add", "level": 1, "paths": [str(src)], "dest": "앨범"})
    assert r["added"] == ["사진.txt"]
    assert [f["name"] for f in W.my_warehouse_op({"op": "list", "level": 1})["items"]] == ["앨범/사진.txt"]
    assert W.my_warehouse_op({"op": "move", "level": 1, "name": "앨범/사진.txt", "dest": "", "new_name": "그림.txt"})["moved"] == "그림.txt"
    assert W.my_warehouse_op({"op": "move", "level": 1, "name": "그림.txt", "dest_level": 2})["level"] == 2
    assert W.my_warehouse_op({"op": "remove", "level": 2, "name": "그림.txt"})["success"]
    t = W.my_warehouse_op({"op": "trash"})
    assert t["count"] == 1 and t["items"][0]["level"] == 2
    assert W.my_warehouse_op({"op": "restore", "level": 2, "name": "그림.txt"})["restored"] == "그림.txt"
    assert W.my_warehouse_op({"op": "remove", "level": 2, "name": "그림.txt"})["success"]
    assert W.my_warehouse_op({"op": "purge", "all": True})["removed"] == 1
    assert W.my_warehouse_op({"op": "remove", "level": 2, "name": "../../etc"})["success"] is False
    assert W.my_warehouse_op({"op": "restore", "level": 9, "name": "x"})["success"] is False


def test_neighbor_warehouse_ops(world, monkeypatch):
    import warehouse_ops as WO
    contacts = [{"id": 1, "url": "https://a.test/", "info_level": 2, "favorite": True},
                {"id": 2, "url": "https://b.test", "info_level": 0, "favorite": False}]
    monkeypatch.setattr(WO, "_bm", lambda: SimpleNamespace(get_warehouse_contacts=lambda: contacts,
                                                           update_neighbor_warehouse=lambda nid, **kw: None,
                                                           delete_contact=lambda cid: None))
    monkeypatch.setattr(WO.wf, "get_scores_map", lambda: {"https://a.test": 3})
    assert WO.allowed_urls(0, False, 0) is None
    assert WO.allowed_urls(1, False, 0) == ["https://a.test"]
    assert WO.allowed_urls(0, False, 2) == ["https://a.test"]
    assert WO.source_warehouse("https://a.test/f?x=1", "") == "https://a.test"
    monkeypatch.setattr(WO.wf, "fetch_manifest", lambda url: (_ for _ in ()).throw(RuntimeError("offline")))
    r = WO.warehouse_op({"op": "retweet", "url": "https://a.test/f?p=사진.jpg", "name": "사진.jpg", "level": 1})
    assert r["success"] and r["file"] == "리트윗/사진.jpg.url" and r["hops"] == 1 and r["warehouse"] == "https://a.test"
    import warehouse_paths as WP
    assert (WP.warehouse_dir(1) / "리트윗" / "사진.jpg.url").read_text().startswith("[InternetShortcut]")
    assert json.loads((WP.warehouse_dir(1) / "리트윗" / ".사진.jpg.url.rt.json").read_text())["mode"] == "link"
    assert WO.warehouse_op({"op": "retweet", "url": "ftp://x"})["success"] is False
    assert WO.warehouse_op({"op": "score"})["success"] is False
    forgotten = []
    monkeypatch.setattr(WO.wf, "forget_warehouse", lambda base: forgotten.append(base))
    assert WO.warehouse_op({"op": "forget", "url": "https://a.test/"})["contacts_removed"] == 1 and forgotten == ["https://a.test"]


# ── 채널 설정 ────────────────────────────────────────────────────────────────

def test_channel_settings_ops(world, monkeypatch):
    import channel_settings_ops as CS
    store = {"gmail": {"channel_type": "gmail", "enabled": 0, "polling_interval": 60, "config": json.dumps({"client_secret": "s", "email": "e"})}}
    def update(ct, enabled=None, config=None, polling_interval=None):
        row = store[ct]
        if enabled is not None: row["enabled"] = int(enabled)
        if polling_interval is not None: row["polling_interval"] = polling_interval
        if config is not None: row["config"] = config
        return row
    monkeypatch.setattr(CS, "_bm", lambda: SimpleNamespace(get_all_channel_settings=lambda: list(store.values()),
                                                           get_channel_setting=lambda ct: store.get(ct), update_channel_setting=update))
    refreshed = []
    poller = SimpleNamespace(running=True, threads={"nostr": 1}, refresh_channel=lambda ct: refreshed.append(ct),
                             poll_now=lambda ct: {"status": "success", "channel": ct})
    monkeypatch.setitem(sys.modules, "channel_poller", SimpleNamespace(get_channel_poller=lambda log_callback=None: poller))
    lst = CS.channel_op({"op": "list"})
    assert lst["items"][0]["config"]["client_secret"] == "***" and lst["items"][0]["config"]["email"] == "e"
    assert CS.channel_op({"op": "status"})["active_channels"] == ["nostr"]
    r = CS.channel_op({"op": "set", "channel_type": "gmail", "enabled": True, "polling_interval": 30})
    assert r["success"] and store["gmail"]["enabled"] == 1 and store["gmail"]["polling_interval"] == 30 and refreshed == ["gmail"]
    assert CS.channel_op({"op": "set", "channel_type": "gmail", "polling_interval": 1})["success"] is False
    assert CS.channel_op({"op": "poll", "channel_type": "gmail"})["status"] == "success"
    assert CS.channel_op({"op": "detail", "channel_type": "zzz"})["success"] is False
    # 관문: set 은 사람 승인
    r = _run('[others:channel]{op: "set", channel_type: "gmail", enabled: false}', str(world.tmp))
    assert r["success"] is False and _approve(r)


# ── 미디어 ───────────────────────────────────────────────────────────────────

def test_media_probe_and_subtitles(world, tmp_path):
    import media_ops as M
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg 없음")
    video = tmp_path / "clip.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "quiet", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5", "-t", "1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True, timeout=60)
    (tmp_path / "clip.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n안녕\n", encoding="utf-8")
    r = M.media_op({"op": "probe", "path": str(video)})
    assert r["success"] and r["video_codec"] == "h264" and r["container"] == "mp4" and r["needs_transcode"] is False
    s = M.media_op({"op": "subtitles", "path": str(video)})
    assert s["success"] and any(x.get("path", "").endswith("clip.srt") or "clip.srt" in json.dumps(x, ensure_ascii=False) for x in s["items"])
    v = M.media_op({"op": "subtitle", "path": str(tmp_path / "clip.srt")})
    assert v["success"] and v["vtt"].startswith("WEBVTT") and "안녕" in v["vtt"]
    assert M.media_op({"op": "probe", "path": str(tmp_path / "없음.mp4")})["success"] is False
    assert M.media_op({"op": "subtitle", "path": str(video), "track": 0})["success"] is False   # 내장 자막 없음
    rc = M.media_op({"op": "transcode", "path": str(video), "dst": str(tmp_path / "out.mp4")})
    assert rc["accepted"] and rc["task_ref"]["kind"] == "media_transcode"
    import task_receipts as T
    out = T.wait(rc["task_ref"], timeout=60, poll=0.2)
    assert out["state"] in ("succeeded", "failed"), out
    if out["state"] == "succeeded":
        assert Path(out["result"]["path"]).exists()


# ── 즐겨찾기(limbs:launch) 별칭과 op ─────────────────────────────────────────

def test_launch_sites_alias_and_ops(world, monkeypatch):
    pp = str(world.tmp)
    r = _run('[limbs:launch]{action: "list"}', pp)      # 옛 키 action → op 별칭
    assert r["success"] is True, r.get("error")
    assert "items" in r["value"]
    r = _run('[limbs:launch]{op: "list"}', pp)
    assert r["success"] is True
    with P.narrow(P.member("m1", 4, "d")):
        r = _run('[limbs:launch]{op: "add", name: "x", url: "https://x.test"}', pp)
        assert r["success"] is False                      # 회원은 등록 못 함(requires owner)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
