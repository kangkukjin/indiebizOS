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

async function serveCached(env, ctx, cacheKey, ctype, request, macSub, cacheable) {
  // R2 캐시 우선 → 없으면 맥에서 pull. cacheable=true 면 전체 응답을 R2 에 캐시.
  const rangeHeader = request.headers.get("range");
  const cached = await env.BUCKET.get(cacheKey, rangeOpts(rangeHeader));
  if (cached) return r2Serve(cached, ctype, rangeHeader);

  if (!env.ORIGIN_BASE || !env.SHOWCASE_SECRET) return new Response("origin 미설정", { status: 500 });
  const oheaders = { "X-Showcase-Secret": env.SHOWCASE_SECRET };
  if (rangeHeader) oheaders["Range"] = rangeHeader;
  let orig;
  try {
    orig = await fetch(macUrl(env, macSub), { headers: oheaders });
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
        return serveCached(env, ctx, key, "image/jpeg", request, macSub, true);
      }
      const key = `cache/media/${fid}/${h}_${v}`;
      const macSub = `media/${encodeURIComponent(slug)}/${encodeURIComponent(fid)}?rel=${encodeURIComponent(rel)}`;
      return serveCached(env, ctx, key, ctypeOf(rel), request, macSub, true);
    }
    return serveIndex(env);
  },
};
