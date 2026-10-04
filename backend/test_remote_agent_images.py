"""원격 사진: 브라우저 선택 → HTTP → AI 입력·DB → 재열기. 모델 호출은 대체한다."""
import base64
import io
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import boot_paths  # noqa: F401
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def photo():
    out = io.BytesIO()
    Image.new('RGB', (32, 24), 'red').save(out, format='PNG')
    return out.getvalue()


@pytest.fixture
def chat(tmp_path, monkeypatch):
    import api_agents
    import api_conversations
    import conversation_db
    from episode_logger import EpisodeLogger

    manager = SimpleNamespace(get_project_path=lambda _: tmp_path)
    monkeypatch.setattr(api_agents, 'project_manager', manager)
    monkeypatch.setattr(api_conversations, 'project_manager', manager)
    monkeypatch.setattr(conversation_db, '_ckpt_schedule', lambda *a: None)
    monkeypatch.setattr(conversation_db, '_ckpt_apply', lambda *a: a[-1])
    monkeypatch.setattr(EpisodeLogger, 'start_episode', lambda *a, **kw: None)
    monkeypatch.setattr(EpisodeLogger, 'end_episode', lambda *a, **kw: None)
    calls = []

    def cognitive(command, history, **kwargs):
        calls.append({'command': command, 'history': history, **kwargs})
        yield {'type': 'final', 'content': '사진을 받았습니다.'}

    runner = SimpleNamespace(config={'name': '사진 담당'}, ai=True, cognitive_stream=cognitive)
    monkeypatch.setattr(api_agents, 'agent_runners', {'p': {'agent_photo': {'runner': runner}}})
    # 스레드의 작업 자체는 그대로 실행하되 테스트가 완료를 결정론적으로 관측한다.
    monkeypatch.setattr(api_agents, 'threading', SimpleNamespace(
        Thread=lambda target, **kw: SimpleNamespace(start=target)))
    (tmp_path / 'agents.yaml').write_text('agents:\n  - id: agent_photo\n    name: 사진 담당\n')
    app = FastAPI()
    app.include_router(api_agents.router)
    app.include_router(api_conversations.router)
    with TestClient(app) as client:
        yield client, calls, tmp_path


@pytest.mark.parametrize('background', [False, True])
def test_command_images_reach_ai_storage_history_and_image_route(chat, photo, background):
    client, calls, root = chat
    images = [{'base64': base64.b64encode(photo).decode(), 'media_type': 'image/png'}] * 2
    response = client.post('/projects/p/agents/agent_photo/command', json={
        'command': '사진 확인', 'images': images, 'background': background})
    assert response.status_code == 200
    assert response.json() == ({'status': 'started'} if background else {'response': '사진을 받았습니다.'})
    assert calls[0]['images'] == images
    messages = client.get('/conversations/p/agent_photo/messages').json()['messages']
    user = next(m for m in messages if not m['is_agent'])
    assert len(user['images']) == 2
    for path in user['images']:
        assert (root / path).read_bytes() == photo
        response = client.get('/conversations/p/image', params={'path': path})
        assert response.status_code == 200 and response.content == photo
        download = client.get('/conversations/p/image', params={'path': path, 'dl': 1})
        assert 'attachment' in download.headers['content-disposition']
    client.post('/projects/p/agents/agent_photo/command', json={'command': '계속'})
    assert calls[-1]['images'] is None
    assert next(m for m in calls[-1]['history'] if m.get('images'))['images'] == images


@pytest.mark.parametrize('path', ['../secret.png', 'images/../../secret.png', 'images/not-image.txt', 'images/link.png'])
def test_image_route_confines_files_to_project_images(chat, path):
    client, _, root = chat
    (root / 'images').mkdir(exist_ok=True)
    (root / 'secret.png').write_bytes(b'private')
    (root / 'images/link.png').symlink_to(root / 'secret.png')
    assert client.get('/conversations/p/image', params={'path': path}).status_code == 403


def test_image_missing_and_auth_boundary(chat):
    from api_launcher_web import is_public_remote_path
    client, _, _ = chat
    assert client.get('/conversations/p/image', params={'path': 'images/missing.png'}).status_code == 404
    assert not is_public_remote_path('GET', '/conversations/p/image')


@pytest.mark.parametrize('target', ['agent', 'system'])
def test_browser_select_send_and_reopen(chat, photo, target):
    from playwright.sync_api import sync_playwright, expect
    from launcher_surface_remote import launcher_html

    client, calls, _ = chat
    sent = []
    system_messages = []
    errors = []

    def route(request_route):
        request = request_route.request
        parsed = urlsplit(request.url)
        path = parsed.path
        if path == '/launcher/app':
            request_route.fulfill(content_type='text/html', body=launcher_html())
            return
        if path.endswith('/start'):
            data = {'status': 'started'}
        elif path == '/system-ai/chat':
            body = request.post_data_json
            sent.append(body)
            system_messages.extend([
                {'id': 1, 'role': 'user', 'content': body['message'], 'images': ['system_ai_images/test.jpg']},
                {'id': 2, 'role': 'assistant', 'content': '사진을 받았습니다.'}])
            data = {'status': 'started'}
        elif path == '/system-ai/conversations':
            data = {'conversations': system_messages}
        elif path == '/system-ai/image':
            request_route.fulfill(content_type='image/png', body=photo)
            return
        elif path.startswith('/conversations/') or path.endswith('/command'):
            if path.endswith('/command'):
                sent.append(request.post_data_json)
            response = client.request(request.method, path + ('?' + parsed.query if parsed.query else ''),
                                      content=request.post_data, headers={'content-type': 'application/json'})
            request_route.fulfill(status=response.status_code, body=response.content,
                                 content_type=response.headers.get('content-type', 'application/json'))
            return
        elif path == '/projects':
            data = {'projects': [{'id': 'p', 'name': '사진 프로젝트'}]}
        elif path == '/projects/p/agents':
            data = {'agents': [{'id': 'agent_photo', 'name': '사진 담당'}]}
        else:
            data = {}
        request_route.fulfill(content_type='application/json', body=json.dumps(data))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/*', route)
        page.goto('http://repair.test/launcher/app')
        expect(page.locator('#apBrowse')).to_contain_text('사진 프로젝트')
        page.evaluate("apSleep=()=>Promise.resolve()")
        if target == 'agent':
            page.evaluate("async()=>{await apBrowseProject('p'); apPickAgent(0);}")
        else:
            page.evaluate('apPickSystem()')
        expect(page.locator('#apAttach')).to_be_visible()
        files = [{'name': f'photo{i}.png', 'mimeType': 'image/png', 'buffer': photo} for i in range(4)]
        page.locator('#apFile').set_input_files(files)
        expect(page.locator('#apChips img')).to_have_count(4)
        page.locator('#apChips button').last.click()
        expect(page.locator('#apChips img')).to_have_count(3)
        page.locator('#apSend').click()  # 사진만 전송
        expect(page.locator('#apSend')).to_be_enabled()
        expect(page.locator('#apMsgs')).to_contain_text('사진을 받았습니다.')
        assert len(sent) == 1 and len(sent[0]['images']) == 3
        assert sent[0].get('command', sent[0].get('message')) == '첨부한 사진을 봐줘.'
        assert sent[0]['background'] is True
        for image in sent[0]['images']:
            assert image['media_type'] == 'image/jpeg'
            assert Image.open(io.BytesIO(base64.b64decode(image['base64']))).size == (32, 24)
        if target == 'agent':
            assert calls[0]['images'] == sent[0]['images']
        expect(page.locator('#apChips')).to_be_hidden()
        page.evaluate('apLoadHistory()')
        expect(page.locator('#apMsgs .bimg')).to_have_count(3 if target == 'agent' else 1)
        page.wait_for_function("Array.from(document.querySelectorAll('#apMsgs .bimg')).every(im=>im.complete && im.naturalWidth>0)")
        expected = '/conversations/p/image?' if target == 'agent' else '/system-ai/image?'
        assert expected in page.locator('#apMsgs .bimg').first.get_attribute('src')
        # 대상을 바꿨을 때 전송 대기 사진이 다른 에이전트에게 넘어가지 않는다.
        page.locator('#apFile').set_input_files(files[:1])
        expect(page.locator('#apChips img')).to_have_count(1)
        page.evaluate('apPickSystem()')
        expect(page.locator('#apChips')).to_be_hidden()
        assert errors == []
        browser.close()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
