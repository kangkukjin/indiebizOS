import requests
import json
import os

# 국가법령정보센터 API 기본 URL
BASE_URL = "http://www.law.go.kr/DRF"

def get_api_key():
    """설정 파일이나 환경 변수에서 API 키를 가져옵니다."""
    # 1. 환경 변수 확인
    api_key = os.environ.get("LAW_API_KEY")
    if api_key:
        return api_key
    
    # 2. config.json 확인
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
            return config.get("api_key")
    
    return None

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """법조인패키지 도구 실행 핸들러"""
    api_key = get_api_key()
    if not api_key:
        return "에러: Law API 키가 설정되지 않았습니다. 패키지 폴더의 config.json에 'api_key'를 입력하거나 LAW_API_KEY 환경 변수를 설정해주세요."

    if tool_name == "search_legal_info":
        query = tool_input.get("query")
        target = tool_input.get("target", "law")
        url = f"{BASE_URL}/lawSearch.do"
        params = {
            "OC": api_key,
            "target": target,
            "type": "JSON",
            "query": query
        }
        response = requests.get(url, params=params)
        return response.text

    elif tool_name == "get_legal_detail":
        item_id = tool_input.get("id")
        target = tool_input.get("target", "law")
        url = f"{BASE_URL}/lawService.do"
        params = {
            "OC": api_key,
            "target": target,
            "type": "JSON",
            "ID": item_id
        }
        response = requests.get(url, params=params)
        return response.text

    elif tool_name == "search_laws":
        query = tool_input.get("query")
        url = f"{BASE_URL}/lawSearch.do"
        params = {
            "OC": api_key,
            "target": "law",
            "type": "JSON",
            "query": query
        }
        response = requests.get(url, params=params)
        return response.text

    elif tool_name == "get_law_detail":
        law_id = tool_input.get("law_id")
        url = f"{BASE_URL}/lawService.do"
        params = {
            "OC": api_key,
            "target": "law",
            "type": "JSON",
            "ID": law_id
        }
        response = requests.get(url, params=params)
        return response.text

    elif tool_name == "search_precedents":
        query = tool_input.get("query")
        url = f"{BASE_URL}/lawSearch.do"
        params = {
            "OC": api_key,
            "target": "prec",
            "type": "JSON",
            "query": query
        }
        response = requests.get(url, params=params)
        return response.text

    elif tool_name == "get_precedent_detail":
        precedent_id = tool_input.get("precedent_id")
        url = f"{BASE_URL}/lawService.do"
        params = {
            "OC": api_key,
            "target": "prec",
            "type": "JSON",
            "ID": precedent_id
        }
        response = requests.get(url, params=params)
        return response.text

    return f"알 수 없는 도구: {tool_name}"
