/**
 * 공개파일 Worker — 멍청한 substrate + 온디맨드 원본(option 1) + 바스켓(비밀 공개주소).
 *
 * 라우팅:
 *   루트(전체공개):
 *     - manifest.json / thumbs/* → R2 직접. media/<fid>/<iid> → 온디맨드(맥 pull + R2 캐시).
 *     - thumbs·media 는 fids.json(루트 공개 폴더 화이트리스트)로 게이트 — 바스켓 전용
 *       (루트 비공개) 폴더의 객체가 bare 경로로 새지 않게.
 *   바스켓(/s/<slug>/...): slug 자체가 비밀 자격증명.
 *     - /s/<slug>/manifest.json → R2 spaces/<slug>/manifest.json.
 *     - /s/<slug>/thumbs·media/<fid>/... → spaces/<slug>/fids.json 에 fid 가 있어야 서빙
 *       (없으면 404). 실제 객체는 전역(thumbs/<fid>·media/<fid>) 공유 — 바스켓 간 중복 없음.
 *     - 그 외 → index.html(SPA). SPA 가 location 에서 스코프를 읽어 URL 을 접두사한다.
 *
 * env: BUCKET(R2), ORIGIN_BASE(예 https://finder.kukjinkang.uk), SHOWCASE_SECRET,
 *      SHOWCASE_TOKEN(선택 — 루트 전용 링크 게이트. /s/ 스코프는 slug 가 게이트라 면제).
 */

const CT = {
  json: "application/json", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
  webp: "image/webp", gif: "image/gif", heic: "image/heic",
  mp4: "video/mp4", webm: "video/webm", mov: "video/quicktime", m4v: "video/x-m4v", mkv: "video/x-matroska",
};
function ctypeOf(key) {
  return CT[key.split(".").pop().toLowerCase()] || "application/octet-stream";
}
function rangeOpts(rangeHeader) {
  if (!rangeHeader) return {};
  const m = /bytes=(\d*)-(\d*)/.exec(rangeHeader);
  if (!m) return {};
  const offset = m[1] ? parseInt(m[1], 10) : undefined;
  const end = m[2] ? parseInt(m[2], 10) : undefined;
  if (offset === undefined) return {};
  return { range: { offset, length: end !== undefined ? end - offset + 1 : undefined } };
}
function r2Response(obj, key, rangeHeader) {
  const headers = new Headers();
  headers.set("content-type", ctypeOf(key));
  headers.set("cache-control", key.endsWith("manifest.json") ? "no-cache" : "public, max-age=86400");
  headers.set("accept-ranges", "bytes");
  obj.writeHttpMetadata(headers);
  if (rangeHeader && obj.range) {
    const start = obj.range.offset || 0;
    const len = obj.range.length || (obj.size - start);
    headers.set("content-range", `bytes ${start}-${start + len - 1}/${obj.size}`);
    return new Response(obj.body, { status: 206, headers });
  }
  return new Response(obj.body, { headers });
}

async function serveR2(env, request, key) {
  const rangeHeader = request.headers.get("range");
  const obj = await env.BUCKET.get(key, rangeOpts(rangeHeader));
  if (!obj) return new Response("404", { status: 404 });
  return r2Response(obj, key, rangeHeader);
}

// fids 화이트리스트 캐시(아이솔레이트 30초) — 게이트 조회가 그리드 100+ 썸네일마다
// R2 GET 을 내는 걸 줄인다. 30초 staleness = 바스켓/폴더 편집이 반영되는 최대 지연.
const _fidsCache = new Map(); // prefix -> {fids:Set, exp:number, present:boolean}
async function fidsFor(env, prefix) {
  const now = Date.now();
  const hit = _fidsCache.get(prefix);
  if (hit && hit.exp > now) return hit;
  let fids = new Set(), present = false;
  try {
    const obj = await env.BUCKET.get(prefix + "fids.json");
    if (obj) {
      present = true;
      const arr = await obj.json();
      if (Array.isArray(arr)) fids = new Set(arr);
    }
  } catch (e) { /* 파싱 실패 = 화이트리스트 없음 취급 */ }
  const rec = { fids, exp: now + 30000, present };
  _fidsCache.set(prefix, rec);
  return rec;
}

async function serveMedia(env, ctx, request, objectKey) {
  // objectKey = media/<fid>/<iid> (전역). R2 캐시 우선, 없으면 맥(ORIGIN_BASE)에서 온디맨드.
  const rangeHeader = request.headers.get("range");
  const cached = await env.BUCKET.get(objectKey, rangeOpts(rangeHeader));
  if (cached) return r2Response(cached, objectKey, rangeHeader);

  if (!env.ORIGIN_BASE || !env.SHOWCASE_SECRET) {
    return new Response("origin 미설정", { status: 500 });
  }
  const parts = objectKey.split("/");        // ["media", fid, iid]
  if (parts.length < 3) return new Response("404", { status: 404 });
  const originUrl = `${env.ORIGIN_BASE.replace(/\/$/, "")}/showcase/origin/${encodeURIComponent(parts[1])}/${encodeURIComponent(parts[2])}`;
  const oheaders = { "X-Showcase-Secret": env.SHOWCASE_SECRET };
  if (rangeHeader) oheaders["Range"] = rangeHeader;   // 동영상 seek 범위 그대로 전달.
  let orig;
  try {
    orig = await fetch(originUrl, { headers: oheaders });
  } catch (e) {
    return new Response("원본을 지금 불러올 수 없습니다 (맥 접근 불가).", { status: 503 });
  }
  if (!orig.ok || !orig.body) {
    return new Response("원본을 지금 불러올 수 없습니다 (맥이 꺼져 있거나 비공개).", { status: 503 });
  }
  const ctype = orig.headers.get("content-type") || ctypeOf(objectKey);
  // Range 응답(206): 부분이라 캐시하지 않고 중계 — 긴 영상 seek 이 곧바로.
  if (rangeHeader && orig.status === 206) {
    const h = new Headers();
    h.set("content-type", ctype);
    h.set("accept-ranges", "bytes");
    const cr = orig.headers.get("content-range"); if (cr) h.set("content-range", cr);
    const cl = orig.headers.get("content-length"); if (cl) h.set("content-length", cl);
    h.set("cache-control", "public, max-age=86400");
    return new Response(orig.body, { status: 206, headers: h });
  }
  // 전체 요청: 스트림 분기 — 하나는 뷰어로, 하나는 R2 캐시로(메모리에 안 담음).
  const [toClient, toCache] = orig.body.tee();
  ctx.waitUntil(env.BUCKET.put(objectKey, toCache, { httpMetadata: { contentType: ctype } }));
  return new Response(toClient, {
    headers: { "content-type": ctype, "accept-ranges": "bytes", "cache-control": "public, max-age=86400" },
  });
}

async function serveIndex(env) {
  if (env.BUCKET) {
    const idx = await env.BUCKET.get("index.html");
    if (idx) {
      const h = new Headers();
      h.set("content-type", "text/html; charset=utf-8");
      h.set("cache-control", "no-cache");
      return new Response(idx.body, { headers: h });
    }
  }
  return new Response("index.html 미배포 — showcase sync 로 업로드 필요", { status: 500 });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = decodeURIComponent(url.pathname).replace(/^\/+/, "");
    if (!env.BUCKET) return serveIndex(env);

    // 스코프 판별 — s/<slug>/<rest>. slug 자체가 비밀 자격증명.
    const isScoped = path === "s" || path.startsWith("s/");
    let rest = path, objPrefix = "", allowPrefix = "";
    if (isScoped) {
      const parts = path.split("/");          // ["s", slug, ...rest]
      const slug = parts[1] || "";
      if (!slug) return serveIndex(env);
      rest = parts.slice(2).join("/");         // "" | "manifest.json" | "thumbs/.." | "media/.." | "f/.."
      objPrefix = `spaces/${slug}/`;           // manifest 는 스코프 프리픽스
      allowPrefix = objPrefix;                 // fids.json 도 스코프
    } else {
      // 루트 전용 링크 토큰(설정 시). 스코프는 slug 가 게이트라 면제.
      if (env.SHOWCASE_TOKEN && env.SHOWCASE_TOKEN.length > 0) {
        if ((url.searchParams.get("t") || "") !== env.SHOWCASE_TOKEN) {
          return new Response("403 — 접근 토큰이 필요합니다.", { status: 403 });
        }
      }
    }

    // manifest.json (루트 or 스코프)
    if (rest === "manifest.json") {
      return serveR2(env, request, objPrefix + "manifest.json");
    }

    // thumbs/* · media/* — fids 화이트리스트 게이트
    if (rest.startsWith("thumbs/") || rest.startsWith("media/")) {
      const seg = rest.split("/");
      const fid = seg[1] || "";
      const allow = await fidsFor(env, allowPrefix);
      // 루트에서 fids.json 이 아직 없으면(구배포 이관 중) fail-open = 옛 전체공개 동작.
      // 스코프에선 fail-closed — 화이트리스트 없으면 접근 불가(비밀 보장).
      const gated = isScoped ? true : allow.present;
      if (gated && !allow.fids.has(fid)) return new Response("404", { status: 404 });
      if (rest.startsWith("thumbs/")) return serveR2(env, request, rest);   // 전역 객체 키
      return serveMedia(env, ctx, request, rest);
    }

    // 그 외 → index.html (SPA; 루트·바스켓·딥링크 f/<fid> 모두)
    return serveIndex(env);
  },
};
