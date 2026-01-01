import os
import psutil
import shutil
import json

def format_size(bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024:
            return f"{bytes:.2f}{unit}"
        bytes /= 1024

def get_storage_info(path="."):
    total, used, free = shutil.disk_usage(path)
    return {
        "total": format_size(total),
        "used": format_size(used),
        "free": format_size(free),
        "percent": (used / total) * 100
    }

def get_system_health():
    cpu_usage = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    
    report = []
    report.append("=== PC 시스템 건강 진단 보고서 ===")
    
    # CPU 진단
    cpu_status = "정상" if cpu_usage < 70 else "주의" if cpu_usage < 90 else "위험"
    report.append(f"1. CPU 사용량: {cpu_usage}% [{cpu_status}]")
    if cpu_status != "정상":
        report.append("   - 처방: 고부하 프로세스가 있는지 확인하고 불필요한 프로그램을 종료하세요.")
        
    # 메모리 진단
    mem_usage = memory.percent
    mem_status = "정상" if mem_usage < 80 else "주의" if mem_usage < 95 else "위험"
    report.append(f"2. 메모리 사용량: {mem_usage}% [{mem_status}]")
    if mem_status != "정상":
        report.append("   - 처방: 사용하지 않는 브라우저 탭이나 무거운 앱을 닫아 메모리를 확보하세요.")
        
    # 디스크 진단
    disk_usage = (disk.used / disk.total) * 100
    disk_status = "정상" if disk_usage < 90 else "주의"
    report.append(f"3. 디스크 사용량: {disk_usage:.1f}% [{disk_status}]")
    if disk_status != "정상":
        report.append("   - 처방: 임시 파일이나 휴지통을 비워 저장 공간을 확보하세요.")
        
    report.append("\n[종합 의견]")
    if cpu_status == "정상" and mem_status == "정상" and disk_status == "정상":
        report.append("현재 시스템 상태가 아주 쾌적합니다! 계속해서 좋은 상태를 유지해 주세요.")
    else:
        report.append("일부 항목에서 주의가 필요합니다. 위 처방 내용을 확인해 보세요.")
        
    return "\n".join(report)

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    pc-manager 도구 핸들러
    """
    action = tool_input.get("action", "scan_storage")
    
    try:
        if action == "scan_storage":
            path = tool_input.get("path", ".")
            info = get_storage_info(path)
            result = f"경로 '{path}'의 저장소 정보:\n- 전체: {info['total']}\n- 사용 중: {info['used']} ({info['percent']:.1f}%)\n- 남은 공간: {info['free']}"
            return json.dumps({"success": True, "data": result}, ensure_ascii=False)
        
        elif action == "check_health":
            result = get_system_health()
            return json.dumps({"success": True, "data": result}, ensure_ascii=False)
        
        else:
            return json.dumps({"success": False, "error": f"알 수 없는 액션: {action}"}, ensure_ascii=False)
            
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
