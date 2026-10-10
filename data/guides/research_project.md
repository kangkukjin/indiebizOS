# 연구 프로젝트

런처 → 새 프로젝트 → 유형 **연구 프로젝트** → 이름을 입력한다. 여러 연구 프로젝트를
만들 수 있으며 자료실은 프로젝트별로 독립적이다. 프로젝트 안에서 새 대화를 만들고,
다시 열어 같은 주제를 이어간다. 대화마다 질문·연구 방향 메모를 관리하고 자료는 함께 검색한다.

## 사용

- **새 대화**에서 교육·경제 같은 주제를 만든 뒤 대화를 선택한다.
- **대화**에서 질문한다. 기존 자료를 회수하고 필요한 추가 조사를 진행하며, 실제 획득한
  IBL 결과와 파일을 자동 보존한다. 창을 닫아도 백엔드가 살아 있으면 실행은 계속된다.
- **대화 설정**에서 제목·고정 연구 메모와 조사 방식을 바꾼다. 저장 자료만 모드는 외부
  획득을 차단한다. 보관한 대화는 보관 해제로 다시 이어갈 수 있다.
- **자료실 / 자료 검색**에서 원문과 출처·확보 범위·색인 상태를 확인한다. 긴 원문은
  다음 부분 읽기로 이어간다. **인용 근거** 탭은 해당 답변에 실제 제공된 발췌를 보여준다.
- **자료 추가**는 파일, URL, 텍스트를 받는다. 지원하지 않는 형식도 원본은 보존하고
  추출 실패를 표시한다. 자료 관리에서 텍스트 추출·검색 준비를 재시도할 수 있다.
- **대화 기록 검색**은 프로젝트 내 주제들의 메시지를 찾는다. 대화가 길면 이전 대화
  읽기로 과거 메시지를 열 수 있다.

자료 확보 범위 full은 도구가 확보해 반환한 본문 기준이다. 검색 결과 snippet은
페이지 전체 원문과 다르며, unknown은 전체 확보를 확인하지 못했다는 뜻이다.
CLI 실행 모델을 설정한 경우 원문 보존을 지원하는 API 보조 모델을 사용한다.
API 평가 모델도 설정되지 않았다면 모델 설정 오류를 먼저 해결해야 한다.

## IBL

```ibl
[self:project]{op:"create",name:"교육 연구",project_kind:"research"}
[self:project]{op:"thread_create",project_ref:"생성된 project_uid",title:"학급 규모"}
[self:project]{op:"thread_send",project_ref:"project_uid",thread_ref:"thread_ref",message:"학급 규모와 학습 효과를 조사해줘",request_id:"클라이언트의 고유 요청 ID"}
[self:notebook]{op:"search",project_ref:"project_uid",query:"학급 규모"}
[self:notebook]{op:"read",project_ref:"project_uid",version_ref:"version_ref"}
[self:notebook]{op:"add",project_ref:"project_uid",version_ref:"version_ref"}
```

thread_send의 task_ref는 기존 self:task로 조회·취소한다. 같은 request_id와 같은 내용의
재전송은 새 턴을 만들지 않는다. project_ref가 있는 notebook은 전역 name과 함께 쓸 수 없다.

## 저장과 복구

프로젝트의 conversations.db가 대화·자료 원장이고 research/objects가 확보한 원문이다.
research/index.db는 파생 검색 색인이다. 백업은 프로젝트 전체를 보존하되 라이브 SQLite는
온라인 backup/VACUUM INTO로 복사한다. 앱의 프로젝트 복제는 이를 적용하고 새 uid를 부여한다.
이름을 바꿔도 uid·원문 판본·인용은 유지된다.

원문 보존 실패는 조사를 실패 처리하고 추가 도구 획득을 차단한다. 디스크 공간·권한을
복구한 뒤 새 메시지로 이어간다. 추출·색인 실패는 자료를 삭제하지 않으므로 원문을 유지한
채 재시도한다. 삭제된 색인 DB는 다음 자료실 접근에서 재생성한다. 백엔드 재시작 때 남은
실행은 중단 상태로 보존하며 새 질문으로 계속할 수 있다. 진행 중인 대화는 먼저 중단한 뒤
프로젝트 이름 변경·복제·휴지통·삭제를 한다.

구현/범위 정본: `docs/RESEARCH_PROJECT_DESIGN_2026_10_10.md` §17.
