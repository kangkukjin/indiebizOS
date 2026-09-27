# Python 라이브러리 직접 호출

현재 IBL의 `[self:python]`은 설치된 Python 함수·클래스·메서드를 이름으로 직접 호출한다.
함수마다 스크립트를 작성·등록할 필요가 없다. Python Libraries 묶음이 활성화되고
`local_python` 정책이 허용한 제한 없는 주인 실행에서 사용할 수 있다.
회원·이웃·포털·제한 에이전트에는 제공하지 않는다. 별도 워커는 보안 샌드박스가 아니다.

```ibl
$평균=[self:python]{op:"call",target:"statistics:mean",args:[[2,4,6]]}
$배열=[self:python]{op:"call",target:"numpy:array",args:[[2,4,6]]}
$목록=$배열 >> [self:python]{op:"call",name:"tolist"}
return {평균:$평균,목록:$목록}
```

- `target`은 `모듈:qualified.name`이다. `args`는 위치 인자 목록, `kwargs`는 키워드 인자다.
  목록 하나를 첫 인자로 줄 때 `args:[[1,2]]`처럼 쓴다. 생략한 기본값은 Python이 적용한다.
- 객체 메서드는 `receiver:$객체,name:"메서드"`로 호출한다. 파이프 입력은 receiver다.
  callable 객체 자체는 name 없이 호출한다. 속성은 `op:"getattr"`; 항목은 `operator:getitem`을 호출한다.
- `result:"auto"`가 기본이다. 기본 값은 IBL 값으로, 배열·DataFrame·tuple·이터레이터 등은
  객체 참조로 반환한다. `ref`는 객체 보존을 강제하고, `value`는 값 변환을 요구한다.
- 객체 참조는 같은 최상위 프로그램 안에서만 유효하다. 함수·반복·관용구로 넘길 수 있지만
  프로그램 종료 뒤 다음 모델 호출에서는 만료된다. 종료 전에 메서드나 export로 값을 얻는다.
  `release`는 참조만 반납한다. 파일/연결의 close는 명시 호출하고 필요하면 finally에 둔다.
- Decimal·큰 정수는 그대로 보존한다. tuple/set/NaN/복소수/바이너리를 임의로 목록·null·문자열로
  바꾸지 않는다. IBL lambda를 Python 콜백으로 넘길 수는 없고, Python callable 참조는 가능하다.

```ibl
$표=[self:python]{op:"call",target:"pandas:DataFrame",args:[{분류:["A","A","B"],금액:[3,5,2]}]}
$묶음=$표 >> [self:python]{op:"call",name:"groupby",args:["분류"],kwargs:{as_index:false}}
$합계=$묶음 >> [self:python]{op:"call",name:"sum",kwargs:{numeric_only:true}}
$행=$합계 >> [self:python]{op:"call",name:"to_dict",kwargs:{orient:"records"}}
return $행 >> [table:filter]{where:($r)=>$r.금액>4}
```

이름을 모르면 `modules{query:"numpy",offset:0,limit:50}`로 설치 후보와 버전을 확인하고,
`describe{target:"statistics:mean"}`으로 서명·문서를 읽는다. 후보는 import 성공 보증이 아니다.
서명을 모르는 함수도 직접 호출할 수 있다. check는 라이브러리를 import/실행하지 않는다.

export 형식은 `list`(기본 컨테이너·ndarray), `records`(DataFrame→items+schema),
`bytes`(bytes→파일, `options:{path:"파일명"}` 필수)다. DataFrame 인덱스 생략과 dtype 등
변환 의미가 결과/근거에 실린다. 시간대 객체 같은 셀은 명시 변환이 더 필요할 수 있다.

변환 실패는 함수를 이미 실행한 뒤의 실패다. 원함수를 다시 호출하지 말고 같은 프로그램의
catch에서 `$error.partial` 참조를 받아 메서드/export로 회수한다.

```ibl
$r=null
[try]{$r=[self:python]{op:"call",target:"builtins:tuple",args:[[1,2]],result:"value"}}
[catch]{$r=$error.partial}
return $r >> [self:python]{op:"export",format:"list"}
```

호출 기본 시간은 60초이며 `timeout`으로 0.01~3600초를 지정한다. 실행 전체 예산·취소가 우선한다.
워커 메모리 1GiB, 객체 4096개, 값 변환 10만 항목·깊이 64·문자열/바이너리 8MiB 한도를 둔다.
큰 결과는 참조로 보존하며 자동으로 일부만 반환하지 않는다. Python 호출은 같은 프로그램에서
직렬 실행된다. async 결과는 기다리고 generator는 자동 소비하지 않는다.

실패는 단계·Python 예외·원인과 실제 호출 여부를 전달한다. stdout은 진단이다.
효과는 unknown이며 자동 retry/reuse하지 않는다. 새 워커로 영수증을 재생해 객체 상태를
복원하지 않는다. 다음 실행은 명시 export한 값을 inputs로 받아 구성한다.
설치/환경 변경은 다음 새 실행에 반영하며 call 안에서 pip를 자동 실행하지 않는다.
