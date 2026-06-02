import json

with open('/Users/kangkukjin/Desktop/AI/indiebizOS/data/packages/installed/tools/youtube/tool.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 요약 도구 추가
new_tool = {
    "name": "summarize_video",
    "description": "유튜브 동영상 자막 추출 + AI 요약 + HTML 보고서 생성 + 브라우저 자동 열기를 한 번에 수행합니다. 영상의 핵심 내용을 빠르고 시각적으로 파악하고 싶을 때 사용.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "YouTube URL"
            },
            "summary_length": {
                "type": "integer",
                "description": "요약 길이 (자). 기본 3000자"
            },
            "language": {
                "type": "string",
                "description": "선호 자막 언어 (예: 'ko', 'en')"
            }
        },
        "required": ["url"]
    }
}

# 기존에 summarize_youtube나 summarize_video가 있는지 확인하고 제거
data['tools'] = [t for t in data['tools'] if t['name'] not in ['summarize_youtube', 'summarize_video']]
data['tools'].insert(4, new_tool)

with open('/Users/kangkukjin/Desktop/AI/indiebizOS/data/packages/installed/tools/youtube/tool.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("tool.json patched")
