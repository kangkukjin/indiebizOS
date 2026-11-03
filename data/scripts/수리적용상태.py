#!/usr/bin/env python3
"""수리적용상태 — self:patch status 관측을 단계별로 표시하는 읽기 어댑터.

args: key, status(self:patch status의 결과), observed_at(그 조회 시각, 선택),
commits(현재 작업 저장소의 최근 커밋 파일, 기본 1), all(종결 세션 포함).
자식은 부모의 수리 소유권을 재구성하지 않는다. status 없이 호출하면 기존
키 인자를 보존하여 부모에게 조회 요청을 반환한다. 세션 원장을 직접 열지 않는다.
items의 라이브 열은 바이트 관측이고 활성·완료 판정이 아니다. 저장 영수증과
현재 조회를 구분하며 현재 실행 판본을 별도 측정하지 않는다.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESS_DIR = os.path.join(ROOT, "data", "system_ai_state", "repair_sessions")
CLOSED = ("applied", "discarded")


def _sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def _git(args):
    try:
        # ★core.quotepath=false — 끄지 않으면 git 이 한글 경로를 "\354\210\230…" 로 이스케이프해
        #   돌려주고, 그 문자열로 os.path.exists 하면 **없는 파일**이 된다. 이 스크립트가
        #   처음 돈 자리에서 자기 자신을 '삭제됨'으로 신고했다(기계도 인코딩으로 거짓말한다).
        r = subprocess.run(["git", "-c", "core.quotepath=false"] + args,
                           cwd=ROOT, capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _head_blob(rel):
    """HEAD 에 있는 그 경로의 blob sha (없으면 None)."""
    out = _git(["rev-parse", "--verify", "-q", f"HEAD:{rel}"]).strip()
    return out or None


def _blob_of(path):
    """작업 파일의 git blob sha (git hash-object — 내용만으로 계산)."""
    if path is None or not os.path.exists(path):
        return None
    return _git(["hash-object", "--", path]).strip() or None


def _git_state(rel, content_path, dirty):
    """이 **변경 내용**이 HEAD 에 있는가 — 라이브의 더러움을 묻지 않는다.

    ★2026-08-24 재수리: 종전엔 `git status` 에 안 뜨면 '커밋됨'이었다. 그러면 격리에만
    있는 새 내용을 라이브가 아직 옛 판일 때 물으면 라이브는 깨끗하니 '커밋됨'이 나온다
    — 66파일이 커밋 0건인데 전부 '커밋됨'으로 보고된 실측. 판정은 내용 blob 으로:
      격리 내용 blob == HEAD blob → 커밋됨
      HEAD 에 경로 없음        → 신규(미커밋)
      다름                     → 미커밋(HEAD와 다름)
    """
    head = _head_blob(rel)
    mine = _blob_of(content_path)
    if mine is None:
        return dirty.get(rel) or "—"
    if head is None:
        return "신규(미커밋)"
    return "커밋됨" if mine == head else "미커밋(HEAD와 다름)"


def project_status(args):
    """Only consume the parent's owner-filtered result; never open session files."""
    key = args.get('key')
    snapshot = args.get('status')
    request = {'action': 'self:patch', 'args': {'op': 'status', **({'key': key} if key else {})}}
    if not isinstance(snapshot, dict) or snapshot.get('success') is not True:
        return {'items': [], 'state': 'unknown', 'reported_complete': None,
                'request': request, 'source_complete': False,
                'unknown': ['부모의 self:patch status 결과가 필요합니다'],
                'message': '세션 원장을 직접 읽지 않습니다. 부모 조회 결과를 status 인자로 전달하세요.'}
    items = []
    for row in snapshot.get('items', []):
        if key and row.get('key') != key:
            continue
        if not args.get('all') and not key and row.get('status') in CLOSED:
            continue
        # Owner adds these fields only where the caller may see full progress.
        fields = ('candidate_hash', 'verified', 'verified_current', 'current_candidate_hash',
                  'execution_checks', 'verification_plan', 'last_preparation', 'applied',
                  'complete', 'stage', 'activation', 'activation_checks', 'commit',
                  'recovery', 'program_scope', 'program_activation', 'root', 'last_error')
        stored = {name: row.get(name) for name in fields}
        items.append({'key': row.get('key'), 'status': row.get('status'),
                      'files': row.get('files', []), 'stored_receipts': stored,
                      'file_observation': row.get('live_comparison'),
                      'source': 'supplied self:patch status',
                      'owner_observed_at': args.get('observed_at'),
                      'active_rechecked_here': False,
                      'unknown': [name for name in ('activation', 'activation_checks', 'commit', 'recovery')
                                  if not row.get(name)]})
    return {'items': items, 'owner_status': snapshot, 'request': request,
            'reported_complete': snapshot.get('complete'),
            'source_complete': bool(items), 'active_rechecked_here': False,
            'unknown': [] if items else ['대상 행 미관측: 세션 부재나 접근 거절을 구별할 수 없습니다'],
            'message': '전달받은 소유자 관측입니다. 저장 영수증·파일 비교·활성·각인은 별개이며 이 호출은 적용이나 복구를 실행하지 않습니다.'}


def main():
    args = json.loads(sys.stdin.read() or '{}')
    result = project_status(args)
    # Optional historical Git rows describe this workspace only, not activation.
    commits = []
    for i in range(max(0, int(args.get('commits', 1) or 0))):
        line = _git(['log', '-1', f'--skip={i}', '--format=%H|%s']).strip()
        if not line:
            break
        sha, _, subject = line.partition('|')
        commits.append({'commit': sha, 'subject': subject, 'workspace': ROOT,
                        'scope': 'historical commit; not current active code',
                        'files': _git(['show', '--name-only', '--format=', sha]).splitlines()})
    result['commits'] = commits
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
