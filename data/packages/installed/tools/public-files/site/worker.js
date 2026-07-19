/**
 * 공개파일 Worker — 라이브 서빙(인덱싱 없음) + 지연 캐시.
 *
 * 갤러리는 전부 바스켓(/s/<slug>/…). bare 루트는 잠금(index.html 이 안내).
 *   - /s/<slug>/list?path=        → 맥(ORIGIN_BASE)이 그 디렉토리를 즉석에서 훑어 JSON(캐시 안 함=항상 최신).
 *   - /s/<slug>/thumb/<fid>?rel=&v= → R2 캐시(cache/thumb/<fid>/<hash(rel)>_<v>.jpg) 우선, 없으면 맥이 생성 → 캐시.
 *   - /s/<slug>/media/<fid>?rel=&v= → 원본. R2 캐시 우선, 없으면 맥에서 스트리밍(Range 통과) + 전체는 캐시.
 *   - 그 외                        → index.html(SPA). SPA 가 location 에서 slug 를 읽어 스코프.
 * v=<mtime> 가 캐시 버전키 — 파일이 바뀌면 mtime 이 바뀌어 새 키로 자동 재생성(옛 캐시는 고아).
 *
 * env: BUCKET(R2, 캐시+SPA 호스팅), ORIGIN_BASE(맥 터널), SHOWCASE_SECRET.
 */

const CT = {
  jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp",
  gif: "image/gif", heic: "image/heic",
  mp4: "video/mp4", webm: "video/webm", mov: "video/quicktime", m4v: "video/x-m4v", mkv: "video/x-matroska",
};
function ctypeOf(key) {
  return CT[key.split(".").pop().toLowerCase()] || "application/octet-stream";
}
// 상대경로 → 짧은 안정 해시(캐시 키용). 폴더 내 충돌 확률 무시 가능.
function cyrb53(str, seed = 0) {
  let h1 = 0xdeadbeef ^ seed, h2 = 0x41c6ce57 ^ seed;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (h2 >>> 0).toString(36) + (h1 >>> 0).toString(36);
}
function rangeOpts(rangeHeader) {
  if (!rangeHeader) return {};
  const m = /bytes=(\d*)-(\d*)/.exec(rangeHeader);
  if (!m || !m[1]) return {};
  const offset = parseInt(m[1], 10);
  const end = m[2] ? parseInt(m[2], 10) : undefined;
  return { range: { offset, length: end !== undefined ? end - offset + 1 : undefined } };
}
function r2Serve(obj, ctype, rangeHeader) {
  const headers = new Headers();
  headers.set("content-type", ctype);
  headers.set("cache-control", "public, max-age=86400");
  headers.set("accept-ranges", "bytes");
  if (rangeHeader && obj.range) {
    const start = obj.range.offset || 0;
    const len = obj.range.length || (obj.size - start);
    headers.set("content-range", `bytes ${start}-${start + len - 1}/${obj.size}`);
    return new Response(obj.body, { status: 206, headers });
  }
  return new Response(obj.body, { headers });
}

async function serveIndex(env) {
  if (env.BUCKET) {
    const idx = await env.BUCKET.get("index.html");
    if (idx) {
      return new Response(idx.body, {
        headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-cache" },
      });
    }
  }
  return new Response("index.html 미배포", { status: 500 });
}

function macUrl(env, sub) {
  return `${env.ORIGIN_BASE.replace(/\/$/, "")}/showcase/${sub}`;
}

function macNewsUrl(env, sub) {
  return `${env.ORIGIN_BASE.replace(/\/$/, "")}/family-news/${sub}`;
}

function macBulletinUrl(env, sub) {
  return `${env.ORIGIN_BASE.replace(/\/$/, "")}/bulletin/${sub}`;
}

function macReportUrl(env, sub) {
  return `${env.ORIGIN_BASE.replace(/\/$/, "")}/report/${sub}`;
}

// 정기보고 발행 면 프록시 — 요청 시 최신 보고서를 렌더하므로 no-store(엣지 stale 금지). 읽기 전용.
async function proxyReport(env, request, sub) {
  if (!env.ORIGIN_BASE || !env.SHOWCASE_SECRET) return new Response("origin 미설정", { status: 500 });
  let r;
  try {
    r = await fetch(macReportUrl(env, sub), { headers: { "X-Showcase-Secret": env.SHOWCASE_SECRET } });
  } catch (e) {
    return new Response("맥 접근 불가", { status: 503 });
  }
  const rct = r.headers.get("content-type") || "text/html; charset=utf-8";
  return new Response(r.body, { status: r.status, headers: { "content-type": rct, "cache-control": "no-store" } });
}

// 자유게시판 페이지·글쓰기 프록시 — 글이 HTML 에 박혀 매 글마다 바뀌므로 no-store(엣지 캐시
// 금지, 포털 /h/ 선례). 이미지(media)만 별도 serveCached 로 R2 캐시. 클라이언트 IP + multipart 통과.
async function proxyBulletin(env, request, sub) {
  if (!env.ORIGIN_BASE || !env.SHOWCASE_SECRET) return new Response("origin 미설정", { status: 500 });
  const headers = { "X-Showcase-Secret": env.SHOWCASE_SECRET };
  const ct = request.headers.get("content-type");
  if (ct) headers["Content-Type"] = ct;    // multipart/form-data 경계 보존
  const ip = request.headers.get("cf-connecting-ip");
  if (ip) headers["X-Client-Ip"] = ip;
  const init = { method: request.method, headers };
  if (request.method === "POST") init.body = await request.arrayBuffer();
  let r;
  try {
    r = await fetch(macBulletinUrl(env, sub), init);
  } catch (e) {
    return new Response("맥 접근 불가", { status: 503 });
  }
  const rct = r.headers.get("content-type") || "text/plain; charset=utf-8";
  return new Response(r.body, {
    status: r.status,
    headers: { "content-type": rct, "cache-control": "no-store" },
  });
}

// 개인 포털(/h/) 프록시 — 쿠키 개인화 HTML 이라 캐시 절대 금지(no-store).
// Cookie/Set-Cookie 왕복 + 리다이렉트(개인 링크 착지 302)는 manual 로 그대로 중계.
async function proxyPortal(env, request, sub) {
  if (!env.ORIGIN_BASE || !env.SHOWCASE_SECRET) return new Response("origin 미설정", { status: 500 });
  const headers = { "X-Showcase-Secret": env.SHOWCASE_SECRET };
  const ct = request.headers.get("content-type");
  if (ct) headers["Content-Type"] = ct;
  const ck = request.headers.get("cookie");
  if (ck) headers["Cookie"] = ck;
  const ip = request.headers.get("cf-connecting-ip");
  if (ip) headers["X-Client-Ip"] = ip;
  const rg = request.headers.get("range");   // 오디오 프록시(tune) 구간 탐색
  if (rg) headers["Range"] = rg;
  const init = { method: request.method, headers, redirect: "manual" };
  if (request.method === "POST") init.body = await request.arrayBuffer();
  let r;
  try {
    r = await fetch(`${env.ORIGIN_BASE.replace(/\/$/, "")}/portal/${sub}`, init);
  } catch (e) {
    return new Response("맥 접근 불가", { status: 503 });
  }
  const h = new Headers();
  h.set("content-type", r.headers.get("content-type") || "text/plain; charset=utf-8");
  h.set("cache-control", "no-store");
  // content-disposition = 창고 파일 내려받기(?download=1)의 저장 강제 + 원래 파일명.
  // 빠지면 브라우저가 인라인 표시로 되돌아가고 비-브라우저 클라이언트는 이름을 잃는다.
  for (const k of ["location", "set-cookie", "content-length", "content-range",
                   "accept-ranges", "content-disposition"]) {
    const v = r.headers.get(k);
    if (v) h.set(k, v);
  }
  return new Response(r.body, { status: r.status, headers: h });
}

// 가족신문 페이지·방명록·업로드 프록시 — 캐시 없음(항상 최신), 클라이언트 IP 전달.
async function proxyNews(env, request, sub) {
  if (!env.ORIGIN_BASE || !env.SHOWCASE_SECRET) return new Response("origin 미설정", { status: 500 });
  const headers = { "X-Showcase-Secret": env.SHOWCASE_SECRET };
  const ct = request.headers.get("content-type");
  if (ct) headers["Content-Type"] = ct;
  const ip = request.headers.get("cf-connecting-ip");
  if (ip) headers["X-Client-Ip"] = ip;
  const init = { method: request.method, headers };
  if (request.method === "POST") init.body = await request.arrayBuffer();
  let r;
  try {
    r = await fetch(macNewsUrl(env, sub), init);
  } catch (e) {
    return new Response("맥 접근 불가", { status: 503 });
  }
  const rct = r.headers.get("content-type") || "text/plain; charset=utf-8";
  return new Response(r.body, {
    status: r.status,
    headers: { "content-type": rct, "cache-control": "no-cache" },
  });
}

async function proxyList(env, slug, path) {
  if (!env.ORIGIN_BASE || !env.SHOWCASE_SECRET) return new Response("origin 미설정", { status: 500 });
  const u = macUrl(env, `list/${encodeURIComponent(slug)}?path=${encodeURIComponent(path)}`);
  let r;
  try {
    r = await fetch(u, { headers: { "X-Showcase-Secret": env.SHOWCASE_SECRET } });
  } catch (e) {
    return new Response(JSON.stringify({ error: "mac_offline" }), { status: 503, headers: { "content-type": "application/json" } });
  }
  const body = await r.text();
  return new Response(body, {
    status: r.status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-cache" },
  });
}

async function serveCached(env, ctx, cacheKey, ctype, request, macAbsUrl, cacheable) {
  // R2 캐시 우선 → 없으면 맥에서 pull. cacheable=true 면 전체 응답을 R2 에 캐시.
  const rangeHeader = request.headers.get("range");
  const cached = await env.BUCKET.get(cacheKey, rangeOpts(rangeHeader));
  if (cached) return r2Serve(cached, ctype, rangeHeader);

  if (!env.ORIGIN_BASE || !env.SHOWCASE_SECRET) return new Response("origin 미설정", { status: 500 });
  const oheaders = { "X-Showcase-Secret": env.SHOWCASE_SECRET };
  if (rangeHeader) oheaders["Range"] = rangeHeader;
  let orig;
  try {
    orig = await fetch(macAbsUrl, { headers: oheaders });
  } catch (e) {
    return new Response("맥 접근 불가", { status: 503 });
  }
  if (!orig.ok || !orig.body) return new Response("원본 없음(맥 꺼짐/비공개)", { status: orig.status === 404 ? 404 : 503 });
  const ct = orig.headers.get("content-type") || ctype;

  // Range 응답(206): 부분이라 캐시 안 함 — 그대로 중계(긴 영상 seek).
  if (rangeHeader && orig.status === 206) {
    const h = new Headers();
    h.set("content-type", ct); h.set("accept-ranges", "bytes");
    const cr = orig.headers.get("content-range"); if (cr) h.set("content-range", cr);
    const cl = orig.headers.get("content-length"); if (cl) h.set("content-length", cl);
    h.set("cache-control", "public, max-age=86400");
    return new Response(orig.body, { status: 206, headers: h });
  }
  // 전체 응답: 캐시 대상이면 스트림 분기(뷰어 + R2), 아니면 그냥 중계.
  if (cacheable) {
    const [toClient, toCache] = orig.body.tee();
    ctx.waitUntil(env.BUCKET.put(cacheKey, toCache, { httpMetadata: { contentType: ct } }));
    return new Response(toClient, { headers: { "content-type": ct, "accept-ranges": "bytes", "cache-control": "public, max-age=86400" } });
  }
  return new Response(orig.body, { headers: { "content-type": ct, "accept-ranges": "bytes", "cache-control": "public, max-age=86400" } });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = decodeURIComponent(url.pathname).replace(/^\/+/, "");
    if (!env.BUCKET) return serveIndex(env);

    // 가족신문 — n/<slug>/... (홈=아카이브, e/<eid>/=판 HTML, media=R2 지연 캐시, gb·upload=쓰기 프록시)
    if (path.startsWith("n/")) {
      const np = path.split("/");            // ["n", slug, ...rest]
      const nslug = np[1] || "";
      const rest = np.slice(2);
      if (!nslug) return serveIndex(env);
      // 상대 URL 이 살도록 트레일링 슬래시 정규화
      if (rest.length === 0 && !url.pathname.endsWith("/")) {
        return Response.redirect(`${url.origin}/n/${nslug}/`, 301);
      }
      if (rest.length === 0 || (rest.length === 1 && rest[0] === "")) {
        return proxyNews(env, request, `page/${encodeURIComponent(nslug)}?path=`);
      }
      if (rest[0] === "e") {
        const eid = rest[1] || "";
        if (!eid) return new Response("bad request", { status: 400 });
        if (rest.length === 2 && !url.pathname.endsWith("/")) {
          return Response.redirect(`${url.origin}/n/${nslug}/e/${eid}/`, 301);
        }
        if (rest.length === 2 || (rest.length === 3 && rest[2] === "")) {
          return proxyNews(env, request, `page/${encodeURIComponent(nslug)}?path=${encodeURIComponent("e/" + eid)}`);
        }
        if (rest[2] === "media" && rest[3]) {
          const file = rest.slice(3).join("/");
          const v = url.searchParams.get("v") || "0";
          const key = `cache/fnews/${eid}/${cyrb53(file)}_${v}`;
          const macAbs = macNewsUrl(env,
            `media/${encodeURIComponent(nslug)}/${encodeURIComponent(eid)}?rel=${encodeURIComponent("photos/" + file)}`);
          return serveCached(env, ctx, key, ctypeOf(file), request, macAbs, true);
        }
        return new Response("not found", { status: 404 });
      }
      if (rest[0] === "gb") {
        const ed = url.searchParams.get("edition") || "";
        const q = ed ? `?edition=${encodeURIComponent(ed)}` : "";
        return proxyNews(env, request, `gb/${encodeURIComponent(nslug)}${q}`);
      }
      if (rest[0] === "upload" && request.method === "POST") {
        const qs = url.searchParams.toString();
        return proxyNews(env, request, `upload/${encodeURIComponent(nslug)}${qs ? "?" + qs : ""}`);
      }
      return new Response("not found", { status: 404 });
    }

    // 개인 포털 — h/<slug>/... (홈·개인 링크 착지·가입·계기 페이지·회원 실행 게이트)
    // 전부 무캐시 프록시(쿠키 개인화). 정적 자산 없음(스타일 인라인).
    if (path.startsWith("h/")) {
      const hp = path.split("/");             // ["h", slug, ...rest]
      const hslug = hp[1] || "";
      const hrest = hp.slice(2);
      if (!hslug) return serveIndex(env);
      if (hrest.length === 0 && !url.pathname.endsWith("/")) {
        return Response.redirect(`${url.origin}/h/${hslug}/`, 301);
      }
      if (hrest.length === 0 || (hrest.length === 1 && hrest[0] === "")) {
        return proxyPortal(env, request, `page/${encodeURIComponent(hslug)}`);
      }
      if (hrest[0] === "k" && hrest[1]) {
        return proxyPortal(env, request, `key/${encodeURIComponent(hslug)}/${encodeURIComponent(hrest[1])}`);
      }
      if (hrest[0] === "join" && request.method === "POST") {
        return proxyPortal(env, request, `join/${encodeURIComponent(hslug)}`);
      }
      if (hrest[0] === "login" && request.method === "POST") {
        return proxyPortal(env, request, `login/${encodeURIComponent(hslug)}`);
      }
      if (hrest[0] === "logout" && request.method === "POST") {
        return proxyPortal(env, request, `logout/${encodeURIComponent(hslug)}`);
      }
      if (hrest[0] === "reset" && request.method === "POST") {
        return proxyPortal(env, request, `reset/${encodeURIComponent(hslug)}`);
      }
      if (hrest[0] === "password" && request.method === "POST") {
        return proxyPortal(env, request, `password/${encodeURIComponent(hslug)}`);
      }
      if (hrest[0] === "inst" && hrest[1]) {
        return proxyPortal(env, request, `inst/${encodeURIComponent(hslug)}/${encodeURIComponent(hrest[1])}`);
      }
      if (hrest[0] === "tune" && hrest[1]) {
        return proxyPortal(env, request, `tune/${encodeURIComponent(hslug)}/${encodeURIComponent(hrest[1])}`);
      }
      if (hrest[0] === "tool" && hrest[1] && request.method === "POST") {
        return proxyPortal(env, request, `tool/${encodeURIComponent(hslug)}/${encodeURIComponent(hrest[1])}`);
      }
      return new Response("not found", { status: 404 });
    }

    // 자유게시판 — b/<slug>/... (페이지=글목록+쓰기폼, post=익명 글쓰기, media=첨부 이미지 R2 캐시)
    if (path.startsWith("b/")) {
      const bp = path.split("/");             // ["b", slug, ...rest]
      const bslug = bp[1] || "";
      const brest = bp.slice(2);
      if (!bslug) return serveIndex(env);
      if (brest.length === 0 && !url.pathname.endsWith("/")) {
        return Response.redirect(`${url.origin}/b/${bslug}/`, 301);
      }
      if (brest.length === 0 || (brest.length === 1 && brest[0] === "")) {
        return proxyBulletin(env, request, `page/${encodeURIComponent(bslug)}`);
      }
      if (brest[0] === "post" && request.method === "POST") {
        return proxyBulletin(env, request, `post/${encodeURIComponent(bslug)}`);
      }
      if (brest[0] === "media" && brest[1]) {
        const pid = brest[1];
        const key = `cache/bulletin/${encodeURIComponent(pid)}`;
        const macAbs = macBulletinUrl(env, `media/${encodeURIComponent(bslug)}/${encodeURIComponent(pid)}`);
        return serveCached(env, ctx, key, "image/jpeg", request, macAbs, true);
      }
      return new Response("not found", { status: 404 });
    }

    // 정기보고 발행 면 — r/<slug>/ (항상 그 폴더 최신 보고서를 렌더). 읽기 전용.
    if (path.startsWith("r/")) {
      const rp = path.split("/");             // ["r", slug, ...rest]
      const rslug = rp[1] || "";
      const rrest = rp.slice(2);
      if (!rslug) return serveIndex(env);
      if (rrest.length === 0 && !url.pathname.endsWith("/")) {
        return Response.redirect(`${url.origin}/r/${rslug}/`, 301);
      }
      if (rrest.length === 0 || (rrest.length === 1 && rrest[0] === "")) {
        return proxyReport(env, request, `page/${encodeURIComponent(rslug)}`);
      }
      return new Response("not found", { status: 404 });
    }

    // 맨 루트(/) = 창고 홈(사람용) — 가장 짧은 주소가 노드의 얼굴. 레벨0은 원래 공개라
    // 옛 bare-루트 잠금(showcase 주소=비밀 시절)을 창고에는 적용하지 않는다.
    if (path === "") {
      return proxyPortal(env, request, "home");
    }
    // 노드의 공개 얼굴(기계용) — 슬러그 없는 canonical 매니페스트. 익명=레벨0 포식면.
    if (path === "manifest" || path === "manifest/") {
      return proxyPortal(env, request, "manifest");
    }
    // 단일 노드 로그인/로그아웃 — 루트 스코프 쿠키 pk(레벨 절단면). POST 만.
    if (path === "login" && request.method === "POST") {
      return proxyPortal(env, request, "node/login");
    }
    if (path === "logout" && request.method === "POST") {
      return proxyPortal(env, request, "node/logout");
    }
    // 창고 방명록 — GET=목록(내 레벨 절단·about= 로 파일별 조회), POST=글 남기기.
    // 쿠키(pk)로 신원이 갈리는 개인화 응답이라 no-store(proxyPortal).
    if (path === "gb" && (request.method === "GET" || request.method === "POST")) {
      return proxyPortal(env, request, `gb${url.search || ""}`);
    }
    // 창고 파일 좋아요 — 토글(회원=쿠키 계정, 손님=IP 단위). 개인화라 no-store(proxyPortal).
    if (path === "like" && request.method === "POST") {
      return proxyPortal(env, request, "like");
    }
    // 창고 파일 — f?path= 단일 관문(주소에 레벨 안 드러남). 레벨 게이트는 맥이 판정
    // (쿠키 pk → 레벨, 밖이면 404). 개인화 응답이라 no-store(proxyPortal).
    if (path === "f") {
      return proxyPortal(env, request, `file${url.search || ""}`);
    }

    // 스코프 경로만 서빙 — s/<slug>/<rest>. 그 외(및 bare 루트)는 SPA(잠금 안내).
    if (path === "s" || !path.startsWith("s/")) return serveIndex(env);
    const parts = path.split("/");            // ["s", slug, kind, fid?]
    const slug = parts[1] || "";
    const rest = parts.slice(2);              // ["list"] | ["thumb", fid] | ["media", fid]
    if (!slug || rest.length === 0) return serveIndex(env);

    const kind = rest[0];
    if (kind === "list") {
      return proxyList(env, slug, url.searchParams.get("path") || "");
    }
    if (kind === "thumb" || kind === "media") {
      const fid = rest[1] || "";
      const rel = url.searchParams.get("rel") || "";
      const v = url.searchParams.get("v") || "0";
      if (!fid || !rel) return new Response("bad request", { status: 400 });
      const h = cyrb53(rel);
      if (kind === "thumb") {
        const key = `cache/thumb/${fid}/${h}_${v}.jpg`;
        const macSub = `thumb/${encodeURIComponent(slug)}/${encodeURIComponent(fid)}?rel=${encodeURIComponent(rel)}`;
        return serveCached(env, ctx, key, "image/jpeg", request, macUrl(env, macSub), true);
      }
      const key = `cache/media/${fid}/${h}_${v}`;
      const macSub = `media/${encodeURIComponent(slug)}/${encodeURIComponent(fid)}?rel=${encodeURIComponent(rel)}`;
      return serveCached(env, ctx, key, ctypeOf(rel), request, macUrl(env, macSub), true);
    }
    return serveIndex(env);
  },
};
