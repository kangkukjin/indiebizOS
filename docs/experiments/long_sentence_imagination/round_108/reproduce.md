# 108회차 증거 재검사

정본 저장소 `/Users/kangkukjin/Desktop/AI/indiebizOS`에서 실행한다.

```bash
.venv/bin/python3 docs/experiments/long_sentence_imagination/round_108/verify_evidence.py
.venv/bin/python3 docs/experiments/long_sentence_imagination/round_108/verify_evidence.py --live
.venv/bin/python3 scripts/check_file_size.py
.venv/bin/python3 scripts/select_tests.py --files data/common_prompts/consciousness_prompt.md data/guides/deep_research.md --explain
.venv/bin/python3 -m pytest backend/test_research_planning.py backend/test_task_repair.py
```

첫 검사는 보존 산출물·인용·호출 계보를 대조한다. 로컬 outputs가 존재하면 입력·시스템 프롬프트 지문과 실제 저장본도 검사한다. `--live`는 원래 outputs 18시도와 training 에피소드 DB 및 현 제품 지문까지 요구한다. 이후 제품 변경이 있으면 live 소스 지문 실패는 당시 시험 실패를 뜻하지 않는다. 이 스크립트는 내용 품질 자동 채점기가 아니다.

요청·사전 확인 조건은 cases.json 및 refinement_cases.json, 수동 의미 판정은 review.json, 실제 출력은 results/·refinement/에 있다. preliminary/는 가이드 크기 압축 전 시도이며 제외하지 않고 비용에 포함한다. recovery_relinked/는 시험 어댑터의 이전 계획 인자 전달을 제품 경로와 맞춘 재실행이다.

모델 재실행은 별도 비용·training 에피소드·계획 파일을 만든다. 보존 러너는 당시 deadline과 입력 지문을 고정하고 기존 폴더 덮어쓰기를 거절한다. 따라서 그대로 실행해 현재 출력에 덮어쓰지 않는다. 새 비교는 새 회차·시간 예산·출력 폴더를 정하고 같은 입력과 사전 조건을 복사한다. run_refined.py의 N04는 N03_refined가 아니라 **원래 N03_final**을 이어야 이전 오류 교정 시험이 유지된다. R03 복원은 recovered_context.json의 합성 자료와 운영자가 제공한 reframe 호출이며 실행자의 자율 행동 시험이 아니다.

현재 제품은 refined_consciousness_prompt.md·refined_deep_research.md와 같은 판본이다. consciousness_prompt.md·deep_research.md는 첫 수정 판본이며, r01_guide.md는 첫 수정 R01의 실제 17바이트 접두어 차이를 보존한다. 판본 경위는 harness_notes.md에 있다. 원래 입력·시스템 프롬프트 전문은 outputs/long_sentence_imagination/2026-11-01_108회차/에 로컬 보존하고 git 증거에는 지문과 응답을 남긴다.
