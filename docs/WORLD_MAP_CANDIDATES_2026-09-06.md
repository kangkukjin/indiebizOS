# 세계의 지도 — 1차 조사: 어휘화되지 않은 분야 표준 리소스 (2026-09-06)

> 사용자 요청: "네가 서치해서 그런 목록을 만들어봐 — 아직 어휘화되지는 않았지만 잠재적으로 쓸모있는, 그 분야에서는 많은 사람들이 사용하는 리소스." 배경: 지금 어휘는 소유자 개인 지식에서 나왔고, 그 지식 밖의 분야는 어휘를 만들 생각조차 못했다. 세계의 지도는 그 사각지대를 비추기 위한 것이다. 사용자 경계: 강력한 것과 사소한 것을 섞으면 지도가 망가진다 — 풍부함이 아니라 선별.

## 0. 방법과 선별 기준

- 조사원 5 (부류 A~E) 병렬, 웹 검색 약 200회 + 정본 페이지 정독. 표 171행, 전 행에 근거 URL 과 확인일. 원본 표는 `docs/world_map/A~E_*.md` (겹침 메모·죽음 목록 포함).
- 선별 기준: ① 그 분야 실무자 대다수가 쓰는 사실상 표준(상위 2~3) ② 무료·오픈 또는 실질 무료 티어 ③ 프로그램으로 부를 수 있음 ④ **2026-09 현재 살아 있음**(검색으로 확인) ⑤ 이미 어휘인 것은 제외, 겹치면 메모로.
- 등급: S=유일·압도적 표준, A=상위 표준, B=대체 있음. 원본 표 기준 **S 59 · A 73 · B 39**.
- 이 문서는 등급이 아니라 **몸에 난 구멍의 크기**로 층을 나눈다. 1층은 지금 몸이 못 하는 일이 뚜렷하고 이 소유자의 빈도가 높은 것, 2층은 나머지 어휘 후보, 3층은 어휘가 아니라 `[self:script]` 로 얼릴 라이브러리, 4층은 새 낱말이 아니라 기존 낱말의 `source`/`channel_type` 옵션.

## 1. 1층 — 지금 몸에 뚜렷한 구멍 (Top 12)

| # | 구멍 | 표준 리소스 | 어휘 후보 형태 | 왜 지금 |
|---|---|---|---|---|
| 1 | **인터넷 너머 내 폰에 닿는 알림이 없다** (`self:notify_user`=데스크탑, `limbs:phone`=USB) | Telegram Bot API(S) · 카카오톡 "나에게 보내기"(S, 검수 불요) · ntfy(A) · **Apprise**(A, 100+ 서비스 한 URL) | `others:channel_send{channel_type:"telegram"\|"kakao_me"\|"ntfy"}` — channel_engine 확장, Apprise 를 다중 백엔드로 | 자율주행 보고서·승인 요청·경보가 밖에 있는 사용자에게 못 간다 |
| 2 | **영상·음성 변환 어휘가 없다** — 몸이 ffmpeg 를 8파일에서 내부 호출하면서 | ffmpeg 9(S) | `table:media{op: convert\|trim\|concat\|extract_audio\|probe\|thumbnail}` | 유튜브 작업 매 호 셸로 우회 |
| 3 | **파일 음성 전사(오프라인·한국어 대량)가 없다** — `sense:listen` 은 마이크+클라우드 | whisper.cpp / mlx-whisper(맥) · faster-whisper(윈)(S) | `engines:stt{path, lang, format:"srt"}` | 강의·유튜브 자막·회의 녹음 |
| 4 | **문서 any→any 변환이 없다** — `table:document` 는 렌더 전용 | pandoc(S) · LibreOffice headless(S, 내부 사용) · Calibre(S, epub) · Docling(A, PDF→구조) | `table:document{op:"convert", to, engine}` + `self:read{engine:"docling"}` | 저술·출판 파이프(docx↔md↔epub↔hwpx) |
| 5 | **공공데이터포털을 "찾아서 부르는" 관문이 없다** — 데이터셋 6개만 코드에 열거 | data.go.kr 카탈로그+범용 호출(S) · 기상청 API허브(S, 관측·특보·지진) · KIPRIS 특허(S) · TAGO 대중교통(A) | `sense:datagokr{op:"search"\|"call"}` · `sense:weather{source:"kma"}` · `sense:patent` · `sense:transit` | 한국 공공 API 수천 개가 데이터로 들어온다 |
| 6 | **월·일 단위 거시 데이터가 없다** — `sense:world_bank` 는 연간 | FRED(S, 무료 키 필수) · 한국은행 ECOS(S) · OECD/IMF/BIS SDMX(A) · Frankfurter 환율(A) | `sense:macro{source:"fred"\|"ecos"\|"oecd"\|"imf"}` · `sense:fx` | 투자·경제 보고서의 정본 소스 |
| 7 | **사라진 페이지·과거 판본을 못 본다** | Wayback Availability/CDX(S) | `sense:wayback{op:"snapshots"\|"at"\|"save", url}` | `sense:crawl` 404 의 자연스러운 짝 |
| 8 | **한국 밖 지리가 없다** — 장소·경로·역지오코딩 전부 카카오 | OSM Overpass/Nominatim/OSRM(S/A) · GeoNames(A) | `sense:osm{op:"query"\|"geocode"\|"reverse"\|"route"}` (한국 밖 폴백) | 해외 여행·해외 부동산·세계 데이터 |
| 9 | **구글 문서·표·일정과 외부 캘린더 동기화가 없다** — Gmail 만 | Google Sheets/Drive/Docs/Calendar(S, 개인 OAuth 심사 불요) · CalDAV/CardDAV(S, iCloud·Nextcloud) · Notion(S) · Todoist(A) · MS Graph(A) | `self:gdrive` · `self:sheet{source:"google"}` · `self:calendar{op:"sync", server}` · `self:notion` · `self:todo` | 사무의 표준 표면 |
| 10 | **세계의 손(MCP)을 못 빌린다** | MCP 공식 레지스트리(S, 9,600 서버) + 상위 서버군(GitHub·filesystem·Notion…) | `sense:mcp{op:"search"}` → `self:package{kind:"mcp"}` → `limbs:mcp{server, tool, args}` | 어휘 없이 남의 도구를 쓰는 유일한 일반 통로. `sense:openapi`(규격 있는 API 는 어휘 없이 부른다)와 한 쌍 |
| 11 | **글로벌 뉴스 관측·백과 산문이 없다** | GDELT DOC 2.0(S, 무키) · Wikipedia REST(S, 산문 — `sense:entity` 는 트리플) | `sense:gdelt{query, days, country}` · `sense:wiki{op:"summary"\|"page"}` | 보고서 소스. 상업 뉴스 API 는 전부 유료화됨 |
| 12 | **한국어 형태소 분석이 없다** | Kiwi kiwipiepy(S, Java 불요) | `table:morph{op:"tokenize"\|"nouns"\|"split"}` | 블로그·자막·검색 파이프의 변환자 |

## 2. 2층 — 나머지 어휘 후보 (S/A, 반복되는 '질의→items' 또는 '효과' 흐름)

| 부류 | 리소스 | 어휘 후보 | 등급 |
|---|---|---|---|
| 집·IoT | Home Assistant REST/WS + MQTT(Mosquitto/paho); Zigbee2MQTT·ESPHome 은 그 위 | `limbs:home{op:"call"}` · `sense:home{op:"state"}` · `sense/limbs:mqtt` | S |
| 개발 | GitHub REST/GraphQL + gh · Docker Engine API · PyPI/npm JSON API | `limbs:github` · `sense:github` · `limbs:container` · `sense:package` | S/A/B |
| 원격·망 | SSH(paramiko 5) · Tailscale(Personal 무료) · mDNS(zeroconf) · WebDAV(rclone remote) | `limbs:ssh{host, cmd}` · `sense:net{op:"peers"\|"discover"}` | S/B |
| 백업·동기화 | rclone(S, 70+ 클라우드) · restic(A) · Syncthing(A, P2P) | `limbs:cloud_storage{op:"sync"\|"ls"\|"copy"}` · `self:backup{op:"snapshot"\|"restore"}` (`data/_backups/` 규약의 기계화) · `others:sync` | S/A |
| 로컬 AI | Hugging Face Hub `hf`(S) · ComfyUI(S, 로컬 이미지 생성) · llama.cpp/MLX(A, 모델 관리) | `sense:hf{op:"search"}` · `self:download{source:"hf"}` · `engines:image_local{workflow}` · `self:model{op:"serve"\|"convert"}` | S/A |
| 메타데이터·OCR·PDF | ExifTool(S) · Tesseract/PaddleOCR/OCRmyPDF(A) · qpdf/pikepdf(A) · ImageMagick/libvips(A) | `sense:exif{op:"read"\|"strip"\|"rename_by_date"}` · `table:ocr{engine}` · `table:pdf{op:"merge"\|"split"}` · `table:image{op:"resize"\|"convert"}` | S/A |
| 음악 | Chromaprint+AcoustID+MusicBrainz(A) · Demucs(A) · Last.fm/ListenBrainz(A/B) | `self:music{op:"identify"\|"scrobble"}` · `table:audio{op:"stems"}` | A |
| 분산 소셜 | Bluesky AT Protocol(A, 심사 없음) · Mastodon/ActivityPub(A) | `others:feed{source}` · `others:publish{to}` (현 publish 는 Nostr 전용) | A |
| 메신저(추가) | Discord webhook/Bot · Matrix(matrix-nio) · signal-cli | `channel_type:"discord"\|"matrix"\|"signal"` | A |
| 위임 허브 | n8n CE(A) · Node-RED(A) · A2A 1.0(A) | `others:delegate{to:"n8n"}` · `others:ask` 의 A2A 백엔드 | A |
| 지식 관리 | Obsidian CLI 1.12(A) · Zotero 7 로컬 API(A) | `self:vault{op:"search"\|"append"}` · `self:library{op:"search"\|"cite"}` | A |
| 학술 보강 | Crossref(S, DOI 정본) · Unpaywall(A) · ORCID(A) | `sense:paper{op:"resolve"\|"open_access"}` · `sense:researcher{source:"orcid"}` | S/A |
| 세계 데이터 | Our World in Data(A) · GeoNames(A) · NASA EONET(B) | `sense:owid{chart_slug}` · `sense:geo` · `sense:world{op:"events"}` | A/B |
| 과학 DB | Copernicus CDS/ERA5 cdsapi(S) · Materials Project(S) · RCSB PDB/UniProt(S) | `sense:climate` · `sense:material` · `sense:protein` | S |
| 생활 | Podcast Index(S) · TMDB(S) · Open Food Facts/USDA(S/A) · 스마트택배(A) · 네이버 데이터랩(A) · Anki(S, ★포트 8765 충돌) · Apple Health 내보내기(A) · Garmin 비공식(B) | `sense:podcast` · `sense:movie` · `sense:food` · `sense:parcel` · `sense:trend` · `engines:flashcard` · `self:health{op:"import"}` | S/A |
| 번역 | DeepL(A, Free 신규 종료 보도) · LibreTranslate/Argos(A, 로컬) | `engines:translate{engine}` | A |
| 애플 | Shortcuts CLI + EventKit(ekctl) · iCloud CalDAV | `limbs:shortcut{name}` · `self:calendar{source:"icloud"}` | A |

## 3. 3층 — 어휘 아님, `[self:script]` 로 얼릴 것 (분야 표준 라이브러리·프로그램)

`world_tools.md` 가 이 층의 지도다. 조사에서 새로 확인된 것(전부 살아 있음, 대부분 pip 휠 즉시):

- **최적화·통계**: OR-Tools(S) · CVXPY(S) · JAX(A) · PyMC/CmdStanPy(A) · Numba(A) · Dask(A) · scikit-image(A)
- **공학 시뮬**: Gmsh(S, pip) → CalculiX/Elmer/FEniCSx/OpenFOAM(🔧) → VTK/PyVista(S, pip)·ParaView(A) · OpenModelica(A, 맥 어려움) · Cantera(S) · KiCad `kicad-cli`(S) · ngspice(S) · CadQuery/build123d(A, 코드 CAD)
- **물리·화학·생명**: LAMMPS(S, pip 휠) · GROMACS(S, brew) · ASE(S) · pymatgen(S) · PySCF(A, Psi4 는 conda 전용) · MDAnalysis/OpenMM(B)
- **천문·지구·지리**: xarray+netCDF4(S) · SunPy(B) · healpy(A, arm64 휠 불확실) · H3(S) · QGIS `qgis_process`(A) · PostGIS(B — 개인 몸은 DuckDB spatial)
- **수학·증명**: Z3(S) · Lean 4+Mathlib(S, Coq→Rocq 개명) · passagemath(A, SageMath pip) · Wolfram Engine(유료·개발자 무료) · PennyLane(A) · igraph(A)
- **시각화·출판**: Graphviz(S) · Manim(S) · Altair(A) · Bokeh(B) · Quarto(S) · marimo(A)
- 다른 언어: Julia 1.12 · R 4.6(juliacall/rpy2 브리지)

**초안 지도 정정(반영함)**: FEniCS→FEniCSx 0.11(conda) · OpenFOAM 맥=`brew install --no-quarantine gerlero/openfoam/openfoam` · Open Babel 휠 py≤3.13 · Blender bpy LTS 밖 판 PyPI 삭제(바이너리 헤드리스 유지) · Jupyter 에 marimo 병기 · PostgreSQL 행에 DuckDB spatial 우선.

## 4. 4층 — 새 낱말이 아니라 옵션 확장 (겹침 메모 요지)

- `sense:paper`: `source:"europepmc"|"core"` · `sense:book`: `source:"openlibrary"` · `sense:stock`: Alpha Vantage/Polygon source · `sense:feed`: JSON Feed 1.1 분기(feedparser 미지원) · `sense:video`: OAuth 로 내 구독/재생목록
- `others:channel_*`: `channel_type:"imap"`(Gmail 외 계정, imap-tools) — 지금은 Gmail·Nostr 둘뿐
- 프로바이더 층: LM Studio 는 base_url 옵션으로, Ollama 모델 관리는 `self:model` 에
- `self:read`: `format:"ics"|"vcf"` · `self:trigger`: `type:"websub"`, Standard Webhooks 서명 검증

## 5. 기존 어휘 수리 후보 (조사의 부산물 — 지도와 무관하게 확인 필요)

| 항목 | 사실 | 확인할 것 |
|---|---|---|
| **OpenAlex API 키 필수** (2026-02-13~, 무료 계정 일 $1) | `sense:paper` 기본 소스가 openalex | 무키 호출이면 지금 깨져 있음 — `OPENALEX_API_KEY` 배선 |
| **네이버 검색 API → NAVER API HUB 이관** (2026-07-31 신규 중단, 책·쇼핑·전문자료 종료, 구 인증 2027-06-30 까지) | `sense:search{naver}`·`sense:restaurant` 가 `openapi.naver.com` 사용 | 도메인·헤더(`X-NCP-APIGW-API-KEY-ID/KEY`) 이관 |
| **Wikimedia 글로벌 한도** (UA 없는 IP 10 req/분) | `sense:entity` | 연락처 포함 User-Agent |
| Crossref polite pool(`mailto=`) · PMC 1만 건 상한 · arXiv 429(3초 간격) | `sense:paper` 각 소스 | 한도 준수 배선 |
| **AnkiConnect 기본 포트 8765** | indiebizOS 백엔드 포트와 동일 | Anki 어휘화 시 충돌 선처리 |
| Bing Search API 전 계열 종료(2025-08) | 몸에 bing 참조가 남아 있으면 죽은 통로 | grep 확인 |

## 6. 쓰지 말 것 (죽음·유료화·개인 불가 — 지도에 남길 가치)

X(Twitter) API(무료 폐지·종량제) · Reddit API(신규 앱 수동 승인) · WhatsApp Business(개인 불가) · 카카오 친구 발송/알림톡(검수·유료 — 나에게 보내기만) · IFTTT/Zapier 무료(사실상 죽음 → n8n) · ngrok 무료(→ Cloudflare Tunnel, 어휘 있음) · Telethon 사용자 계정 자동화(밴 위험 → Bot API) · Slack 웹훅(legacy) · JMAP(채택 미미, IMAP 유지) · Bing Search(종료) · NewsAPI(무료=개발 전용) · HathiTrust Data API(종료) · Papago API(종료 → DeepL/로컬) · Spotify Web API(2026-02 Premium·5명·엔드포인트 제거) · Strava API(유료+AI 컨텍스트 주입 금지 — indiebizOS 에 넣을 수 없음) · Trakt(API 앱=VIP) · Goodreads(2020 종료) · Pocket(2025 종료) · Google Photos Library API(앱 업로드분만) · Google Fit(2026 말 종료 → Health Connect) · SmartThings(2026-10 유료 → HA) · 오픈뱅킹/마이데이터(법인 심사 — 폰 결제 알림 포획이 현실적 최선) · 홈택스(개인 API 없음 → browser) · 쿠팡/네이버 커머스(판매자 전용) · 배달 플랫폼(API 없음) · Khan/Coursera(API 없음) · Google Keep(엔터프라이즈 전용) · 후계: Coq→Rocq, python-igraph→igraph, pystan→CmdStanPy, huggingface-cli→`hf`, SoX→ffmpeg, Spleeter→Demucs, A1111→ComfyUI, Mendeley→Zotero, Resilio→Syncthing

## 7. "지도가 실제로 도움이 되는가" — 관찰 설계

사용자 물음: *지도가 있다고 알려주기만 하면 에이전트가 이따금 들여다보고 새 연결·도구를 찾아낼까?* 아직 모른다. 지금 입구는 12_ibl_only Key Principles 2 의 한 줄뿐이고, 회상은 과거 성공 문장(해마)이 우선이라 지도가 후보에 오르는 경로는 좁다. 판별은 다음 셋으로 한다.

1. **열었나** — 주행당 `read_guide world_tools.md` 호출 수(episode_log). 0 이면 지도가 아니라 **입구**의 문제(프롬프트 한 줄이 약함, 또는 `<execution_map>` 가지에 안 걸림).
2. **골랐나** — 지도에 있는 도구를 써서 성공한 에피소드 수, 그리고 그 문장이 해마에 저장·재회상되는지(회상 귀속). 열었는데 안 고르면 지도 **내용**의 문제(구멍이 안 보이거나 통로가 불명).
3. **승인이 왔나** — `approval_required` 봉투 수와 사용자 승인/거부 비율. 골랐는데 승인이 없으면 **표면**의 문제.

2주 관찰 뒤에도 1 이 0 이면 대안은 둘이다. (a) 지도를 목차 한 층(부류 12개 이름)으로 상시 주입하고 상세는 회상으로 — `<memory_map>` 과 같은 규약. (b) 반대로 지도를 버리고 1층 12개를 바로 어휘로 결정화 — 사용자 판정 대상(언어 개정).

## 8. 다음 걸음 (판정 요청 없이 할 수 있는 것 / 판정 대상)

- **할 수 있는 것**: §5 수리 후보 확인(OpenAlex 키·네이버 HUB·UA) · `world_tools.md` 3층 갱신(반영함) · §7 계수 로그(episode_log 에 read_guide 파일명·install_lib 상태가 이미 남는지 확인)
- **판정 대상(언어 개정)**: 1층 12개 중 어느 것을 어휘로 결정화할지, 그리고 지도의 형태(별도 트리 vs 가이드 한 장 vs 목차 상시 주입). 원칙상 새 낱말의 기본 답은 "아니오" 이므로, 결정화는 실제 반복(해마 회상 귀속)이 생긴 뒤가 맞다 — 단 1번(폰 알림 채널)·2번(ffmpeg)·5번(공공데이터 관문)은 반복이 이미 셸 우회로 존재한다.
