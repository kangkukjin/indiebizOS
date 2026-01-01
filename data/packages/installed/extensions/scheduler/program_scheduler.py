"""
program_scheduler.py - 프로그램 스케줄러
에이전트 없이 백그라운드에서 정해진 시간에 작업 실행

예시 작업:
- 매일 아침 6시: 블로그 새 글 확인 + 요약 생성
"""

import os
import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

# 설정 파일 경로
BASE_DIR = Path(__file__).parent
SCHEDULE_CONFIG_PATH = BASE_DIR / "data" / "program_schedule.json"

# 기본 스케줄 설정
DEFAULT_SCHEDULE = {
    "tasks": [
        {
            "id": "blog_sync",
            "name": "블로그 동기화",
            "description": "새 글 확인 및 요약 생성",
            "time": "06:00",
            "enabled": True,
            "action": "blog_sync",
            "last_run": None
        }
    ]
}


class ProgramScheduler:
    """프로그램 스케줄러"""
    
    def __init__(self, log_callback: Callable[[str], None] = None):
        self.log_callback = log_callback or print
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.config = self._load_config()
        
        # 작업 함수 등록
        self.actions: Dict[str, Callable] = {
            "blog_sync": self._action_blog_sync,
        }
    
    def _log(self, message: str):
        """로그 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_callback(f"[스케줄러 {timestamp}] {message}")
    
    def _load_config(self) -> dict:
        """설정 로드"""
        if SCHEDULE_CONFIG_PATH.exists():
            try:
                with open(SCHEDULE_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return DEFAULT_SCHEDULE.copy()
    
    def _save_config(self):
        """설정 저장"""
        SCHEDULE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEDULE_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def get_tasks(self) -> List[dict]:
        """작업 목록 반환"""
        return self.config.get("tasks", [])
    
    def add_task(self, name: str, description: str, time: str, action: str, enabled: bool = True) -> dict:
        """작업 추가"""
        task_id = f"task_{int(datetime.now().timestamp())}"
        task = {
            "id": task_id,
            "name": name,
            "description": description,
            "time": time,
            "enabled": enabled,
            "action": action,
            "last_run": None
        }
        self.config["tasks"].append(task)
        self._save_config()
        return task
    
    def update_task(self, task_id: str, **kwargs):
        """작업 수정"""
        for task in self.config["tasks"]:
            if task["id"] == task_id:
                task.update(kwargs)
                self._save_config()
                return True
        return False
    
    def delete_task(self, task_id: str) -> bool:
        """작업 삭제"""
        original_len = len(self.config["tasks"])
        self.config["tasks"] = [t for t in self.config["tasks"] if t["id"] != task_id]
        if len(self.config["tasks"]) < original_len:
            self._save_config()
            return True
        return False
    
    def toggle_task(self, task_id: str) -> bool:
        """작업 활성화/비활성화 토글"""
        for task in self.config["tasks"]:
            if task["id"] == task_id:
                task["enabled"] = not task["enabled"]
                self._save_config()
                return task["enabled"]
        return False
    
    def start(self):
        """스케줄러 시작"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self._log("프로그램 스케줄러 시작됨")
    
    def stop(self):
        """스케줄러 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self._log("프로그램 스케줄러 중지됨")
    
    def _run_loop(self):
        """스케줄러 메인 루프"""
        while self.running:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            
            for task in self.config.get("tasks", []):
                if not task.get("enabled", True):
                    continue
                
                if task.get("time") != current_time:
                    continue
                
                # 오늘 이미 실행했는지 확인
                last_run = task.get("last_run")
                if last_run:
                    last_run_date = datetime.fromisoformat(last_run).date()
                    if last_run_date == now.date():
                        continue
                
                # 작업 실행
                self._execute_task(task)
            
            # 1분마다 체크
            time.sleep(60)
    
    def _execute_task(self, task: dict):
        """작업 실행"""
        action_name = task.get("action")
        action_func = self.actions.get(action_name)
        
        if not action_func:
            self._log(f"알 수 없는 작업: {action_name}")
            return
        
        self._log(f"작업 시작: {task['name']}")
        
        try:
            action_func()
            
            # 마지막 실행 시간 기록
            task["last_run"] = datetime.now().isoformat()
            self._save_config()
            
            self._log(f"작업 완료: {task['name']}")
            
        except Exception as e:
            self._log(f"작업 실패: {task['name']} - {str(e)}")
    
    def run_task_now(self, task_id: str):
        """작업 즉시 실행"""
        for task in self.config["tasks"]:
            if task["id"] == task_id:
                threading.Thread(
                    target=self._execute_task,
                    args=(task,),
                    daemon=True
                ).start()
                return True
        return False
    
    # =========================================================================
    # 작업 함수들
    # =========================================================================
    
    def _action_blog_sync(self):
        """블로그 동기화: 새 글 확인 + 요약 생성"""
        from tool_blog_insight import blog_check_new_posts, blog_get_posts, get_db
        import google.generativeai as genai
        
        # 1. 새 글 확인
        self._log("새 글 확인 중...")
        result = blog_check_new_posts()
        
        if result.get("new_count", 0) > 0:
            self._log(f"새 글 {result['new_count']}개 발견")
        else:
            self._log("새 글 없음")
        
        # 2. 요약 없는 글 확인
        conn = get_db()
        rows = conn.execute("""
            SELECT COUNT(*) FROM posts p
            LEFT JOIN summaries s ON p.post_id = s.post_id
            WHERE s.post_id IS NULL
        """).fetchone()
        without_summary = rows[0]
        conn.close()
        
        if without_summary == 0:
            self._log("모든 글에 요약이 있음")
            return
        
        self._log(f"요약 없는 글 {without_summary}개, 요약 생성 시작...")
        
        # 3. 요약 생성 (최대 50개씩)
        self._generate_summaries(limit=50)
    
    def _generate_summaries(self, limit: int = 50):
        """요약 생성 (배치)"""
        import google.generativeai as genai
        from tool_blog_insight import get_db
        
        # API 키 (환경변수에서 읽기)
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            self._log("GOOGLE_API_KEY 환경변수가 설정되지 않았습니다")
            return
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        conn = get_db()
        
        # 요약 없는 글 가져오기
        rows = conn.execute("""
            SELECT p.post_id, p.title, p.category, p.content
            FROM posts p
            LEFT JOIN summaries s ON p.post_id = s.post_id
            WHERE s.post_id IS NULL
            ORDER BY p.pub_date DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        if not rows:
            return
        
        prompt_template = """다음 블로그 글을 읽고 500자 내외로 요약해주세요.
또한 키워드 3~5개를 쉼표로 구분해서 추출해주세요.

응답 형식:
[요약]
(요약 내용)

[키워드]
(키워드들)

---
제목: {title}
카테고리: {category}

본문:
{content}
"""
        
        success = 0
        for row in rows:
            post_id = row['post_id']
            
            try:
                prompt = prompt_template.format(
                    title=row['title'],
                    category=row['category'] or '',
                    content=row['content'][:15000]
                )
                
                response = model.generate_content(prompt)
                text = response.text
                
                # 파싱
                summary = ""
                keywords = ""
                current = None
                for line in text.split('\n'):
                    if '[요약]' in line:
                        current = 'summary'
                    elif '[키워드]' in line:
                        current = 'keywords'
                    elif current == 'summary':
                        summary += line + '\n'
                    elif current == 'keywords':
                        keywords += line
                
                summary = summary.strip()
                keywords = keywords.strip()
                
                # 저장
                conn.execute("""
                    INSERT OR REPLACE INTO summaries (post_id, summary, keywords)
                    VALUES (?, ?, ?)
                """, (post_id, summary, keywords))
                conn.commit()
                
                success += 1
                self._log(f"요약 완료: {row['title'][:30]}...")
                
                time.sleep(1)  # Rate limit
                
            except Exception as e:
                self._log(f"요약 실패: {post_id} - {str(e)}")
                time.sleep(5)
        
        conn.close()
        self._log(f"요약 생성 완료: {success}/{len(rows)}개")


# 싱글톤 인스턴스
_scheduler_instance: Optional[ProgramScheduler] = None


def get_program_scheduler(log_callback: Callable[[str], None] = None) -> ProgramScheduler:
    """프로그램 스케줄러 인스턴스 반환"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ProgramScheduler(log_callback)
    return _scheduler_instance
