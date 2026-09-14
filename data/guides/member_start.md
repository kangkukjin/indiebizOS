# 회원 시작 문장 열 개

이 가이드는 주인이 발행한 회원 채팅의 입문서다. 주인용 명령창과 회원용 명령창은 신원이 다르다.
주인은 **내 어휘 → system_essentials → 기본설명 → 회원에게 공개**를 켠다. 묶음이 주인에게 잠들면
회원에게도 닫힌다. 회원은 발급받은 `mode: member` helper를 실행한다. 키를 채팅에 붙이지 않는다.

예시 경로는 회원 기기의 경로다. PC에서는 자기 폴더의 절대경로로 바꾸고, Android는 회원 앱 저장소 안의
상대경로를 쓴다. 텍스트 줄 범위와 PDF/DOCX/XLSX/XLS 읽기, PDF/DOCX 양식 채우기를 지원한다.
Android 파일 가져오기는 원래 확장자를 보존하며 결과 문서는 **파일 내보내기**로 저장소를 선택한다. 주인 설정·다른 기기로의 위임은 공개하지 않는다.
각 예시는 **뜻 → 문장 → 확인** 순서다. 코드블록은 직접 입력할 수 있는 IBL이다.

1. **폴더 보기** — 폴더의 파일 목록을 읽는다. 확인: 결과 경로가 내 기기의 경로인지 본다.
```ibl
[self:list]{path:"."}
```

2. **텍스트 읽기** — 자신의 메모를 읽는다. 확인: 기기를 끊으면 허브 대신 읽기가 실패한다.
```ibl
[self:read]{path:"memo.txt"}
```

3. **새 메모 저장** — 승인 판에서 경로와 본문을 확인하고 허용한다. 확인: 성공 영수증 이후 파일이 생긴다.
```ibl
[self:write]{path:"memo.txt",content:"오늘의 메모"}
```

4. **폴더 만들기** — 로컬 승인이 필요한 작업이다. 확인: 자신의 파일 앱에 폴더가 생긴다.
```ibl
[self:mkdir]{path:"notes"}
```

5. **파일 옮기기** — 이미 있는 대상 파일에는 덮어쓰지 않는다. 확인: 원본이 옮겨지고 대상에 내용이 남는다.
```ibl
[self:move]{src:"memo.txt",dest:"notes/memo.txt"}
```

6. **읽은 내용을 다른 파일에 저장** — 파이프의 문자열을 로컬 쓰기로 전달한다. 확인: 두 파일 본문이 같다.
```ibl
[self:read]{path:"notes/memo.txt"} >> [self:write]{path:"notes/copy.txt"}
```

7. **등록 프로그램 보기** — PC 로컬 프로그램 원장을 읽는다. 확인: 허브에 설치된 프로그램은 나오지 않는다.
```ibl
[self:script]{op:"list"}
```

8. **완성한 프로그램 등록** — PC의 기존 파일을 승인해 등록한다. Python/Bash/Node 역할 이름을 사용한다.
자원 파일은 프로그램 폴더 안에 두고 resources에 상대경로를 적는다. dependencies는 패키지명·버전의 기록이며
자동 설치하지 않는다. 확인: 내보내기에 프로그램과 자원이 포함된다.
```ibl
[self:script]{op:"register",id:"greet",path:"greet.py",interpreter:"python3",resources:["template.txt"],dependencies:[]}
```

9. **등록 프로그램 실행** — stdin으로 JSON 입력을 받는 프로그램을 자기 PC에서 실행한다.
확인: 승인 없이 실행되지 않는다. Android 회원 앱에는 Python/Bash/Node 실행기가 없으므로 정직하게 거절한다.
```ibl
[self:script]{op:"run",id:"greet",args:{name:"회원"}}
```

10. **기억을 가지고 독립하기** — 화면의 **기억 내보내기**를 누른다. PC는 ZIP 경로를 알려주고,
Android는 저장 위치 선택기를 연다. 독립 설치본에서 아래 명령을 실행한다. 확인: 가져온 대화와 심층기억을
자기 시스템에서 조회할 수 있다. 같은 ZIP을 다시 가져와도 대화·기억이 중복되지 않는다.
```sh
.venv/bin/python3 scripts/import_member_archive.py /받은/경로/member-export.zip
```

완료 여부를 잃은 작업은 **최근 작업 결과 → 결과 불명**에 남는다. 같은 효과를 다시 내는 명령을 자동으로
보내지 않는다. 원래 파일/실행 결과를 확인한 회원이 새 실행 여부를 결정한다.
세션 간 이어지는 대화·장기 기억의 정본은 로컬 SQLite다. 허브는 처리 동안 회원 본문을 보고,
모델 제공자에도 입력을 보내므로 로컬 전용 추론이라는 뜻은 아니다.

## 문서·라디오·폰 사용 예

- PDF 부분 읽기: `[self:read]{path:"report.pdf",pages:"2-4"}`
- 텍스트 범위: `[self:read]{path:"memo.txt",start_line:2,end_line:5}`
- 양식 완성: `[self:fill]{path:"form.docx",data:{이름:"회원"},output:"done.docx"}` — 기기 저장을 승인한 뒤 성공한다.
- 라디오 묶음을 공개하면 `[sense:radio]{op:"korean"}` → `[limbs:radio]{op:"play",station_id:"kbs_1radio"}`.
  회원 기기에서 재생을 승인한다. 브라우저의 지원 형식에 따라 재생이 거절될 수 있다.
  `[limbs:radio]{op:"status"}`로 확인하고 `op:"stop"`으로 멈춘다. PC 회원 화면을 켜 둔다.
- Android 묶음을 공개하면 폰의 **위치 허용** 버튼 → `[sense:here]{}`. 정밀도도 함께 확인한다.
  **접근성 설정**에서 회원 앱 서비스를 켠 뒤 `[limbs:android]{op:"snapshot"}` → 탭/입력을 요청한다.
  위치·화면 접근은 매 작업 승인 대상이며, 허브 PC의 위치·화면으로 대체하지 않는다.

파일 전달·감사·지원 형식의 자세한 계약: member_contract.md.
