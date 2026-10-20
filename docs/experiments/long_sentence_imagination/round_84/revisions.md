# 초안 수정 이력

- v0→v1 (check 2건): L56 삼항식 안 `[self:read]` 호출 → `[if]` 블록으로 분리(PURE_EXPRESSION). L66 `content:$req.ask_user` Null|Text → assert 뒤 `text()`로 Text 확정(TYPE). 진단의 hint만으로 고쳤고 내부 코드는 열지 않았다.
- v1→v2 (check 1건): `text(Null|Text)` 도 TYPE 거절 → `get($req,"ask_user","")` 로 결측 기본값 조회. 모델 추출 필드가 전부 nullable 이라 파일 쓰기 전 Text 확정 방법을 교재에서 바로 찾기 어려웠다(발견 후보).
- v2→v3 (T5b 실행 뒤 의미 수정): 제약확인이 cost/hours null 을 불충족으로 떨어뜨려 채택 0건·"거절 사유 없음" 메모가 나왔다. null=미확인을 `unverified` 묶음으로 분리하고 brief 지시에 세 묶음을 구분해 넘긴다(교재 "미확인과 0을 섞지 않는다"·judge null=미결정 규칙을 내 코드가 어겼던 것). 검사 통과 뒤 T5b 를 reuse 로 재실행.
