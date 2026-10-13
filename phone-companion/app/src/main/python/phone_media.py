"""Phone assembly of the shared media service. No extension credentials in ordinary calls."""
import json
import os

_installed = False


def install(app):
    global _installed
    if _installed:
        return
    os.environ.setdefault("INDIEBIZ_MEDIA_STATE_DIR", os.path.join(os.environ["INDIEBIZ_USERDATA"], "media"))
    import api_media
    import media_sessions
    from java import jclass
    # The phone's final 404 handler must stay last.
    tail = [r for r in app.router.routes if getattr(r, 'path', '') == '/{full_path:path}']
    app.router.routes[:] = [r for r in app.router.routes if r not in tail]
    app.include_router(api_media.router)
    app.router.routes.extend(tail)
    bridge = jclass('com.indiebiz.phoneagent.media.MediaBridge')
    media_sessions.subscribe(lambda event, s: bridge.callEvent(event, json.dumps(s)))
    _installed = True
    start_inbox()


def start_inbox():
    from indienet import get_indienet
    from java import jclass
    net = get_indienet()
    if not net.is_initialized():
        return
    pub = net.identity.public_key_hex
    jclass('com.indiebiz.phoneagent.media.CallInbox').start(json.dumps(net._self_dm_relays()), pub)


def receive_event(raw):
    """Kotlin's persistent relay subscription sends only signed gift-wraps to this boundary."""
    import nostr_phone_bridge
    import media_sessions
    import media_signaling
    out = nostr_phone_bridge.unwrap_dm(json.loads(str(raw)))
    if out and media_signaling.is_call_frame_content(out.get('content')):
        media_sessions.receive_remote(json.loads(out['content']), source='nostr', sender_hex=out['sender'])
