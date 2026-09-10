#!/usr/bin/env python3
"""원고 점검→노트→음성→접합→덱 영상→측정. inspect 후 같은 manifest_hash로 run한다.
args: lecture_id, lecture_dir(프로젝트 덱), source, references[], voice, mode(inspect|run),
manifest_hash, bookends, narration{gpu,speed,chunk,...}, render{captions,...}, normalize{...}.
긴 실행은 self:script background:true로 호출한다. 단계 진척은 stderr PROGRESS로 흘린다.
"""
from filelock import FileLock, Timeout
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "data/packages/installed/tools/lecture_workspace"))
import lecture_store  # noqa: E402
import deck_video  # noqa: E402
from verification_cache import file_hash  # noqa: E402


def module(name):
    spec = importlib.util.spec_from_file_location("recipe_" + name, ROOT / "data/scripts" / (name + ".py"))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def signature(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def progress(phase, **values):
    print("PROGRESS " + json.dumps({"phase": phase, **values}, ensure_ascii=False), file=sys.stderr, flush=True)


def script(name, args):
    result, cleanup_failed = None, False
    with subprocess.Popen([sys.executable, str(ROOT / "data/scripts" / (name + ".py"))],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, cwd=ROOT) as process:
        process.stdin.write(json.dumps(args, ensure_ascii=False))
        process.stdin.close()
        for line in process.stdout:
            print(line.rstrip(), file=sys.stderr, flush=True)
            if "PROGRESS " in line:
                try:
                    cleanup_failed |= json.loads(line.split("PROGRESS ", 1)[1]).get("cleanup") == "failed"
                except ValueError:
                    pass
            try:
                value = json.loads(line)
                if isinstance(value, dict) and any(k in value for k in ("items", "error", "success")):
                    result = value
            except ValueError:
                pass
        if process.wait() or cleanup_failed or not result or result.get("error") or result.get("failed") or result.get("success") is False:
            raise RuntimeError(f"{name} 실패/부분 완료/자원 정리 실패: {result}")
    return result


def preflight(args):
    lecture_id = args["lecture_id"]
    if Path(lecture_id).name != lecture_id or lecture_id in {".", ".."}:
        raise ValueError("lecture_id가 잘못됐습니다")
    directory = Path(args.get("lecture_dir") or lecture_store.lecture_dir(lecture_id)).resolve()
    if directory.name != lecture_id:
        raise ValueError("lecture_dir의 폴더 이름은 lecture_id와 같아야 합니다")
    deck = json.loads((directory / "deck.json").read_text())
    if (directory / "narration_live/timeline.json").exists():
        raise ValueError("실강 녹음 덱입니다. 복제 음성 제작 절차 대신 기존 녹음 덱 영상 경로를 사용하세요")
    if deck.get("lecture_id") != lecture_id:
        raise ValueError("lecture_dir와 lecture_id가 다릅니다")
    source = Path(args.get("source") or deck.get("narration_source", {}).get("path", "")).resolve()
    if not source.is_file():
        raise ValueError("정본 원고 source가 필요합니다")
    prepare = module("나레이션원고추출")
    prepared = prepare.prepare({**args, "lecture_dir": str(directory), "source": str(source), "inspect": True})
    narration = module("나레이션생성")
    voice = args.get("voice") or narration.default_voice()
    voice_file, voice_text = narration.load_voice(voice)
    bookends = Path(args.get("bookends") or ROOT / "outputs/narration/bookends3").resolve()
    assets = [directory / deck["slides"][sid]["png_file"] for sid in deck["slide_order"]]
    references = [Path(p).resolve() for p in args.get("references", [])]
    recipe_path = ROOT / "data/recipes/narrated_video_v1.json"
    recipe = json.loads(recipe_path.read_text())
    tool_paths = [ROOT / "data/scripts" / (name + ".py") for name in
                  ("나레이션원고추출", "나레이션생성", "인사말붙이기", "영상음량정렬", "영상제작파이프라인")]
    files = [source, Path(voice_file), bookends / "intro.wav", bookends / "outro.wav", recipe_path,
             Path(deck_video.__file__), *tool_paths, *assets, *references]
    manifest = {"recipe": recipe, "lecture_id": lecture_id, "order": deck["slide_order"],
                "voice": voice, "voice_text": voice_text, "voice_file": str(Path(voice_file)), "source": str(source),
                "files": {str(p): file_hash(p) for p in files},
                "narration": args.get("narration", {}), "render": args.get("render", {}),
                "normalize": args.get("normalize"), "bookends": str(bookends)}
    return directory, manifest, prepared


def execute(args):
    directory, manifest, prepared = preflight(args)
    key = signature(manifest)
    checkpoint = {"kind": "source_and_narration", "hash": key, "source": manifest["source"],
                  "references": args.get("references", []), "voice": manifest["voice"],
                  "count": prepared["count"], "estimated_seconds": prepared["estimated_seconds"],
                  "pending_checks": ["원문의 핵심·대안 보존", "원고의 왜곡·인칭·분량", "선택한 목소리·시각 품질"]}
    if args.get("mode", "inspect") == "inspect":
        return {"success": True, "manifest_hash": key, "preflight": prepared,
                "supervision_checkpoint": checkpoint, "message": "검토 후 같은 인자와 manifest_hash로 mode=run. 모델 호출·제작 없음."}
    if args.get("mode") != "run" or args.get("manifest_hash") != key:
        raise ValueError("입력·제작법이 바뀌었거나 manifest_hash가 없습니다. inspect를 다시 확인하세요")
    work = directory / "video_pipeline"
    work.mkdir(exist_ok=True)
    lock = FileLock(str(work / "lock"), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        raise ValueError("이 덱의 제작 파이프라인이 이미 실행 중입니다. 기존 작업 로그를 보세요")
    try:
        state_path = work / "state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        def stage(name, inputs, run):
            # 긴 외부 작업 사이에도 승인한 원천 입력이 바뀌지 않았는지 확인한다.
            if signature(preflight(args)[1]) != key:
                raise ValueError("제작 중 원천 입력이 바뀌었습니다. 완료 단계는 보존하고 재점검하세요")
            stage_key = signature(inputs)
            old = state.get(name, {})
            if old.get("key") == stage_key and old.get("outputs") and all(Path(p).exists() and file_hash(p) == h for p, h in old["outputs"].items()):
                progress(name, reused=True)
                return old["result"]
            progress(name, reused=False)
            result, paths = run()
            state[name] = {"key": stage_key, "result": result, "outputs": {str(p): file_hash(p) for p in paths}}
            atomic(state_path, state)
            return result

        prepared = module("나레이션원고추출").prepare({**args, "lecture_dir": str(directory),
                  "source": manifest["source"], "apply_notes": True, "inspect": False})
        texts = json.loads(Path(prepared["path"]).read_text())
        raw = directory / "narration_raw"
        raw.mkdir(exist_ok=True)
        # 장별 지문으로 변경된 원고만 굽는다. 과거 음성의 존재만으로 재사용하지 않는다.
        voice_settings = {"voice": manifest["voice"], "reference": manifest["voice_text"],
                          "files": {p: h for p, h in manifest["files"].items()
                                    if p == manifest["voice_file"] or p.endswith("나레이션생성.py")},
                          **manifest["narration"]}
        changed = []
        for sid, text in texts.items():
            expected = signature({"text": text, "voice": voice_settings})
            old = state.get("audio:" + sid, {})
            target = raw / (sid + ".wav")
            if old.get("key") != expected or not target.exists() or old.get("hash") != file_hash(target):
                changed.append(sid)
        if changed:
            progress("narration", total=len(changed), completed=0)
            with tempfile.TemporaryDirectory(dir=work) as tmp:
                script("나레이션생성", {**manifest["narration"], "texts": {sid: texts[sid] for sid in changed},
                       "voice": manifest["voice"], "out_dir": tmp, "force": True})
                for sid in changed:
                    generated = Path(tmp) / (sid + ".wav")
                    if not generated.is_file():
                        raise ValueError(f"음성 미회수: {sid}")
                for sid in changed:
                    target = raw / (sid + ".wav")
                    os.replace(Path(tmp) / (sid + ".wav"), target)
                    state["audio:" + sid] = {"key": signature({"text": texts[sid], "voice": voice_settings}), "hash": file_hash(target)}
                atomic(state_path, state)
        audio = directory / "narration"
        stage("bookends", {"raw": {sid: file_hash(raw / (sid + ".wav")) for sid in texts}, "manifest": key},
              lambda: (script("인사말붙이기", {"lecture_id": args["lecture_id"], "lecture_dir": str(directory),
                       "raw_dir": str(raw), "out_dir": str(audio), "bookends": manifest["bookends"]}),
                       [audio / (sid + ".wav") for sid in texts]))
        # deck_video는 원래 제작 엔진을 그대로 사용한다. 렌더러·음성을 바꾸지 않는다.
        lecture_store.set_roots(directory.parent, [directory.parent])
        def render():
            result = deck_video.build(args["lecture_id"], {"captions": True, **manifest["render"]},
                                      on_progress=lambda *a, **kw: progress("render", detail=str(a)[:300]))
            if result.get("skipped") or result.get("missing_notes"):
                raise ValueError("렌더에서 슬라이드 또는 노트가 누락됐습니다")
            return result, [Path(result["output"])]
        rendered = stage("render", {"manifest": key, "audio": {sid: file_hash(audio / (sid + ".wav")) for sid in texts}}, render)
        output = Path(rendered["output"])
        if manifest["normalize"] is not None:
            options = manifest["normalize"]
            result = stage("normalize", {"src": file_hash(output), "options": options},
                lambda: (module("영상음량정렬").align({**options, "src": str(output), "dst": str(output.with_name(output.stem + "_aligned.mp4"))}),
                         [output.with_name(output.stem + "_aligned.mp4")]))
            output = Path(result["items"][0]["path"])
        measured = module("영상음량정렬").measure(output)
        result = {"success": True, "items": [{"path": str(output), **measured}], "manifest_hash": key,
                  "coverage": "길이·음량·파일 정합성. 의미·발음·자연스러움은 실제 청취와 내용 검수가 필요함",
                  "source_hash": manifest["files"][manifest["source"]], "state": str(state_path)}
        atomic(work / "completion.json", result)
        progress("complete", completed=len(texts), total=len(texts))
        return result

    finally:
        lock.release()


if __name__ == "__main__":
    try:
        print(json.dumps(execute(json.loads(sys.stdin.read() or "{}")), ensure_ascii=False))
    except Exception as exc:
        progress("failed", error=str(exc))
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
