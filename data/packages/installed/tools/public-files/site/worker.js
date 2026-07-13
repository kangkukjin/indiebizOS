/**
 * 공개파일 Worker — 멍청한 substrate + 온디맨드 원본(option 1).
 *
 * 서빙:
 *   - manifest.json / thumbs/*  → R2 에서 직접(동기화가 미리 올림).
 *   - media/<fid>/<iid>         → 온디맨드: R2 캐시 우선, 없으면 맥(ORIGIN_BASE)에서
 *                                  끌어와 스트리밍하며 동시에 R2 에 캐시(본 것만 쌓임).
 *   - 그 외                     → R2 의 index.html (SPA).
 *
 * 대용량 동영상도 Worker 메모리에 통째로 안 올리도록 body.tee() 스트림 + waitUntil 캐시.
 *
 * env: BUCKET(R2), ORIGIN_BASE(예 https://finder.kukjinkang.uk), SHOWCASE_SECRET,
 *      SHOWCASE_TOKEN(선택 — 링크전용 게이트).
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
  headers.set("cache-control", key === "manifest.json" ? "no-cache" : "public, max-age=86400");
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

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = decodeURIComponent(url.pathname).replace(/^\/+/, "");

    // 토큰 게이트(SHOWCASE_TOKEN 설정 시 링크전용)
    if (env.SHOWCASE_TOKEN && env.SHOWCASE_TOKEN.length > 0) {
      if ((url.searchParams.get("t") || "") !== env.SHOWCASE_TOKEN) {
        return new Response("403 — 접근 토큰이 필요합니다.", { status: 403 });
      }
    }

    // manifest / thumbs — R2 직접
    if ((path === "manifest.json" || path.startsWith("thumbs/")) && env.BUCKET) {
      const rangeHeader = request.headers.get("range");
      const obj = await env.BUCKET.get(path, rangeOpts(rangeHeader));
      if (!obj) return new Response("404", { status: 404 });
      return r2Response(obj, path, rangeHeader);
    }

    // media/<fid>/<iid> — 온디맨드 원본
    if (path.startsWith("media/") && env.BUCKET) {
      const rangeHeader = request.headers.get("range");
      const cached = await env.BUCKET.get(path, rangeOpts(rangeHeader));
      if (cached) return r2Response(cached, path, rangeHeader);

      if (!env.ORIGIN_BASE || !env.SHOWCASE_SECRET) {
        return new Response("origin 미설정", { status: 500 });
      }
      const parts = path.split("/");           // ["media", fid, iid]
      if (parts.length < 3) return new Response("404", { status: 404 });
      const originUrl = `${env.ORIGIN_BASE.replace(/\/$/, "")}/showcase/origin/${encodeURIComponent(parts[1])}/${encodeURIComponent(parts[2])}`;
      // ★Range 를 origin 으로 전달 — 브라우저의 동영상 스트리밍/seek 범위를 그대로 넘겨
      // 긴 영상도 전체를 안 당기고 필요한 구간만 받아 즉시 재생·탐색.
      const oheaders = { "X-Showcase-Secret": env.SHOWCASE_SECRET };
      if (rangeHeader) oheaders["Range"] = rangeHeader;
      let orig;
      try {
        orig = await fetch(originUrl, { headers: oheaders });
      } catch (e) {
        return new Response("원본을 지금 불러올 수 없습니다 (맥 접근 불가).", { status: 503 });
      }
      if (!orig.ok || !orig.body) {
        return new Response("원본을 지금 불러올 수 없습니다 (맥이 꺼져 있거나 비공개).", { status: 503 });
      }
      const ctype = orig.headers.get("content-type") || ctypeOf(path);
      // Range 응답(206): 부분이라 R2 에 캐시하지 않고 그대로 중계 — 긴 영상 seek 이 곧바로 동작.
      if (rangeHeader && orig.status === 206) {
        const h = new Headers();
        h.set("content-type", ctype);
        h.set("accept-ranges", "bytes");
        const cr = orig.headers.get("content-range"); if (cr) h.set("content-range", cr);
        const cl = orig.headers.get("content-length"); if (cl) h.set("content-length", cl);
        h.set("cache-control", "public, max-age=86400");
        return new Response(orig.body, { status: 206, headers: h });
      }
      // 전체 요청(이미지 등): 스트림 분기 — 하나는 뷰어로, 하나는 R2 캐시로(메모리에 안 담음).
      const [toClient, toCache] = orig.body.tee();
      ctx.waitUntil(env.BUCKET.put(path, toCache, { httpMetadata: { contentType: ctype } }));
      return new Response(toClient, {
        headers: { "content-type": ctype, "accept-ranges": "bytes", "cache-control": "public, max-age=86400" },
      });
    }

    // 그 외 → R2 index.html (SPA)
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
  },
};
