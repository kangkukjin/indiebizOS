/**
 * DiscoverPane — 이웃찾기 탭. #IndieNet 발견 노트(소개발행)의 수신면.
 * 발견 채널은 #indienet 에 고정([others:feed]{hashtag:"indienet"}) — 소개발행(publish_intro)이
 * 항상 #IndieNet 으로 나가므로 수신도 같은 주파수여야 한다. 활성 보드(active_board)는 IndieNet
 * 창의 항해 상태일 뿐, 보드를 전환한 기기에서도 이웃찾기는 흔들리면 안 된다.
 * 창고 문맥으로 보여준다: 소개 본문의 "공유창고 : <url>" 을 파싱해 그 자리에서
 * 창고이웃 등록(/warehouse-feed/neighbors/add)으로 잇는다 — 소개발행(발신)의 짝.
 */
import { useCallback, useState, type ReactNode } from 'react';
import { Package, RefreshCw, Search, Plus } from 'lucide-react';
import { runIBL } from '../generic/manifest';
import { useRetryingLoad } from '../../lib/use-retrying-load';
import { API } from './shared';

export function DiscoverPane() {
  interface IntroItem { author: string; author_full: string; content: string; time: string; id?: string }
  const [items, setItems] = useState<IntroItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<Record<string, boolean>>({});
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const r = (await runIBL('[others:feed]{op: "read", hashtag: "indienet", limit: 50}')) as Record<string, unknown>;
      if (r?.error) throw new Error(String(r.error));
      // 보드 통화는 채팅방 관례(과거→최신)로 온다 — 게시판형 목록은 최신 글이 맨 위.
      const arr = Array.isArray(r?.items) ? (r.items as IntroItem[]) : [];
      setItems(arr.slice().reverse());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
      throw e;                        // 실패를 굳히지 않는다 — 훅이 백오프 재시도
    }
    setBusy(false);
  }, []);
  const { retry, retrying } = useRetryingLoad(load);

  // 소개 본문에서 공유창고 주소를 뽑는다 — 계약: "공유창고 Warehouse : <url>" 라벨
  // (indienet_publish.publish_intro, 한/영 병기). ★키워드 게이트: "공유창고"와 "warehouse"가
  // **둘 다** 있어야 창고 글로 간주 — 정식 발행은 항상 병기하므로, 잡담에 한쪽 단어가
  // 등장해도 버튼이 안 붙는다(+URL 존재까지 삼중 조건). 라벨 형식이 아니면 마지막 URL 폴백.
  const whUrlOf = (content: string): string | null => {
    if (!(/공유창고/.test(content) && /warehouse/i.test(content))) return null;
    const m = content.match(/(?:공유창고|warehouse)[^\n]*?:\s*(https?:\/\/\S+)/i);
    if (m) return m[1];
    const urls = content.match(/https?:\/\/\S+/g);
    return urls?.length ? urls[urls.length - 1] : null;
  };
  const openUrl = (url: string) => {
    const el = (window as any).electron;
    if (el?.openExternal) el.openExternal(url);
    else window.open(url, '_blank', 'noopener');
  };
  // 본문 속 URL을 클릭 가능한 링크로 — Electron 창 안 내비게이션을 막고 기본 브라우저로 연다.
  const linkify = (text: string): ReactNode[] => {
    const parts: ReactNode[] = [];
    const re = /https?:\/\/\S+/g;
    let last = 0;
    let m: RegExpExecArray | null;
    let k = 0;
    while ((m = re.exec(text))) {
      if (m.index > last) parts.push(text.slice(last, m.index));
      const url = m[0];
      parts.push(
        <a
          key={k++}
          href={url}
          className="text-[#B45309] underline underline-offset-2 hover:text-[#D97706] break-all"
          title="브라우저로 열기"
          onClick={(e) => { e.preventDefault(); openUrl(url); }}
        >{url}</a>,
      );
      last = m.index + url.length;
    }
    if (last < text.length) parts.push(text.slice(last));
    return parts;
  };
  // 작성자 클릭 = DM — 이웃이면 그 이웃으로, 아니면 npub 로 이웃 등록부터([others:neighbor] save 는
  // npub 멱등: 같은 npub 이웃이 있으면 그대로 반환). 그 뒤 메신저 창을 그 이웃의 대화로 딥링크
  // (localStorage 핸드오프 — MessengerInstrumentView 가 마운트/storage 이벤트로 소비).
  const openDm = async (it: IntroItem) => {
    const npub = it.author_full || '';
    if (!npub.startsWith('npub')) { window.alert('작성자의 nostr 주소를 확인할 수 없어요.'); return; }
    try {
      const r = (await runIBL(
        `[others:neighbor]{op: "save", name: ${JSON.stringify(it.author)}, npub: ${JSON.stringify(npub)}}`,
      )) as Record<string, unknown>;
      const nb = (r?.neighbor ?? null) as { id?: number } | null;
      if (!nb?.id) throw new Error(String(r?.error || r?.message || '이웃 등록 실패'));
      localStorage.setItem('indiebiz_messenger_dm_nid', String(nb.id));
      const el = (window as any).electron;
      if (el?.openMessengerWindow) el.openMessengerWindow();
      else window.location.hash = '#/messenger';   // 브라우저 폴백 (런처 연락처 버튼과 동일)
    } catch (e) {
      window.alert(`DM 열기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // 게시판처럼 한마디 — [others:feed]{op:"post"} 로 #IndieNet 보드에 kind:1 발행(커뮤니티 계기와 동일 경로).
  // ★hashtag 고정 필수: 안 넘기면 post_to_board 가 활성 보드로 폴백 — 보드 전환한 기기에선 다른 방에 발행된다.
  // 소개만이 아니라 일반 대화도 이 스트림에서 오간다. ★내용은 JSON.stringify 로 이스케이프(따옴표·줄바꿈).
  const postMsg = async () => {
    const t = draft.trim();
    if (!t || posting) return;
    setPosting(true);
    try {
      const r = (await runIBL(`[others:feed]{op: "post", hashtag: "indienet", content: ${JSON.stringify(t)}}`)) as Record<string, unknown>;
      if (r?.error || r?.success === false) throw new Error(String(r.error || r.message || '게시 실패'));
      setDraft('');
      await retry();  // 릴레이 반영이 늦으면 목록에 아직 없을 수 있다 — 새로고침으로 다시 확인
    } catch (e) {
      window.alert(`게시 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
    setPosting(false);
  };

  // npub = 소개 작성자의 서명 신원 — 서버가 창고(풀)+nostr(푸시) 두 접점을 한 이웃에 모으고,
  // 같은 npub 의 기존 이웃이 있으면 새 레코드 대신 그에게 창고를 단다(신원 앵커).
  const addNeighbor = async (url: string, npub: string) => {
    try {
      const body: Record<string, unknown> = { url };
      if (npub) body.npub = npub;
      const r = await fetch(`${API}/warehouse-feed/neighbors/add`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => null);
        throw new Error(d?.detail || `HTTP ${r.status}`);
      }
      setAdded((a) => ({ ...a, [url]: true }));
      window.alert('창고이웃으로 등록했어요 — 이웃 탭 피드에 이 창고의 소식이 흐릅니다.');
    } catch (e) {
      window.alert(`등록 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4">
      <div className="max-w-3xl mx-auto space-y-3">
        <div className="flex items-center gap-2">
          <p className="text-xs text-stone-500">
            #IndieNet 게시판 — 자기소개도 일반 대화도 여기서 흐릅니다. <strong>공유창고 Warehouse</strong> 병기
            표시가 있는 글은 그 자리에서 창고이웃으로 등록할 수 있어요. (정식 소개는 위의 <strong>소개발행</strong> 버튼으로)
          </p>
          <div className="flex-1" />
          <button
            className="p-1.5 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-stone-100 shrink-0"
            title="새로고침" onClick={() => retry()}
          >
            <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
          </button>
        </div>
        {/* 작성바 — 게시판처럼 한마디. 공개 발행임을 placeholder 로 명시. */}
        <div className="flex items-end gap-2 px-3 py-2.5 rounded-xl bg-white border border-stone-200">
          <textarea
            rows={draft.includes('\n') || draft.length > 60 ? 3 : 1}
            className="flex-1 resize-none text-sm text-stone-800 placeholder:text-stone-400 outline-none bg-transparent"
            placeholder="#IndieNet 게시판에 한마디 — 소개도, 일반 대화도 좋아요 (모두에게 공개 발행됩니다)"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button
            className="px-3 py-1.5 text-xs rounded-lg bg-[#D97706] text-white hover:bg-[#B45309] disabled:opacity-50 shrink-0"
            disabled={posting || !draft.trim()}
            onClick={postMsg}
          >
            {posting ? '게시 중…' : '게시'}
          </button>
        </div>
        {error && (
          <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center gap-2">
            <span className="flex-1">{error}{retrying && <span className="ml-1 text-red-400">— 백엔드를 기다리는 중…</span>}</span>
            <button className="shrink-0 px-2 py-0.5 rounded-md border border-red-200 bg-white hover:bg-red-50"
                    onClick={() => retry()}>다시 시도</button>
          </div>
        )}
        {busy && !items.length && <div className="text-sm text-stone-400 py-8 text-center">릴레이에서 소개를 모으는 중…</div>}
        {!busy && !items.length && !error && (
          <div className="text-center text-stone-400 py-10">
            <Search className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p className="text-sm">아직 소개가 없어요 — 먼저 소개발행으로 나를 알려보세요</p>
          </div>
        )}
        <ul className="space-y-2">
          {items.map((it, i) => {
            const wh = whUrlOf(it.content);
            return (
              <li key={it.id || i} className="px-4 py-3 rounded-xl bg-white border border-stone-200">
                <div className="flex items-center gap-2 text-xs text-stone-400 mb-1">
                  <button
                    className="font-medium text-stone-600 hover:text-[#B45309] hover:underline underline-offset-2"
                    title="DM 보내기 — 메신저에서 이 사람과의 대화를 엽니다 (이웃이 아니면 등록부터)"
                    onClick={() => openDm(it)}
                  >
                    💬 {it.author}
                  </button>
                  <span>{it.time}</span>
                </div>
                <p className="text-sm text-stone-800 whitespace-pre-wrap break-words">{linkify(it.content)}</p>
                {wh && (
                  <div className="flex items-center gap-2 mt-2">
                    <button
                      className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border border-stone-200 text-stone-600 hover:border-[#D97706]/40 hover:text-[#B45309]"
                      title="이 사람의 공개 창고를 브라우저로 열기"
                      onClick={() => openUrl(wh)}
                    >
                      <Package className="w-3.5 h-3.5" /> 창고 열기
                    </button>
                    <button
                      className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg bg-[#D97706] text-white hover:bg-[#B45309] disabled:opacity-50"
                      title="창고이웃으로 등록 — 이웃 탭 피드에 이 창고의 새 파일이 흐릅니다"
                      disabled={!!added[wh]}
                      onClick={() => addNeighbor(wh, it.author_full || '')}
                    >
                      <Plus className="w-3.5 h-3.5" /> {added[wh] ? '등록됨' : '창고이웃 등록'}
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
