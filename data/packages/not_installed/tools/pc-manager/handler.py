import os
import hashlib
import subprocess
import json
import time
from pathlib import Path
from collections import defaultdict

try:
    import psutil
except ImportError:
    psutil = None

def get_size(path):
    """폴더 크기 계산 (du 명령어 사용 - 빠름)"""
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
        # du -sk: 킬로바이트 단위로 빠르게 계산
        result = subprocess.run(
            ['du', '-sk', str(path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            size_kb = int(result.stdout.split()[0])
            return size_kb * 1024
        return 0
    except:
        return 0

def analyze_storage(path=None, depth=2):
    root = Path(path or os.path.expanduser('~'))
    result = {'path': str(root), 'total_size': 0, 'details': []}
    try:
        items = list(root.iterdir())
        for item in items:
            size = get_size(item)
            result['total_size'] += size
            result['details'].append({'name': item.name, 'size': size, 'is_dir': item.is_dir()})
        result['details'].sort(key=lambda x: x['size'], reverse=True)
        return result
    except Exception as e:
        return {'error': str(e)}

def find_duplicates(path=None, max_files=5000, timeout_seconds=60):
    """중복 파일 찾기 (파일 수 제한 및 타임아웃 적용)"""
    import time
    start_time = time.time()
    root = Path(path or os.path.expanduser('~'))
    hashes = defaultdict(list)
    duplicates = []
    file_count = 0
    try:
        for dirpath, _, filenames in os.walk(root):
            if time.time() - start_time > timeout_seconds:
                break  # 타임아웃
            for f in filenames:
                file_count += 1
                if file_count > max_files:
                    break
                full_path = os.path.join(dirpath, f)
                try:
                    with open(full_path, 'rb') as f_obj:
                        file_hash = hashlib.md5(f_obj.read(1024*1024)).hexdigest()
                        hashes[file_hash].append(full_path)
                except:
                    continue
            if file_count > max_files:
                break
        for h, paths in hashes.items():
            if len(paths) > 1:
                try:
                    size = os.path.getsize(paths[0])
                    duplicates.append({'hash': h, 'paths': paths, 'size_per_file': size, 'total_waste': size * (len(paths)-1)})
                except:
                    pass
        return {'duplicates': duplicates, 'potential_savings': sum(d['total_waste'] for d in duplicates), 'scanned_files': file_count}
    except Exception as e:
        return {'error': str(e)}

def find_junk(path=None, max_files=5000, timeout_seconds=30):
    """정크 파일 찾기 (파일 수 제한 및 타임아웃 적용)"""
    import time
    start_time = time.time()
    root = Path(path or os.path.expanduser('~'))
    junk_patterns = ['*.log', '*.tmp', '.DS_Store', 'Thumbs.db', '.cache/*', '*/cache/*']
    found_junk = []
    total_size = 0
    file_count = 0
    try:
        for pattern in junk_patterns:
            if time.time() - start_time > timeout_seconds:
                break
            for p in root.rglob(pattern):
                file_count += 1
                if file_count > max_files or time.time() - start_time > timeout_seconds:
                    break
                if p.is_file():
                    try:
                        size = p.stat().st_size
                        found_junk.append({'path': str(p), 'size': size})
                        total_size += size
                    except:
                        pass
        return {'junk_files': found_junk, 'total_junk_size': total_size, 'scanned_files': file_count}
    except Exception as e:
        return {'error': str(e)}

def get_system_overview():
    try:
        os_ver = subprocess.check_output(['sw_vers', '-productVersion'], timeout=5).decode().strip()
        model = subprocess.check_output(['sysctl', '-n', 'hw.model'], timeout=5).decode().strip()
        cpu = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], timeout=5).decode().strip()
        uptime = subprocess.check_output(['uptime'], timeout=5).decode().strip()

        mem_info = {}
        if psutil:
            mem = psutil.virtual_memory()
            mem_info = {'total': mem.total, 'available': mem.available, 'percent': mem.percent}

        storage_info = get_detailed_storage()

        return {
            'os_version': os_ver,
            'model': model,
            'cpu': cpu,
            'uptime': uptime,
            'memory': mem_info,
            'storage_gb': storage_info.get('internal_disk_size_gb', 'Unknown'),
            'storage_free_gb': storage_info.get('internal_free_gb', 'Unknown')
        }
    except Exception as e:
        return {'error': str(e)}

def get_physical_disk_size(disk_id="disk0"):
    """diskutil을 사용해 물리 디스크의 실제 크기를 가져옴"""
    try:
        output = subprocess.check_output(['diskutil', 'info', disk_id], timeout=10).decode()
        for line in output.split('\n'):
            if 'Disk Size:' in line:
                # "Disk Size: 251.0 GB (251000193024 Bytes)"
                import re
                match = re.search(r'\((\d+) Bytes\)', line)
                if match:
                    return int(match.group(1))
        return 0
    except:
        return 0

def get_detailed_storage():
    """df 명령어로 빠르게 디스크 정보 조회"""
    try:
        result = subprocess.run(
            ['df', '-P', '-k'],
            capture_output=True, text=True, timeout=5
        )

        volumes = []
        internal_size_gb = 0
        internal_free_gb = 0

        for line in result.stdout.strip().split('\n')[1:]:
            parts = line.split()
            if len(parts) >= 6 and parts[0].startswith('/dev/disk'):
                try:
                    size_kb = int(parts[1])
                    used_kb = int(parts[2])
                    avail_kb = int(parts[3])
                    capacity = parts[4]
                    mount_point = ' '.join(parts[5:])
                except ValueError:
                    continue

                is_internal = mount_point == '/' or mount_point.startswith('/System')
                size_gb = round(size_kb / 1024 / 1024, 1)
                used_gb = round(used_kb / 1024 / 1024, 1)
                avail_gb = round(avail_kb / 1024 / 1024, 1)

                volumes.append({
                    'name': mount_point.split('/')[-1] or 'Macintosh HD',
                    'mount_point': mount_point,
                    'size_gb': size_gb,
                    'used_gb': used_gb,
                    'available_gb': avail_gb,
                    'capacity': capacity,
                    'is_internal': is_internal
                })

                if mount_point == '/':
                    internal_size_gb = size_gb
                    internal_free_gb = avail_gb

        return {
            'internal_disk_size_gb': internal_size_gb,
            'internal_free_gb': internal_free_gb,
            'volumes': volumes
        }
    except Exception as e:
        return {'error': str(e)}

def list_external_drives():
    try:
        output = subprocess.check_output(['diskutil', 'list', 'external'], timeout=10).decode()
        return {'external_drives': output}
    except subprocess.TimeoutExpired:
        return {'error': '외장 드라이브 검색 시간 초과 (10초)'}
    except Exception as e:
        return {'error': str(e)}

def get_resource_usage(limit=5):
    if not psutil: return {'error': 'psutil not installed'}
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
        try:
            processes.append(proc.info)
        except: continue
    processes.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
    return {'top_processes': processes[:limit]}

def execute(tool_name, parameters, project_path="."):
    if tool_name == 'analyze_storage':
        return analyze_storage(parameters.get('path'), parameters.get('depth', 2))
    elif tool_name == 'find_duplicates':
        return find_duplicates(parameters.get('path'))
    elif tool_name == 'find_junk':
        return find_junk(parameters.get('path'))
    elif tool_name == 'get_system_overview':
        return get_system_overview()
    elif tool_name == 'get_detailed_storage':
        return get_detailed_storage()
    elif tool_name == 'get_resource_usage':
        return get_resource_usage(parameters.get('limit', 5))
    elif tool_name == 'list_external_drives':
        return list_external_drives()
    else:
        return {'error': f'Unknown tool: {tool_name}'}
