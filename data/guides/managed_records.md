# 공동 업무 기록 — self:record

`self:record`는 파일 덮어쓰기 도구가 아니다. 등록한 업무 명령을 인증된 주체로 실행하고,
권한·관계·버전을 검사한 뒤 변경·이력·영수증·대기 항목을 함께 확정한다.
업무 공간의 데이터는 공간 운영자 기기에 남는다. 회원의 개인 파일·기억 저장과 구분한다.

## 시작

1. 내 어휘에서 **Managed Records / 공동 업무** 묶음을 켠다.
2. 앱 모드의 **공동 업무**를 열거나 `/records/app`에 접속한다.
3. 공간 관리에서 업무 정의 JSON을 선택하고 검사한 뒤 공간 이름으로 생성한다.
4. 참여할 이웃 번호와 역할을 등록한다. 회원은 기존 회원 열쇠로 `/m/records/app`에서 접속한다.
5. 기록을 선택하고 명령을 실행한다. 처리할 때 본 버전과 입력을 보낸다.

바로 사용할 수 있는 선언 예시:
- [재고와 주문](examples/managed_orders.json): 상품 재고 등록 → 주문 생성 → 재고 조건부 확정.
- [두 사람의 승인](examples/managed_approvals.json): 주문 생성 → 검토 접수 → 서로 다른 두 검토자 승인.

예시는 앱 정의만 제공한다. 실제 재고·주문·회원은 만들지 않는다. 역할 이름은 예시에서
admin/clerk/reviewer이고 앱이 자유롭게 바꿀 수 있다. 공간 소유자에게는 초기 admin 역할만 부여한다.

## IBL

```text
[self:record]{op:"describe"}
[self:record]{op:"describe", space:"shop"}
[self:record]{op:"query", space:"shop", collection:"orders", where:{status:"draft"}, limit:50}
[self:record]{op:"detail", space:"shop", collection:"orders", id:"기록ID"}
[self:record]{op:"apply", space:"shop", command:"confirm", definition_revision:1,
 input:{order_id:"기록ID"}, expected:[{collection:"orders",id:"기록ID",revision:1}],
 request_id:"주문확정_고유번호"}
[self:record]{op:"receipt", space:"shop", request_id:"주문확정_고유번호"}
[self:record]{op:"inbox", space:"shop"}
```

op는 `describe/query/detail/apply/history/inbox/receipt`다. 설계 초기의 get 표기는 기존 IBL
정본의 단건 조회 이름인 **detail**로 맞췄다. 새 get 별칭은 만들지 않는다.
describe에 collection·id를 함께 주면 선택한 업무 인스턴스에 고정된 정의의 명령을 설명한다.
조회는 items 통화다. 표 연산·AI 구조화·문서 출력과 기존 파이프로 결합할 수 있다.
apply는 effect 봉투이며 전체 내부 변경 행을 공개하지 않는다.

조회 조건은 객체 또는 조건 객체의 AND 목록이다. 읽을 수 없는 필드는 검색·정렬·집계에 쓸 수 없다.
다음 페이지는 같은 조건과 반환된 cursor를 보낸다. 권한·정의·확정 상태가 바뀌면 cursor를 다시 받는다.

## 정의 계약 v1

최상위는 `contract_version:1`, `collections`, `commands`이며 선택으로 `name`, `notice`,
`processes`, `effects`, `subscriptions`, `views`, `roles`를 둔다. 이름·업종은 데이터다.
`views`와 `roles`는 설명 메타이며 권한 부여는 공간의 membership 관리에서 한다.

기록 묶음에는 fields, access, 선택 unique·invariants·process·additional을 둔다.
타입은 string/integer/number/boolean/object/array/record_ref/artifact_ref다.
required, nullable, default, enum, min/max, max_length를 지원한다.
object는 fields, array는 items로 하위 계약을 선언한다. 필드 이름의 `_` 접두는 서버 예약이다.
record_ref는 collection을 요구하며 같은 공간의 살아 있는 기록을 가리켜야 한다.
고유 키는 `unique:[[필드1,필드2]]`. null은 고유 키에 허용하지 않는다.

접근 예:

```json
{"read":{"roles":["clerk"],"where":"$record._created_by == $actor.subject","fields":["title","status"]}}
```

명령은 input, allow, 선택 read·require·change·emit·reason_required·confirmation을 가진다.
allow는 roles/subjects, 선택 where/deny_self를 사용한다. deny_self는 읽은 첫 기록의 작성·제출 주체 필드를 지정한다.
read는 별칭마다 collection·id·version(observed/current)를 선언한다.
observed는 expected에 정확한 revision이 필수다. current는 트랜잭션 안의 최신 데이터로 조건을 검사한다.
internal_access는 명령 내부에서만 읽는 묶음을 운영자가 명시적으로 발행하는 기능이다.
일반 기록 조회 권한을 넓히지 않는다. 개인 자료를 우회하는 범용 경로는 받지 않는다.

`{"expr":"$stock.available - $order.quantity"}`는 기존 공용 순수 식이다.
`"$input"`, `"$order.stock_id"`는 타입을 보존하는 참조다. 도구 호출·AI 판단·임의 코드를 식으로 실행하지 않는다.
require와 invariants는 정확히 true일 때만 통과한다. 숫자·날짜·동등 비교는 기존 IBL과 같은 의미를 쓴다.

변경 원자:
- `create:{collection,as,values}`: 서버 ID 생성, 기본값 적용.
- `patch:{record,set}`: 읽은/생성한 별칭 수정. 상태·시스템 필드 직접 변경 금지.
- `archive:{record}`: 보관. 다른 살아 있는 기록이 참조하면 실패한다.
- `transition:{record,from,to}`: process에 해당 명령의 간선이 있어야 한다.
- `task:{op:create,record,roles|subjects,command,...}`: 대기 작업 생성.
- `task:{op:claim|complete|cancel,id,revision}`: 담당 배정·승인·취소. complete는 기록 변경 앞에 둔다.

process는 field(기본 status), initial, transitions를 갖는다. transitions는 명령 이름을 키로
from/to와 선택 task를 지정한다. task는 quorum, required_roles, deny_self(기본 true), label,
due_seconds, timeout_command, timeout_input을 지원한다. 실제 승인자가 같은 사람이면 로그인 경로를
바꿔도 한 표다. 대상 버전이 바뀌면 옛 작업 항목은 승인할 수 없다.
`confirmation:"human"` 명령은 업무 화면의 확인 증표가 필요하다. IBL로 사람 확인을 대신 발급하지 않는다.

## 후속 처리

emit는 event, 선택 record·payload·effect를 갖는다. subscriptions는 사건 이름마다
`{command,input,expected}` 목록이다. 자동 구독 순환은 등록 때 거절한다.
타이머·구독·외부 효과는 영속 큐에 남고 백엔드 재시작 뒤 다시 확인한다.
발신 워커는 묶음 활성 상태와 공간 중지 상태를 확인한다.

기본 외부 어댑터는 http다. 운영자가 effects에 adapter/http, url(HTTPS), 선택 credential_env,
idempotency_header, lookup_url(`{effect_id}` 자리), timeout(1~30초)을 선언한다.
비밀 값은 JSON에 넣지 않고 기존 환경 자격 이름만 참조한다.
상대 서비스는 JSON `status:succeeded|failed|unknown`으로 처리 결과를 응답해야 한다.
단순 HTTP 200/202를 업무 성공으로 바꾸지 않는다. 필요하면 상대 API와 이 계약을 맞추는 어댑터를 등록한다.
success_command/success_input, failure_command/failure_input으로 결과를 후속 명령에 연결한다.
결과 식에서는 `$payload`, `$result`를 참조한다.

원격 응답이 불명확하면 unknown으로 남긴다. 처리 상태 화면에서 근거를 적어 성공·실패를 확인하거나
재처리를 승인한다. 같은 효과 ID를 유지한다. 완료된 처리를 다시 발송하지 않으며 환불·취소는 새 보상 명령으로 정의한다.

## 운영 계약

- request_id는 논리 동작 하나에 하나다. 타임아웃·재시도에는 같은 값, 내용을 바꾸면 새 값이다.
- 같은 ID·같은 내용의 성공 요청은 영수증을 돌려주고, 같은 ID·다른 내용은 거절한다.
- 일반 명령에 admin_ 접두 요청 ID는 사용할 수 없다.
- 재시도도 현재 읽기 권한을 적용한다. 영수증으로 접근이 취소된 기록 본문을 읽을 수 없다.
- 현재 정책이 허용하는 한 기존 업무 인스턴스는 시작한 정의 버전으로 진행한다. 새 업무는 최신 정의를 쓴다.
- 새 정의는 기존 데이터 전체의 제약 검사를 통과해야 발행된다. 비호환 데이터 변환은 자동으로 추측하지 않는다.
- 첨부는 20MiB 이하, 불변 ID·내용 지문으로 연결한다. 이름이 같아도 새 내용은 별도 첨부다.
- 초기 실행 상한: 공간당 1,000개 기록, 명령 입력 256KiB, 한 명령 변경 100개, 페이지 200개, 식 2,048자.
  상한 초과는 일부만 성공시키지 않고 거절한다. 큰 업무 공간은 저장 인덱스 확장 후 이 제한을 조정해야 한다.
- 현재 패키지는 PC 호스트용이다. 폰·회원 브라우저는 같은 호스트의 앱을 사용한다. 오프라인 확정을 지원하지 않는다.
- 내보내기는 DB snapshot과 첨부를 묶는다. 복원은 새 공간 이름에만 가능하고 참여 권한·확인 증표를 승계하지 않는다.
- 복원 공간은 중지 상태다. 외부 처리 결과를 대사하고 복구 확인을 완료한 뒤 재개한다.
- 로컬 저장소는 `data/record_spaces/`이며 git에서 제외된다. 패키지를 잠재워도 자료는 삭제되지 않는다.

업무 화면은 기존 앱 렌더러의 `web_app` 바인딩으로 PC·웹에서 같은 서버 화면을 연다.
명령 요청은 action ID와 구조화 값으로 전달하므로 객체·목록·첨부가 IBL 문자열 치환을 거치지 않는다.
기존 단일 값 회원 앱의 동작은 바꾸지 않는다.

## 데이터 구조 이전

호환되는 필드·명령 추가는 `publish`로 발행한다. 기존 기록이 새 계약을 만족하지 않으면 전체 발행이 거절된다.
비호환 변경은 관리 화면에서 업무 중지 → 새 정의와 필드 변환 입력 → 정의·데이터 함께 이전 순서다.
열린 승인 작업·미완료 후속 처리는 먼저 종결해야 한다. 변환은 묶음별 `set`·`drop`이며 각 식은
변경 전 `$record`를 읽는다. 기록 ID는 유지하고 버전·정의·변경 전후 이력을 함께 확정한다.

```json
{"stocks":{"set":{"category":"general","available":{"expr":"$record.available"}},"drop":["old_field"]}}
```

관리 API는 `POST /records/admin/{space}/migrate`이며 definition·transforms·expected_revision·
request_id·reason을 보낸다. 검사 실패 때 정의·자료·관리 버전은 모두 그대로다.
이전 후 업무 재개는 별도 관리 동작이다. AI가 기존 장부의 의미나 이전 규칙을 자동으로 추정하지 않는다.

외부 어댑터는 현재 위임자의 역할을 전송 전에 다시 검사한다. 이미 진행 중인 원격 호출을 취소하는 기능은 아니다.
확인 증표는 인증된 브라우저 화면의 확인 절차이며 전자서명·생체 인증 증명은 아니다.
첨부 열람과 새 참조에는 업로더 또는 현재 열람 가능한 기록의 첨부라는 권한 근거가 필요하다.

### 공유 업무 서버 화면과 감사 범위 (2026-09-20)

- `app.web_app`: 같은 서버 경로만 선언한다. 정적 경로 검증 후 PC·웹의 공통 iframe 렌더러가 연다.
  회원 자작 앱은 이 키를 사용할 수 없다. 공개 패키지는 경로의 서버 인증·타입 입력·권한 검사를 갖춰야 한다.
- `resource_scope:app_shared`: `lands_on:hub`의 명시적 공동 자료 쓰기다. 기존 회원 개인 파일 쓰기와 구별한다.
- 공유 액션의 `path_audited`에는 패키지 실행 지문뿐 아니라 `dependencies: {저장소 상대경로: SHA-256}`로
  실제 권한·저장·입출력 구현을 묶는다. 구현을 변경하면 경로를 재검토한 뒤 지문을 갱신한다.
  지문만 자동 갱신하는 작업을 감사로 취급하지 않는다.
