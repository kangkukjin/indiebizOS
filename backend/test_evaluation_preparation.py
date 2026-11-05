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


def write_image(path, color):
    from PIL import Image
    Image.new('RGB', (16, 16), color).save(path)


@pytest.mark.parametrize("encoded", [False, True])
def test_visual_collection_keeps_paths_and_ignores_image_bytes(tmp_path, encoded):
    image = tmp_path / "그림 공백.png"
    write_image(image, 'red')
    other = tmp_path / "other.jpg"
    write_image(other, 'blue')
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
    for i, image in enumerate(images):
        write_image(image, (i * 60, 0, 0))
    calls = [{"input": {"path": str(images[0])},
              "result": f"Created: {images[1]}\n![view]({images[2]})"}]
    response = f"`{images[3]}`\n/missing.png"
    found = Evaluator()._collect_visual_artifacts(response, calls, max_images=3)
    assert [i["_path"] for i in found] == [str(p) for p in images[1:]]
    assert all(i["media_type"] == "image/png" for i in found)


def test_native_pixels_survive_path_replacement_and_omitted_image_can_be_recovered(supervisor, tmp_path):
    from final_evaluator import prepare, snapshot_error
    from evaluation_input import evidence_requests, recover, new_evidence_requests
    paths = [tmp_path / f'screenshot-{i}.png' for i in range(4)]
    for i, path in enumerate(paths):
        write_image(path, (i * 60, 0, 0))
        supervisor.observe_native({'type': 'tool_start', 'id': str(i), 'name': 'view_image',
                                   'input': {'path': str(path)}})
        supervisor.observe_native({'type': 'tool_result', 'id': str(i), 'name': 'view_image',
                                   'result': '', 'images': [{'base64': base64.b64encode(path.read_bytes()).decode(),
                                                             'media_type': 'image/png'}]})
    original = paths[0].read_bytes()
    paths[0].unlink()
    write_image(paths[1], 'green')
    supervisor.store.put_response('네 화면을 대조했다.')
    packet = prepare(supervisor)
    assert len(packet['images']) == 3 and len(packet['context']['visual_evidence']) == 4
    ref = packet['context']['visual_evidence'][0]['id']
    request = evidence_requests('EVIDENCE_REQUESTS: ' + json.dumps([
        {'criterion_id': 'C1', 'evidence_id': ref, 'start': 0, 'end': 1}]), packet)
    assert request['status'] == 'normalized'
    packet['attachments'].extend(recover(supervisor, request['requests']))
    assert base64.b64decode(packet['images'][-1]['base64']) == original
    assert not new_evidence_requests(request['requests'], packet['attachments'])
    assert snapshot_error(supervisor) is None
    packet['images'][-1]['base64'] = base64.b64encode(b'altered').decode()
    assert snapshot_error(supervisor)


def test_successful_empty_capture_command_does_not_invent_pixels(supervisor, tmp_path):
    from final_evaluator import prepare
    path = tmp_path / 'hidden.png'
    write_image(path, 'blue')
    supervisor.run_tool('shell', {'command': f'capture-screen {path}'}, lambda: '')
    supervisor.store.put_response('촬영 명령 종료')
    assert prepare(supervisor)['images'] == []


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
