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
    # self 노드 — 시스템 관리, 파일, 출력, 도구 탐색
    # =========================================================================

    # time
    ("현재 시간 알려줘", '[self:time]', "self", "single", 1, "self,time"),
    ("지금 몇 시야?", '[self:time]', "self", "single", 1, "self,time"),
    ("오늘 날짜 알려줘", '[self:time]', "self", "single", 1, "self,time"),

    # discover
    ("주가 관련 도구 찾아봐", '[self:discover]{query: "주가"}', "self", "single", 1, "self,discover"),
    ("날씨 기능 뭐 있어?", '[self:discover]{query: "날씨"}', "self", "single", 1, "self,discover"),
    ("음악 관련 기능 알려줘", '[self:discover]{query: "음악"}', "self", "single", 1, "self,discover"),
    ("사진 관련 도구 뭐 있어?", '[self:discover]{query: "사진"}', "self", "single", 1, "self,discover"),
    ("법률 검색 기능 있어?", '[self:discover]{query: "법률"}', "self", "single", 1, "self,discover"),

    # open / open_url
    ("이 파일 열어줘", '[self:open]{path: "/path/to/file.html"}', "self", "single", 1, "self,open"),
    ("파일 탐색기 열어줘", '[self:explorer]{path: "~/Desktop"}', "self", "single", 1, "self,explorer"),
    ("이 URL 열어줘", '[limbs:open_url]{path: "https://example.com"}', "limbs", "single", 1, "limbs,open_url"),
    ("구글 열어줘", '[limbs:open_url]{path: "https://google.com"}', "limbs", "single", 1, "limbs,open_url"),
    ("이 사이트 브라우저로 열어", '[limbs:open_url]{path: "https://example.com"}', "limbs", "single", 1, "limbs,open_url"),

    # CCTV / 실시간 영상
    ("광화문 CCTV 보여줘", '[sense:cctv_search]{query: "광화문"}', "sense", "single", 1, "sense,cctv_search"),
    ("해운대 지금 모습 보여줘", '[sense:cctv_search]{query: "해운대"}', "sense", "single", 1, "sense,cctv_search"),
    ("경부고속도로 교통 상황", '[sense:cctv_search]{query: "경부고속도로"}', "sense", "single", 1, "sense,cctv_search"),
    ("한라산 실시간 영상", '[sense:cctv_search]{query: "한라산"}', "sense", "single", 1, "sense,cctv_search"),
    ("타임스퀘어 웹캠 검색", '[sense:webcam]{query: "Times Square", category: "city"}', "sense", "single", 1, "sense,webcam"),
    ("서울역 근처 CCTV", '[sense:cctv_search]{query: "서울역"}', "sense", "single", 1, "sense,cctv_search"),
    ("CCTV 영상 열어줘", '[sense:cctv_open]{name: "CCTV이름"}', "sense", "single", 1, "sense,cctv_open"),
    ("CCTV 소스 상태 확인", '[sense:cctv_sources]', "sense", "single", 1, "sense,cctv_sources"),

    # file / output
    ("결과를 파일로 저장해", '[self:local_save]{path: "result.md"}', "self", "single", 1, "self,file"),
    ("보고서를 HTML로 저장해줘", '[self:local_save]{path: "report.html"}', "self", "single", 1, "self,file"),
    ("클립보드에 복사해줘", '[limbs:clipboard]{content: "복사할 내용"}', "limbs", "single", 1, "limbs,clipboard"),
    ("UI에 결과 표시해줘", '[limbs:gui]{content: "분석 결과"}', "limbs", "single", 1, "limbs,gui"),

    # file management
    ("바탕화면 파일 목록 보여줘", '[self:storage_scan]{path: "~/Desktop"}', "self", "single", 1, "self,list"),
    ("보고서.md 파일 읽어줘", '[self:local_save]{path: "보고서.md"}', "self", "single", 1, "self,read"),
    ("PDF 파일 읽어줘", '[self:local_save]{path: "문서.pdf"}', "self", "single", 1, "self,read_pdf"),
    ("메모 파일 써줘", '[self:local_save]{path: "memo.md"}', "self", "single", 1, "self,write"),
    ("py 파일 찾아줘", '[self:storage_scan]{path: "*.py"}', "self", "single", 1, "self,find"),
    ("파일에서 에러 찾아줘", '[limbs:grep]{pattern: "error"}', "limbs", "single", 1, "limbs,grep"),
    ("파일 복사해줘", '[self:local_save]{path: "source.txt"}', "self", "single", 1, "self,copy"),
    ("파일 이름 바꿔줘", '[self:local_save]{path: "old_name.txt"}', "self", "single", 1, "self,move"),
    ("저장소 용량 보여줘", '[self:storage_scan]', "self", "single", 1, "self,summary"),
    ("볼륨 목록 보여줘", '[self:storage_scan]', "self", "single", 1, "self,volumes"),

    # =========================================================================
    # others 노드 — 에이전트 간 위임/협업 (Phase 23)
    # =========================================================================

    # delegate — 같은 프로젝트 내 동료 에이전트에게 위임
    ("심장전문에게 심장 검사 요청해", '[others:delegate]{agent_id: "심장전문", message: "환자의 심장 관련 증상을 분석해주세요"}', "others", "single", 1, "others,delegate"),
    ("내과에게 두통 증상 분석 맡겨", '[others:delegate]{agent_id: "내과", message: "두통 증상 분석해주세요"}', "others", "single", 1, "others,delegate"),
    ("스토리텔러에게 슬라이드 만들어달라고 해", '[others:delegate]{agent_id: "스토리텔러", message: "AI 트렌드 발표자료 만들어줘"}', "others", "single", 1, "others,delegate"),
    ("정보수집 에이전트에게 자료 조사 맡겨", '[others:delegate]{agent_id: "정보수집", message: "최신 AI 뉴스 정리해줘"}', "others", "single", 1, "others,delegate"),

    # ask — 다른 프로젝트 에이전트에게 질문/위임 (비동기)
    ("투자 에이전트한테 물어봐", '[others:ask]{agent_id: "투자/투자컨설팅", message: "삼성전자 투자 의견 알려줘"}', "others", "single", 1, "others,ask"),
    ("컨텐츠 에이전트한테 부탁해", '[others:ask]{agent_id: "컨텐츠/컨텐츠", message: "블로그 글 분석해줘"}', "others", "single", 1, "others,ask"),
    ("정보센터에 분석 요청해", '[others:ask]{agent_id: "정보센터/정보수집", message: "AI 트렌드 조사해줘"}', "others", "single", 1, "others,ask"),
    ("의료팀에게 건강 상담 요청해", '[others:ask]{agent_id: "의료/가정의학과", message: "두통이 자주 발생하는 원인을 알려줘"}', "others", "single", 1, "others,ask"),
    ("법률 에이전트한테 임대차 관련 질문해", '[others:ask]{agent_id: "법률/법률", message: "임대차보호법 관련 질문입니다"}', "others", "single", 1, "others,ask"),

    # ask_sync — 동기 질문 (파이프라인/워크플로우용)
    ("투자 에이전트에게 동기적으로 분석 요청", '[others:ask_sync]{agent_id: "투자/투자컨설팅", message: "이 데이터를 분석해줘"}', "others", "single", 1, "others,ask_sync"),
    ("컨텐츠 에이전트에게 즉시 답변 요청", '[others:ask_sync]{agent_id: "컨텐츠/컨텐츠", message: "이 글을 요약해줘"}', "others", "single", 1, "others,ask_sync"),

    # delegate_project — 시스템 AI가 프로젝트 에이전트에게 위임
    ("의료 프로젝트 내과에게 위임해", '[others:delegate_project]{agent_id: "의료/내과", message: "두통 증상 분석해주세요"}', "others", "single", 1, "others,delegate_project"),
    ("투자 프로젝트에 분석 맡겨", '[others:delegate_project]{agent_id: "투자/투자컨설팅", message: "포트폴리오 리밸런싱 분석"}', "others", "single", 1, "others,delegate_project"),
    ("홍보팀에게 슬라이드 제작 위임해", '[others:delegate_project]{agent_id: "홍보/storyteller", message: "분기 실적 발표 슬라이드 만들어줘"}', "others", "single", 1, "others,delegate_project"),

    # info — 에이전트/프로젝트 정보 조회
    ("에이전트 정보 알려줘", '[others:agent_info]{agent_id: "투자/투자컨설팅"}', "others", "single", 1, "others,info"),
    ("의료 프로젝트 에이전트들 뭐 있어?", '[others:agent_info]{agent_id: "의료"}', "others", "single", 1, "others,info"),

    # list_projects — 프로젝트/에이전트 목록
    ("프로젝트 목록 보여줘", '[others:list_projects]', "others", "single", 1, "others,list_projects"),
    ("어떤 에이전트들이 있어?", '[others:list_projects]', "others", "single", 1, "others,list_projects"),

    # workflow
    ("저장된 워크플로우 목록 보여줘", '[self:event_status]', "self", "single", 1, "self,list_workflows"),
    ("뉴스 브리핑 워크플로우 실행해", '[limbs:run]{name: "news_briefing"}', "limbs", "single", 1, "limbs,run"),

    # switches / events
    ("스위치 목록 보여줘", '[self:event_status]', "self", "single", 1, "self,list_switches"),
    ("트리거 목록 보여줘", '[self:event_history]', "self", "single", 1, "self,list_events"),
    ("이벤트 시스템 상태 확인", '[self:event_status]', "self", "single", 1, "self,status"),

    # user interaction
    ("할일 목록 만들어줘", '[limbs:todo]{content: "할일 정리"}', "limbs", "single", 1, "limbs,todo"),
    ("사용자에게 알림 보내줘", '[limbs:notify_user]{message: "작업 완료"}', "limbs", "single", 1, "limbs,notify_user"),
    ("사용자에게 확인 요청해", '[limbs:ask_user]{question: "계속 진행할까요?"}', "limbs", "single", 1, "limbs,ask_user"),
    ("API 도구 목록 보여줘", '[limbs:list_api]', "limbs", "single", 1, "limbs,list_api"),
    ("다운로드해줘", '[limbs:download]{url: "https://example.com/file.zip"}', "limbs", "single", 1, "limbs,download"),

    # =========================================================================
    # sense 노드 — 데이터 조사/검색 (투자, 뉴스, 날씨 등)
    # =========================================================================

    # 주가/투자
    ("삼성전자 주가 알려줘", '[sense:stock_info]{symbol: "삼성전자"}', "sense", "single", 1, "sense,price"),
    ("삼성전자 주가 조회", '[sense:stock_info]{symbol: "005930"}', "sense", "single", 1, "sense,price"),
    ("애플 주가 확인해줘", '[sense:stock_info]{symbol: "AAPL"}', "sense", "single", 1, "sense,price"),
    ("테슬라 주가 보여줘", '[sense:stock_info]{symbol: "TSLA"}', "sense", "single", 1, "sense,price"),
    ("SPY ETF 가격 알려줘", '[sense:stock_info]{symbol: "SPY"}', "sense", "single", 1, "sense,price"),
    ("금 시세 알려줘", '[sense:stock_info]{symbol: "GC=F"}', "sense", "single", 1, "sense,price"),
    ("한국 주가 기간별 조회해줘", '[sense:stock_info]{symbol: "005930"}', "sense", "single", 1, "sense,kr_price"),
    ("미국 주가 기간별 조회", '[sense:stock_info]{symbol: "AAPL"}', "sense", "single", 1, "sense,us_price"),
    ("비트코인 시세 알려줘", '[sense:stock_info]{coin_id: "bitcoin"}', "sense", "single", 1, "sense,crypto"),
    ("이더리움 가격 확인", '[sense:stock_info]{coin_id: "ethereum"}', "sense", "single", 1, "sense,crypto"),
    ("종목 코드 검색해줘", '[sense:stock_info]{query: "반도체"}', "sense", "single", 1, "sense,search_stock"),
    ("삼성전자 종목 상세 정보", '[sense:stock_info]{symbol: "005930"}', "sense", "single", 1, "sense,info"),
    ("삼성전자 뉴스 알려줘", '[sense:stock_info]{symbol: "삼성전자"}', "sense", "single", 1, "sense,news"),
    ("테슬라 관련 뉴스", '[sense:stock_info]{symbol: "TSLA"}', "sense", "single", 1, "sense,stock_news"),
    ("삼성전자 실적 발표 일정", '[sense:stock_info]{symbol: "005930"}', "sense", "single", 1, "sense,earnings"),

    # 기업정보/재무
    ("삼성전자 기업 정보", '[sense:stock_info]{query: "삼성전자"}', "sense", "single", 1, "sense,kr_company"),
    ("애플 기업 프로필", '[sense:stock_info]{symbol: "AAPL"}', "sense", "single", 1, "sense,us_company"),
    ("삼성전자 재무제표", '[sense:stock_info]{query: "삼성전자"}', "sense", "single", 1, "sense,kr_financial"),
    ("애플 재무제표 보여줘", '[sense:stock_info]{symbol: "AAPL"}', "sense", "single", 1, "sense,us_financial"),
    ("삼성전자 공시 검색", '[sense:stock_info]{query: "삼성전자"}', "sense", "single", 1, "sense,kr_disclosure"),
    ("애플 SEC 공시 조회", '[sense:stock_info]{symbol: "AAPL"}', "sense", "single", 1, "sense,us_filing"),

    # 투자자 매매동향
    ("외국인 매매동향 알려줘", '[sense:stock_info]{symbol: "STK"}', "sense", "single", 1, "sense,kr_investor"),
    ("코스닥 투자자 매매동향", '[sense:stock_info]{symbol: "KSQ"}', "sense", "single", 1, "sense,kr_investor"),
    ("오늘 외국인 순매수 얼마야?", '[sense:stock_info]{symbol: "STK"}', "sense", "single", 1, "sense,kr_investor"),
    ("삼성전자 투자자별 매매동향", '[sense:stock_info]{symbol: "005930"}', "sense", "single", 1, "sense,kr_stock_investor"),

    # 웹 검색/크롤링
    ("AI 뉴스 검색해줘", '[sense:web_search]{query: "AI 뉴스"}', "sense", "single", 1, "sense,web_search"),
    ("반도체 뉴스 검색해줘", '[sense:web_search]{query: "반도체"}', "sense", "single", 1, "sense,search_news"),
    ("부동산 뉴스 찾아줘", '[sense:web_search]{query: "부동산"}', "sense", "single", 1, "sense,search_news"),
    ("경제 뉴스 검색", '[sense:web_search]{query: "경제"}', "sense", "single", 1, "sense,search_news"),
    ("이 웹페이지 내용 가져와", '[sense:web_search]{url: "https://example.com/article"}', "sense", "single", 1, "sense,crawl"),
    ("네이버 메인 크롤링해줘", '[sense:web_search]{url: "https://naver.com"}', "sense", "single", 1, "sense,crawl"),

    # 날씨/위치
    ("서울 날씨 알려줘", '[sense:navigate_route]{query: "서울"}', "sense", "single", 1, "sense,weather"),
    ("부산 날씨 확인", '[sense:navigate_route]{query: "부산"}', "sense", "single", 1, "sense,weather"),
    ("강남역 맛집 찾아줘", '[sense:navigate_route]{query: "강남역"}', "sense", "single", 1, "sense,restaurant"),
    ("청주 맛집 추천해줘", '[sense:navigate_route]{query: "청주"}', "sense", "single", 1, "sense,restaurant"),
    ("지도에 표시해줘", '[sense:navigate_route]{query: "강남역"}', "sense", "single", 1, "sense,map"),

    # 법률/통계
    ("임대차보호법 검색해줘", '[sense:web_search]{query: "임대차보호법"}', "sense", "single", 1, "sense,search_laws"),
    ("근로기준법 찾아봐", '[sense:web_search]{query: "근로기준법"}', "sense", "single", 1, "sense,search_laws"),
    ("인구 통계 검색", '[sense:web_search]{query: "인구"}', "sense", "single", 1, "sense,search_kosis"),

    # 문화/도서
    ("공연 검색해줘", '[sense:web_search]{query: "뮤지컬"}', "sense", "single", 1, "sense,performance"),
    ("전시회 정보 찾아줘", '[sense:web_search]{query: "미술"}', "sense", "single", 1, "sense,exhibit"),
    ("책 검색해줘", '[sense:web_search]{query: "인공지능"}', "sense", "single", 1, "sense,book"),
    ("도서 상세 정보", '[sense:web_search]{query: "9791192107103"}', "sense", "single", 1, "sense,book_detail"),

    # 쇼핑
    ("노트북 가격 비교해줘", '[sense:web_search]{query: "맥북 프로 14인치"}', "sense", "single", 1, "sense,search_shopping"),
    ("에어팟 가격 검색", '[sense:web_search]{query: "에어팟 프로"}', "sense", "single", 1, "sense,search_shopping"),

    # 부동산
    ("아파트 매매 실거래가 조회", '[sense:web_search]{query: "11110"}', "sense", "single", 1, "sense,apt_trade"),
    ("아파트 전월세 조회", '[sense:web_search]{query: "11110"}', "sense", "single", 1, "sense,apt_rent"),
    ("지역코드 검색", '[sense:web_search]{query: "서울"}', "sense", "single", 1, "sense,district_codes"),

    # 사진
    ("여행 사진 검색해줘", '[self:photo_scan]{query: "여행"}', "self", "single", 1, "self,search_photos"),
    ("사진 통계 보여줘", '[self:photo_scan]', "self", "single", 1, "self,photo_stats"),
    ("사진 갤러리 열어줘", '[self:photo_scan]', "self", "single", 1, "self,gallery"),
    ("사진관리창 열어줘", '[self:photo_scan]', "self", "single", 1, "self,photo_manager"),

    # 블로그
    ("블로그에서 AI 글 검색", '[self:photo_scan]{query: "인공지능"}', "self", "single", 1, "self,rag_search"),
    ("블로그 글 목록 보여줘", '[self:photo_scan]', "self", "single", 1, "self,posts"),
    ("블로그 통계 보여줘", '[self:photo_scan]', "self", "single", 1, "self,blog_stats"),
    ("새 블로그 글 있어?", '[self:photo_scan]', "self", "single", 1, "self,check_new"),
    ("블로그 인사이트 분석해줘", '[self:photo_scan]{query: "AI 트렌드"}', "self", "single", 1, "self,insight"),

    # 메모리/대화
    ("최근 대화 보여줘", '[self:photo_scan]', "self", "single", 1, "self,recent"),
    ("대화 내용 검색해줘", '[self:photo_scan]{query: "주식"}', "self", "single", 1, "self,search_memory"),
    ("메모리에 저장해줘", '[self:photo_scan]{query: "중요한 정보"}', "self", "single", 1, "self,save_memory"),
    ("메모리에서 검색해줘", '[self:photo_scan]{query: "투자"}', "self", "single", 1, "self,memory_search"),

    # 건강
    ("건강 기록 조회", '[self:health_query]{category: "요약"}', "self", "single", 1, "self,health_query"),
    ("혈압 기록 저장해줘", '[self:health_save]{category: "혈압", value: {systolic: 130, diastolic: 85}}', "self", "single", 1, "self,health_save"),
    ("혈액검사 결과 찾아줘", '[self:health_query]{category: "검색", keyword: "혈액검사"}', "self", "single", 1, "self,health_query"),
    ("내 건강기록 보여줘", '[self:health_query]{category: "요약"}', "self", "single", 1, "self,health_query"),
    ("혈당 기록 조회해줘", '[self:health_query]{category: "혈당"}', "self", "single", 1, "self,health_query"),
    ("오늘 혈압 저장해줘", '[self:health_save]{category: "혈압", value: {systolic: 128, diastolic: 90}}', "self", "single", 1, "self,health_save"),
    ("건강기록에서 혈액검사 결과 찾아줘", '[self:health_query]{category: "혈액검사"}', "self", "single", 1, "self,health_query"),
    ("최근 혈압 기록 보여줘", '[self:health_query]{category: "혈압"}', "self", "single", 1, "self,health_query"),
    ("복용 중인 약 목록", '[self:health_query]{category: "투약"}', "self", "single", 1, "self,health_query"),
    ("체중 기록해줘", '[self:health_save]{category: "체중", value: 75}', "self", "single", 1, "self,health_save"),

    # 홈페이지/웹 관리
    ("관리하는 홈페이지 목록 보여줘", '[engines:site_list]', "engines", "single", 1, "engines,site_list"),
    ("등록된 사이트 몇 개야?", '[engines:site_list]', "engines", "single", 1, "engines,site_list"),
    ("새 사이트 등록해줘", '[engines:site_register]{name: "내 사이트", local_path: "/path/to/site"}', "engines", "single", 1, "engines,site_register"),
    ("사이트 삭제해줘", '[engines:site_remove]{site_id: "my-site"}', "engines", "single", 1, "engines,site_remove"),

    # 학술
    ("AI 논문 검색해줘", '[sense:web_search]{query: "artificial intelligence"}', "sense", "single", 1, "sense,search_arxiv"),
    ("학술 논문 찾아줘", '[sense:web_search]{query: "machine learning"}', "sense", "single", 1, "sense,search_scholar"),

    # =========================================================================
    # tools 노드 — 음악/라디오/유튜브
    # =========================================================================

    # 음악 재생
    ("슬픈 피아노곡 틀어줘", '[limbs:play]{query: "슬픈 피아노곡"}', "limbs", "single", 1, "limbs,play"),
    ("재즈 음악 틀어줘", '[limbs:play]{query: "jazz music"}', "limbs", "single", 1, "limbs,play"),
    ("잔잔한 음악 재생해", '[limbs:play]{query: "잔잔한 배경음악"}', "limbs", "single", 1, "limbs,play"),
    ("BTS 노래 틀어줘", '[limbs:play]{query: "BTS"}', "limbs", "single", 1, "limbs,play"),
    ("클래식 음악 들려줘", '[limbs:play]{query: "클래식 음악"}', "limbs", "single", 1, "limbs,play"),

    # 유튜브 검색/정보
    ("유튜브에서 피아노곡 검색해", '[sense:search_youtube]{query: "피아노곡"}', "sense", "single", 1, "sense,search_youtube"),
    ("유튜브 검색 결과만 보여줘", '[sense:search_youtube]{query: "AI 뉴스"}', "sense", "single", 1, "sense,search_youtube"),
    ("이 영상 정보 알려줘", '[sense:video_info]{url: "https://youtube.com/watch?v=example"}', "sense", "single", 1, "sense,info"),
    ("영상 자막 추출해줘", '[limbs:youtube_download]{url: "https://youtube.com/watch?v=example"}', "limbs", "single", 1, "limbs,transcript"),
    ("영상 오디오 다운로드해줘", '[limbs:youtube_download]{url: "https://youtube.com/watch?v=example"}', "limbs", "single", 1, "limbs,download"),

    # 재생 컨트롤
    ("다음 곡으로 넘겨줘", '[limbs:skip]', "limbs", "single", 1, "limbs,skip"),
    ("음악 정지해", '[limbs:stop]', "limbs", "single", 1, "limbs,stop"),
    ("현재 재생 목록 보여줘", '[limbs:queue]', "limbs", "single", 1, "limbs,queue"),
    ("재생 상태 확인", '[limbs:player_status]', "limbs", "single", 1, "limbs,status"),
    ("볼륨 올려줘", '[limbs:volume]{volume: "80"}', "limbs", "single", 1, "limbs,volume"),
    ("이 곡 큐에 추가해줘", '[limbs:queue_add]{query: "아이유"}', "limbs", "single", 1, "limbs,queue_add"),

    # 라디오
    ("KBS 라디오 찾아줘", '[sense:search_radio]{query: "KBS"}', "sense", "single", 1, "sense,search_radio"),
    ("한국 라디오 채널 목록", '[sense:korean_radio]{query: "KBS"}', "sense", "single", 1, "sense,korean"),
    ("라디오 틀어줘", '[limbs:play]{query: "KBS 클래식FM"}', "limbs", "single", 1, "limbs,radio_play"),
    ("라디오 꺼줘", '[limbs:stop]', "limbs", "single", 1, "limbs,radio_stop"),
    ("즐겨찾기 라디오 보여줘", '[limbs:queue]', "limbs", "single", 1, "limbs,favorites"),

    # =========================================================================
    # forge 노드 — 콘텐츠 생성
    # =========================================================================

    # 신문
    ("신문 만들어줘", '[engines:newspaper]{keywords: "AI, 경제, 문화"}', "engines", "single", 1, "engines,newspaper"),
    ("AI 뉴스 신문 만들어", '[engines:newspaper]{keywords: "AI"}', "engines", "single", 1, "engines,newspaper"),
    ("구글뉴스 신문 생성해줘", '[engines:newspaper]{keywords: "AI, 청주, 세종, 문화, 여행, 과학, 경제"}', "engines", "single", 1, "engines,newspaper"),
    # 신문 파이프라인 (검색 → 생성 → 브라우저)
    ("이란 전쟁 뉴스 검색해서 신문 만들어줘", '[sense:web_search]{query: "이란 전쟁"} >> [engines:newspaper]{keywords: "이란과 전쟁"} >> [self:open]{path: "browse"}', "sense,forge,self", "pipeline", 3, "sense,web_search,forge,newspaper,self,open"),
    ("AI 뉴스 신문 만들어서 열어줘", '[engines:newspaper]{keywords: "AI"} >> [self:open]{path: "browse"}', "engines,self", "pipeline", 2, "engines,newspaper,self,open"),

    # 차트/시각화
    ("라인 차트 그려줘", '[engines:line]{title: "주가 추이"}', "engines", "single", 1, "engines,line"),
    ("바 차트 만들어줘", '[engines:bar]{title: "매출 비교"}', "engines", "single", 1, "engines,bar"),
    ("파이 차트 그려줘", '[engines:pie]{title: "시장 점유율"}', "engines", "single", 1, "engines,pie"),
    ("캔들스틱 차트 그려줘", '[engines:candlestick]{title: "삼성전자 주가"}', "engines", "single", 1, "engines,candlestick"),
    ("히트맵 만들어줘", '[engines:heatmap]{title: "상관관계"}', "engines", "single", 1, "engines,heatmap"),
    ("차트 대시보드 만들어줘", '[engines:multi]{title: "투자 대시보드"}', "engines", "single", 1, "engines,multi"),

    # 슬라이드/영상
    ("발표 슬라이드 만들어줘", '[engines:slide]{topic: "AI 트렌드 2026"}', "engines", "single", 1, "engines,slide"),
    ("고품질 슬라이드 만들어줘", '[engines:slide_shadcn]{topic: "분기 실적"}', "engines", "single", 1, "engines,slide_shadcn"),
    ("영상 만들어줘", '[engines:video]{topic: "회사 소개"}', "engines", "single", 1, "engines,video"),
    ("TTS로 음성 변환해줘", '[engines:tts]{text: "안녕하세요, 오늘 뉴스입니다"}', "engines", "single", 1, "engines,tts"),

    # 음악/작곡
    ("피아노곡 작곡해줘", '[engines:music]{title: "편안한 피아노 소품"}', "engines", "single", 1, "engines,music"),

    # AI 이미지
    ("AI 이미지 만들어줘", '[engines:image_gemini]{prompt: "아름다운 한국 산 풍경"}', "engines", "single", 1, "engines,image_gemini"),

    # 웹사이트
    ("웹사이트 만들어줘", '[engines:create_site]{name: "카페 홈페이지"}', "engines", "single", 1, "engines,create_site"),
    ("랜딩 페이지 만들어줘", '[engines:create_site]{name: "제품 소개 페이지"}', "engines", "single", 1, "engines,create_site"),
    ("사이트 배포해줘", 'run_command("cd /path/to/site && vercel --prod --yes")', "run_command", "single", 1, "run_command"),

    # 설계
    ("집 설계 시작해줘", '[engines:create_design]{name: "내 집"}', "engines", "single", 1, "engines,create_design"),
    ("평면도 그려줘", '[engines:floor_plan]{design_id: "design_1"}', "engines", "single", 1, "engines,floor_plan"),

    # =========================================================================
    # tools 노드 — 브라우저/안드로이드/데스크탑
    # =========================================================================

    # 브라우저
    ("이 사이트 Playwright로 열어", '[limbs:navigate]{url: "https://google.com"}', "limbs", "single", 1, "limbs,navigate"),
    ("페이지 스냅샷 찍어", '[limbs:browser_snapshot]', "limbs", "single", 1, "limbs,snapshot"),
    ("스크린샷 찍어줘", '[limbs:screenshot]', "limbs", "single", 1, "limbs,screenshot"),
    ("페이지 내용 추출해", '[limbs:content]', "limbs", "single", 1, "limbs,content"),
    ("JavaScript 실행해줘", '[limbs:evaluate]{expression: "document.title"}', "limbs", "single", 1, "limbs,evaluate"),

    # 안드로이드
    ("연결된 기기 목록 보여줘", '[limbs:devices]', "limbs", "single", 1, "limbs,devices"),
    ("안드로이드 화면 캡처", '[limbs:android_screenshot]', "limbs", "single", 1, "limbs,android_screenshot"),
    ("문자 목록 보여줘", '[limbs:sms_list]', "limbs", "single", 1, "limbs,sms_list"),
    ("통화 이력 보여줘", '[limbs:call_log]', "limbs", "single", 1, "limbs,call_log"),
    ("연락처 검색해줘", '[limbs:contacts]{query: "홍길동"}', "limbs", "single", 1, "limbs,contacts"),
    ("안드로이드 관리창 열어줘", '[limbs:manager]', "limbs", "single", 1, "limbs,manager"),

    # 데스크탑
    ("Mac 화면 캡처해줘", '[limbs:desktop_screenshot]', "limbs", "single", 1, "limbs,desktop_screenshot"),

    # =========================================================================
    # others 노드 — 통신
    # =========================================================================

    ("이메일 보내줘", '[others:channel_send]{to: "user@example.com"}', "others", "single", 1, "others,send_email"),
    ("이웃 목록 보여줘", '[others:channel_read]', "others", "single", 1, "others,neighbors"),
    ("이웃 상세 정보 조회", '[others:channel_read]{query: "홍길동"}', "others", "single", 1, "others,neighbor_detail"),
    ("메시지 검색해줘", '[others:channel_search]{query: "미팅"}', "others", "single", 1, "others,search"),

    # =========================================================================
    # 파이프라인 — 순차 실행 (>>)
    # =========================================================================

    # 검색 → 저장
    ("AI 뉴스 검색해서 파일로 저장해줘", '[sense:web_search]{query: "AI 뉴스"} >> [self:local_save]{path: "ai_news.md"}', "sense,self", "pipeline", 2, "pipeline,sequential"),
    ("부동산 뉴스 찾아서 저장해", '[sense:web_search]{query: "부동산"} >> [self:local_save]{path: "부동산뉴스.md"}', "sense,self", "pipeline", 2, "pipeline,sequential"),
    ("반도체 뉴스 검색해서 정리해줘", '[sense:web_search]{query: "반도체"} >> [self:local_save]{path: "반도체뉴스.md"}', "sense,self", "pipeline", 2, "pipeline,sequential"),

    # 검색 → 차트
    ("삼성전자 주가 조회해서 차트로 그려줘", '[sense:stock_info]{symbol: "삼성전자"} >> [engines:line]{title: "삼성전자 주가 차트"}', "sense,forge", "pipeline", 2, "pipeline,sequential"),
    ("애플 주가 차트 만들어줘", '[sense:stock_info]{symbol: "AAPL"} >> [engines:line]{title: "AAPL 주가 차트"}', "sense,forge", "pipeline", 2, "pipeline,sequential"),

    # 유튜브 → 저장
    ("유튜브 자막 추출해서 파일로 저장해", '[limbs:youtube_download]{url: "https://youtube.com/watch?v=example"} >> [self:local_save]{path: "transcript.md"}', "limbs,self", "pipeline", 2, "pipeline,sequential"),

    # 검색 → 에이전트 분석 (others 노드 파이프라인)
    ("AI 뉴스 찾아서 투자 에이전트에게 분석 요청해", '[sense:web_search]{query: "AI 뉴스"} >> [others:ask_sync]{agent_id: "투자/투자컨설팅", message: "이 뉴스를 투자 관점에서 분석해줘"}', "sense,others", "pipeline", 2, "pipeline,sequential"),
    ("부동산 뉴스 찾아서 부동산 에이전트에게 넘겨줘", '[sense:web_search]{query: "부동산"} >> [others:ask_sync]{agent_id: "부동산/부동산", message: "이 뉴스에서 시장 동향을 분석해줘"}', "sense,others", "pipeline", 2, "pipeline,sequential"),
    ("블로그 글 찾아서 컨텐츠 에이전트에게 분석 맡겨", '[self:photo_scan]{query: "AI"} >> [others:ask_sync]{agent_id: "컨텐츠/컨텐츠", message: "이 글들의 핵심 인사이트를 정리해줘"}', "self,others", "pipeline", 2, "pipeline,sequential"),

    # 크롤링 → 저장
    ("웹페이지 크롤링해서 저장해", '[sense:web_search]{url: "https://example.com"} >> [self:local_save]{path: "crawled.md"}', "sense,self", "pipeline", 2, "pipeline,sequential"),

    # 블로그 → 저장
    ("블로그에서 AI 글 찾아서 정리해줘", '[self:photo_scan]{query: "AI"} >> [self:local_save]{path: "blog_ai.md"}', "self,self", "pipeline", 2, "pipeline,sequential"),

    # =========================================================================
    # 파이프라인 — 병렬 실행 (&)
    # =========================================================================

    # 주가 비교
    ("삼성전자랑 SK하이닉스 주가 비교해줘", '[sense:stock_info]{symbol: "삼성전자"} & [sense:stock_info]{symbol: "SK하이닉스"}', "sense", "pipeline", 2, "pipeline,parallel"),
    ("애플이랑 마이크로소프트 주가 비교", '[sense:stock_info]{symbol: "AAPL"} & [sense:stock_info]{symbol: "MSFT"}', "sense", "pipeline", 2, "pipeline,parallel"),
    ("한미 주요 종목 동시 확인", '[sense:stock_info]{symbol: "005930"} & [sense:stock_info]{symbol: "AAPL"} & [sense:stock_info]{symbol: "SPY"}', "sense", "pipeline", 2, "pipeline,parallel"),

    # 뉴스 동시 검색
    ("AI 뉴스랑 부동산 뉴스 같이 검색해", '[sense:web_search]{query: "AI 뉴스"} & [sense:web_search]{query: "부동산 뉴스"}', "sense", "pipeline", 2, "pipeline,parallel"),

    # 날씨 비교
    ("서울이랑 부산 날씨 같이 알려줘", '[sense:navigate_route]{query: "서울"} & [sense:navigate_route]{query: "부산"}', "sense", "pipeline", 2, "pipeline,parallel"),

    # ★ 시간 + 주가 + 뉴스 (스위치에서 자주 쓰는 패턴!)
    ("현재 시간과 코스피 주가와 뉴스를 동시에 조회해줘", '[self:time] & [sense:stock_info]{symbol: "^KS11"} & [sense:web_search]{query: "한국 증시"}', "self,sense", "pipeline", 2, "pipeline,parallel"),
    ("시간이랑 삼성전자 주가 같이 알려줘", '[self:time] & [sense:stock_info]{symbol: "005930"}', "self,sense", "pipeline", 2, "pipeline,parallel"),
    ("코스피 코스닥 동시 조회", '[sense:stock_info]{symbol: "^KS11"} & [sense:stock_info]{symbol: "^KQ11"}', "sense", "pipeline", 2, "pipeline,parallel"),
    ("외국인 매매동향과 뉴스 같이 확인", '[sense:stock_info]{symbol: "STK"} & [sense:web_search]{query: "외국인 매매"}', "sense", "pipeline", 2, "pipeline,parallel"),

    # 크롤링 병렬
    ("네이버랑 다음 메인 동시에 크롤링", '[sense:web_search]{url: "https://naver.com"} & [sense:web_search]{url: "https://daum.net"}', "sense", "pipeline", 2, "pipeline,parallel"),

    # =========================================================================
    # 파이프라인 — 복합 (병렬 + 순차 + Fallback)
    # =========================================================================

    # 병렬 → 저장
    ("AI랑 부동산 뉴스 찾아서 브리핑 파일로 만들어줘", '[sense:web_search]{query: "AI 뉴스"} & [sense:web_search]{query: "부동산 뉴스"} >> [self:local_save]{path: "briefing.md"}', "sense,self", "complex", 3, "pipeline,complex"),

    # 3단 파이프라인 (검색 → 에이전트 분석 → 저장)
    ("삼성전자 뉴스 찾아서 분석하고 결과 저장해", '[sense:web_search]{query: "삼성전자"} >> [others:ask_sync]{agent_id: "투자/투자컨설팅", message: "분석해줘"} >> [self:local_save]{path: "분석결과.md"}', "sense,others,self", "complex", 3, "pipeline,complex"),
    ("블로그 인사이트 보고서 만들어줘", '[self:photo_scan]{query: "최근 글", type: "blog", count: 10} >> [others:ask_sync]{agent_id: "컨텐츠/컨텐츠", message: "인사이트 보고서 작성해줘"} >> [self:local_save]{path: "insight_report.html", format: "html"}', "self,others,self", "complex", 3, "pipeline,complex"),

    # 병렬 위임 (여러 프로젝트에 동시 요청)
    ("의료팀이랑 투자팀 동시에 물어봐", '[others:delegate_project]{agent_id: "의료/내과", message: "건강 분석"} & [others:delegate_project]{agent_id: "투자/투자컨설팅", message: "투자 분석"}', "others", "complex", 2, "others,parallel_delegation"),

    # Fallback
    ("삼성전자 주가 조회하되 실패하면 종목 검색해", '[sense:stock_info]{symbol: "삼성전자"} ?? [sense:stock_info]{symbol: "삼성전자"}', "sense", "pipeline", 2, "pipeline,fallback"),
    ("뉴스 검색 시도하고 안 되면 웹 검색해", '[sense:web_search]{query: "AI"} ?? [sense:web_search]{query: "AI 뉴스"}', "sense", "pipeline", 2, "pipeline,fallback"),

    # 유튜브 → 재생
    ("피아노곡 검색해서 재생해", '[sense:search_youtube]{query: "피아노곡"} >> [limbs:play]', "sense,tools", "pipeline", 2, "pipeline,sequential"),

    # 시간 + 주가 + 뉴스 + 외국인 (종합 증시 체크)
    ("종합 증시 상황 확인해줘", '[self:time] & [sense:stock_info]{symbol: "^KS11"} & [sense:stock_info]{symbol: "^KQ11"} & [sense:stock_info]{symbol: "STK"} & [sense:web_search]{query: "한국 증시"}', "self,sense", "complex", 3, "pipeline,complex"),
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
