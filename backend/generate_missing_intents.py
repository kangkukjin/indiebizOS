"""
미커버 97개 액션에 대한 합성 intent 생성 스크립트

각 액션의 description, implementation, keywords를 기반으로
자연스러운 한국어 intent 변형을 생성하여 용례 DB에 추가한다.

실행: cd backend && python3 generate_missing_intents.py
"""

import json
import sqlite3
import re
from datetime import datetime
from pathlib import Path

DB_PATH = Path('..') / 'data' / 'ibl_usage.db'

# 액션별 합성 intent 매핑
# 각 액션에 대해 (intent, ibl_code) 쌍을 수동으로 정의
SYNTHETIC_DATA = {
    # ── sense ──
    "sense:search_ddg": [
        ("웹 검색해줘", "[sense:search_ddg]"),
        ("인터넷 검색 좀", "[sense:search_ddg]"),
        ("구글링 해줘", "[sense:search_ddg]"),
        ("검색해봐", "[sense:search_ddg]"),
        ("웹에서 찾아줘", "[sense:search_ddg]"),
    ],
    "sense:cctv_nearby": [
        ("근처 CCTV 찾아줘", "[sense:cctv_nearby]"),
        ("주변 CCTV 있어?", "[sense:cctv_nearby]"),
        ("가까운 CCTV 보여줘", "[sense:cctv_nearby]"),
        ("이 근처 교통 카메라", "[sense:cctv_nearby]"),
    ],
    "sense:info": [
        ("삼성전자 기본 정보", '[sense:info]{symbol: "삼성전자"}'),
        ("애플 시가총액 알려줘", '[sense:info]{symbol: "AAPL"}'),
        ("종목 정보 조회해줘", "[sense:info]"),
        ("PER이랑 배당 확인해줘", "[sense:info]"),
        ("이 주식 기본 데이터 봐봐", "[sense:info]"),
    ],
    "sense:company_news": [
        ("삼성전자 관련 뉴스", '[sense:company_news]{symbol: "삼성전자"}'),
        ("테슬라 뉴스 찾아줘", '[sense:company_news]{symbol: "TSLA"}'),
        ("이 종목 뉴스 뭐 있어", "[sense:company_news]"),
        ("기업 뉴스 검색해줘", "[sense:company_news]"),
    ],
    "sense:save": [
        ("이 가게 정보 저장해", "[sense:save]"),
        ("맛집 정보 DB에 넣어줘", "[sense:save]"),
        ("지역 정보 저장", "[sense:save]"),
    ],
    "sense:resolve_library": [
        ("라이브러리 ID 조회해줘", "[sense:resolve_library]"),
        ("Context7 ID 찾아줘", "[sense:resolve_library]"),
    ],

    # ── self ──
    "self:blog_search": [
        ("블로그 검색해줘", "[self:blog_search]"),
        ("블로그에서 찾아봐", "[self:blog_search]"),
        ("내 블로그 글 검색", "[self:blog_search]"),
        ("블로그 글 찾아줘", "[self:blog_search]"),
    ],
    "self:blog_content": [
        ("블로그 글 전문 보여줘", "[self:blog_content]"),
        ("그 블로그 글 내용 보자", "[self:blog_content]"),
        ("블로그 글 읽어줘", "[self:blog_content]"),
    ],
    "self:blog_posts": [
        ("블로그 글 목록 보여줘", "[self:blog_posts]"),
        ("블로그 최근 글 뭐 있어", "[self:blog_posts]"),
        ("블로그 포스트 리스트", "[self:blog_posts]"),
    ],
    "self:blog_check_new": [
        ("블로그 새 글 있어?", "[self:blog_check_new]"),
        ("블로그 업데이트 확인", "[self:blog_check_new]"),
    ],
    "self:blog_rebuild_index": [
        ("블로그 인덱스 재구축", "[self:blog_rebuild_index]"),
        ("블로그 검색 인덱스 갱신", "[self:blog_rebuild_index]"),
    ],
    "self:kinsight": [
        ("블로그 인사이트 분석해줘", "[self:kinsight]"),
        ("블로그 인사이트 뽑아줘", "[self:kinsight]"),
        ("블로그 분석 결과 보여줘", "[self:kinsight]"),
    ],
    "self:memory_save": [
        ("심층 메모리에 저장해", "[self:memory_save]"),
        ("이거 깊이 기억해둬", "[self:memory_save]"),
        ("장기 메모리에 넣어줘", "[self:memory_save]"),
    ],
    "self:memory_search": [
        ("심층 메모리 검색해줘", "[self:memory_search]"),
        ("기억 속에서 찾아봐", "[self:memory_search]"),
        ("저장한 거 검색해", "[self:memory_search]"),
    ],
    "self:cctv_refresh": [
        ("CCTV 새로고침", "[self:cctv_refresh]"),
        ("CCTV 목록 갱신해줘", "[self:cctv_refresh]"),
    ],
    "self:cctv_sources": [
        ("CCTV 소스 목록", "[self:cctv_sources]"),
        ("CCTV 상태 확인해줘", "[self:cctv_sources]"),
        ("등록된 CCTV 보여줘", "[self:cctv_sources]"),
        ("CCTV 돌아가고 있어?", "[self:cctv_sources]"),
    ],
    "self:cctv_stats": [
        ("CCTV 통계 보여줘", "[self:cctv_stats]"),
        ("CCTV 운영 현황", "[self:cctv_stats]"),
    ],
    "self:folder_annotate": [
        ("폴더에 메모 남겨줘", "[self:folder_annotate]"),
        ("이 폴더에 주석 달아", "[self:folder_annotate]"),
    ],
    "self:folder_annotations": [
        ("폴더 메모 보여줘", "[self:folder_annotations]"),
        ("폴더 주석 확인", "[self:folder_annotations]"),
    ],
    "self:photo_duplicates": [
        ("중복 사진 찾아줘", "[self:photo_duplicates]"),
        ("사진 중복 검사", "[self:photo_duplicates]"),
        ("같은 사진 있나 확인해", "[self:photo_duplicates]"),
    ],
    "self:photo_gallery": [
        ("사진 갤러리 보여줘", "[self:photo_gallery]"),
        ("사진 모아서 보여줘", "[self:photo_gallery]"),
    ],
    "self:photo_list_scans": [
        ("스캔 목록 보여줘", "[self:photo_list_scans]"),
        ("사진 스캔 현황", "[self:photo_list_scans]"),
    ],
    "self:photo_timeline": [
        ("사진 타임라인 보여줘", "[self:photo_timeline]"),
        ("시간순으로 사진 보기", "[self:photo_timeline]"),
    ],
    "self:storage_summary": [
        ("저장 공간 현황", "[self:storage_summary]"),
        ("디스크 용량 확인해줘", "[self:storage_summary]"),
        ("스토리지 상태 보여줘", "[self:storage_summary]"),
    ],

    # ── limbs (android) ──
    "limbs:android_apps": [
        ("폰에 깔린 앱 목록", "[limbs:android_apps]"),
        ("핸드폰 앱 리스트", "[limbs:android_apps]"),
    ],
    "limbs:android_app_info": [
        ("앱 정보 보여줘", "[limbs:android_app_info]"),
        ("이 앱 상세 정보", "[limbs:android_app_info]"),
    ],
    "limbs:android_app_sizes": [
        ("앱 용량 확인해줘", "[limbs:android_app_sizes]"),
        ("앱별 저장공간 사용량", "[limbs:android_app_sizes]"),
    ],
    "limbs:android_app_usage": [
        ("앱 사용 시간 보여줘", "[limbs:android_app_usage]"),
        ("어떤 앱 많이 썼어?", "[limbs:android_app_usage]"),
    ],
    "limbs:android_call": [
        ("전화 걸어줘", "[limbs:android_call]"),
        ("통화 연결해줘", "[limbs:android_call]"),
    ],
    "limbs:android_call_log": [
        ("통화 기록 보여줘", "[limbs:android_call_log]"),
        ("최근 전화 목록", "[limbs:android_call_log]"),
    ],
    "limbs:android_contact_list": [
        ("폰 연락처 목록", "[limbs:android_contact_list]"),
        ("핸드폰 주소록 보여줘", "[limbs:android_contact_list]"),
    ],
    "limbs:android_contact_search": [
        ("폰에서 연락처 검색", "[limbs:android_contact_search]"),
        ("핸드폰 주소록에서 찾아", "[limbs:android_contact_search]"),
    ],
    "limbs:android_delete_call_log": [
        ("통화 기록 삭제", "[limbs:android_delete_call_log]"),
    ],
    "limbs:android_delete_contact": [
        ("폰 연락처 삭제", "[limbs:android_delete_contact]"),
    ],
    "limbs:android_delete_messages": [
        ("메시지 삭제해줘", "[limbs:android_delete_messages]"),
    ],
    "limbs:android_delete_mms": [
        ("MMS 삭제", "[limbs:android_delete_mms]"),
    ],
    "limbs:android_delete_sms": [
        ("문자 삭제해줘", "[limbs:android_delete_sms]"),
    ],
    "limbs:android_devices": [
        ("연결된 안드로이드 기기", "[limbs:android_devices]"),
        ("폰 연결 상태 확인", "[limbs:android_devices]"),
    ],
    "limbs:android_end_call": [
        ("전화 끊어줘", "[limbs:android_end_call]"),
        ("통화 종료", "[limbs:android_end_call]"),
    ],
    "limbs:android_find_element": [
        ("화면에서 요소 찾아줘", "[limbs:android_find_element]"),
    ],
    "limbs:android_find_tap": [
        ("화면에서 찾아서 터치해", "[limbs:android_find_tap]"),
    ],
    "limbs:android_grant_permissions": [
        ("앱 권한 허용해줘", "[limbs:android_grant_permissions]"),
    ],
    "limbs:android_hierarchy": [
        ("화면 구조 분석해줘", "[limbs:android_hierarchy]"),
    ],
    "limbs:android_long_press": [
        ("길게 눌러줘", "[limbs:android_long_press]"),
    ],
    "limbs:android_manager": [
        ("안드로이드 매니저 실행", "[limbs:android_manager]"),
    ],
    "limbs:android_mms": [
        ("MMS 보여줘", "[limbs:android_mms]"),
    ],
    "limbs:android_notifications": [
        ("폰 알림 확인해줘", "[limbs:android_notifications]"),
        ("핸드폰 알림 보여줘", "[limbs:android_notifications]"),
    ],
    "limbs:android_open_app": [
        ("폰에서 앱 열어줘", "[limbs:android_open_app]"),
        ("핸드폰 앱 실행해", "[limbs:android_open_app]"),
    ],
    "limbs:android_permissions": [
        ("앱 권한 목록 확인", "[limbs:android_permissions]"),
    ],
    "limbs:android_pull_file": [
        ("폰에서 파일 가져와", "[limbs:android_pull_file]"),
    ],
    "limbs:android_push_file": [
        ("폰에 파일 보내줘", "[limbs:android_push_file]"),
    ],
    "limbs:android_sms_list": [
        ("문자 목록 보여줘", "[limbs:android_sms_list]"),
        ("받은 문자 확인", "[limbs:android_sms_list]"),
    ],
    "limbs:android_sms_search": [
        ("문자에서 검색해줘", "[limbs:android_sms_search]"),
    ],
    "limbs:android_sms_send": [
        ("문자 보내줘", "[limbs:android_sms_send]"),
        ("SMS 전송해", "[limbs:android_sms_send]"),
    ],
    "limbs:android_swipe": [
        ("화면 스와이프해줘", "[limbs:android_swipe]"),
    ],
    "limbs:android_tap": [
        ("화면 터치해줘", "[limbs:android_tap]"),
    ],
    "limbs:android_tap_grid": [
        ("그리드 위치 터치", "[limbs:android_tap_grid]"),
    ],
    "limbs:android_type_text": [
        ("폰에 텍스트 입력해줘", "[limbs:android_type_text]"),
    ],
    "limbs:android_uninstall": [
        ("앱 삭제해줘", "[limbs:android_uninstall]"),
        ("앱 지워줘", "[limbs:android_uninstall]"),
    ],
    "limbs:android_all_messages": [
        ("폰 메시지 전부 보여줘", "[limbs:android_all_messages]"),
    ],
    "limbs:browser_close": [
        ("브라우저 탭 닫아줘", "[limbs:browser_close]"),
        ("브라우저 닫아", "[limbs:browser_close]"),
    ],
    "limbs:browser_content": [
        ("웹페이지 내용 가져와", "[limbs:browser_content]"),
        ("이 페이지 텍스트 추출해", "[limbs:browser_content]"),
        ("사이트 내용 읽어줘", "[limbs:browser_content]"),
    ],
    "limbs:browser_navigate": [
        ("이 URL로 이동해줘", "[limbs:browser_navigate]"),
        ("웹사이트 열어줘", "[limbs:browser_navigate]"),
        ("브라우저로 접속해", "[limbs:browser_navigate]"),
    ],
    "limbs:cctv_open": [
        ("CCTV 영상 열어줘", "[limbs:cctv_open]"),
        ("CCTV 화면 보여줘", "[limbs:cctv_open]"),
        ("CCTV 스트리밍 시작", "[limbs:cctv_open]"),
    ],
    "limbs:chrome_connect": [
        ("크롬 브라우저 연결", "[limbs:chrome_connect]"),
    ],
    "limbs:chrome_disconnect": [
        ("크롬 연결 해제", "[limbs:chrome_disconnect]"),
    ],
    "limbs:chrome_status": [
        ("크롬 연결 상태 확인", "[limbs:chrome_status]"),
    ],
    "limbs:explorer": [
        ("파일 탐색기 열어줘", "[limbs:explorer]"),
        ("폴더 열어줘", "[limbs:explorer]"),
    ],
    "limbs:find": [
        ("파일 찾아줘", "[limbs:find]"),
        ("파일 검색해줘", "[limbs:find]"),
    ],
    "limbs:launch": [
        ("프로그램 실행해줘", "[limbs:launch]"),
        ("앱 열어줘", "[limbs:launch]"),
        ("이거 실행해", "[limbs:launch]"),
    ],
    "limbs:photo_manager": [
        ("사진 매니저 실행", "[limbs:photo_manager]"),
    ],
    "limbs:route_navigate": [
        ("길 안내해줘", "[limbs:route_navigate]"),
        ("네비게이션 시작해", "[limbs:route_navigate]"),
        ("경로 안내해줘", "[limbs:route_navigate]"),
    ],
    "limbs:show_map": [
        ("지도 보여줘", "[limbs:show_map]"),
        ("이 위치 지도로 봐", "[limbs:show_map]"),
    ],

    # ── engines ──
    "engines:arch_create": [
        ("건축 프로젝트 생성", "[engines:arch_create]"),
        ("새 건축 설계 시작", "[engines:arch_create]"),
    ],
    "engines:arch_elevation": [
        ("건물 입면도 보여줘", "[engines:arch_elevation]"),
    ],
    "engines:arch_export": [
        ("건축 도면 내보내기", "[engines:arch_export]"),
    ],
    "engines:arch_floor_plan": [
        ("평면도 보여줘", "[engines:arch_floor_plan]"),
        ("층별 평면도 생성", "[engines:arch_floor_plan]"),
    ],
    "engines:arch_get": [
        ("건축 프로젝트 정보", "[engines:arch_get]"),
    ],
    "engines:arch_list": [
        ("건축 프로젝트 목록", "[engines:arch_list]"),
    ],
    "engines:arch_modify": [
        ("건축 설계 수정", "[engines:arch_modify]"),
    ],
    "engines:arch_report": [
        ("건축 보고서 생성", "[engines:arch_report]"),
    ],
    "engines:arch_section": [
        ("건물 단면도 보여줘", "[engines:arch_section]"),
    ],
    "engines:arch_view_3d": [
        ("건물 3D 뷰 보여줘", "[engines:arch_view_3d]"),
        ("3D 모델 보기", "[engines:arch_view_3d]"),
    ],
    "engines:html_video": [
        ("HTML 영상 만들어줘", "[engines:html_video]"),
    ],
    "engines:remotion_video": [
        ("Remotion 영상 생성", "[engines:remotion_video]"),
        ("프로그래밍 영상 만들어", "[engines:remotion_video]"),
    ],
    "engines:web_create_page": [
        ("웹 페이지 만들어줘", "[engines:web_create_page]"),
        ("새 페이지 추가해", "[engines:web_create_page]"),
    ],
    "engines:web_create_site": [
        ("웹사이트 생성해줘", "[engines:web_create_site]"),
        ("새 사이트 만들어", "[engines:web_create_site]"),
    ],
    "engines:web_fetch_component": [
        ("웹 컴포넌트 가져와", "[engines:web_fetch_component]"),
    ],
    "engines:web_list_components": [
        ("웹 컴포넌트 목록", "[engines:web_list_components]"),
    ],
    "engines:web_list_sections": [
        ("웹 섹션 목록 보여줘", "[engines:web_list_sections]"),
    ],
    "engines:web_live_check": [
        ("웹사이트 살아있나 확인", "[engines:web_live_check]"),
        ("사이트 접속 되나 체크", "[engines:web_live_check]"),
    ],
    "engines:web_preview": [
        ("웹사이트 미리보기", "[engines:web_preview]"),
    ],
    "engines:web_site_list": [
        ("등록된 웹사이트 목록", "[engines:web_site_list]"),
        ("사이트 리스트 보여줘", "[engines:web_site_list]"),
    ],
    "engines:web_site_register": [
        ("웹사이트 등록해줘", "[engines:web_site_register]"),
    ],
    "engines:web_site_remove": [
        ("웹사이트 삭제해줘", "[engines:web_site_remove]"),
    ],
    "engines:web_site_update": [
        ("웹사이트 업데이트해줘", "[engines:web_site_update]"),
    ],
    "engines:web_snapshot": [
        ("웹 스냅샷 찍어줘", "[engines:web_snapshot]"),
        ("웹사이트 캡처해", "[engines:web_snapshot]"),
    ],
}


def main():
    conn = sqlite3.connect(str(DB_PATH))
    now = datetime.now().isoformat()

    inserted = 0
    skipped = 0

    for action_key, pairs in SYNTHETIC_DATA.items():
        for intent, code in pairs:
            exists = conn.execute(
                'SELECT count(*) FROM ibl_examples WHERE intent = ?', (intent,)
            ).fetchone()[0]
            if exists:
                skipped += 1
                continue

            node = action_key.split(':')[0]
            conn.execute(
                'INSERT INTO ibl_examples (intent, ibl_code, nodes, category, difficulty, source, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (intent, code, node, 'single', 1, 'manual_coverage', now, now)
            )
            inserted += 1

    conn.commit()

    total = conn.execute('SELECT count(*) FROM ibl_examples').fetchone()[0]
    conn.close()

    covered_actions = len(SYNTHETIC_DATA)
    total_intents = sum(len(v) for v in SYNTHETIC_DATA.values())
    print(f'대상 액션: {covered_actions}개')
    print(f'생성 intent: {total_intents}개')
    print(f'신규 추가: {inserted}개, 스킵(중복): {skipped}개')
    print(f'DB 총 용례: {total}개')


if __name__ == '__main__':
    main()
