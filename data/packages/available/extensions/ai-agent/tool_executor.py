"""
ai/tool_executor.py - 도구 실행 로직
"""

import json
import traceback

from .imports import (
    DYNAMIC_TOOL_SELECTOR_AVAILABLE,
    select_my_tools,
    list_available_tools,
    download_youtube_music,
    get_youtube_info,
    get_youtube_transcript,
    list_available_transcripts,
    summarize_youtube,
    search_blog,
    get_post_content,
    search_semantic,
    generate_newspaper,
    generate_magazine,
    use_webcrawl_tool,
    use_websearch_tool,
    use_googlenews_tool,
)

from tools import (
    execute_python,
    execute_nodejs,
    open_in_browser,
    read_file,
    write_file,
    list_directory,
    call_agent,
    list_agents,
    get_my_tools,
    get_current_time,
    get_channel_status,
    check_nostr_messages,
    create_task,
    get_task,
    complete_task,
)


class ToolExecutorMixin:
    """도구 실행 믹스인"""

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """도구 실행"""
        log_msg = f"   [AI] 도구 호출: {tool_name}"
        print(log_msg)

        # 도구 호출 시 from_where를 AI 자신(agent_name)으로 변경
        original_from = self.current_from_where
        if self.agent_name:
            self.current_from_where = self.agent_name

        try:
            # 0. 동적 도구 선택 시스템
            if tool_name == "select_my_tools":
                if DYNAMIC_TOOL_SELECTOR_AVAILABLE:
                    task_description = tool_input.get("task_description", "")
                    result = select_my_tools(task_description, agent_name=self.agent_name)

                    selected = result.get("selected_tools", [])
                    my_allowed = self.agent_config.get('allowed_tools', []) if self.agent_config else []

                    can_use = [t for t in selected if t in my_allowed]
                    need_delegate = [t for t in selected if t not in my_allowed]

                    return json.dumps({
                        "success": True,
                        "message": f"작업 분석 완료",
                        "can_use_directly": can_use,
                        "need_delegation": need_delegate,
                        "recommendation": result.get("recommendation", "")
                    }, ensure_ascii=False)
                else:
                    return json.dumps({"success": False, "message": "동적 도구 선택 시스템이 비활성화됨"}, ensure_ascii=False)

            if tool_name == "list_available_tools":
                if DYNAMIC_TOOL_SELECTOR_AVAILABLE:
                    result = list_available_tools()
                    return json.dumps(result, ensure_ascii=False)
                else:
                    return json.dumps({"success": False, "message": "동적 도구 선택 시스템이 비활성화됨"}, ensure_ascii=False)

            # 1. 기본 도구들
            if tool_name == "get_current_time":
                result = get_current_time()
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "execute_python":
                code = tool_input.get("code", "")
                result = execute_python(code)
                return result

            elif tool_name == "execute_nodejs":
                code = tool_input.get("code", "")
                result = execute_nodejs(code)
                return result

            elif tool_name == "open_in_browser":
                file_path = tool_input.get("file_path", "")
                result = open_in_browser(file_path)
                return result

            elif tool_name == "read_file":
                file_path = tool_input.get("file_path", "")
                result = read_file(file_path)
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "write_file":
                file_path = tool_input.get("file_path", "")
                content = tool_input.get("content", "")
                result = write_file(file_path, content)
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "list_directory":
                dir_path = tool_input.get("dir_path", "")
                result = list_directory(dir_path)
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "call_agent":
                agent_name = tool_input.get("agent_name", "")
                message = tool_input.get("message", "")
                result = call_agent(agent_name, message, from_where=self.current_from_where)
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "list_agents":
                result = list_agents()
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "get_my_tools":
                result = get_my_tools()
                return json.dumps(result, ensure_ascii=False)

            # Task 시스템
            elif tool_name == "create_task":
                result = create_task(**tool_input)
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "get_task":
                result = get_task(**tool_input)
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "complete_task":
                result = complete_task(**tool_input)
                return json.dumps(result, ensure_ascii=False)

            # 채널 도구
            elif tool_name == "get_channel_status":
                result = get_channel_status()
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "check_nostr_messages":
                result = check_nostr_messages()
                return json.dumps(result, ensure_ascii=False)

            # 웹 도구들
            elif tool_name == "web_crawl":
                if use_webcrawl_tool is None:
                    return json.dumps({"success": False, "message": "웹 크롤링 도구가 설치되지 않았습니다."}, ensure_ascii=False)
                result = use_webcrawl_tool(tool_input)
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "web_search":
                if use_websearch_tool is None:
                    return json.dumps({"success": False, "message": "웹 검색 도구가 설치되지 않았습니다."}, ensure_ascii=False)
                result = use_websearch_tool(tool_input)
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "google_news_search":
                if use_googlenews_tool is None:
                    return json.dumps({"success": False, "message": "Google News 검색 도구가 설치되지 않았습니다."}, ensure_ascii=False)
                result = use_googlenews_tool(tool_input)
                return json.dumps(result, ensure_ascii=False)

            # 브라우저 자동화
            elif tool_name == "browser_action":
                try:
                    from tool_browser import use_tool as browser_use_tool
                    task = tool_input.get("task", "")
                    output_file = tool_input.get("output_file")
                    result = browser_use_tool(task=task, output_file=output_file)
                    return json.dumps(result, ensure_ascii=False)
                except ImportError:
                    return json.dumps({"success": False, "message": "브라우저 자동화 도구가 설치되지 않았습니다."}, ensure_ascii=False)

            # PC 관리 도구
            elif tool_name.startswith("pc_"):
                try:
                    from tool_pc_manager import use_tool as pc_use_tool
                    result = pc_use_tool(tool_name, tool_input)
                    return json.dumps(result, ensure_ascii=False)
                except ImportError:
                    return json.dumps({"success": False, "message": "PC 관리 도구가 설치되지 않았습니다."}, ensure_ascii=False)

            # Legacy 도구들
            else:
                return self._execute_legacy_tool(tool_name, tool_input)

        finally:
            self.current_from_where = original_from

    def _execute_legacy_tool(self, tool_name: str, tool_input: dict) -> str:
        """레거시 도구 실행 (이메일, Nostr, YouTube, 블로그 등)"""
        # Gmail
        if tool_name == "send_email":
            if hasattr(self, "gmail") and self.gmail:
                to = tool_input.get("to", "")
                if "@indiebiz.local" in to or to == "gui":
                    return json.dumps({
                        "success": False,
                        "message": f"{to}는 GUI 주소로 이메일을 보낼 수 없습니다."
                    }, ensure_ascii=False)

                subject = tool_input.get("subject", "")
                body = tool_input.get("body", "")
                attachment_path = tool_input.get("attachment_path")

                try:
                    self.gmail.send_message(to=to, subject=subject, body=body, attachment_path=attachment_path)
                    if attachment_path:
                        result = {"success": True, "message": f"{to}에게 이메일을 첨부파일과 함께 전송했습니다."}
                    else:
                        result = {"success": True, "message": f"{to}에게 이메일을 전송했습니다."}
                except Exception as e:
                    result = {"success": False, "message": f"이메일 전송 실패: {str(e)}"}
                return json.dumps(result, ensure_ascii=False)
            else:
                return json.dumps({"success": False, "message": "이 에이전트는 이메일 전송 권한이 없습니다."}, ensure_ascii=False)

        # Nostr
        elif tool_name == "send_nostr_message":
            if hasattr(self, "nostr") and self.nostr:
                to = tool_input.get("to", "")
                message = tool_input.get("message", "")

                print(f"   [AI 디버그] send_nostr_message 호출: to={to}")
                try:
                    success = self.nostr.send_message(to=to, subject="", body=message)
                    result = {"success": success, "message": "Nostr DM을 전송했습니다." if success else "Nostr DM 전송 실패"}
                except Exception as e:
                    print(f"   [AI 디버그] 오류: {e}")
                    traceback.print_exc()
                    result = {"success": False, "message": f"Nostr DM 전송 실패: {str(e)}"}
                return json.dumps(result, ensure_ascii=False)
            else:
                return json.dumps({"success": False, "message": "이 에이전트는 Nostr 채널이 없습니다."}, ensure_ascii=False)

        elif tool_name == "search_nostr_notes":
            if hasattr(self, "nostr") and self.nostr:
                query = tool_input.get("query")
                author = tool_input.get("author")
                limit = int(tool_input.get("limit", 10))
                language = tool_input.get("language")
                try:
                    notes = self.nostr.search_public_notes(query=query, author=author, limit=limit, language=language)
                    if not notes:
                        return "Nostr에서 검색 결과를 찾지 못했습니다."
                    else:
                        result = f"Nostr에서 {len(notes)}개의 노트를 찾았습니다:\n\n"
                        for i, note in enumerate(notes, 1):
                            content_display = note['content'][:500] + "..." if len(note['content']) > 500 else note['content']
                            result += f"{i}. **작성자**: {note['author']}\n   **내용**: {content_display}\n   **시간**: {note['timestamp']}\n\n"
                        return result
                except Exception as e:
                    return f"Nostr 검색 실패: {str(e)}"
            else:
                return json.dumps({"success": False, "message": "이 에이전트는 Nostr 채널이 없습니다."}, ensure_ascii=False)

        elif tool_name == "search_nostr_band":
            if hasattr(self, "nostr") and self.nostr:
                query = tool_input.get("query", "")
                limit = int(tool_input.get("limit", 10))
                try:
                    notes = self.nostr.search_nostr_band(query=query, limit=limit)
                    if not notes:
                        return f"nostr.band에서 '{query}' 검색 결과를 찾지 못했습니다."
                    else:
                        result = f"nostr.band에서 '{query}' 검색 결과 {len(notes)}개:\n\n"
                        for i, note in enumerate(notes, 1):
                            content_display = note['content'][:500] + "..." if len(note['content']) > 500 else note['content']
                            result += f"{i}. **작성자**: {note['author'][:16]}...\n   **내용**: {content_display}\n   **시간**: {note['timestamp']}\n\n"
                        return result
                except Exception as e:
                    return f"nostr.band 검색 실패: {str(e)}"
            else:
                return json.dumps({"success": False, "message": "이 에이전트는 Nostr 채널이 없습니다."}, ensure_ascii=False)

        # 스케줄러
        elif tool_name == "scheduler":
            try:
                from tool_scheduler import scheduler_tool, get_scheduler
                scheduler = get_scheduler(output_router=None)
                command = tool_input.get('command', '')
                return scheduler_tool(command=command, from_where=self.current_from_where or "ai_agent", reply_to="system")
            except Exception as e:
                return json.dumps({"success": False, "message": f"스케줄러 오류: {str(e)}"}, ensure_ascii=False)

        # 신문/잡지 생성
        elif tool_name == "generate_newspaper":
            if generate_newspaper is None:
                return json.dumps({"success": False, "message": "신문 생성 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            keywords = tool_input.get("keywords", [])
            title = tool_input.get("title", "IndieBiz Daily")
            exclude_sources = tool_input.get("exclude_sources", [])
            if not keywords:
                return json.dumps({"success": False, "message": "키워드가 필요합니다"}, ensure_ascii=False)
            result = generate_newspaper(keywords, title, exclude_sources)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "generate_magazine":
            if generate_magazine is None:
                return json.dumps({"success": False, "message": "잡지 생성 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            preset = tool_input.get("preset")
            sections = tool_input.get("sections")
            title = tool_input.get("title")
            if not preset and not sections:
                return json.dumps({"success": False, "message": "preset 또는 sections 중 하나는 필수입니다"}, ensure_ascii=False)
            result = generate_magazine(preset=preset, sections=sections, title=title)
            return json.dumps(result, ensure_ascii=False)

        # YouTube 도구들
        elif tool_name == "download_youtube_music":
            if download_youtube_music is None:
                return json.dumps({"success": False, "message": "YouTube 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            url = tool_input.get("url", "")
            filename = tool_input.get("filename", "output.mp3")
            result = download_youtube_music(url, filename)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "get_youtube_info":
            if get_youtube_info is None:
                return json.dumps({"success": False, "message": "YouTube 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            url = tool_input.get("url", "")
            result = get_youtube_info(url)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "get_youtube_transcript":
            if get_youtube_transcript is None:
                return json.dumps({"success": False, "message": "YouTube 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            url = tool_input.get("url", "")
            languages = tool_input.get("languages", None)
            result = get_youtube_transcript(url, languages)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "list_available_transcripts":
            if list_available_transcripts is None:
                return json.dumps({"success": False, "message": "YouTube 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            url = tool_input.get("url", "")
            result = list_available_transcripts(url)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "summarize_youtube":
            if summarize_youtube is None:
                return json.dumps({"success": False, "message": "YouTube 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            url = tool_input.get("url", "")
            summary_length = tool_input.get("summary_length", 3000)
            languages = tool_input.get("languages", None)
            result = summarize_youtube(url, summary_length, languages)
            return json.dumps(result, ensure_ascii=False)

        # 블로그 RAG 도구들
        elif tool_name == "search_blog":
            if search_blog is None:
                return json.dumps({"success": False, "message": "블로그 RAG 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            query = tool_input.get("query", "")
            limit = tool_input.get("limit", 5)
            result = search_blog(query, limit)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "get_post_content":
            if get_post_content is None:
                return json.dumps({"success": False, "message": "블로그 RAG 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            post_id = tool_input.get("post_id", "")
            result = get_post_content(post_id)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "search_semantic":
            if search_semantic is None:
                return json.dumps({"success": False, "message": "블로그 RAG 도구가 설치되지 않았습니다."}, ensure_ascii=False)
            query = tool_input.get("query", "")
            limit = tool_input.get("limit", 5)
            result = search_semantic(query, limit)
            return json.dumps(result, ensure_ascii=False)

        # Blog Insight 도구들
        elif tool_name == "blog_insight_report":
            from tool_blog_insight import blog_insight_report
            count = tool_input.get("count", 50)
            category = tool_input.get("category", None)
            result = blog_insight_report(count=count, category=category)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "blog_get_posts":
            from tool_blog_insight import blog_get_posts
            result = blog_get_posts(**tool_input)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "blog_get_post":
            from tool_blog_insight import blog_get_post
            result = blog_get_post(**tool_input)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "blog_get_summaries":
            from tool_blog_insight import blog_get_summaries
            result = blog_get_summaries(**tool_input)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "blog_search":
            from tool_blog_insight import blog_search as blog_insight_search
            result = blog_insight_search(**tool_input)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "blog_stats":
            from tool_blog_insight import blog_stats
            result = blog_stats()
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "blog_check_new_posts":
            from tool_blog_insight import blog_check_new_posts
            result = blog_check_new_posts()
            return json.dumps(result, ensure_ascii=False)

        # 카메라 도구
        elif tool_name in ["capture_camera", "list_cameras"]:
            from tool_camera import use_tool as camera_use_tool
            result = camera_use_tool(tool_name, tool_input)
            return json.dumps(result, ensure_ascii=False)

        # 안드로이드 관리 도구
        elif tool_name.startswith("android_"):
            from tool_android import use_tool as android_use_tool
            result = android_use_tool(tool_name, tool_input)
            return json.dumps(result, ensure_ascii=False)

        return f"알 수 없는 도구: {tool_name}"
