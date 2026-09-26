# 에피소드 4019·4020 — 확정 오류 수리

## 관측과 범위

4019는 KOSPI 보드에 보유 수량의 평가금액, 4020은 평균 매수가 기준 평가손익·수익률을
추가한 작업이다. 원장은 `data/world_pulse.db`의 해당 episode_log와 trajectory_event다.
최초 숙고 OFF의 EXECUTE 경로이므로 평가 미실행은 현재 계약에 맞는다.

이번 변경은 실행 오류 재발 방지와 운영 소스 보존이다. 전체 맥락·토큰·라운드 최적화는
포함하지 않으며 비용 개선을 주장하지 않는다.

## 확인한 오류와 처리

| 오류 | 재현·판정 | 처리 |
| --- | --- | --- |
| 반환 객체 필드 안의 table 파이프 | 당시 계약의 PURE_EXPRESSION으로 거절 | 당시에는 앞 변수로 분리하는 교재·회귀를 추가. 이후 [2026-09-26 컨테이너 호출 개정](IBL_CONTAINER_CALLS_2026_09_26.md)에서 직접 호출을 허용 |
| contains 내장 함수 가정 | 원래 실패 문장에 함께 들어 있던 미지원 호출 | 정확한 URL 일치 예제로 교정. contains 미지원·in은 목록 원소 검사임을 설명 |
| worker.js의 export 로딩 실패 | 기존 Node 20에서 직접 import 시 재현 | 프로젝트 package.json에 type: module 선언 |
| Wrangler와 Node 버전 불일치 | 기존 로그의 Node 20 / Wrangler 4.137.0 요구사항 불일치 | 프로젝트 개발 의존성·lockfile에 Node 22.23.3과 Wrangler 4.137.0 고정, npm test/build/deploy 경로 마련 |
| 무시 대상 소스 커밋 실패 | worker.js와 wrangler.toml이 Git 비추적 상태 | .gitignore에 KOSPI 앱의 소스·설정·검증·문서 6개 파일만 예외. 나머지 산출물·캐시·비밀 파일은 제외 |

전역 Node를 바꾸지 않는다. npm 스크립트는 프로젝트의 Node 바이너리를 사용한다.
기존 Node 20으로 첫 의존성 설치 시 엔진 경고는 남을 수 있지만, 설치 후 테스트·빌드는
고정한 Node 22로 실행된다. Cloudflare·웹앱 가이드는 이 프로젝트 계약을 먼저 읽게 한다.
Wrangler 일반 설치 근거: https://developers.cloudflare.com/workers/wrangler/install-and-update/

## 검증

- 수정 전의 Node 직접 import 실패가 수정 후 정상으로 바뀜.
- `npm exec -- node --version`: v22.23.3.
- `npm test`: 3개 테스트 통과. 실제 Worker가 반환하는 HTML의 스크립트로 상승·하락·본전·
  시세 누락·다른 종목 격리·갱신·HTTP 실패를 검사. API의 음수 등락과 원천 폴백·전체 실패도 검사.
- `npm run build`: Wrangler dry-run 성공, 업로드 없음.
- `.venv/bin/python -m pytest backend/test_ibl_v2_core.py backend/test_ibl_composition_teaching.py -q -o addopts=''`: 92개 통과.
- 운영 URL을 실제 브라우저로 열어 평가금액·매수금액·손익·수익률 표시 확인, 콘솔 오류·경고 없음.
- 허용 소스는 추적 가능하며 `.env`, `.wrangler`, `node_modules`, 다른 outputs 및 중첩 outputs는 계속 무시됨.

Worker의 계산·HTML·시세 처리 코드는 이번에 바꾸지 않았다. 기존 운영 소스를 처음 추적한 것이다.
따라서 원격 재배포는 필요하지 않다. 확인한 조건에서는 손익 계산 오류를 재현하지 못했다.
가격 원천의 모든 상황이나 전체 백엔드 회귀를 검증했다는 뜻은 아니다.
