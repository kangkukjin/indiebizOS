"""설치 없는 회원 웹앱. 공통 화면 + 브라우저 저장·실행 어댑터."""
from pathlib import Path

from member_shell import member_html

ASSETS = ('member_browser_store.js', 'member_browser_files.js',
          'member_browser_runtime.js', 'member_browser_boot.js')


def browser_html():
    html = member_html()
    html = html.replace('<main>', '<main id="memberWorkspace" hidden>', 1)
    html = html.replace('async function memberBoot(){', 'async function workspaceBoot(){')
    html = html.replace('작업 중 · 화면을 닫아도 연결 프로그램이 계속 실행합니다',
                        '작업 중 · 이 탭을 열어 두세요. 화면을 닫으면 중단될 수 있습니다')
    html = html.replace('내 컴퓨터', '내 기기')
    html = html.replace("'task_id'].includes", "'task_id','body_session'].includes")
    html = html.replace("shell:'명령 실행'", "javascript:'브라우저 계산',shell:'명령 실행'")
    html = html.replace("document.getElementById('gearLever').contains",
                        "document.getElementById('gearLever')?.contains")
    html = html.replace("if('serviceWorker' in navigator){", "if(false){")
    login = '''<main id="memberLogin"><small>INDIEBIZ · MEMBER WORKSPACE</small>
<h1>내 기기에서 바로 시작하세요</h1>
<p>설치 없이 AI와 앱을 사용합니다. 기억·작업·파일은 이 기기의 브라우저에 보관합니다.</p>
<form id="browserLoginForm"><label>초대받은 회원 키<input id="browserKey" type="password" autocomplete="off" required aria-label="회원 키"></label><button id="browserConnect">작업 공간 열기</button></form>
<p id="browserLoginStatus" role="status"></p><small>AI 요청은 허브와 모델 제공자가 처리합니다. 다른 기기와 기억을 자동 공유하지 않습니다.</small></main>'''
    html = html.replace('<main id="memberWorkspace"', login + '<main id="memberWorkspace"', 1)
    html = html.replace('<button class="secondary" id="export">기억 내보내기</button>',
                        '<div class="browserTools"><button class="secondary" id="export">기억 내보내기</button><button class="secondary" id="browserLogout">연결 종료</button></div>')
    html = html.replace('<small id="status">', '''<details id="browserStorage"><summary>이 기기의 보관·복원</summary><p id="browserStorageStatus"></p><button id="browserPersist" class="secondary">지속 보관 요청</button><label>백업 복원<input id="browserRestore" type="file" accept="application/json,.json" aria-label="백업 복원"></label></details><small id="status">''', 1)
    html = html.replace('<button id="saveFile">저장</button>', '<button id="saveFile">저장</button><button id="browserDownloadFile">기기에 내려받기</button>')
    html = html.replace('<div id="taskProgress"', '<div id="memberArtifacts" aria-live="polite"></div><div id="taskProgress"', 1)
    css = '''#memberLogin{max-width:580px;margin:7vh auto}#memberLogin p{line-height:1.8}#browserLoginForm{position:static;display:flex;flex-direction:column}#browserKey{display:block;width:100%;padding:15px;margin:12px 0;border:1px solid #bdc9c1;border-radius:10px;font:inherit}.browserTools{display:flex;gap:8px}#browserStorage{margin:12px 0}#workspacePicker{display:none}.fileActions{flex-wrap:wrap}#importFile{max-width:100%}@media(max-width:700px){header{align-items:flex-start;gap:8px}.browserTools{flex-direction:column}#memberLogin{margin:3vh auto}#send{flex-wrap:wrap}#message{min-width:100%}#filePath{width:100%}.user{margin-left:15px}.assistant{margin-right:0}}'''
    html = html.replace('</style>', css + '</style>', 1)
    root = Path(__file__).resolve().parents[1] / 'static'
    scripts = '\n'.join((root / name).read_text(encoding='utf-8') for name in ASSETS)
    return html.replace('</script></html>', scripts.replace('</script', '<\\/script') + '</script></html>')
