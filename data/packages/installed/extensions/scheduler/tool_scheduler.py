#!/usr/bin/env python3
"""
tool_scheduler.py - 매일 할일 스케줄러 (스탠다드 도구)

스탠다드 도구 입출력 형태:
입력: [명령, from_where, reply_to]
출력: OutputRouter를 통해 자동 라우팅
"""

import schedule
import time
import yaml
import threading
from pathlib import Path
from datetime import datetime
class SchedulerTool:
    """
    매일 할일 스케줄러 도구
    
    agents.yaml의 daily_tasks를 읽어서 정해진 시간에
    지정된 에이전트에게 메시지를 전송합니다.
    """
    
    def __init__(self, agents_yaml_path="agents.yaml", output_router=None):
        self.yaml_path = Path(agents_yaml_path)
        self.output_router = output_router
        self.running = False
        self.thread = None
        self.scheduled_tasks = []
        
        # 마지막 실행 기록 파일
        self.last_run_file = Path("tokens/scheduler_last_run.json")
        self.last_run_file.parent.mkdir(parents=True, exist_ok=True)
    
    def __call__(self, command: str, from_where: str, reply_to: str) -> str:
        """
        스탠다드 도구 인터페이스
        
        명령어:
        - "start" : 스케줄러 시작
        - "stop" : 스케줄러 중지
        - "status" : 현재 상태 확인
        - "list" : 등록된 할일 목록 보기
        - "reload" : 할일 목록 다시 로드
        
        Args:
            command: 실행할 명령
            from_where: 명령을 보낸 곳 (에이전트 ID 또는 채널)
            reply_to: 응답을 보낼 곳
        
        Returns:
            결과 메시지 (OutputRouter를 통해 자동 라우팅됨)
        """
        try:
            parts = command.strip().lower().split()
            if not parts:
                return self._error_response("명령을 입력하세요: start, stop, status, list, reload")
            
            cmd = parts[0]
            
            if cmd == "start":
                return self._start_scheduler(from_where, reply_to)
            elif cmd == "stop":
                return self._stop_scheduler(from_where, reply_to)
            elif cmd == "status":
                return self._get_status(from_where, reply_to)
            elif cmd == "list":
                return self._list_tasks(from_where, reply_to)
            elif cmd == "reload":
                return self._reload_tasks(from_where, reply_to)
            else:
                return self._error_response(f"알 수 없는 명령: {cmd}\n사용 가능: start, stop, status, list, reload")
        
        except Exception as e:
            return self._error_response(f"스케줄러 오류: {e}")
    
    def _start_scheduler(self, from_where: str, reply_to: str) -> str:
        """스케줄러 시작"""
        if self.running:
            return "스케줄러가 이미 실행 중입니다."
        
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        
        # 할일 로드
        tasks = self._load_tasks()
        task_count = len(tasks)
        
        return f"✅ 스케줄러가 시작되었습니다.\n등록된 할일: {task_count}개"
    
    def _stop_scheduler(self, from_where: str, reply_to: str) -> str:
        """스케줄러 중지"""
        if not self.running:
            return "스케줄러가 실행 중이 아닙니다."
        
        self.running = False
        schedule.clear()
        
        return "⏹️ 스케줄러가 중지되었습니다."
    
    def _get_status(self, from_where: str, reply_to: str) -> str:
        """현재 상태 확인"""
        status = "실행 중" if self.running else "중지됨"
        task_count = len(self.scheduled_tasks)
        
        # 다음 실행 예정 작업
        jobs = schedule.get_jobs()
        next_runs = []
        for job in jobs[:3]:  # 최대 3개만
            next_run = job.next_run
            if next_run:
                next_runs.append(f"  - {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        
        result = f"📊 스케줄러 상태: {status}\n"
        result += f"등록된 할일: {task_count}개\n"
        
        if next_runs:
            result += "\n다음 실행 예정:\n" + "\n".join(next_runs)
        
        return result
    
    def _list_tasks(self, from_where: str, reply_to: str) -> str:
        """등록된 할일 목록"""
        tasks = self._load_tasks()
        
        if not tasks:
            return "등록된 할일이 없습니다."
        
        result = "📋 매일 할일 목록:\n\n"
        for i, task in enumerate(tasks, 1):
            time_str = task.get('time', '??:??')
            target = task.get('target', '???')
            message = task.get('message', '')
            
            result += f"{i}. [{time_str}] {target}\n"
            result += f"   {message[:60]}{'...' if len(message) > 60 else ''}\n\n"
        
        return result
    
    def _reload_tasks(self, from_where: str, reply_to: str) -> str:
        """할일 목록 다시 로드"""
        if not self.running:
            return "스케줄러가 실행 중이 아닙니다. 먼저 'start'로 시작하세요."
        
        # 기존 스케줄 제거
        schedule.clear()
        
        # 새로 로드
        tasks = self._load_tasks()
        for task in tasks:
            self._register_task(task)
        
        return f"✅ 할일 목록이 다시 로드되었습니다. ({len(tasks)}개)"
    
    def _error_response(self, message: str) -> str:
        """에러 응답"""
        return f"❌ {message}"
    
    def _load_tasks(self) -> list:
        """agents.yaml에서 매일 할일 로드"""
        try:
            if not self.yaml_path.exists():
                return []
            
            with open(self.yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            tasks = config.get('common', {}).get('daily_tasks', [])
            self.scheduled_tasks = tasks
            return tasks
        
        except Exception as e:
            print(f"[오류] 할일 로드 실패: {e}")
            return []
    
    def _register_task(self, task: dict):
        """작업을 스케줄에 등록"""
        time_str = task.get('time', '')
        target = task.get('target', '')
        message = task.get('message', '')
        
        if not all([time_str, target, message]):
            print(f"[경고] 불완전한 작업: {task}")
            return
        
        # 시간 형식 변환: '3:00' -> '03:00'
        time_parts = time_str.split(':')
        if len(time_parts) == 2:
            hour = time_parts[0].zfill(2)  # 2자리로 패딩
            minute = time_parts[1].zfill(2)
            time_str = f"{hour}:{minute}"
        elif len(time_parts) == 3:
            hour = time_parts[0].zfill(2)
            minute = time_parts[1].zfill(2)
            second = time_parts[2].zfill(2)
            time_str = f"{hour}:{minute}:{second}"
        
        # 스케줄 등록
        schedule.every().day.at(time_str).do(
            self._send_scheduled_message,
            target_agent=target,
            message=message
        )
        
        print(f"[등록] {time_str} → {target}: {message[:30]}...")
    
    def _send_scheduled_message(self, target_agent: str, message: str, task_id: str = None):
        """
        스케줄된 메시지를 대상 에이전트에게 전송
        
        AgentRunner의 internal_messages 큐에 직접 추가합니다.
        (다른 스탠다드 도구들과 동일한 패턴)
        """
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] 스케줄 실행: {target_agent} <- {message[:30]}...")
            
            # AgentRunner의 internal_messages 큐에 직접 추가
            from agent_runner import AgentRunner
            
            # 에이전트가 아직 시작되지 않았으면 대기 (최대 60초)
            import time
            max_wait = 60
            waited = 0
            while target_agent not in AgentRunner.internal_messages and waited < max_wait:
                print(f"[대기 중] {target_agent} 에이전트가 아직 시작되지 않음... ({waited}초)")
                time.sleep(5)
                waited += 5
            
            if target_agent not in AgentRunner.internal_messages:
                print(f"[실패] 대상 에이전트 없음: {target_agent} (60초 대기 후에도 시작 안 됨)")
                return
            
            # 딕셔너리 형태로 메시지 추가
            msg_dict = {
                'content': message,
                'from_where': 'scheduler',
                'reply_to': target_agent
            }
            
            AgentRunner.internal_messages[target_agent].append(msg_dict)
            print(f"[성공] {target_agent}에게 메시지 전송됨")
            
            # 마지막 실행 시간 기록
            if task_id:
                self._save_last_run(task_id, datetime.now())
        
        except Exception as e:
            print(f"[오류] 메시지 전송 중 오류: {e}")
    
    def _run_scheduler(self):
        """스케줄러 메인 루프 (별도 스레드에서 실행)"""
        print("="*50)
        print("IndieBiz 스케줄러 시작")
        print("="*50)
        
        # 초기 로드
        tasks = self._load_tasks()
        for task in tasks:
            self._register_task(task)
        
        # 시작 시 놓친 스케줄 확인 및 실행 (별도 스레드로)
        missed_tasks_thread = threading.Thread(
            target=self._check_and_run_missed_tasks,
            args=(tasks,),
            daemon=True
        )
        missed_tasks_thread.start()
        
        # 1시간마다 재로딩 스케줄 등록
        schedule.every().hour.do(self._reload_scheduled)
        
        print(f"\n스케줄러 가동 중... 등록된 할일: {len(tasks)}개\n")
        
        # 메인 루프
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(30)  # 30초마다 체크
            except Exception as e:
                print(f"[오류] 스케줄러 실행 중 오류: {e}")
        
        print("\n스케줄러 종료됨")
    
    def _reload_scheduled(self):
        """1시간마다 자동 재로딩"""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 스케줄 자동 재로딩...")
        
        # 기존 스케줄 제거 (재로딩 스케줄 제외)
        jobs = schedule.get_jobs()
        for job in jobs:
            if job.job_func.func.__name__ != '_reload_scheduled':
                schedule.cancel_job(job)
        
        # 새로운 할일 로드
        tasks = self._load_tasks()
        for task in tasks:
            self._register_task(task)
        
        print(f"재로딩 완료: {len(tasks)}개 작업")
    
    def _check_and_run_missed_tasks(self, tasks: list):
        """
        놓친 스케줄 확인 및 실행
        
        프로그램이 수면 모드에 있었거나 꺼져있어서 놓친 스케줄을
        찾아서 즉시 실행합니다.
        """
        now = datetime.now()
        today = now.date()
        
        # 마지막 실행 기록 로드
        last_runs = self._load_last_runs()
        
        missed_count = 0
        
        for task in tasks:
            time_str = task.get('time', '')
            target = task.get('target', '')
            message = task.get('message', '')
            
            if not all([time_str, target, message]):
                continue
            
            # 오늘 실행 예정 시간
            time_parts = time_str.split(':')
            if len(time_parts) >= 2:
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                
                scheduled_time = datetime(
                    today.year, today.month, today.day,
                    hour, minute
                )
                
                # task ID 생성 (동일 키로 마지막 실행 기록 관리)
                task_id = f"{target}_{time_str}"
                
                # 마지막 실행 시간
                last_run = last_runs.get(task_id)
                
                # 조건 확인:
                # 1. 예정 시간이 지났고
                # 2. 오늘 아직 실행하지 않았으면
                if now > scheduled_time:
                    # 오늘 실행했는지 확인
                    if last_run:
                        last_run_date = datetime.fromisoformat(last_run).date()
                        if last_run_date == today:
                            # 오늘 이미 실행함
                            continue
                    
                    # 놓친 스케줄 발견!
                    print(f"\n[놓친 스케줄] {time_str}에 실행했어야 할 작업 발견")
                    print(f"  대상: {target}")
                    print(f"  메시지: {message[:50]}...")
                    print(f"  즉시 실행합니다!\n")
                    
                    # 즉시 실행
                    self._send_scheduled_message(target, message, task_id)
                    missed_count += 1
        
        if missed_count > 0:
            print(f"\n✅ {missed_count}개의 놓친 스케줄을 실행했습니다.\n")
        else:
            print(f"\n✓ 놓친 스케줄 없음\n")
    
    def _load_last_runs(self) -> dict:
        """마지막 실행 기록 로드"""
        if not self.last_run_file.exists():
            return {}
        
        try:
            import json
            with open(self.last_run_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[경고] 마지막 실행 기록 로드 실패: {e}")
            return {}
    
    def _save_last_run(self, task_id: str, run_time: datetime):
        """마지막 실행 시간 기록"""
        try:
            import json
            
            # 기존 기록 로드
            last_runs = self._load_last_runs()
            
            # 업데이트
            last_runs[task_id] = run_time.isoformat()
            
            # 저장
            with open(self.last_run_file, 'w') as f:
                json.dump(last_runs, f, indent=2)
        
        except Exception as e:
            print(f"[경고] 마지막 실행 시간 저장 실패: {e}")


# 도구 인스턴스 (싱글톤)
_scheduler_instance = None


def get_scheduler(agents_yaml_path="agents.yaml", output_router=None):
    """스케줄러 싱글톤 인스턴스 가져오기"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SchedulerTool(agents_yaml_path, output_router)
    elif output_router is not None:
        # OutputRouter 업데이트
        _scheduler_instance.output_router = output_router
    return _scheduler_instance


# 스탠다드 도구 인터페이스
def scheduler_tool(command: str, from_where: str, reply_to: str) -> str:
    """
    스케줄러 스탠다드 도구
    
    사용 예:
    - scheduler_tool("start", "agent_001", "gui")
    - scheduler_tool("status", "agent_001", "gui")
    - scheduler_tool("list", "agent_001", "gui")
    """
    scheduler = get_scheduler()
    return scheduler(command, from_where, reply_to)


if __name__ == "__main__":
    # 테스트용 독립 실행
    scheduler = SchedulerTool("agents.yaml")
    
    print("스케줄러 시작...")
    result = scheduler("start", "test", "test")
    print(result)
    
    print("\n상태 확인...")
    result = scheduler("status", "test", "test")
    print(result)
    
    print("\n할일 목록...")
    result = scheduler("list", "test", "test")
    print(result)
    
    # 계속 실행
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n종료...")
        scheduler("stop", "test", "test")
