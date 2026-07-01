# 웹 검색 가이드 (Web Search Guide)

일반 웹은 폴백이다 — indiebizOS는 여러 도메인에 *어휘(IBL 액션)*를 가져, 많은 검색을 일반 크롤보다 빠르고 구조적으로 한다. **먼저 어휘, 없으면 웹.**

## 1. 액션 먼저 — 어휘가 있으면 그게 빠르다
- 검색 전에 **이 도메인에 IBL 액션이 있는지 보라.** 있으면 일반 웹검색보다 빠르고·구조화돼 있고·공식 API(권위)다.
- 액션이 흔한 도메인: 구매·가격비교 · 법령·판례 · 논문·연구자 · 통계 · 기업·주가·공시 · 부동산 시세·매물 · 도서·고전 · 공연·전시 · 창업지원·경진 · 맛집·상권·지역 · 뉴스 · 날씨·CCTV · 유튜브·라디오.
- 구체 액션명·파라미터는 IBL 카탈로그(execute_ibl)에 있고, 복잡하면 `read_guide`로 도메인 가이드(예: "법률"·"통계"·"부동산")를 읽어라. **여기서 다시 나열하지 않는다.**
- **일반 웹검색(`search_naver`·`search_ddg`·`crawl`)은** 액션이 없거나, 액션 밖의 맥락·후기·비교가 필요할 때의 폴백. 배운 검색 관습(포식 기억)이 있으면 그걸 우선하라.

## 2. 일반 웹검색을 쓸 때 — 키워드·소스·언어·카테고리
- **키워드 (개인화의 핵심)**: 사용자의 말을 그대로 검색창에 넣지 말고 **문맥에 맞는 키워드를 골라 넣어라** — 사용자의 분야·의도·알려진 맥락(포식 기억 owner_model)·중의성 해소어를 얹어서. 검색창은 맥락을 모르지만 너는 안다 — **그게 일반 검색이 못 이기는 개인화 검색의 강점이다.** 예: 모호한 이름·용어는 분야·소속으로 좁히고, 의도(사기/알아보기/비교)에 맞는 어휘를 더한다.
- **소스**: 한국어·국내는 `search_naver`(국내 콘텐츠 압도적), 글로벌·영어는 `search_ddg`. 전문 사이트가 있으면 홈페이지 말고 *검색어·필터 박힌 결과 페이지*로 바로.
- **언어**: 대상 국가 언어로도 검색하라(일본→일본어, 글로벌→영어). 한국어만으론 현지 정보를 놓친다.
- **카테고리**: 넓게 잡아라("약"→의약품+건강식품+한방약+영양제…). 하나에 갇히면 관련 정보를 놓친다.

## 3. 넓게 → 좁게, 그리고 판단
- **1차 넓게**(키워드·언어·소스 다양, snippet이면 충분) → **2차 좁게**(유망 후보 2~3개만 `crawl`로 상세 검증). 안 나오면 키워드·카테고리·언어를 바꿔 재시도.
- **"없다"고 단정하지 말라**(못 찾은 것일 수 있음). **snippet만으로 확정하지 말고** 핵심은 원본 `crawl`로. **URL·제품명·수치를 지어내지 말라** — 검색으로 확인된 것만.

## 4. 웹 랜드마크 — 어디로 가나 (액션 없는 잔여)

*§1의 액션으로 닿는 도메인은 빼고, 일반 크롤로만 닿는 출처 지도.* 국적은 도메인의 본질을 따름(제도·로컬=한국 / AI·경제·외교·과학·지식=국제 권위).

### 한국 크롤 잔여 (제도·로컬)
- 경제·투자: [한국은행 ECOS](https://ecos.bok.or.kr) 거시 시계열 · [지표누리](https://index.go.kr) 국가지표 · [KRX 데이터](https://data.krx.co.kr) 시세·지수 · [FnGuide 컴퍼니가이드](https://comp.fnguide.com) 재무·컨센서스 · [세이브로](https://seibro.or.kr) 배당·권리
- 부동산: [R-ONE](https://www.reb.or.kr/r-one) 지수·동향 · [호갱노노](https://hogangnono.com) 실거래 지도 · [부동산플래닛](https://www.bdsplanet.com) 토지·건물 · [밸류맵](https://www.valueupmap.com)·[디스코](https://www.disco.re) 토지·빌딩
- 법률: [케이스노트](https://casenote.kr) 판례 · [찾기쉬운 생활법령](https://easylaw.go.kr) 생활법률 · [헌법재판소](https://www.ccourt.go.kr) · [의안정보](https://likms.assembly.go.kr) 법안
- 의료: [국가건강정보포털](https://health.kdca.go.kr) 질병정보 · [약학정보원](https://www.health.kr) 의약품 · [의약품안전나라](https://nedrug.mfds.go.kr) 허가·안전 · [심평원](https://www.hira.or.kr)·[건보공단](https://www.nhis.or.kr) 병원·검진
- 창업·기업·행정: [기업마당](https://www.bizinfo.go.kr) 지원사업 · [중소벤처24](https://www.smes.go.kr)·[KISED](https://www.kised.or.kr) · [나라장터](https://www.g2b.go.kr) 조달 · [홈택스](https://www.hometax.go.kr) 세무 · [키프리스](https://www.kipris.or.kr) 특허·상표 · [정부24](https://www.gov.kr)·[복지로](https://www.bokjiro.go.kr) · [도로명주소](https://www.juso.go.kr)·[인터넷등기소](https://www.iros.go.kr)
- 공모전·대외활동(한국): [위비티](https://www.wevity.com)·[씽굿](https://www.thinkcontest.com)·[올콘](https://www.all-con.co.kr)·[링커리어](https://linkareer.com)·[캠퍼스픽](https://www.campuspick.com) 공모전·경진대회 집계 (※정부 창업지원 공고는 액션 [sense:startup]로 접근)
- 학술·도서·문화: [RISS](https://www.riss.kr)·[ScienceON](https://scienceon.kisti.re.kr) 국내 학술 · [국립중앙도서관](https://www.nl.go.kr)·[국회도서관](https://www.nanet.go.kr) · [알라딘](https://www.aladin.co.kr)·[교보문고](https://www.kyobobook.co.kr) · [문화포털](https://www.culture.go.kr)·[MMCA](https://www.mmca.go.kr)·[e뮤지엄](https://www.emuseum.go.kr)
- 뉴스·정세(한국): [연합뉴스](https://www.yna.co.kr)·[빅카인즈](https://www.bigkinds.or.kr) 뉴스아카이브 · [KIEP](https://www.kiep.go.kr)·[세종연구소](https://www.sejong.org)·[아산정책연구원](https://www.asaninst.org)

### 국제 권위 크롤
- AI: [arXiv](https://arxiv.org/list/cs.AI/recent) · [HF Papers](https://huggingface.co/papers) 지금 중요한 논문 · [OpenReview](https://openreview.net) 동료심사 · [Anthropic](https://www.anthropic.com/research)·[DeepMind](https://deepmind.google/research/) · [LMArena](https://lmarena.ai)·[Artificial Analysis](https://artificialanalysis.ai) 모델 순위 · [Papers with Code](https://paperswithcode.com)
- 경제데이터: [FRED](https://fred.stlouisfed.org) 거시 84만 시계열 · [World Bank](https://data.worldbank.org) · [IMF/WEO](https://www.imf.org/en/Publications/WEO) · [OECD](https://data.oecd.org) · [Our World in Data](https://ourworldindata.org) · [Trading Economics](https://tradingeconomics.com) · [SEC EDGAR](https://www.sec.gov/edgar) 미국 공시
- 외교·정세: [Foreign Affairs](https://www.foreignaffairs.com) · [Foreign Policy](https://foreignpolicy.com) · [The Diplomat](https://thediplomat.com) 아태 · [The Economist](https://www.economist.com) · [CFR](https://www.cfr.org)·[Brookings](https://www.brookings.edu)·[CSIS](https://www.csis.org)·[Carnegie](https://carnegieendowment.org)·[Chatham House](https://www.chathamhouse.org)·[RAND](https://www.rand.org)
- 국제뉴스·기술: [Reuters](https://www.reuters.com)·[AP](https://apnews.com)·[BBC](https://www.bbc.com/news)·[Bloomberg](https://www.bloomberg.com)·[FT](https://www.ft.com)·[Al Jazeera](https://www.aljazeera.com) · [Hacker News](https://news.ycombinator.com)·[Techmeme](https://www.techmeme.com)·[Stratechery](https://stratechery.com)
- 과학·뉴로: [Nature](https://www.nature.com)·[Science](https://www.science.org)·[PNAS](https://www.pnas.org)·[eLife](https://elifesciences.org)·[Cell](https://www.cell.com)·[J Neurosci](https://www.jneurosci.org) · [OpenNeuro](https://openneuro.org) 신경영상 데이터 · [Allen Brain Atlas](https://portal.brain-map.org) 뇌지도
- 학술도구: [Google Scholar](https://scholar.google.com)·[PubMed](https://pubmed.ncbi.nlm.nih.gov)·[PMC](https://www.ncbi.nlm.nih.gov/pmc)·[bioRxiv](https://www.biorxiv.org)·[medRxiv](https://www.medrxiv.org)·[Semantic Scholar](https://www.semanticscholar.org)·[Connected Papers](https://www.connectedpapers.com)·[OpenAlex](https://openalex.org)·[Zenodo](https://zenodo.org)
- 지식·레퍼런스: [Wikipedia](https://en.wikipedia.org)·[Wikidata](https://www.wikidata.org)·[Wolfram Alpha](https://www.wolframalpha.com)·[Stanford Encyclopedia of Philosophy](https://plato.stanford.edu) 철학 권위·[Internet Archive](https://archive.org) 절판·웨이백·[위키문헌](https://ko.wikisource.org)
- 개발: [GitHub](https://github.com)·[Stack Overflow](https://stackoverflow.com)·[MDN](https://developer.mozilla.org)·[PyPI](https://pypi.org)·[Hugging Face](https://huggingface.co)
- AI 공모전·해커톤(국제): [Devpost](https://devpost.com)·[Devfolio](https://devfolio.co)·[MLH](https://mlh.io) 해커톤 · [lablab.ai](https://lablab.ai) AI 해커톤 · [AIcrowd](https://www.aicrowd.com)·[DrivenData](https://www.drivendata.org) 경진대회 (※Kaggle은 공식 API라 액션화 예정)
- 인물·신원 찾기(OSINT — 로그인 벽 잦음→검색 스니펫 우회): [LinkedIn](https://www.linkedin.com) 직업·경력·[Facebook](https://www.facebook.com)·[Instagram](https://www.instagram.com)·[X](https://x.com)·[ORCID](https://orcid.org) 연구자ID·[ResearchGate](https://www.researchgate.net)·[DBLP](https://dblp.org) CS 연구자·[나무위키](https://namu.wiki) 한국 인물·동창/총동문회 학력 단서
