import boot_paths  # noqa: F401
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from lsp_transport import Client, LspError

SERVER = r'''
import json,sys,time,os

def send(value):
    body=json.dumps(value,ensure_ascii=False).encode()
    packet=('Content-Length: %d\r\n\r\n'%len(body)).encode()+body
    for start in range(0,len(packet),3):
        sys.stdout.buffer.write(packet[start:start+3]);sys.stdout.buffer.flush()

def read():
    headers={}
    while True:
        line=sys.stdin.buffer.readline()
        if not line: sys.exit()
        if line==b'\r\n':break
        k,v=line.decode().split(':',1);headers[k.lower()]=v.strip()
    return json.loads(sys.stdin.buffer.read(int(headers['content-length'])))

held=None
while True:
    value=read();method=value.get('method');rid=value.get('id')
    if method=='config':
        send({'jsonrpc':'2.0','id':'server-id','method':'workspace/configuration','params':{'items':[]}})
        answer=read()
        send({'id':rid,'result':answer.get('result')})
    elif method=='reverse':
        if held is None:held=rid
        else:
            send({'id':rid,'result':'둘째😀'});send({'id':held,'result':'첫째'});held=None
    elif method=='slow':
        time.sleep(.15);send({'id':rid,'result':'late'})
    elif method=='die':os._exit(1)
    elif method=='shutdown':send({'id':rid,'result':None})
    elif method=='exit':sys.exit()
    elif rid is not None:send({'id':rid,'result':value.get('params')})
'''


@pytest.fixture
def transport(tmp_path):
    script = tmp_path / 'fake.py'; script.write_text(SERVER)
    client = Client([sys.executable, '-u', str(script)], tmp_path,
                    on_request=lambda method, params: {'configuration': '한글😀'})
    yield client
    client.close()


def test_fragmented_utf8_reverse_request_and_out_of_order_responses(transport):
    assert transport.request('config') == {'configuration': '한글😀'}
    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(transport.request, 'reverse')
        b = pool.submit(transport.request, 'reverse')
        assert {a.result(), b.result()} == {'첫째', '둘째😀'}


def test_timeout_cancel_late_result_does_not_contaminate_next_request(transport):
    with pytest.raises(LspError) as timeout:
        transport.request('slow', timeout=.03)
    assert timeout.value.code == 'LSP_TIMEOUT'
    assert transport.request('echo', {'next': True}) == {'next': True}
    with pytest.raises(LspError) as cancelled:
        transport.request('slow', cancelled=lambda: True)
    assert cancelled.value.code == 'LSP_CANCELLED'
    assert transport.request('echo', {'safe': True}) == {'safe': True}


def test_process_loss_fails_current_and_future_requests_promptly(transport):
    with pytest.raises(LspError):transport.request('die')
    start = time.monotonic()
    with pytest.raises(LspError):transport.request('echo')
    assert time.monotonic() - start < .5
