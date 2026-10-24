# 하드웨어 연결 개선 적용 증거 — 2026-10-25

설계·구현 정본은 [계획서 §9](../../HARDWARE_CONNECTION_LATENCY_DESIGN_2026_10_25.md).
PC 구현 `ac19d287`, TV 구현 `dbc06ff8` 기준이다.

`before-pc-public.json`과 `after-pc-public.json`은 같은 tv1 장치에서 공개
`[fn:PC제어]`의 status를 한 호출자에서 순차 10회 실행한 원자료다. 로컬 monotonic
clock으로 HTTP 요청부터 공개 결과 반환까지 재며 LLM 추론은 포함하지 않는다.
정상 표본 모두 `verified:true`. 중앙값 9.3422초 → 8.18045초, 최댓값
18.698초 → 8.2871초였다. 부하·캐시·다른 PC 업데이트 트래픽을 통제한 실험은
아니므로 차이 전체를 변경의 인과 효과나 성능 보장으로 주장하지 않는다.
기준선 첫 호출도 포함했다. cold/warm/TTL 집단을 분리한 실측, 장치 내부 실행/정리와
로컬 완료→송신 시작의 별도 계측, AI 토큰 절감은 미측정이다.

`excluded-during-update-pc-public.json`(67.6414초)과
`excluded-during-restart-pc-public.json`(64.0216초)은 각각 배포·허브 재기동과
겹친 pending 관측이다. 정상 표본에서 제외하되 원자료를 보존한다. 요청은 읽기
전용이며 정상 완료로 간주하지 않았다.

`*-acceptance.json`은 신규 헬퍼의 실제 정보 조회 성공·지문 확인이다.
tv1과 KHJoffice는 새 Windows 상주 헬퍼로 재접속했고 rollback이 없었다.
`rollout.json`의 맥12·맥26은 오프라인으로 업데이트를 제출하지 않았다.
Mac 산출물은 ad-hoc 빌드이며 개인키 서명·원격 적용은 미실시다.

`before-tv-public.json` 10건과 `after-tv-observation.json`은 모두 TV 미응답이다.
통신 경로의 반환 `success:true`를 실제 TV 관측 성공으로 보지 않는다.
실제 TV의 handshake 재사용·키/전원·단절 복구·cold/warm/TTL 성능은 미검증이며,
그 동작의 자동검사와 실기기 검증을 구분한다. 전원·키 명령을 보내지 않았다.

`summary.json`은 정상 PC 표본 집계와 최종 전수 검사 결과다.
재현 도구 `probe_pc.py`는 장치 ID와 새 출력 파일을 인자로 받으며, 기존 파일을
덮어쓰지 않는다. 현재 버전 측정만 하며 구버전 설치나 업데이트는 하지 않는다.
