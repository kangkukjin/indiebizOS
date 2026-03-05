"""
rebuild_usage_db.py - IBL 용례 사전 수동 재구축
수작업으로 검증된 올바른 IBL 예제로 DB를 재구성합니다.

사용법:
  cd backend && python rebuild_usage_db.py
"""

import sys
import os
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

DB_PATH = str(Path(__file__).parent.parent / "data" / "ibl_usage.db")

# =============================================================================
# 수작업 검증 예제 데이터
# (intent, ibl_code, nodes, category, difficulty, tags)
# =============================================================================

EXAMPLES = [
    # =========================================================================
    # system 노드 — 시스템 관리, 파일, 출력, 도구 탐색
    # =========================================================================

    # time
    ("현재 시간 알려줘", '[system:time]()', "system", "single", 1, "system,time"),
    ("지금 몇 시야?", '[system:time]()', "system", "single", 1, "system,time"),
    ("오늘 날짜 알려줘", '[system:time]()', "system", "single", 1, "system,time"),

    # discover
    ("주가 관련 도구 찾아봐", '[system:discover]("주가")', "system", "single", 1, "system,discover"),
    ("날씨 기능 뭐 있어?", '[system:discover]("날씨")', "system", "single", 1, "system,discover"),
    ("음악 관련 기능 알려줘", '[system:discover]("음악")', "system", "single", 1, "system,discover"),
    ("사진 관련 도구 뭐 있어?", '[system:discover]("사진")', "system", "single", 1, "system,discover"),
    ("법률 검색 기능 있어?", '[system:discover]("법률")', "system", "single", 1, "system,discover"),

    # open / open_url
    ("이 파일 열어줘", '[system:open]("/path/to/file.html")', "system", "single", 1, "system,open"),
    ("파일 탐색기 열어줘", '[system:explorer]("~/Desktop")', "system", "single", 1, "system,explorer"),
    ("이 URL 열어줘", '[system:open_url]("https://example.com")', "system", "single", 1, "system,open_url"),
    ("구글 열어줘", '[system:open_url]("https://google.com")', "system", "single", 1, "system,open_url"),
    ("이 사이트 브라우저로 열어", '[system:browse]("https://example.com")', "system", "single", 1, "system,browse"),

    # file / output
    ("결과를 파일로 저장해", '[system:file]("result.md")', "system", "single", 1, "system,file"),
    ("보고서를 HTML로 저장해줘", '[system:file]("report.html")', "system", "single", 1, "system,file"),
    ("클립보드에 복사해줘", '[system:clipboard]("복사할 내용")', "system", "single", 1, "system,clipboard"),
    ("UI에 결과 표시해줘", '[system:gui]("분석 결과")', "system", "single", 1, "system,gui"),

    # file management
    ("바탕화면 파일 목록 보여줘", '[system:list]("~/Desktop")', "system", "single", 1, "system,list"),
    ("보고서.md 파일 읽어줘", '[system:read]("보고서.md")', "system", "single", 1, "system,read"),
    ("PDF 파일 읽어줘", '[system:read_pdf]("문서.pdf")', "system", "single", 1, "system,read_pdf"),
    ("메모 파일 써줘", '[system:write]("memo.md")', "system", "single", 1, "system,write"),
    ("py 파일 찾아줘", '[system:find]("*.py")', "system", "single", 1, "system,find"),
    ("파일에서 에러 찾아줘", '[system:grep]("error")', "system", "single", 1, "system,grep"),
    ("파일 복사해줘", '[system:copy]("source.txt")', "system", "single", 1, "system,copy"),
    ("파일 이름 바꿔줘", '[system:move]("old_name.txt")', "system", "single", 1, "system,move"),
    ("저장소 용량 보여줘", '[system:summary]()', "system", "single", 1, "system,summary"),
    ("볼륨 목록 보여줘", '[system:volumes]()', "system", "single", 1, "system,volumes"),

    # =========================================================================
    # team 노드 — 에이전트 간 위임/협업 (Phase 23)
    # =========================================================================

    # delegate — 같은 프로젝트 내 동료 에이전트에게 위임
    ("심장전문에게 심장 검사 요청해", '[team:delegate]("심장전문") {message: "환자의 심장 관련 증상을 분석해주세요"}', "team", "single", 1, "team,delegate"),
    ("내과에게 두통 증상 분석 맡겨", '[team:delegate]("내과") {message: "두통 증상 분석해주세요"}', "team", "single", 1, "team,delegate"),
    ("스토리텔러에게 슬라이드 만들어달라고 해", '[team:delegate]("스토리텔러") {message: "AI 트렌드 발표자료 만들어줘"}', "team", "single", 1, "team,delegate"),
    ("정보수집 에이전트에게 자료 조사 맡겨", '[team:delegate]("정보수집") {message: "최신 AI 뉴스 정리해줘"}', "team", "single", 1, "team,delegate"),

    # ask — 다른 프로젝트 에이전트에게 질문/위임 (비동기)
    ("투자 에이전트한테 물어봐", '[team:ask]("투자/투자컨설팅") {message: "삼성전자 투자 의견 알려줘"}', "team", "single", 1, "team,ask"),
    ("컨텐츠 에이전트한테 부탁해", '[team:ask]("컨텐츠/컨텐츠") {message: "블로그 글 분석해줘"}', "team", "single", 1, "team,ask"),
    ("정보센터에 분석 요청해", '[team:ask]("정보센터/정보수집") {message: "AI 트렌드 조사해줘"}', "team", "single", 1, "team,ask"),
    ("의료팀에게 건강 상담 요청해", '[team:ask]("의료/가정의학과") {message: "두통이 자주 발생하는 원인을 알려줘"}', "team", "single", 1, "team,ask"),
    ("법률 에이전트한테 임대차 관련 질문해", '[team:ask]("법률/법률") {message: "임대차보호법 관련 질문입니다"}', "team", "single", 1, "team,ask"),

    # ask_sync — 동기 질문 (파이프라인/워크플로우용)
    ("투자 에이전트에게 동기적으로 분석 요청", '[team:ask_sync]("투자/투자컨설팅") {message: "이 데이터를 분석해줘"}', "team", "single", 1, "team,ask_sync"),
    ("컨텐츠 에이전트에게 즉시 답변 요청", '[team:ask_sync]("컨텐츠/컨텐츠") {message: "이 글을 요약해줘"}', "team", "single", 1, "team,ask_sync"),

    # delegate_project — 시스템 AI가 프로젝트 에이전트에게 위임
    ("의료 프로젝트 내과에게 위임해", '[team:delegate_project]("의료/내과") {message: "두통 증상 분석해주세요"}', "team", "single", 1, "team,delegate_project"),
    ("투자 프로젝트에 분석 맡겨", '[team:delegate_project]("투자/투자컨설팅") {message: "포트폴리오 리밸런싱 분석"}', "team", "single", 1, "team,delegate_project"),
    ("홍보팀에게 슬라이드 제작 위임해", '[team:delegate_project]("홍보/storyteller") {message: "분기 실적 발표 슬라이드 만들어줘"}', "team", "single", 1, "team,delegate_project"),

    # info — 에이전트/프로젝트 정보 조회
    ("에이전트 정보 알려줘", '[team:info]("투자/투자컨설팅")', "team", "single", 1, "team,info"),
    ("의료 프로젝트 에이전트들 뭐 있어?", '[team:info]("의료")', "team", "single", 1, "team,info"),

    # list_projects — 프로젝트/에이전트 목록
    ("프로젝트 목록 보여줘", '[team:list_projects]()', "team", "single", 1, "team,list_projects"),
    ("어떤 에이전트들이 있어?", '[team:list_projects]()', "team", "single", 1, "team,list_projects"),

    # workflow
    ("저장된 워크플로우 목록 보여줘", '[system:list_workflows]()', "system", "single", 1, "system,list_workflows"),
    ("뉴스 브리핑 워크플로우 실행해", '[system:run]("news_briefing")', "system", "single", 1, "system,run"),

    # switches / events
    ("스위치 목록 보여줘", '[system:list_switches]()', "system", "single", 1, "system,list_switches"),
    ("트리거 목록 보여줘", '[system:list_events]()', "system", "single", 1, "system,list_events"),
    ("이벤트 시스템 상태 확인", '[system:status]()', "system", "single", 1, "system,status"),

    # user interaction
    ("할일 목록 만들어줘", '[system:todo]("할일 정리")', "system", "single", 1, "system,todo"),
    ("사용자에게 알림 보내줘", '[system:notify_user]("작업 완료")', "system", "single", 1, "system,notify_user"),
    ("사용자에게 확인 요청해", '[system:ask_user]("계속 진행할까요?")', "system", "single", 1, "system,ask_user"),
    ("API 도구 목록 보여줘", '[system:list_api]()', "system", "single", 1, "system,list_api"),
    ("다운로드해줘", '[system:download]("https://example.com/file.zip")', "system", "single", 1, "system,download"),

    # =========================================================================
    # source 노드 — 데이터 조사/검색 (투자, 뉴스, 날씨 등)
    # =========================================================================

    # 주가/투자
    ("삼성전자 주가 알려줘", '[source:price]("삼성전자")', "source", "single", 1, "source,price"),
    ("삼성전자 주가 조회", '[source:price]("005930")', "source", "single", 1, "source,price"),
    ("애플 주가 확인해줘", '[source:price]("AAPL")', "source", "single", 1, "source,price"),
    ("테슬라 주가 보여줘", '[source:price]("TSLA")', "source", "single", 1, "source,price"),
    ("SPY ETF 가격 알려줘", '[source:price]("SPY")', "source", "single", 1, "source,price"),
    ("금 시세 알려줘", '[source:price]("GC=F")', "source", "single", 1, "source,price"),
    ("한국 주가 기간별 조회해줘", '[source:kr_price]("005930")', "source", "single", 1, "source,kr_price"),
    ("미국 주가 기간별 조회", '[source:us_price]("AAPL")', "source", "single", 1, "source,us_price"),
    ("비트코인 시세 알려줘", '[source:crypto]("bitcoin")', "source", "single", 1, "source,crypto"),
    ("이더리움 가격 확인", '[source:crypto]("ethereum")', "source", "single", 1, "source,crypto"),
    ("종목 코드 검색해줘", '[source:search_stock]("반도체")', "source", "single", 1, "source,search_stock"),
    ("삼성전자 종목 상세 정보", '[source:info]("005930")', "source", "single", 1, "source,info"),
    ("삼성전자 뉴스 알려줘", '[source:news]("삼성전자")', "source", "single", 1, "source,news"),
    ("테슬라 관련 뉴스", '[source:stock_news]("TSLA")', "source", "single", 1, "source,stock_news"),
    ("삼성전자 실적 발표 일정", '[source:earnings]("005930")', "source", "single", 1, "source,earnings"),

    # 기업정보/재무
    ("삼성전자 기업 정보", '[source:kr_company]("삼성전자")', "source", "single", 1, "source,kr_company"),
    ("애플 기업 프로필", '[source:us_company]("AAPL")', "source", "single", 1, "source,us_company"),
    ("삼성전자 재무제표", '[source:kr_financial]("삼성전자")', "source", "single", 1, "source,kr_financial"),
    ("애플 재무제표 보여줘", '[source:us_financial]("AAPL")', "source", "single", 1, "source,us_financial"),
    ("삼성전자 공시 검색", '[source:kr_disclosure]("삼성전자")', "source", "single", 1, "source,kr_disclosure"),
    ("애플 SEC 공시 조회", '[source:us_filing]("AAPL")', "source", "single", 1, "source,us_filing"),

    # 투자자 매매동향
    ("외국인 매매동향 알려줘", '[source:kr_investor]("STK")', "source", "single", 1, "source,kr_investor"),
    ("코스닥 투자자 매매동향", '[source:kr_investor]("KSQ")', "source", "single", 1, "source,kr_investor"),
    ("오늘 외국인 순매수 얼마야?", '[source:kr_investor]("STK")', "source", "single", 1, "source,kr_investor"),
    ("삼성전자 투자자별 매매동향", '[source:kr_stock_investor]("005930")', "source", "single", 1, "source,kr_stock_investor"),

    # 웹 검색/크롤링
    ("AI 뉴스 검색해줘", '[source:web_search]("AI 뉴스")', "source", "single", 1, "source,web_search"),
    ("반도체 뉴스 검색해줘", '[source:search_news]("반도체")', "source", "single", 1, "source,search_news"),
    ("부동산 뉴스 찾아줘", '[source:search_news]("부동산")', "source", "single", 1, "source,search_news"),
    ("경제 뉴스 검색", '[source:search_news]("경제")', "source", "single", 1, "source,search_news"),
    ("이 웹페이지 내용 가져와", '[source:crawl]("https://example.com/article")', "source", "single", 1, "source,crawl"),
    ("네이버 메인 크롤링해줘", '[source:crawl]("https://naver.com")', "source", "single", 1, "source,crawl"),

    # 날씨/위치
    ("서울 날씨 알려줘", '[source:weather]("서울")', "source", "single", 1, "source,weather"),
    ("부산 날씨 확인", '[source:weather]("부산")', "source", "single", 1, "source,weather"),
    ("강남역 맛집 찾아줘", '[source:restaurant]("강남역")', "source", "single", 1, "source,restaurant"),
    ("청주 맛집 추천해줘", '[source:restaurant]("청주")', "source", "single", 1, "source,restaurant"),
    ("지도에 표시해줘", '[source:map]("강남역")', "source", "single", 1, "source,map"),

    # 법률/통계
    ("임대차보호법 검색해줘", '[source:search_laws]("임대차보호법")', "source", "single", 1, "source,search_laws"),
    ("근로기준법 찾아봐", '[source:search_laws]("근로기준법")', "source", "single", 1, "source,search_laws"),
    ("인구 통계 검색", '[source:search_kosis]("인구")', "source", "single", 1, "source,search_kosis"),

    # 문화/도서
    ("공연 검색해줘", '[source:performance]("뮤지컬")', "source", "single", 1, "source,performance"),
    ("전시회 정보 찾아줘", '[source:exhibit]("미술")', "source", "single", 1, "source,exhibit"),
    ("책 검색해줘", '[source:book]("인공지능")', "source", "single", 1, "source,book"),
    ("도서 상세 정보", '[source:book_detail]("9791192107103")', "source", "single", 1, "source,book_detail"),

    # 쇼핑
    ("노트북 가격 비교해줘", '[source:search_shopping]("맥북 프로 14인치")', "source", "single", 1, "source,search_shopping"),
    ("에어팟 가격 검색", '[source:search_shopping]("에어팟 프로")', "source", "single", 1, "source,search_shopping"),

    # 부동산
    ("아파트 매매 실거래가 조회", '[source:apt_trade]("11110")', "source", "single", 1, "source,apt_trade"),
    ("아파트 전월세 조회", '[source:apt_rent]("11110")', "source", "single", 1, "source,apt_rent"),
    ("지역코드 검색", '[source:district_codes]("서울")', "source", "single", 1, "source,district_codes"),

    # 사진
    ("여행 사진 검색해줘", '[source:search_photos]("여행")', "source", "single", 1, "source,search_photos"),
    ("사진 통계 보여줘", '[source:photo_stats]()', "source", "single", 1, "source,photo_stats"),
    ("사진 갤러리 열어줘", '[source:gallery]()', "source", "single", 1, "source,gallery"),
    ("사진관리창 열어줘", '[source:photo_manager]()', "source", "single", 1, "source,photo_manager"),

    # 블로그
    ("블로그에서 AI 글 검색", '[source:rag_search]("인공지능")', "source", "single", 1, "source,rag_search"),
    ("블로그 글 목록 보여줘", '[source:posts]()', "source", "single", 1, "source,posts"),
    ("블로그 통계 보여줘", '[source:blog_stats]()', "source", "single", 1, "source,blog_stats"),
    ("새 블로그 글 있어?", '[source:check_new]()', "source", "single", 1, "source,check_new"),
    ("블로그 인사이트 분석해줘", '[source:insight]("AI 트렌드")', "source", "single", 1, "source,insight"),

    # 메모리/대화
    ("최근 대화 보여줘", '[source:recent]()', "source", "single", 1, "source,recent"),
    ("대화 내용 검색해줘", '[source:search_memory]("주식")', "source", "single", 1, "source,search_memory"),
    ("메모리에 저장해줘", '[source:save_memory]("중요한 정보")', "source", "single", 1, "source,save_memory"),
    ("메모리에서 검색해줘", '[source:memory_search]("투자")', "source", "single", 1, "source,memory_search"),

    # 건강
    ("건강 기록 조회", '[source:health_query]()', "source", "single", 1, "source,health_query"),
    ("혈압 기록 저장해줘", '[source:save_health]("blood_pressure")', "source", "single", 1, "source,save_health"),

    # 학술
    ("AI 논문 검색해줘", '[source:search_arxiv]("artificial intelligence")', "source", "single", 1, "source,search_arxiv"),
    ("학술 논문 찾아줘", '[source:search_scholar]("machine learning")', "source", "single", 1, "source,search_scholar"),

    # =========================================================================
    # stream 노드 — 음악/라디오/유튜브
    # =========================================================================

    # 음악 재생
    ("슬픈 피아노곡 틀어줘", '[stream:play]("슬픈 피아노곡")', "stream", "single", 1, "stream,play"),
    ("재즈 음악 틀어줘", '[stream:play]("jazz music")', "stream", "single", 1, "stream,play"),
    ("잔잔한 음악 재생해", '[stream:play]("잔잔한 배경음악")', "stream", "single", 1, "stream,play"),
    ("BTS 노래 틀어줘", '[stream:play]("BTS")', "stream", "single", 1, "stream,play"),
    ("클래식 음악 들려줘", '[stream:play]("클래식 음악")', "stream", "single", 1, "stream,play"),

    # 유튜브 검색/정보
    ("유튜브에서 피아노곡 검색해", '[stream:search_youtube]("피아노곡")', "stream", "single", 1, "stream,search_youtube"),
    ("유튜브 검색 결과만 보여줘", '[stream:search_youtube]("AI 뉴스")', "stream", "single", 1, "stream,search_youtube"),
    ("이 영상 정보 알려줘", '[stream:info]("https://youtube.com/watch?v=example")', "stream", "single", 1, "stream,info"),
    ("영상 자막 추출해줘", '[stream:transcript]("https://youtube.com/watch?v=example")', "stream", "single", 1, "stream,transcript"),
    ("영상 오디오 다운로드해줘", '[stream:download]("https://youtube.com/watch?v=example")', "stream", "single", 1, "stream,download"),

    # 재생 컨트롤
    ("다음 곡으로 넘겨줘", '[stream:skip]()', "stream", "single", 1, "stream,skip"),
    ("음악 정지해", '[stream:stop]()', "stream", "single", 1, "stream,stop"),
    ("현재 재생 목록 보여줘", '[stream:queue]()', "stream", "single", 1, "stream,queue"),
    ("재생 상태 확인", '[stream:status]()', "stream", "single", 1, "stream,status"),
    ("볼륨 올려줘", '[stream:volume]("80")', "stream", "single", 1, "stream,volume"),
    ("이 곡 큐에 추가해줘", '[stream:queue_add]("아이유")', "stream", "single", 1, "stream,queue_add"),

    # 라디오
    ("KBS 라디오 찾아줘", '[stream:search_radio]("KBS")', "stream", "single", 1, "stream,search_radio"),
    ("한국 라디오 채널 목록", '[stream:korean]("KBS")', "stream", "single", 1, "stream,korean"),
    ("라디오 틀어줘", '[stream:radio_play]("KBS 클래식FM")', "stream", "single", 1, "stream,radio_play"),
    ("라디오 꺼줘", '[stream:radio_stop]()', "stream", "single", 1, "stream,radio_stop"),
    ("즐겨찾기 라디오 보여줘", '[stream:favorites]()', "stream", "single", 1, "stream,favorites"),

    # =========================================================================
    # forge 노드 — 콘텐츠 생성
    # =========================================================================

    # 신문
    ("신문 만들어줘", '[forge:newspaper]("AI, 경제, 문화")', "forge", "single", 1, "forge,newspaper"),
    ("AI 뉴스 신문 만들어", '[forge:newspaper]("AI")', "forge", "single", 1, "forge,newspaper"),
    ("구글뉴스 신문 생성해줘", '[forge:newspaper]("AI, 청주, 세종, 문화, 여행, 과학, 경제")', "forge", "single", 1, "forge,newspaper"),

    # 차트/시각화
    ("라인 차트 그려줘", '[forge:line]("주가 추이")', "forge", "single", 1, "forge,line"),
    ("바 차트 만들어줘", '[forge:bar]("매출 비교")', "forge", "single", 1, "forge,bar"),
    ("파이 차트 그려줘", '[forge:pie]("시장 점유율")', "forge", "single", 1, "forge,pie"),
    ("캔들스틱 차트 그려줘", '[forge:candlestick]("삼성전자 주가")', "forge", "single", 1, "forge,candlestick"),
    ("히트맵 만들어줘", '[forge:heatmap]("상관관계")', "forge", "single", 1, "forge,heatmap"),
    ("차트 대시보드 만들어줘", '[forge:multi]("투자 대시보드")', "forge", "single", 1, "forge,multi"),

    # 슬라이드/영상
    ("발표 슬라이드 만들어줘", '[forge:slide]("AI 트렌드 2026")', "forge", "single", 1, "forge,slide"),
    ("고품질 슬라이드 만들어줘", '[forge:slide_shadcn]("분기 실적")', "forge", "single", 1, "forge,slide_shadcn"),
    ("영상 만들어줘", '[forge:video]("회사 소개")', "forge", "single", 1, "forge,video"),
    ("TTS로 음성 변환해줘", '[forge:tts]("안녕하세요, 오늘 뉴스입니다")', "forge", "single", 1, "forge,tts"),

    # 음악/작곡
    ("피아노곡 작곡해줘", '[forge:music]("편안한 피아노 소품")', "forge", "single", 1, "forge,music"),

    # AI 이미지
    ("AI 이미지 만들어줘", '[forge:image_gemini]("아름다운 한국 산 풍경")', "forge", "single", 1, "forge,image_gemini"),

    # 웹사이트
    ("웹사이트 만들어줘", '[forge:create_site]("카페 홈페이지")', "forge", "single", 1, "forge,create_site"),
    ("랜딩 페이지 만들어줘", '[forge:create_site]("제품 소개 페이지")', "forge", "single", 1, "forge,create_site"),
    ("사이트 배포해줘", '[forge:deploy]("my-site")', "forge", "single", 1, "forge,deploy"),

    # 설계
    ("집 설계 시작해줘", '[forge:create_design]("내 집")', "forge", "single", 1, "forge,create_design"),
    ("평면도 그려줘", '[forge:floor_plan]("design_1")', "forge", "single", 1, "forge,floor_plan"),

    # =========================================================================
    # interface 노드 — 브라우저/안드로이드/데스크탑
    # =========================================================================

    # 브라우저
    ("이 사이트 Playwright로 열어", '[interface:navigate]("https://google.com")', "interface", "single", 1, "interface,navigate"),
    ("페이지 스냅샷 찍어", '[interface:snapshot]()', "interface", "single", 1, "interface,snapshot"),
    ("스크린샷 찍어줘", '[interface:screenshot]()', "interface", "single", 1, "interface,screenshot"),
    ("페이지 내용 추출해", '[interface:content]()', "interface", "single", 1, "interface,content"),
    ("JavaScript 실행해줘", '[interface:evaluate]("document.title")', "interface", "single", 1, "interface,evaluate"),

    # 안드로이드
    ("연결된 기기 목록 보여줘", '[interface:devices]()', "interface", "single", 1, "interface,devices"),
    ("안드로이드 화면 캡처", '[interface:android_screenshot]()', "interface", "single", 1, "interface,android_screenshot"),
    ("문자 목록 보여줘", '[interface:sms_list]()', "interface", "single", 1, "interface,sms_list"),
    ("통화 이력 보여줘", '[interface:call_log]()', "interface", "single", 1, "interface,call_log"),
    ("연락처 검색해줘", '[interface:contacts]("홍길동")', "interface", "single", 1, "interface,contacts"),
    ("안드로이드 관리창 열어줘", '[interface:manager]()', "interface", "single", 1, "interface,manager"),

    # 데스크탑
    ("Mac 화면 캡처해줘", '[interface:desktop_screenshot]()', "interface", "single", 1, "interface,desktop_screenshot"),

    # =========================================================================
    # messenger 노드 — 통신
    # =========================================================================

    ("이메일 보내줘", '[messenger:send_email]("user@example.com")', "messenger", "single", 1, "messenger,send_email"),
    ("이웃 목록 보여줘", '[messenger:neighbors]()', "messenger", "single", 1, "messenger,neighbors"),
    ("이웃 상세 정보 조회", '[messenger:neighbor_detail]("홍길동")', "messenger", "single", 1, "messenger,neighbor_detail"),
    ("메시지 검색해줘", '[messenger:search]("미팅")', "messenger", "single", 1, "messenger,search"),

    # =========================================================================
    # 파이프라인 — 순차 실행 (>>)
    # =========================================================================

    # 검색 → 저장
    ("AI 뉴스 검색해서 파일로 저장해줘", '[source:web_search]("AI 뉴스") >> [system:file]("ai_news.md")', "source,system", "pipeline", 2, "pipeline,sequential"),
    ("부동산 뉴스 찾아서 저장해", '[source:search_news]("부동산") >> [system:file]("부동산뉴스.md")', "source,system", "pipeline", 2, "pipeline,sequential"),
    ("반도체 뉴스 검색해서 정리해줘", '[source:search_news]("반도체") >> [system:file]("반도체뉴스.md")', "source,system", "pipeline", 2, "pipeline,sequential"),

    # 검색 → 차트
    ("삼성전자 주가 조회해서 차트로 그려줘", '[source:price]("삼성전자") >> [forge:line]("삼성전자 주가 차트")', "source,forge", "pipeline", 2, "pipeline,sequential"),
    ("애플 주가 차트 만들어줘", '[source:price]("AAPL") >> [forge:line]("AAPL 주가 차트")', "source,forge", "pipeline", 2, "pipeline,sequential"),

    # 유튜브 → 저장
    ("유튜브 자막 추출해서 파일로 저장해", '[stream:transcript]("https://youtube.com/watch?v=example") >> [system:file]("transcript.md")', "stream,system", "pipeline", 2, "pipeline,sequential"),

    # 검색 → 에이전트 분석 (team 노드 파이프라인)
    ("AI 뉴스 찾아서 투자 에이전트에게 분석 요청해", '[source:web_search]("AI 뉴스") >> [team:ask_sync]("투자/투자컨설팅") {message: "이 뉴스를 투자 관점에서 분석해줘"}', "source,team", "pipeline", 2, "pipeline,sequential"),
    ("부동산 뉴스 찾아서 부동산 에이전트에게 넘겨줘", '[source:search_news]("부동산") >> [team:ask_sync]("부동산/부동산") {message: "이 뉴스에서 시장 동향을 분석해줘"}', "source,team", "pipeline", 2, "pipeline,sequential"),
    ("블로그 글 찾아서 컨텐츠 에이전트에게 분석 맡겨", '[source:rag_search]("AI") >> [team:ask_sync]("컨텐츠/컨텐츠") {message: "이 글들의 핵심 인사이트를 정리해줘"}', "source,team", "pipeline", 2, "pipeline,sequential"),

    # 크롤링 → 저장
    ("웹페이지 크롤링해서 저장해", '[source:crawl]("https://example.com") >> [system:file]("crawled.md")', "source,system", "pipeline", 2, "pipeline,sequential"),

    # 블로그 → 저장
    ("블로그에서 AI 글 찾아서 정리해줘", '[source:rag_search]("AI") >> [system:file]("blog_ai.md")', "source,system", "pipeline", 2, "pipeline,sequential"),

    # =========================================================================
    # 파이프라인 — 병렬 실행 (&)
    # =========================================================================

    # 주가 비교
    ("삼성전자랑 SK하이닉스 주가 비교해줘", '[source:price]("삼성전자") & [source:price]("SK하이닉스")', "source", "pipeline", 2, "pipeline,parallel"),
    ("애플이랑 마이크로소프트 주가 비교", '[source:price]("AAPL") & [source:price]("MSFT")', "source", "pipeline", 2, "pipeline,parallel"),
    ("한미 주요 종목 동시 확인", '[source:price]("005930") & [source:price]("AAPL") & [source:price]("SPY")', "source", "pipeline", 2, "pipeline,parallel"),

    # 뉴스 동시 검색
    ("AI 뉴스랑 부동산 뉴스 같이 검색해", '[source:web_search]("AI 뉴스") & [source:web_search]("부동산 뉴스")', "source", "pipeline", 2, "pipeline,parallel"),

    # 날씨 비교
    ("서울이랑 부산 날씨 같이 알려줘", '[source:weather]("서울") & [source:weather]("부산")', "source", "pipeline", 2, "pipeline,parallel"),

    # ★ 시간 + 주가 + 뉴스 (스위치에서 자주 쓰는 패턴!)
    ("현재 시간과 코스피 주가와 뉴스를 동시에 조회해줘", '[system:time]() & [source:price]("^KS11") & [source:search_news]("한국 증시")', "system,source", "pipeline", 2, "pipeline,parallel"),
    ("시간이랑 삼성전자 주가 같이 알려줘", '[system:time]() & [source:price]("005930")', "system,source", "pipeline", 2, "pipeline,parallel"),
    ("코스피 코스닥 동시 조회", '[source:price]("^KS11") & [source:price]("^KQ11")', "source", "pipeline", 2, "pipeline,parallel"),
    ("외국인 매매동향과 뉴스 같이 확인", '[source:kr_investor]("STK") & [source:search_news]("외국인 매매")', "source", "pipeline", 2, "pipeline,parallel"),

    # 크롤링 병렬
    ("네이버랑 다음 메인 동시에 크롤링", '[source:crawl]("https://naver.com") & [source:crawl]("https://daum.net")', "source", "pipeline", 2, "pipeline,parallel"),

    # =========================================================================
    # 파이프라인 — 복합 (병렬 + 순차 + Fallback)
    # =========================================================================

    # 병렬 → 저장
    ("AI랑 부동산 뉴스 찾아서 브리핑 파일로 만들어줘", '[source:web_search]("AI 뉴스") & [source:web_search]("부동산 뉴스") >> [system:file]("briefing.md")', "source,system", "complex", 3, "pipeline,complex"),

    # 3단 파이프라인 (검색 → 에이전트 분석 → 저장)
    ("삼성전자 뉴스 찾아서 분석하고 결과 저장해", '[source:search_news]("삼성전자") >> [team:ask_sync]("투자/투자컨설팅") {message: "분석해줘"} >> [system:file]("분석결과.md")', "source,team,system", "complex", 3, "pipeline,complex"),
    ("블로그 인사이트 보고서 만들어줘", '[source:search]("최근 글") {type: "blog", count: 10} >> [team:ask_sync]("컨텐츠/컨텐츠") {message: "인사이트 보고서 작성해줘"} >> [system:file]("insight_report.html") {format: "html"}', "source,team,system", "complex", 3, "pipeline,complex"),

    # 병렬 위임 (여러 프로젝트에 동시 요청)
    ("의료팀이랑 투자팀 동시에 물어봐", '[team:delegate_project]("의료/내과") {message: "건강 분석"} & [team:delegate_project]("투자/투자컨설팅") {message: "투자 분석"}', "team", "complex", 2, "team,parallel_delegation"),

    # Fallback
    ("삼성전자 주가 조회하되 실패하면 종목 검색해", '[source:price]("삼성전자") ?? [source:search_stock]("삼성전자")', "source", "pipeline", 2, "pipeline,fallback"),
    ("뉴스 검색 시도하고 안 되면 웹 검색해", '[source:search_news]("AI") ?? [source:web_search]("AI 뉴스")', "source", "pipeline", 2, "pipeline,fallback"),

    # 유튜브 → 재생
    ("피아노곡 검색해서 재생해", '[stream:search_youtube]("피아노곡") >> [stream:play]($)', "stream", "pipeline", 2, "pipeline,sequential"),

    # 시간 + 주가 + 뉴스 + 외국인 (종합 증시 체크)
    ("종합 증시 상황 확인해줘", '[system:time]() & [source:price]("^KS11") & [source:price]("^KQ11") & [source:kr_investor]("STK") & [source:search_news]("한국 증시")', "system,source", "complex", 3, "pipeline,complex"),
]


def main():
    # 1. 백업
    backup_path = DB_PATH + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, backup_path)
        print(f"[백업] {backup_path}")

    # 2. 기존 데이터 삭제 (curated 4개만 유지)
    conn = sqlite3.connect(DB_PATH)

    # curated 보존, 나머지 삭제
    cursor = conn.execute("SELECT COUNT(*) FROM ibl_examples WHERE source = 'curated'")
    curated_count = cursor.fetchone()[0]
    print(f"[유지] curated: {curated_count}개")

    conn.execute("DELETE FROM ibl_examples WHERE source != 'curated'")

    # FTS 동기화
    conn.execute("DELETE FROM ibl_examples_fts")
    conn.execute("""
        INSERT INTO ibl_examples_fts(intent, ibl_code)
        SELECT intent, ibl_code FROM ibl_examples
    """)

    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM ibl_examples").fetchone()[0]
    print(f"[삭제 완료] 남은 레코드: {remaining}개")

    # 3. 새 예제 삽입
    now = datetime.now().isoformat()
    inserted = 0
    for intent, ibl_code, nodes, category, difficulty, tags in EXAMPLES:
        conn.execute(
            """INSERT INTO ibl_examples
               (intent, ibl_code, nodes, category, difficulty, source, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'curated_v2', ?, ?, ?)""",
            (intent, ibl_code, nodes, category, difficulty, tags, now, now)
        )
        inserted += 1

    conn.commit()

    # 4. FTS 재구축 (content-sync 테이블은 'rebuild' 명령 사용)
    conn.execute("INSERT INTO ibl_examples_fts(ibl_examples_fts) VALUES('rebuild')")
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM ibl_examples").fetchone()[0]
    print(f"\n[완료] 새 예제 {inserted}개 삽입")
    print(f"[완료] 전체 레코드: {total}개")

    # 5. 통계
    print("\n=== 소스별 분포 ===")
    for row in conn.execute("SELECT source, COUNT(*) FROM ibl_examples GROUP BY source"):
        print(f"  {row[0]}: {row[1]}개")

    print("\n=== 카테고리별 분포 ===")
    for row in conn.execute("SELECT category, COUNT(*) FROM ibl_examples GROUP BY category"):
        print(f"  {row[0]}: {row[1]}개")

    print("\n=== 노드별 분포 ===")
    for row in conn.execute("SELECT nodes, COUNT(*) FROM ibl_examples GROUP BY nodes ORDER BY COUNT(*) DESC LIMIT 10"):
        print(f"  {row[0]}: {row[1]}개")

    # execution_logs도 초기화 (잘못된 패턴 로그)
    log_count = conn.execute("SELECT COUNT(*) FROM ibl_execution_logs").fetchone()[0]
    conn.execute("DELETE FROM ibl_execution_logs")
    conn.commit()
    print(f"\n[로그 초기화] 실행 로그 {log_count}개 삭제 (auto_log 오염 방지)")

    conn.close()
    print("\n✅ DB 재구축 완료!")
    print("💡 서버 재시작 후 적용됩니다.")


if __name__ == '__main__':
    main()
