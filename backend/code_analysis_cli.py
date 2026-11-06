"""JSON stdin/stdout workspace client; --mcp exposes scoped IBL and sandbox commands."""
import boot_paths  # noqa: F401
import argparse
import json
import os
import sys

from code_analysis_channel import request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--connection', default=os.environ.get('CODE_ANALYSIS_CONNECTION'))
    parser.add_argument('--mcp', action='store_true')
    args = parser.parse_args()
    if not args.connection:
        parser.error('작업 실행자가 발행한 CODE_ANALYSIS_CONNECTION이 필요합니다')
    if not args.mcp:
        print(json.dumps(request(args.connection, json.load(sys.stdin)), ensure_ascii=False))
        return
    from tool_loader import load_tool_schema
    schema = load_tool_schema('execute_ibl')
    tools = [{'name': 'execute_ibl', 'description': '현재 작업 사본의 읽기 전용 IBL. 코드 분석은 workspace read selector.analysis.',
              'inputSchema': schema['input_schema']},
             {'name': 'run_command', 'description': '현재 사본의 OS 격리 명령. 코드 분석 CLI도 같은 채널을 사용합니다.',
              'inputSchema': {'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command']}}]
    for line in sys.stdin:
        incoming = json.loads(line)
        if 'id' not in incoming:
            continue
        response = {'jsonrpc': '2.0', 'id': incoming['id']}
        try:
            method, params = incoming['method'], incoming.get('params', {})
            if method == 'initialize':
                result = {'protocolVersion': params.get('protocolVersion', '2024-11-05'), 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'indiebiz-workspace', 'version': '1'}}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': tools}
            elif method == 'tools/call':
                name, arguments = params['name'], params.get('arguments', {})
                if name == 'execute_ibl':
                    value = request(args.connection, {'op': 'ibl', 'args': arguments})
                elif name == 'run_command':
                    value = request(args.connection, {'op': 'command', 'command': arguments.get('command')}, timeout=260)
                else:
                    raise ValueError('알 수 없는 도구')
                result = {'content': [{'type': 'text', 'text': value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}]}
            else:
                raise ValueError('지원하지 않는 MCP 메서드')
            response['result'] = result
        except Exception as exc:
            response['error'] = {'code': -32603, 'message': str(exc)}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
