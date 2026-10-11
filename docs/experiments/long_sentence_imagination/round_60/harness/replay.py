"""Call the same IBL API implementation in a process using the isolated bridge."""
import boot_paths  # noqa: F401
import asyncio
import json
import sys
import time
from pathlib import Path
from api_ibl import IBLRequest, execute_ibl_code


async def main():
    for request_path in sys.argv[1:]:
        path = Path(request_path)
        request = json.loads(path.read_text())
        started = time.time()
        result = await execute_ibl_code(IBLRequest(**request))
        elapsed = time.time() - started
        path.with_name(path.stem + '_isolated_result.json').write_text(json.dumps({
            'request': request, 'response': result, 'elapsed': elapsed,
        }, ensure_ascii=False, indent=2))
        print(json.dumps({'request': str(path), 'elapsed': elapsed,
                          'success': result.get('success'), 'value': result.get('value'),
                          'error': result.get('error')}, ensure_ascii=False))
        if not result.get('success'):
            raise RuntimeError('IBL replay failed; see preserved response')


if __name__ == '__main__':
    asyncio.run(main())
