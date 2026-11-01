"""Round 105: isolated actual IBL execution, registration and real-model exercise."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa
import os, json, shutil, subprocess, time, hashlib, argparse
from contextlib import redirect_stdout
OUT = ROOT / 'outputs/long_sentence_imagination/2026-11-01_105회차'
DOC = Path(__file__).parent

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))

def setup(name):
    body = OUT / name
    (body / 'data/scripts').mkdir(parents=True, exist_ok=True)
    (body / 'data/workflows').mkdir(exist_ok=True)
    (body / 'outputs').mkdir(exist_ok=True)
    for n in ('ibl_nodes.yaml', 'package_meta.json', 'vocabulary_policy.yaml', 'core_manifest.json', 'api_registry.yaml', 'guide_db.json'):
        shutil.copyfile(ROOT / 'data' / n, body / 'data' / n)
    for n in ('packages','vocabulary','guides','system_docs'):
        target=body / 'data' / n
        if not target.exists(): target.symlink_to(ROOT / 'data' / n, target_is_directory=True)

    if not (body/'backend').exists(): (body/'backend').symlink_to(ROOT/'backend', target_is_directory=True)
    shutil.copyfile(ROOT/'data/scripts/capability_change.py',body/'data/scripts/capability_change.py')
    import yaml
    production=yaml.safe_load((ROOT/'data/scripts/registry.yaml').read_text())
    (body/'data/scripts/registry.yaml').write_text(yaml.safe_dump({'능력변경':production['능력변경']},allow_unicode=True))
    # Neither model nor script children can write outside their own body.
    profile = '(version 1)\n(deny default)\n(allow process*)\n(allow sysctl-read)\n(allow mach-lookup)\n(allow file-read*)\n(allow file-write* (subpath '+json.dumps(str(body),ensure_ascii=False)+') (literal "/dev/null"))\n(deny network*)\n'
    for denied in (ROOT/'.env', OUT/'trainer', OUT/'oracle', ROOT/'docs/experiments'):
        if denied != body and denied != DOC:
            profile += '(deny file-read* (subpath '+json.dumps(str(denied),ensure_ascii=False)+'))\n'
    # The harness itself must be importable; oracle and sibling bodies remain unavailable.
    profile = profile.replace('(deny file-read* (subpath '+json.dumps(str(ROOT/'docs/experiments'),ensure_ascii=False)+'))\n','')
    if name!='trainer': profile += '(deny file-read* (subpath '+json.dumps(str(OUT/'trainer'),ensure_ascii=False)+'))\n'
    (body/'sandbox.sb').write_text(profile)
    return body

def environment(body):
    allowed=('PATH','HOME','USER','LANG','LC_ALL','TERM','TMPDIR','SYSTEMROOT')
    env={k:v for k,v in os.environ.items() if k in allowed}
    env.update(INDIEBIZ_BASE_PATH=str(body), INDIEBIZ_SOURCE_ROOT=str(body),
        INDIEBIZ_CODE_ROOT=str(ROOT),INDIEBIZ_FUNCTION_STORE_ROOT=str(body/'data/workflows'),
        INDIEBIZ_RUNTIME_STATE_DIR=str(body/'runtime'),PYTHONDONTWRITEBYTECODE='1',
        GIT_CEILING_DIRECTORIES=str(OUT),TMPDIR=str(body/'tmp'))
    (body/'tmp').mkdir(exist_ok=True)
    return env

def initialise(body):
    os.environ.update(environment(body))
    import workflow_store, function_store
    workflow_store._get_workflows_path=lambda: body/'data/workflows'
    from function_library import register
    if not function_store.resolve('능력변경완료'):
        register('능력변경완료',(ROOT/'data/idioms/capability_change.ibl').read_text(),
            description='관용구·스크립트·어휘 변경의 계획·검사·등록·새 호출 검증·필요한 각인을 연결',edition=2)

def execute(body, request):
    from ibl_v2_entry import handle_request
    from thread_context import actor_context
    from ibl_v2_adapters import load_registry
    start=time.monotonic()
    with actor_context(agent_id='ls105',task_id='ls105',origin='training'):
        if request.get('describe'):
            cat=load_registry(str(body),'ls105')
            result={'actions':{n:cat[n].contract for n in request['describe'] if n in cat}}
        else:
            result=handle_request({'edition':2,'origin':'training',**request},str(body),'ls105')
    with (body/'calls.jsonl').open('a') as f:
        f.write(json.dumps({'at':time.time(),'request':request,'result':result,'seconds':time.monotonic()-start},ensure_ascii=False,default=str)+'\n')
    return result

def serve(body):
    from mcp.server.fastmcp import FastMCP
    with redirect_stdout(sys.stderr): initialise(body)
    mcp=FastMCP('indiebizos')
    @mcp.tool()
    def execute_ibl(code: str='',inputs: dict|None=None,describe:list[str]|None=None,check:bool=False,resume:dict|None=None,reuse:dict|None=None,read_result:dict|None=None)->dict:
        """IBL 실행·검사. describe로 실제 액션 계약 조회, read_result로 저장 결과 조회. origin은 training이다."""
        with redirect_stdout(sys.stderr):
            if read_result:
                from model_result_view import read_result as read_saved
                return read_saved(read_result)
            req={'code':code,'inputs':inputs or {},'check':check}
            for k,v in [('describe',describe),('resume',resume),('reuse',reuse)]:
                if v is not None:req[k]=v
            result=execute(body,req)
            from model_result_view import project_result
            return project_result(result)
    @mcp.tool()
    def read_guide(query:str)->dict:
        """운영 가이드 읽기. 파일 이름으로 읽거나 제목·설명·태그에서 검색한다. 빈 query는 목차."""
        directory=ROOT/'data/guides'
        entries=json.loads((ROOT/'data/guide_db.json').read_text()).get('guides',[])
        name=query if query.endswith('.md') else query+'.md'
        path=directory/name
        if path.is_file() and path.resolve().is_relative_to(directory):
            result={'file':name,'content':path.read_text()}
        else:
            words=query.lower().split()
            matches=[e for e in entries if not words or any(w in json.dumps(e,ensure_ascii=False).lower() for w in words)]
            result={'guides':matches[:30],'count':len(matches)}
        with (body/'guides.jsonl').open('a') as f:f.write(json.dumps({'query':query,'result':result},ensure_ascii=False)+'\n')
        return result
    mcp.run(transport='stdio')

def child(body,request):
    req=body/'request.json';dump(req,request)
    p=subprocess.run(['/usr/bin/sandbox-exec','-f',str(body/'sandbox.sb'),sys.executable,str(Path(__file__).resolve()),'execute',str(body),str(req)],env=environment(body),cwd=body,capture_output=True,text=True,timeout=180)
    if p.returncode: raise RuntimeError(p.stderr[-3500:]+p.stdout[-1000:])
    return json.loads(p.stdout)

def model(body,prompt_file,label,resume=None):
    from providers.claude_code import ClaudeCodeProvider
    prompt=(ROOT/'data/common_prompts/fragments/12_ibl_only.md').read_text()
    prompt+='\n시험 몸의 경로는 '+str(body)+'. 자료는 inputs/, 산출물은 outputs/이다. 공개 가이드는 read_guide로 조회할 수 있다. 다른 실행자의 자료·정답·훈련 코드·backend 소스는 읽지 않는다. 필요하면 현재 몸 안의 파일을 저작하고 등록할 수 있다. 네이티브 도구 대신 제공된 MCP를 사용한다. 외부 발송은 범위 밖이다.\n'
    provider=ClaudeCodeProvider(api_key='',model='opus',system_prompt=prompt,project_path=str(body),agent_name='ls105',agent_id='ls105')
    if not provider.init_client():raise RuntimeError('model init failed')
    config=body/'mcp.json'
    dump(config,{'mcpServers':{'indiebizos':{'command':'/usr/bin/sandbox-exec','args':['-f',str(body/'sandbox.sb'),sys.executable,str(Path(__file__).resolve()),'serve',str(body)],'env':environment(body)}}})
    cmd=[provider._binary_path,'--print','--output-format','json','--model',provider.model,'--permission-mode','bypassPermissions','--setting-sources','','--tools','','--strict-mcp-config','--mcp-config',str(config),'--allowed-tools','mcp__indiebizos__execute_ibl,mcp__indiebizos__read_guide','--append-system-prompt',prompt,'--max-turns','45']
    if resume:cmd+=['--resume',resume]
    started=time.time()
    p=subprocess.run(cmd,input=Path(prompt_file).read_text(),text=True,cwd=body,env=provider._build_env(),capture_output=True,timeout=720)
    (OUT/(label+'.model.json')).write_text(p.stdout)
    (OUT/(label+'.stderr.txt')).write_text(p.stderr)
    dump(OUT/(label+'.timing.json'),{'started':started,'ended':time.time(),'returncode':p.returncode})
    print(json.dumps({'label':label,'returncode':p.returncode,'elapsed':time.time()-started,'stdout_bytes':len(p.stdout)}))

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='setup':
        for n in ['trainer','ai']:setup(n)
    elif mode=='execute':
        with redirect_stdout(sys.stderr):
            body=Path(sys.argv[2]);initialise(body);result=execute(body,json.loads(Path(sys.argv[3]).read_text()))
        print(json.dumps(result,ensure_ascii=False,default=str))
    elif mode=='serve':serve(Path(sys.argv[2]))
    elif mode=='model':model(Path(sys.argv[2]).resolve(),sys.argv[3],sys.argv[4],sys.argv[5] if len(sys.argv)>5 else None)
