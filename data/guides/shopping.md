# 새 상품 가격비교 검색 가이드 (`[sense:search_shopping]`)

새 상품의 값을 알아볼 때 쓰는 어휘. 중고 매물은 `[sense:used]`, 외주·프리랜서는
`[sense:freelance]` 가 따로 있다 — 이 문서는 **새 상품 가격비교**만 다룬다.

```
[sense:search_shopping]{query: "무선 이어폰"}                 # 다나와 가격비교(기본이자 유일)
[sense:search_shopping]{query: "노트북", display: 10}
```

통화 = `{total, items: [{name, price, mall, link, image, category, site, spec}]}`
(`price` 는 콤마 없는 숫자 문자열, `spec` 은 다나와 스펙 요약 한 줄.)

## 1. site 축 — 이제 다나와 하나뿐

| site | 소스 | 어디서 되나 | 비고 |
|------|------|------------|------|
| `danawa` (기본) | 다나와 가격비교 | **PC·폰 모두** | 순수 HTTP. 상품명·최저가·스펙·상품 링크 |
| `naver` | — | 죽음 | 안내 문구만 반환 (아래 §3) |

`site` 를 생략하면 다나와다. **사실상 쓸 일이 없는 파라미터**이니 그냥 빼고 불러라.

### ★은퇴한 축: `used` · `all` (2026-08-04)

`site: "used"`(중고나라·번개장터 Playwright 스크래핑)와 그걸 합치던 `site: "all"` 은
**어휘에서 제거했다**. 되살리지 말 것 — 두 가지 이유가 겹친다.

1. **죽어 있었다.** 두 사이트 개편으로 셀렉터(`ul.grid > li`,
   `div[class*='ProductItem']`)가 낡아 **라이브 0건**이었다(실측: 11.6초 걸려 빈 목록).
   두 블록 다 `except: pass` 라 실패가 침묵해서, 호출자는 "중고 매물이 없다"와
   "긁기가 깨졌다"를 구별할 수 없었다.
2. **고칠 가치가 없다.** 바로 그 두 소스를 **`[sense:used]` 가 내부 API 로 이미 더 잘
   준다** — 실측 번개장터 0.1초·중고나라 0.3초(스크래퍼의 11.6초 대비 40배 이상).
   소스도 넷(번개장터·당근·중고나라·네이버카페)이고 동네 스코프까지 되며,
   브라우저 자동화가 아니라 **폰에서도 돈다**. 스크래퍼를 고쳐 봐야 더 느리고 더 약한
   두 번째 창구가 하나 더 생길 뿐이다.

→ **중고 매물은 `[sense:used]`.** 자세한 건 `used_market.md`.

옛 습관으로 `site: "used"`/`"all"` 을 넣어도 에러는 안 난다 — 다나와 결과에
`note`(중고는 `[sense:used]` 로 가라)를 붙여 돌려준다.

## 2. 다나와 (기본 축)

- 엔드포인트 = `search.danawa.com/dsearch.php` 검색 결과 HTML. 상품 목록이 **첫 HTML 에
  SSR 로 박혀 있어** 정규식 파싱으로 충분하다 (크몽처럼 클라이언트 fetch 구조가 아니다).
- **봇 차단도 TLS 지문 검사도 없다** — `curl_cffi` 크롬 위장조차 불필요하고 stdlib
  `urllib` 만으로 200 이 나온다(실측). 직방·크몽과 달리 위장이 필요 없는 순한 소스.
  → 그래서 `tool_danawa.py` 는 curl_cffi 가 있으면 쓰고 **없으면 urllib 로 폴백**한다.
  이 폴백이 폰(Chaquopy — curl_cffi 없음) 동작의 전부다. 지우지 말 것.
- `limit` 파라미터는 다나와가 30/60/90 만 받는다 → 30 을 받아 클라이언트에서 자른다.
- 상품 카드 = `<li id="productItem숫자">`, 이름 = `p.prod_name > a`,
  가격 = `p.price_sect ... <strong>`, 스펙 = `div.spec_list`.
- 상품 URL = `prod.danawa.com/info/?pcode=…` (그대로 열림).

## 3. ★네이버 축은 죽었다 (2026-08-04 실측 종결)

되살리려 시도하기 전에 이 절을 읽어라. **두 겹 모두 막혔다.**

**① 공식 오픈API** — `/v1/search/shop.json` = `404 SE05 "존재하지 않는 검색 api"`.
네이버가 은퇴시켰다. `NAVER_CLIENT_ID` 와 무관하며 book/doc 축도 같이 죽었다.

**② 내부 API 발굴** (직방 `tool_zigbang`·크몽 `tool_freelance` 선례로 시도) — 전부 차단:

- `search.shopping.naver.com/api/search/all` → **418** (I'm a teapot = WAF 봇 차단).
  ★판별법: **없는 경로는 404 `text/plain` 9바이트**로 답한다. 즉 418 은
  "경로는 살아있는데 WAF 가 막는다"는 뜻이지 "없다"가 아니다.
  `/ns/v1/search/paged-composite-cards` 도 418(존재+차단).
- 검색 페이지 HTML(웹·`m.shopping`·`msearch.shopping`) 전부 418 → SSR 추출 경로도 없음.
- 쿠키 부트스트랩(`naver.com` → `shopping.naver.com` 방문 후 재시도)도 418 그대로.
- `curl_cffi impersonate="chrome"` **무효** — TLS 지문 위장으로 뚫리는 층이 아니다.
- **실제 창을 띄운 Chromium(headed)조차 캡차**로 착지: `ncpt.naver.com/v1/wcpt/*`
  영수증 이미지 문제 + 쿠키 `sus_val`·`X-Wtm-Cpt-Tk`(네이버 WTM 봇탐지 플랫폼).
  → headless 탐지가 아니라 **자동화 전면 게이트**다.
- `robots.txt` = `User-agent: * / Disallow: /` — 정책상으로도 금지.

남은 길은 캡차를 푸는 것뿐인데 그건 하지 않는다(우회 금지이고, 애초에 언제 깨질지 모르는
토대다). 새 플러스스토어(`shopping.naver.com/ns/search`)도 자동화 브라우저에선 302 →
"지금 이 서비스와 연결할 수 없습니다" 오류 면으로 간다.

**대체 후보도 실측함**: 통합검색(`search.naver.com`)은 200 이 나오지만 고유 상품이
**3개**뿐이고 대부분 광고 블록이라 검색 소스로 부적합하다(robots 도 `Disallow: /`).

→ 되살릴 여지가 생겼는지 보려면 **`/api/search/all` 이 418 에서 200 으로 바뀌었는지**부터
재실측하라. 그 전엔 다른 시도가 다 헛수고다.

## 4. 자주 하는 실수

- 중고를 이 어휘로 찾는 것 — `site: "used"`/`"all"` 축은 은퇴했다(§1). `[sense:used]`.
- 은퇴한 중고 스크래퍼를 "고쳐 되살리는" 것 — §1 의 두 번째 이유를 먼저 읽을 것.
  셀렉터를 고칠 수 있느냐가 아니라, 고쳐도 `[sense:used]` 보다 느리고 약하다는 게 요점이다.
- `price` 를 그대로 출력하는 것 — 콤마 없는 숫자 문자열이라 사람에게 보여줄 땐 포맷 필요.
- 네이버 쇼핑을 다시 붙이려 드는 것 — §3 을 먼저 읽을 것.
