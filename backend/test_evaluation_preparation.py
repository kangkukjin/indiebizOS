"""이미지 도구 결과의 경로 탐색 비용과 최종 검사 준비의 관측 경계."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest
import boot_paths  # noqa: F401
from final_evaluator import Evaluator
from test_conscious_supervisor import supervisor, finish, verdict  # noqa: F401


@pytest.mark.parametrize("encoded", [False, True])
def test_visual_collection_keeps_paths_and_ignores_image_bytes(tmp_path, encoded):
    image = tmp_path / "그림 공백.png"
    image.write_bytes(b"local visual evidence")
    other = tmp_path / "other.jpg"
    other.write_bytes(b"other evidence")
    ignored = tmp_path / "binary.jpg"
    ignored.write_bytes(b"not a path field")
    result = {"result": json.dumps({"image_path": str(image)}),
              "images": [{"base64": str(ignored), "file_path": str(other)}],
              "image_data": {"b64": str(ignored)}, "image_base64": str(ignored)}
    original = json.dumps(result)
    calls = [{"result": original if encoded else result}]
    images = Evaluator()._collect_visual_artifacts(
        f"![artifact]({other}) https://example.invalid/other.jpg", calls)
    assert [i["_path"] for i in images] == [str(image), str(other)]
    assert images[0]["base64"] == base64.b64encode(image.read_bytes()).decode()
    assert json.dumps(result) == original


def test_plain_text_paths_and_limit_keep_latest_existing_images(tmp_path):
    images = [tmp_path / f"image{i}.PNG" for i in range(4)]
    for image in images:
        image.write_bytes(image.name.encode())
    calls = [{"input": {"path": str(images[0])},
              "result": f"Created: {images[1]}\n![view]({images[2]})"}]
    response = f"`{images[3]}`\n/missing.png"
    found = Evaluator()._collect_visual_artifacts(response, calls, max_images=3)
    assert [i["_path"] for i in found] == [str(p) for p in images[1:]]
    assert all(i["media_type"] == "image/png" for i in found)


def test_large_binary_and_plain_slash_runs_do_not_rescan_each_slash():
    # 자식 프로세스 한도로 퇴행 시에도 수분간 pytest/백엔드를 붙잡지 않는다.
    code = """
import sys
sys.path.insert(0, 'backend')
import boot_paths
from final_evaluator import Evaluator
import json
blob = '/AAA' * 500000
calls = [{'result': json.dumps({'images': [{'base64': blob}]})},
         {'result': blob}, {'result': 'https://example.invalid/' + blob}]
assert Evaluator()._collect_visual_artifacts('', calls) == []
"""
    subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                   timeout=10, check=True, capture_output=True, text=True)


def test_evaluation_records_wait_and_preparation_separately(supervisor, monkeypatch):
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: verdict(c))
    started = threading.Event()
    log = supervisor.log

    def record(kind, **fields):
        row = log(kind, **fields)
        if kind == "evaluation.stage_started" and fields.get("stage") == "wait":
            started.set()
        return row

    monkeypatch.setattr(supervisor, "log", record)
    result = []
    supervisor.review_lock.acquire()
    worker = threading.Thread(target=lambda: result.extend(finish(supervisor, "완성 답변")))
    worker.start()
    try:
        assert started.wait(3)
        assert not result
    finally:
        supervisor.review_lock.release()
        worker.join(5)
    assert not worker.is_alive()
    assert result[-1]["content"] == "완성 답변"
    events = [json.loads(l) for l in (supervisor.store.directory / "events.jsonl").read_text().splitlines()]
    stages = [e for e in events if e["kind"] == "evaluation.stage_finished"]
    assert [e["stage"] for e in stages] == ["wait", "visual", "prepare", "checkpoint"]
    assert all(e["completed"] and e["elapsed_s"] >= 0 for e in stages)
    cost = supervisor.store.cost_summary(1)
    assert cost["evaluation_wait_s"] > 0
    assert cost["evaluation_prepare_s"] >= cost["evaluation_visual_s"]


def test_preparation_failure_still_closes_timing_and_never_evaluates(supervisor, monkeypatch):
    def fail(*a, **kw):
        raise ValueError("fixture preparation failure")
    monkeypatch.setattr("final_evaluator.prepare", fail)
    monkeypatch.setattr("final_evaluator.invoke", lambda *a, **kw: pytest.fail("자료 없는 평가"))
    finish(supervisor, "완성 답변")
    events = [json.loads(l) for l in (supervisor.store.directory / "events.jsonl").read_text().splitlines()]
    prepared = next(e for e in events if e["kind"] == "evaluation.stage_finished" and e["stage"] == "prepare")
    assert not prepared["completed"] and prepared["elapsed_s"] >= 0
    assert supervisor.store.cost_summary(1)["evaluation_prepare_s"] >= 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
