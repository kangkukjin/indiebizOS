"""
Opus 품질 대량 합성: 489개 코드 × 5건 = ~2,445건
의미적으로 완전히 다른 구어체 표현을 생성한다.
"""
import json, re, random
from pathlib import Path

random.seed(42)
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT = PROJECT_ROOT / "data" / "ibl_synthetic_opus.json"

with open('/tmp/ibl_batch_all.json') as f:
    all_items = json.load(f)

# ====================================================================
# 핵심: 액션 패턴별 구어체 변형 사전 (의미적 도약 포함)
# ====================================================================

# 파라미터 추출
def p(code, key):
    m = re.search(rf'{key}:\s*"([^"]*)"', code)
    return m.group(1) if m else ""

def action(code):
    m = re.search(r'\[(\w+:\w+)\]', code)
    return m.group(1) if m else ""

# 액션별 변형 생성 함수
def gen(code, intents):
    a = action(code)
    results = []

    # ---- sense:navigate ----
    if a == "sense:navigate":
        dest = p(code, "destination")
        origin = p(code, "origin")
        if dest and origin:
            results += [
                f"{dest} 어떻게 가?",
                f"{origin}에서 {dest} 가는 법",
                f"{dest} 네비 켜줘",
                f"{dest}까지 얼마나 걸려?",
                f"{dest} 가는 길 좀 알려줘",
            ]

    # ---- self:time ----
    elif a == "self:time":
        results += ["몇 시야", "시간 좀", "오늘 며칠", "무슨 요일이야", "지금 몇 시"]

    # ---- self:discover ----
    elif a == "self:discover":
        q = p(code, "query")
        if q:
            results += [
                f"{q} 할 수 있는 거 뭐야?", f"{q} 관련 기능 뭐 있지",
                f"{q} 어떻게 해?", f"나 {q} 하고 싶은데", f"{q} 되나?"
            ]

    # ---- sense:search / search_news ----
    elif a in ("sense:search", "sense:search_news"):
        q = p(code, "query")
        if q:
            results += [
                f"{q} 좀 찾아봐", f"{q} 관련 뭐 있어?",
                f"{q} 요즘 어때", f"{q} 소식 좀", f"{q} 알아봐줘"
            ]

    # ---- sense:stock_info / kr_price / us_price ----
    elif a in ("sense:stock_info", "sense:kr_price", "sense:us_price", "sense:price"):
        sym = p(code, "symbol") or p(code, "coin_id") or p(code, "corp_name")
        if sym:
            results += [
                f"{sym} 지금 얼마야", f"{sym} 좀 봐봐", f"{sym} 오늘 어때",
                f"{sym} 시세 좀", f"{sym} 올랐어?"
            ]
        q = p(code, "query")
        if q:
            results += [f"{q} 종목 뭐 있어?", f"{q} 관련 주식", f"{q} 찾아봐"]

    # ---- sense:navigate_route (날씨/맛집 등) ----
    elif a == "sense:navigate_route":
        q = p(code, "query")
        if q:
            results += [
                f"{q} 어때?", f"{q} 좀 알려줘", f"{q} 정보 좀",
                f"{q} 관련 찾아줘", f"{q} 알아봐"
            ]

    # ---- sense:weather ----
    elif a == "sense:weather":
        city = p(code, "city")
        if city:
            results += [
                f"{city} 날씨 어때", f"{city} 비 오나?", f"{city} 오늘 기온",
                f"{city} 우산 챙겨야 해?", f"지금 {city} 밖에 어때"
            ]

    # ---- sense:cctv_search ----
    elif a == "sense:cctv_search":
        q = p(code, "query")
        if q:
            results += [
                f"{q} 지금 어때?", f"{q} 실시간 좀", f"{q} 카메라 봐봐",
                f"{q} 상황 좀 봐줘", f"{q} 사람 많아?"
            ]

    # ---- self:save_memory ----
    elif a == "self:save_memory":
        results += [
            "이거 기억해둬", "잊지 마 이거", "메모해놔",
            "나중에 쓸 거야 저장해", "이거 적어둬"
        ]

    # ---- self:search_memory ----
    elif a == "self:search_memory":
        q = p(code, "query")
        if q:
            results += [
                f"{q} 관련 뭐 있었지?", f"{q} 기억나?",
                f"전에 {q} 관련 메모한 거", f"{q} 어디 적어뒀지?",
                f"{q} 관련 저장한 거 찾아"
            ]
        else:
            results += ["전에 뭐 메모했었지", "기억해둔 거 찾아봐", "저장한 거 있어?"]

    # ---- self:memory_read ----
    elif a == "self:memory_read":
        results += ["저장한 거 읽어봐", "메모 내용 좀", "기억해둔 거 보여줘"]

    # ---- self:memory_delete ----
    elif a == "self:memory_delete":
        results += ["그 메모 지워", "저장한 거 삭제해", "필요없는 거 정리해"]

    # ---- self:health_query ----
    elif a == "self:health_query":
        cat = p(code, "category")
        kw = p(code, "keyword")
        if kw:
            results += [f"{kw} 결과 있어?", f"{kw} 찾아봐", f"{kw} 기록 보여줘"]
        elif cat:
            results += [f"{cat} 기록 봐줘", f"{cat} 어때?", f"최근 {cat}", f"{cat} 상태 좀"]
        else:
            results += ["건강 상태 어때?", "내 건강 기록 좀", "몸 상태 체크해봐"]

    # ---- self:health_save ----
    elif a == "self:health_save":
        cat = p(code, "category")
        results += [f"{cat} 기록해", f"오늘 {cat} 저장해줘", f"{cat} 입력해"]

    # ---- self:schedule ----
    elif a == "self:schedule":
        results += ["알람 맞춰줘", "예약해둬", "나중에 해줘", "리마인더 설정해", "스케줄 잡아"]

    # ---- limbs:play ----
    elif a == "limbs:play":
        q = p(code, "query")
        if q:
            results += [
                f"{q} 틀어", f"{q} 듣고 싶어", f"{q} 재생해",
                f"{q} 좀 들을래", f"{q} 켜줘"
            ]
        else:
            results += ["노래 틀어", "음악 좀 켜줘", "뭐 좀 틀어줘"]

    # ---- limbs:skip/stop/queue/volume ----
    elif a == "limbs:skip":
        results += ["다음 곡", "이거 넘겨", "스킵", "다른 거 틀어", "다음 노래"]
    elif a == "limbs:stop":
        results += ["꺼", "멈춰", "노래 꺼", "음악 멈춰", "정지"]
    elif a == "limbs:queue":
        results += ["지금 뭐 듣고 있어?", "재생목록 뭐야", "큐 보여줘"]
    elif a == "limbs:volume":
        results += ["소리 키워", "볼륨 올려", "소리 좀 줄여", "소리 크게"]
    elif a == "limbs:queue_add":
        q = p(code, "query")
        if q:
            results += [f"{q} 다음에 틀어줘", f"{q} 추가해", f"{q} 큐에 넣어"]

    # ---- others:delegate / ask ----
    elif a in ("others:delegate", "others:delegate_project"):
        agent = p(code, "agent_id")
        name = agent.split("/")[-1] if "/" in agent else agent
        results += [
            f"{name}한테 맡겨", f"{name}에게 시켜", f"{name}한테 넘겨줘",
            f"{name}이 처리해줬으면", f"{name}한테 부탁해"
        ]
    elif a in ("others:ask", "others:ask_sync"):
        agent = p(code, "agent_id")
        name = agent.split("/")[-1] if "/" in agent else agent
        results += [
            f"{name}한테 물어봐", f"{name} 의견 좀", f"{name}한테 상담해봐",
            f"{name}이 뭐라 해?", f"{name}한테 질문해"
        ]

    # ---- others:list_projects / agent_info ----
    elif a == "others:list_projects":
        results += ["팀 누가 있어", "프로젝트 뭐 있지", "에이전트 현황 좀"]
    elif a == "others:agent_info":
        agent = p(code, "agent_id")
        name = agent.split("/")[-1] if "/" in agent else agent
        results += [f"{name} 뭐 할 수 있어?", f"{name} 정보 좀", f"{name} 에이전트 알려줘"]

    # ---- self:local_save / write / file ----
    elif a in ("self:local_save", "self:write", "self:file"):
        results += ["파일로 저장해", "이거 저장해줘", "문서로 남겨", "파일에 써줘", "저장 좀"]

    # ---- self:read / read_pdf ----
    elif a in ("self:read", "self:read_pdf"):
        path = p(code, "path")
        if path:
            results += [f"{path} 읽어줘", f"{path} 내용 좀", f"이 파일 봐봐"]
        else:
            results += ["파일 읽어줘", "내용 좀 봐봐", "이거 읽어봐"]

    # ---- self:storage_scan / list / find ----
    elif a in ("self:storage_scan", "self:list"):
        path = p(code, "path")
        if path:
            results += [f"{path} 뭐 있어?", f"{path} 파일 좀 봐", f"{path} 목록 좀"]
        else:
            results += ["파일 뭐 있어?", "목록 좀 보여줘", "용량 얼마야"]
    elif a == "self:find":
        pat = p(code, "pattern")
        results += [f"{pat} 파일 어디 있지?", f"{pat} 찾아봐", f"{pat} 어디있어"]

    # ---- limbs:os_open / navigate ----
    elif a in ("limbs:os_open", "limbs:navigate"):
        results += ["이거 열어", "브라우저로 띄워줘", "링크 열어봐", "이 사이트 켜줘"]

    # ---- limbs:clipboard ----
    elif a in ("limbs:clipboard", "self:clipboard"):
        results += ["복사해", "클립보드에 넣어", "카피해줘", "이거 복사"]

    # ---- limbs:screenshot / desktop_screenshot / android_screenshot ----
    elif "screenshot" in a:
        results += ["화면 캡처해", "스크린샷 찍어", "화면 찍어줘"]

    # ---- limbs:sms_list / sms_send / sms_search ----
    elif a == "limbs:sms_list":
        results += ["문자 뭐 왔어?", "메시지 좀 봐", "문자 확인해줘"]
    elif a == "limbs:sms_send":
        results += ["문자 보내줘", "메시지 하나 보내", "문자 좀 써줘"]
    elif a == "limbs:sms_search":
        q = p(code, "query")
        results += [f"{q} 문자 있어?", f"{q} 관련 메시지 찾아"]

    # ---- limbs:call / call_log ----
    elif a == "limbs:call":
        results += ["전화 걸어줘", "통화 좀 해야 돼", "전화 좀 해줘"]
    elif a == "limbs:call_log":
        results += ["누가 전화했어?", "통화 이력 좀", "전화 기록 봐"]

    # ---- limbs:contacts ----
    elif a == "limbs:contacts":
        q = p(code, "query")
        if q:
            results += [f"{q} 연락처 있어?", f"{q} 전화번호 좀", f"{q} 번호 알려줘"]

    # ---- limbs:notifications ----
    elif a == "limbs:notifications":
        results += ["알림 뭐 왔어", "알림 좀 봐", "노티 확인해"]

    # ---- limbs:apps / open_app ----
    elif a == "limbs:apps":
        results += ["앱 뭐 깔려있어", "앱 목록 좀", "설치된 앱 보여줘"]
    elif a == "limbs:open_app":
        pkg = p(code, "package")
        app_name = "카톡" if "kakao" in pkg else "앱"
        results += [f"{app_name} 켜줘", f"{app_name} 열어", f"{app_name} 실행해"]

    # ---- engines:chart / line / bar / pie 등 ----
    elif a in ("engines:line", "engines:bar", "engines:pie", "engines:candlestick", "engines:chart", "engines:heatmap", "engines:scatter", "engines:multi"):
        title = p(code, "title")
        if title:
            results += [f"{title} 차트 그려줘", f"{title} 그래프 만들어", f"{title} 시각화해줘"]
        else:
            results += ["차트 그려줘", "그래프 만들어", "시각화해줘"]

    # ---- engines:slide / slide_shadcn ----
    elif a in ("engines:slide", "engines:slide_shadcn"):
        topic = p(code, "topic")
        if topic:
            results += [f"{topic} 발표자료 만들어", f"{topic} PPT 좀", f"{topic} 슬라이드 제작해"]
        else:
            results += ["발표자료 만들어", "PPT 좀", "프레젠테이션 만들어줘"]

    # ---- engines:video / remotion ----
    elif a in ("engines:video", "engines:remotion"):
        topic = p(code, "topic") or p(code, "composition")
        results += ["영상 만들어줘", "동영상 제작해", "비디오 좀 만들어"]

    # ---- engines:tts ----
    elif a == "engines:tts":
        results += ["음성으로 바꿔줘", "읽어주는 거 만들어", "TTS로 변환해"]

    # ---- engines:music / abc_* ----
    elif a == "engines:music":
        results += ["작곡해줘", "곡 하나 만들어봐", "음악 만들어"]
    elif a == "engines:abc_search":
        results += ["악보 찾아줘", "악보 검색해"]
    elif a == "engines:abc_to_midi":
        results += ["악보를 미디로 바꿔", "MIDI 변환해줘"]

    # ---- engines:image_gemini ----
    elif a == "engines:image_gemini":
        results += ["그림 그려줘", "이미지 만들어", "AI로 그림 좀"]

    # ---- engines:create_site ----
    elif a == "engines:create_site":
        name = p(code, "name")
        results += ["웹사이트 만들어줘", "홈페이지 좀 만들어", f"{name} 사이트 만들어"]

    # ---- engines:newspaper ----
    elif a == "engines:newspaper":
        results += ["뉴스 신문 만들어", "오늘 뉴스 정리해줘", "신문 좀 만들어줘"]

    # ---- self:list_workflows / list_switches / list_triggers ----
    elif a == "self:list_workflows":
        results += ["워크플로우 뭐 있어", "자동화 목록 좀", "워크플로우 보여줘"]
    elif a == "self:list_switches":
        results += ["스위치 뭐 있어", "토글 목록 좀", "스위치 현황"]
    elif a == "self:list_triggers":
        results += ["트리거 뭐 걸려있어", "자동실행 목록", "트리거 보여줘"]

    # ---- self:recent ----
    elif a == "self:recent":
        results += ["최근 대화 뭐였지", "아까 뭐 얘기했지", "대화 이력 좀"]

    # ---- self:posts / blog_stats / rag_search / insight ----
    elif a == "self:posts":
        results += ["블로그 글 뭐 있어", "내 글 목록 좀", "블로그 보여줘"]
    elif a == "self:blog_stats":
        results += ["블로그 현황 어때", "블로그 통계 좀", "블로그 상태"]
    elif a == "self:rag_search":
        q = p(code, "query")
        results += [f"블로그에서 {q} 찾아봐", f"{q} 관련 글 있어?"]
    elif a == "self:insight":
        q = p(code, "query")
        results += [f"{q} 인사이트 좀", f"{q} 분석해줘"]

    # ---- self:photo_scan / search_photos / duplicates ----
    elif a == "self:photo_scan":
        q = p(code, "query")
        if q:
            results += [f"{q} 사진 있어?", f"{q} 사진 찾아봐"]
        else:
            results += ["사진 몇 장이야", "사진 현황 좀"]
    elif a == "self:search_photos":
        q = p(code, "query")
        results += [f"{q} 사진 찾아줘", f"{q} 관련 사진"]
    elif a == "self:duplicates":
        results += ["중복 사진 있어?", "같은 사진 찾아봐"]

    # ---- sense:search_shopping ----
    elif a == "sense:search_shopping":
        q = p(code, "query")
        if q:
            results += [f"{q} 얼마야", f"{q} 가격 비교 좀", f"{q} 최저가", f"{q} 어디가 싸?"]

    # ---- sense:crawl ----
    elif a == "sense:crawl":
        results += ["이 사이트 긁어와", "페이지 내용 가져와", "웹페이지 읽어봐"]

    # ---- sense:crypto ----
    elif a == "sense:crypto":
        coin = p(code, "coin")
        if coin:
            name = "비트코인" if "bitcoin" in coin else "이더리움" if "ethereum" in coin else coin
            results += [f"{name} 지금 얼마야", f"{name} 올랐어?", f"{name} 시세 좀"]

    # ---- sense:apt_trade / apt_rent ----
    elif a in ("sense:apt_trade", "sense:house_trade"):
        results += ["아파트값 어때", "매매 실거래가 봐줘", "집값 좀 봐"]
    elif a in ("sense:apt_rent", "sense:house_rent"):
        results += ["전세 시세 어때", "월세 얼마야", "전월세 좀 봐"]

    # ---- others:channel_send / channel_read / channel_search / neighbors ----
    elif a == "others:channel_send":
        results += ["메일 보내줘", "이메일 하나 써", "메시지 전송해"]
    elif a == "others:channel_read":
        q = p(code, "query")
        if q:
            results += [f"{q} 정보 좀", f"{q} 연락처"]
        else:
            results += ["이웃 누가 있어", "연락처 목록 좀", "이웃 현황"]
    elif a == "others:channel_search":
        q = p(code, "query")
        results += [f"{q} 관련 메시지 있어?", f"{q} 검색해봐"]
    elif a == "others:neighbors":
        results += ["이웃 목록 좀", "주변 사람들 누가 있지", "이웃 보여줘"]
    elif a == "others:neighbor_detail":
        name = p(code, "name")
        results += [f"{name} 정보 좀", f"{name} 알려줘", f"{name} 누구야"]
    elif a == "others:messages":
        contact = p(code, "contact")
        results += [f"{contact}이랑 대화 내용", f"{contact} 메시지 봐", f"{contact} 이력"]

    # ---- limbs:todo ----
    elif a in ("limbs:todo", "self:todo"):
        act = p(code, "action")
        if act == "list":
            results += ["할일 뭐 있어", "투두 목록 좀", "할 거 뭐야"]
        elif act == "add":
            results += ["할일 추가해", "투두에 넣어줘", "할 거 하나 추가"]
        else:
            results += ["할일 정리해줘", "투두 만들어", "할 거 목록 좀"]

    # ---- limbs:run ----
    elif a in ("limbs:run", "self:run"):
        name = p(code, "name")
        if name:
            results += [f"{name} 실행해", f"{name} 돌려줘", f"{name} 시작해"]
        else:
            results += ["실행해줘", "돌려줘", "시작해"]

    # ---- limbs:back / tab_new / tab_list / tab_close / scroll / click / type ----
    elif a == "limbs:back":
        results += ["뒤로 가", "뒤로가기", "이전 페이지"]
    elif a == "limbs:tab_new":
        results += ["새 탭 하나", "탭 열어", "새 탭"]
    elif a == "limbs:tab_list":
        results += ["탭 뭐 열려있어", "탭 목록 좀"]
    elif a == "limbs:tab_close":
        results += ["이 탭 닫아", "탭 닫기"]
    elif a == "limbs:scroll":
        results += ["밑으로 내려", "스크롤 좀", "아래로 가"]
    elif a == "limbs:click":
        results += ["이거 클릭해", "눌러줘"]
    elif a == "limbs:type":
        results += ["이거 입력해", "텍스트 넣어줘"]

    # ---- 파이프라인 (>> 연산자) ----
    if ">>" in code:
        # 파이프라인은 원래 intent 기반으로 변형
        for intent in intents[:1]:
            words = intent.replace("해줘", "").replace("해서", " 하고").strip()
            results.append(words + " 좀")
            results.append("그거 " + intent.split("해")[0] + "해봐")

    # ---- 병렬 (& 연산자) ----
    if "&" in code and ">>" not in code:
        for intent in intents[:1]:
            results.append(intent.replace("와 ", "이랑 ").replace("동시에 ", "같이 "))

    # ---- 폴백: 원래 intent의 구어체 변형 ----
    if len(results) < 3:
        for intent in intents[:2]:
            # 어미 구어체화
            for formal, casual_list in [
                ("해줘", ["해", "좀", "해봐"]),
                ("알려줘", ["말해줘", "알려", "좀"]),
                ("보여줘", ["보여", "좀 봐", "봐봐"]),
                ("찾아줘", ["찾아", "찾아봐", "검색해"]),
                ("열어줘", ["열어", "켜줘", "띄워"]),
                ("검색해줘", ["찾아봐", "검색해", "좀 봐"]),
                ("조회", ["확인", "봐봐", "체크"]),
            ]:
                if formal in intent:
                    for c in casual_list[:2]:
                        new = intent.replace(formal, c)
                        if new != intent:
                            results.append(new)
                    break

    # 중복 제거 + 기존 intent 제거
    seen = set(intents)
    unique = []
    for r in results:
        r = r.strip()
        if r and r not in seen and len(r) > 1:
            seen.add(r)
            unique.append(r)
    return unique[:5]


# ====================================================================
# 메인: 전체 489개 코드에 대해 생성
# ====================================================================

all_synthetic = []
for code, intents in all_items:
    variations = gen(code, intents)
    for v in variations:
        all_synthetic.append({"intent": v, "ibl_code": code, "source": "opus_bulk"})

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(all_synthetic, f, ensure_ascii=False, indent=2)

# 통계
codes_covered = len(set(item['ibl_code'] for item in all_synthetic))
print(f"총 {len(all_synthetic)}건 생성, {codes_covered}개 코드 커버")

# 액션별 분포
from collections import Counter
action_counts = Counter(action(item['ibl_code']) for item in all_synthetic)
print(f"\n상위 15개 액션:")
for a, c in action_counts.most_common(15):
    print(f"  {a}: {c}건")
