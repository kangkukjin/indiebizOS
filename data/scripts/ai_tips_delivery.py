"""AI 팁 보고서의 공유판과 짧은 완료 결과. 모델 호출이나 알림을 추가하지 않는다."""
import datetime as dt
from pathlib import Path
from common.pkg_utils import load_sibling
from supervision_delivery import stage_artifact

ROOT = Path(__file__).resolve().parents[2]
io = load_sibling(__file__, 'ai_tips_storage')
renderer = load_sibling(__file__, '보고서HTML')


def settings(request):
    """호출자가 원장·최근 보고서·실행 폴더를 열지 않아도 같은 기본 회차를 고른다."""
    config = dict(request)
    config.setdefault('root', str(ROOT / 'outputs/ai_tips_reports'))
    config.setdefault('date', dt.date.today().isoformat())
    config.setdefault('mode', 'commit')
    config.setdefault('reader_context', 'Claude Code·IndieBiz OS를 사용하는 고급 사용자. AI 도구를 실제 업무와 코딩에 활용하는 구체적인 방법.')
    topic = config.get('topic')
    if not topic:
        # 같은 날짜의 기본 호출은 같은 run으로 돌아간다. 후속 주제는 어제까지의 최신 호에서 가져온다.
        root = Path(config['root'])
        covered = io.load_json(root / '_covered_videos.json', {'recent_topics': []})
        previous = [r for r in covered.get('recent_topics', []) if r.get('date', '') < config['date']]
        topic = '코딩'
        if previous:
            last = previous[-1]
            candidates = sorted(root.glob('ai_tips_report_' + last['date'] + '_*.md'))
            for path in reversed(candidates):
                import re
                match = re.search(r'^## 다음 주제 후보\s*\n+([^#\n]+)', path.read_text(), re.M)
                if match:
                    topic = match[1].strip()
                    break
        config['topic'] = topic
        config.setdefault('run_id', config['date'] + '-auto-v5')
    config.setdefault('share_root', str(ROOT / '공유창고/0/AI 팁들'))
    return config


def deliver(state):
    config, run = state['config'], Path(state['run'])
    item = dict(state['prepared_result']['items'][0])
    item.update(summary=state['summary'], topic=config['topic'],
                video_count=len(state['sources']), limitations=state['limitations'])
    if config['mode'] == 'draft':
        return {**item, 'status': 'draft', 'shared_report': None, 'published': False}
    report = Path(item['report'])
    io.require(io.digest(report.read_text()) == state['report_hash'],
               '저장 후 보고서가 변경됐습니다. 변경된 본문을 확인해야 합니다')
    destination = Path(config['share_root']).expanduser()
    io.require(destination.is_absolute() and destination.resolve() != Path('/'), 'share_root는 폴더 절대경로')
    destination = destination / ('AI 팁 보고서 ' + config['date'] + ' ' + state['safe_topic'] + '.html')
    # 개인 독자 맥락은 공유 요약에 쓰지 않고, 적용 의견은 줄 단위로 제거한다.
    public_summary = f"최근 영상 {len(state['sources'])}편에서 {config['topic']} 주제의 AI 활용 팁 {state['counts']['new_tips']}개를 정리했다."
    source = run / 'shared-source.md'
    text = state['markdown'].replace('\n' + state['summary'] + '\n', '\n' + public_summary + '\n', 1)
    io.atomic(source, text, text=True)
    rendered = renderer.render({'src': str(source), 'dst': str(run / 'shared-preview.html'),
                                'theme': 'card', 'drop_lines': ['우리 시스템 함의']})
    html = Path(rendered['items'][0]['path']).read_bytes()
    io.require(rendered['items'][0]['dropped_lines'] == state['counts']['new_tips'], '공유판의 개인 의견 제거 수 불일치')
    with io.file_lock(destination):
        if destination.exists():
            io.require(destination.read_bytes() == html, '공유창고에 다른 내용의 같은 이름 보고서가 있습니다')
            pending = None
        else:
            pending = stage_artifact(destination, html, ROOT / '공유창고')
            if not pending:
                io.atomic(destination, html.decode('utf-8'), text=True)
    item.update(status='publication_pending' if pending else 'completed',
                shared_report=str(destination), published=not bool(pending))
    if pending:
        item['shared_preview'] = pending['staged']
    io.atomic(run / 'delivery.json', {'target': str(destination), 'html_hash': io.digest(html.decode()),
                                     'pending': bool(pending), 'rendered': rendered['items'][0]})
    return item
