"""구형 브라우저도 같은 원본·판본 계약을 소비하는 ES5 표시 어댑터."""
import json
from surface_assets import asset_snapshot, read_asset, render_template


@asset_snapshot()
def lite_html(display=True):
    from launcher_render_core import load_conversation_js
    from surface_display import describe
    shared = load_conversation_js()
    code = read_asset('remote/lite-display.js')
    html = render_template('remote/launcher_lite_html.html', conversation_js=shared,
                           lite_js=code, display_bootstrap='')
    if not display:
        return html
    descriptor = describe(html, 'lite', code, shared, kernel='shared/lite-display-host.js')
    script = (read_asset('shared/lite-display-host.js') + '\nIndieLite.start('
              + json.dumps(descriptor, ensure_ascii=False).replace('<', '\\u003c')
              + ',function(){getConversation().arrange(document.getElementById("chatMenuActions"),'
              + '{older:"chatOlder",history:"chatHistoryOpen",new:"chatNew"});renderSessionList();});IndieLite.watch(api);')
    return render_template('remote/launcher_lite_html.html', conversation_js=shared,
                           lite_js=code, display_bootstrap=script)


def lite_display():
    from launcher_render_core import load_conversation_js
    from surface_display import describe
    with asset_snapshot():
        return describe(lite_html(False), 'lite', read_asset('remote/lite-display.js'),
                        load_conversation_js(), kernel='shared/lite-display-host.js')


def __getattr__(name):
    if name == 'LAUNCHER_LITE_HTML':
        return lite_html()
    raise AttributeError(name)
