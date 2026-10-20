# 웹 랜드마크 지도 (Web Landmarks)

*어휘로 연결된 원천 밖에서 무엇을 더 살필지 알려주는 출처의 지도.* 특정 도메인에 IBL 액션이 있어도 그 액션이 시장·관점 전체를 덮는 것은 아니다. 국적은 필요한 자료가 있는 곳에 맞춘다(제도·로컬=한국 / 국제 비교·해외 구매=해당 국가). 이 파일은 `web_search.md`(검색법)·`shopping.md`(구매)·`forage_search.md`(포식)가 공유하는 **단일 소스**다 — 랜드마크 추가·수정은 여기서만. 등재는 자동 접근 성공이나 현재 판매·서비스 상태의 보증이 아니다.

### 한국에서 구매할 제품을 찾을 때

다음은 조사할 채널의 후보 지도이며 모든 사이트를 순회하는 체크리스트가 아니다. 사용자 목적·예산·사용 지역·새 상품/중고·직구 선호를 바탕으로 필요한 채널을 고른다. 한국어 요청만으로 해외 후보를 제외하지 않는다. 한 소스에서 후보가 많이 나와도 다른 채널이 가격·적합성·구매 조건을 바꿀 수 있는지 검토한다.

| 역할 | 출발점 | 확인할 내용 |
| --- | --- | --- |
| 제품 후보·가격대 | [다나와](https://www.danawa.com/) · [네이버 가격비교/쇼핑](https://shopping.naver.com/) · [에누리](https://www.enuri.com/) | 브랜드·모델·사양·가격대. 가격비교에 잡힌 판매처만으로 시장 전체를 조사했다고 보지 않는다. |
| 실제 판매 조건 | [쿠팡](https://www.coupang.com/) · [네이버 스마트스토어](https://smartstore.naver.com/) · [G마켓](https://www.gmarket.co.kr/) · [11번가](https://www.11st.co.kr/) · 브랜드 공식몰 | 정확한 모델·옵션·판매자, 배송·설치비를 포함한 가격, 쿠폰 적용 자격·배송·반품 조건. |
| 홈쇼핑·백화점 유통 | [GS SHOP](https://www.gsshop.com/) · [CJ온스타일](https://www.cjonstyle.com/) · [현대Hmall](https://www.hmall.com/) · [롯데홈쇼핑](https://www.lotteimall.com/) · [SSG닷컴](https://www.ssg.com/) | 방송 구성품·할인 조건·유통 전용 모델. 이름이 비슷해도 동일 모델인지 확인하고 불필요한 사은품을 가격 이점으로 세지 않는다. |
| 제조사 원문 | 해당 제조사의 제품 페이지·설명서·고객지원·공식 판매점 안내 | 사양·모델 차이·보증·수리·소모품 비용. 판매자의 기능 설명을 원문과 대조한다. |
| 실사용 경험 | [네이버 블로그](https://section.blog.naver.com/) · [네이버 카페](https://section.cafe.naver.com/) · [유튜브](https://www.youtube.com/) · 구매 후기·품목별 전문 커뮤니티 | 장기 사용·청소·관리·반복 고장. 협찬·제휴 여부와 사용 모델·시점을 확인하고 같은 홍보 원문을 독립 근거로 중복 계산하지 않는다. |
| 독립 시험·비교 | [한국소비자원](https://www.kca.go.kr/) · [소비자24](https://www.consumer.go.kr/) | 해당 품목의 시험 자료 유무, 시험 모델·시기·조건. 시험하지 않은 다른 모델까지 결론을 확장하지 않는다. |
| 해외 구매 대안 | [알리익스프레스](https://www.aliexpress.com/) · [아마존](https://www.amazon.com/) · [아마존 일본](https://www.amazon.co.jp/) · 해외 제조사 공식몰 | 국내에 없는 대안과 총구매비용(배송·세금 포함), 한국 배송·전압·규격·보증·반품 조건. 직구가 유리한지는 제품별로 판단한다. |
| 중고·리퍼 | [당근](https://www.daangn.com/) · [번개장터](https://m.bunjang.co.kr/) · [중고나라](https://web.joongna.com/) · 제조사/유통사 리퍼몰 | 같은 예산의 대안, 사용 상태·구성품·잔여 보증·거래 지역. 새 상품 요구와 충돌하면 제외한다. |
| 품목별 전문점·실물 확인 | 가구=[오늘의집](https://ohou.se/)·브랜드 매장, 의류=[무신사](https://www.musinsa.com/)·[29CM](https://www.29cm.co.kr/), 부품·공구=해당 전문몰 | 범용 쇼핑몰에서 놓친 후보. 착용감·조작감 등 온라인 근거로 확정하기 어려운 조건은 실물 확인 과제로 남긴다. |

**실행 연결**: `[sense:search_shopping]`은 다나와 후보 수집이고, `[sense:used]`는 중고 원천별 조회다. 그 밖의 채널은 `[sense:search]`의 국내/해외 검색과 `site:` 질의로 후보를 찾고 `[sense:crawl]`로 원문을 확인한다. 네이버 블로그·카페는 `source:"naver", type:"blog"|"cafe"`를 사용한다. 필요한 브라우저 조작·로그인과 차단 대응은 [웹 검색 가이드](web_search.md)를 따른다. 이 지도에 네이버 쇼핑이 있다는 이유로 은퇴한 `search_shopping site:naver`를 호출하지 않는다. 기존 어댑터의 과거 실패도 해당 시장을 영구 제외할 근거로 삼지 않는다.

**범위와 종료**: 가격만 묻는 요청에는 필요한 가격 원천을 좁혀 보고, 제품 선택 요청에는 후보·실제 구매 조건·제품 검증의 서로 다른 역할을 살핀다. 홈쇼핑·해외몰·전문점 등이 선택을 바꿀 가능성이 있으면 같은 조사에서 넓힌다. 유효한 후보와 핵심 조건의 근거가 확보되어 추가 탐색의 가치가 작으면 마친다. 결과에는 실제 확인한 채널, 선택에 영향을 줄 미확인·접근 실패와 주요 제외 이유를 간단히 남긴다. 검색 요약만 본 것과 본문 확인을 구별하며, 접근 실패를 상품 부재로 해석하지 않는다.

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
