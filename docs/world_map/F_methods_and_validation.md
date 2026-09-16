# 방법의 지도 보완 — 적용 조건과 대안

확인일: 2026-09-16. 방법 이름을 모르는 작업 질문에서 드러난 공백을 보완한다.
아래는 원문을 재배포한 것이 아니라 공식 문서·저자 자료를 바탕으로 편집한 짧은 기능·조건·대안 메모다.
프롬프트용 이름·한 줄 설명의 정본은 `data/knowledge_catalog/world.yaml`이다.
설치 여부·최신 버전·무료 한도를 주장하지 않는다. 통로가 없는 방법은 모델의 사고·분석 과정에서 쓸 수 있다.

## randomized_experiment

**무작위 대조 실험 (A/B testing)** — 무작위 배정이 가능할 때 두 처치의 결과 차이 비교; 사전 지표·표본 설계 필요.

배정과 표본 단위를 먼저 정한다. 관찰자료의 전후 차이만으로 무작위 실험 효과를 주장하지 않는다. 관찰자료 대안은 인과 DAG·차분의 차분.
근거: [공식 문서·저자 안내](https://www.itl.nist.gov/div898/handbook/pri/section3/pri331.htm).

## factorial_design

**요인 실험 설계 (Factorial design)** — 여러 요인을 조합해 주효과·상호작용을 추정; 실험 횟수와 교락 고려.

단일 변수씩 바꾸는 실험이 놓치는 상호작용을 찾는다. 부분 요인 설계는 횟수를 줄이는 대신 교락을 검토한다.
근거: [공식 문서·저자 안내](https://www.itl.nist.gov/div898/handbook/pri/section3/pri333.htm).

## bootstrap

**부트스트랩 (Bootstrap)** — 표본을 재추출해 통계량의 신뢰구간 추정; 표본 대표성과 의존구조 고려.

SciPy stats.bootstrap으로 구현할 수 있다. 시계열·군집 자료를 독립 표본처럼 재추출하지 않는다. 퇴화 표본에서는 구간이 정의되지 않을 수 있다.
근거: [공식 문서·저자 안내](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html).

## sensitivity_analysis

**Sobol 민감도 분석** — 입력 범위를 변화시켜 출력 변동에 대한 변수별 기여와 상호작용 분석.

SALib의 표본 생성·모델 실행·분석 순서를 따른다. 변수 범위와 분포 선택이 결과에 영향을 주며, 예측 기여를 인과 효과로 바꾸지 않는다.
근거: [공식 문서·저자 안내](https://salib.readthedocs.io/en/latest/user_guide/basics.html).

## causal_dag

**인과 DAG (Causal diagram)** — 인과 가정을 방향 그래프로 표현해 교란·매개·통제 변수와 식별 가능성 검토.

DoWhy는 가정 모델링→식별→추정→반박의 흐름을 제공한다. 그래프를 그렸다는 사실만으로 가정이 증명되지는 않는다.
근거: [공식 문서·저자 안내](https://www.pywhy.org/dowhy/main/user_guide/causal_tasks/estimating_causal_effects/index.html).

## difference_in_differences

**차분의 차분 (Difference-in-differences)** — 처치·비교 집단의 전후 변화 차이로 효과 추정; 평행추세·선행반응 부재 가정 검토.

사전 추세·동시 충격과 비교집단 적합성을 점검한다. 시행 시점이 다른 자료는 단순 이중고정효과를 무조건 적용하지 않는다.
근거: [공식 문서·저자 안내](https://mixtape.scunning.com/08a-difference_in_differences).

## propensity_matching

**성향점수 매칭 (Propensity score matching)** — 관측 공변량으로 처치 확률이 비슷한 대상을 매칭; 미관측 교란은 해결하지 못함.

CausalML의 매칭·가중치 방법을 비교한다. 공통 지지와 매칭 후 균형을 확인해야 하며 무작위화의 대체 보증이 아니다.
근거: [공식 문서·저자 안내](https://causalml.readthedocs.io/en/latest/methodology.html#matching).

## systematic_review

**체계적 문헌고찰 (Systematic review)** — 질문·검색식·포함 기준을 정해 연구를 선별하고 근거를 종합; 편향과 누락 점검.

검색 과정과 선택 이유를 기록한다. Cochrane은 보건 연구 중심 자료이며 다른 분야에는 검색원·기준을 맞춰야 한다. 단순 결과 개수로 충실도를 판단하지 않는다.
근거: [공식 문서·저자 안내](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04).

## citation_chaining

**인용 추적 (Citation chaining)** — 핵심 문헌의 참고문헌·후속 인용을 따라 관련 연구 확장; 검색식 기반 조사와 병행.

OpenAlex 등 인용 자료를 활용할 수 있다. 시작 문헌의 관점과 출판 편향이 전파될 수 있어 독립 검색을 병행한다.
근거: [공식 문서·저자 안내](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04).

## thematic_analysis

**성찰적 주제분석 (Reflexive thematic analysis)** — 인터뷰·관찰 기록을 반복 검토·코딩해 의미 패턴과 주제를 해석.

Braun·Clarke 저자 사이트의 6단계 안내와 이해 페이지를 확인했다(검색 색인; 직접 본문 요청 502). 빈도 집계와 해석을 구분하고 분석자의 관점을 성찰한다.
근거: [공식 문서·저자 안내](https://www.thematicanalysis.net/doing-reflexive-ta/).

## mcda

**다기준 의사결정 분석 (MCDA)** — 여러 평가 기준·가중치로 대안을 비교; 가중치 변화에 따른 순위 민감도 점검.

기준·척도·가중치를 명시한다. 점수가 가치판단을 대신하지 않는다. 단일 가중합이 부적절하면 파레토 대안 집합을 함께 본다.
근거: [공식 문서·저자 안내](https://www.gov.uk/government/publications/multi-criteria-analysis-manual-for-making-government-policy).

## pareto_optimization

**파레토 다목적 최적화** — 충돌하는 목적 사이에서 다른 대안에 일방적으로 열등하지 않은 절충 해 집합 탐색.

pymoo 등으로 비지배 해를 찾을 수 있다. 파레토 집합이 최종 선택을 대신하지 않으며 선호·제약을 따로 결정한다.
근거: [공식 문서·저자 안내](https://pymoo.org/getting_started/part_1.html).

## discrete_event_simulation

**이산사건 시뮬레이션 (Discrete-event simulation)** — 도착·처리·자원 점유 사건으로 대기열과 병목 모의실험; 입력 분포 검증 필요.

SimPy는 시간에 따른 프로세스와 공유 자원을 모델링한다. 도착률·처리시간을 관측 자료로 보정한다. 분포 가정을 실제 시스템의 사실로 간주하지 않는다.
근거: [공식 문서·저자 안내](https://simpy.readthedocs.io/en/latest/).

## critical_path

**주공정법 (Critical Path Method)** — 작업 기간·선후관계로 완료일을 결정하는 경로와 여유시간 계산.

의존관계와 작업 기간이 필요하다. 자원 수량 제약이 중요하면 OR-Tools 같은 자원 제약 일정 방법을 함께 검토한다.
근거: [공식 문서·저자 안내](https://www.cmu.edu/cee/projects/PMbook/10_Fundamental_Scheduling_Procedures.html).

## dynamic_programming

**동적 계획법 (Dynamic programming)** — 중복 부분문제의 답을 저장·재사용해 단계별 최적화; 상태·전이·최적부분구조 필요.

상태 설계와 최적부분구조를 확인한다. 모든 탐색 문제가 작은 상태 공간을 갖는 것은 아니다. 제약 솔버와 비교할 수 있다.
근거: [공식 문서·저자 안내](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/resources/mit6_006s20_lec16/).

## bayesian_optimization

**베이지안 최적화 (Bayesian optimization)** — 평가가 비싼 함수의 대리모형으로 다음 실험점 선택; 탐색·활용 균형 고려.

scikit-optimize의 공식 예제는 적은 함수 평가로 탐색하는 흐름을 설명한다. 차원·잡음·평가 비용에 따라 무작위 탐색과 비교한다. 설치 상태는 별도 확인한다.
근거: [공식 문서·저자 안내](https://scikit-optimize.github.io/stable/auto_examples/bayesian-optimization.html).

## property_testing

**속성 기반 테스트 (Property-based testing)** — 다양한 입력을 생성해 불변식을 검사하고 실패 입력 축소; 정확한 속성 정의 필요.

Hypothesis로 입력 생성과 축소를 수행한다. 일부 예제가 아니라 연산의 속성을 정의하며, 잘못 정의한 속성은 정확성을 증명하지 못한다.
근거: [공식 문서·저자 안내](https://hypothesis.readthedocs.io/en/latest/).

## state_machine_testing

**상태 기반 테스트 (Stateful testing)** — 조작 순서를 생성해 상태 전이와 불변식 검사; 참조 모델·사전조건 정의 필요.

Hypothesis의 규칙 기반 상태기계를 사용할 수 있다. 단일 함수 입력 테스트와 달리 조작의 순서를 검증한다.
근거: [공식 문서·저자 안내](https://hypothesis.readthedocs.io/en/latest/stateful.html).

## delta_debugging

**델타 디버깅 (Delta debugging)** — 실패 여부를 반복 시험하며 입력·변경을 줄여 최소 재현 사례 탐색.

Zeller의 방법은 실패 판정을 반복 실행할 수 있어야 한다. 불안정한 실패는 축소를 방해하며 최소 사례가 근본 원인 설명과 동일하지는 않다.
근거: [공식 문서·저자 안내](https://www.st.cs.uni-saarland.de/dd/).

## fmea

**고장형태·영향분석 (FMEA)** — 부품·기능별 고장 형태와 상위 영향을 검토하여 예방·검출 조치 정리.

NASA FMECA 안내를 근거로 부품·기능에서 상위 영향으로 분석한다. 사고에서 원인 조합으로 내려가는 FTA와 보완 관계다.
근거: [공식 문서·저자 안내](https://standards.nasa.gov/node/12367).

## fault_tree

**결함수 분석 (Fault Tree Analysis)** — 상위 실패 사건에서 원인 조합을 AND·OR로 전개; 독립성·공통원인 가정 점검.

NASA 안내는 상위 실패에서 원인으로 내려가는 분석과 FMEA의 차이를 설명한다. 논리 구조와 확률 입력의 근거가 필요하다.
근거: [공식 문서·저자 안내](https://s3vi.ndc.nasa.gov/ssri-kb/topics/16/).

## threat_modeling

**위협 모델링 (Threat modeling)** — 자산·데이터 흐름·신뢰 경계에서 위협과 완화책 식별; 구조 변경 때 갱신.

OWASP 절차를 따라 자산과 경계를 확인한다. 공격 시뮬레이션 실행 권한과는 별개이며, 특정 프레임워크 목록만으로 위험이 모두 드러나지 않는다.
근거: [공식 문서·저자 안내](https://community.owasp.org/Threat_Modeling).

## process_mining

**프로세스 마이닝 (Process mining)** — 사례 ID·활동·시각이 있는 이벤트 로그로 실제 업무 흐름과 준수 여부 분석.

PM4Py 공식 문서와 conformance 모듈을 근거로 한다. 로그의 사건 순서·사례 식별이 필요하며 누락 로그는 잘못된 흐름을 만들 수 있다.
근거: [공식 문서·저자 안내](https://pm4py-source.readthedocs.io/en/latest/).

## value_stream_mapping

**가치흐름도 (Value Stream Mapping)** — 공정의 작업·대기·재고·재작업을 그려 낭비와 개선 지점 파악.

EPA 안내의 현재 상태→미래 상태 흐름을 따른다. 정적 관찰만으로 변동성 효과를 예측하기 어려우면 이산사건 시뮬레이션을 함께 쓴다.
근거: [공식 문서·저자 안내](https://www.epa.gov/e3/e3-value-stream-mapping-how-guide).

## card_sorting

**카드 소팅 (Card sorting)** — 사용자의 항목 묶음·명명 방식으로 정보구조 설계; 기존 탐색성 검증은 별도.

NN/g의 사용자 분류 연구 방법이다. 자연스러운 묶음을 찾는 방법과 실제 메뉴에서 항목을 찾는지 확인하는 트리 테스트를 구분한다.
근거: [공식 문서·저자 안내](https://www.nngroup.com/articles/card-sorting-definition/).

## usability_testing

**사용성 테스트 (Usability testing)** — 대표 사용자의 실제 과업 수행을 관찰해 막힘·오류 발견; 선호 설문과 구분.

대표 과업과 사용자를 정하고 관찰한다. 브라우저 자동화 검사는 실제 사람의 이해와 어려움을 대체하지 못한다.
근거: [공식 문서·저자 안내](https://www.nngroup.com/articles/usability-testing-101/).

## journey_mapping

**사용자 여정 지도 (Journey mapping)** — 목표 달성 과정의 단계·접점·행동·경험을 정리; 조사 근거로 불편 지점 확인.

NN/g의 여정 지도 구성에 근거한다. 상상으로 채운 경험은 가설로 표시하고 실제 관찰·인터뷰와 구분한다.
근거: [공식 문서·저자 안내](https://www.nngroup.com/articles/journey-mapping-101/).

## retrieval_practice

**인출 연습 (Retrieval practice)** — 답을 먼저 떠올리고 피드백으로 확인하는 학습; 단순 재독과 구분.

Anki 공식 설명의 active recall 원리다. 피드백으로 오류를 확인하며, 답을 보는 것만으로 회상에 성공했다고 기록하지 않는다.
근거: [공식 문서·저자 안내](https://docs.ankiweb.net/background.html).

## spaced_repetition

**간격 반복 (Spaced repetition)** — 기억 상태에 따라 복습 간격을 조절하여 장기 기억 유지.

Anki 같은 도구로 반복 시점을 관리할 수 있다. 장기 기억 연습과 새로운 개념 이해·문제 적용 능력을 구분한다.
근거: [공식 문서·저자 안내](https://docs.ankiweb.net/background.html).

## toulmin

**툴민 논증 모형 (Toulmin model)** — 주장·자료·논거·한정·반박을 구분해 논증의 연결과 빠진 전제 점검.

Purdue의 논증 모형 설명에 근거한다. 구조를 점검하는 방법이며 근거 사실의 진위를 대신 검증하지 않는다.
근거: [공식 문서·저자 안내](https://owl.purdue.edu/owl/general_writing/academic_writing/historical_perspectives_on_argumentation/toulmin_argument.html).

## time_series_cv

**시계열 교차검증 (Rolling-origin validation)** — 과거로 학습하고 이후 구간으로 예측 평가; 시간 순서·정보 누출 방지.

scikit-learn TimeSeriesSplit은 시점 순서를 유지한다. 지표 비교에는 관측 간격·평가 기간과 필요시 gap을 고려한다.
근거: [공식 문서·저자 안내](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

## survival_analysis

**생존분석 (Survival analysis)** — 사건이 일어날 때까지의 시간을 중도절단과 함께 분석; 관측 종료와 사건 구분.

lifelines 소개처럼 아직 사건이 발생하지 않은 관측을 단순 누락시키지 않는다. Cox 같은 특정 모형을 고르면 그 가정도 따로 확인한다.
근거: [공식 문서·저자 안내](https://lifelines.readthedocs.io/en/latest/Survival%20Analysis%20intro.html).

## rapidfuzz

**RapidFuzz** — 문자열 유사도로 철자·표기 차이가 있는 이름 후보 검색; 동일 개체 확정과 구분.

문자열 점수는 후보 탐색에 사용한다. 이름과 주소 등 여러 필드의 동일 개체 추정에는 Splink 등 레코드 연결 방법을 비교한다.
근거: [공식 문서·저자 안내](https://rapidfuzz.github.io/RapidFuzz/).

## splink

**Splink** — 공통 식별자 없는 명부를 여러 필드의 확률적 레코드 연결로 매칭.

영국 법무부의 공식 프로젝트 문서를 근거로 한다. 비교 필드·차단 규칙·오연결을 검토하고 확률을 확정 신원으로 간주하지 않는다.
근거: [공식 문서·저자 안내](https://moj-analytical-services.github.io/splink/).

## great_expectations

**Great Expectations** — 표의 결측·범위·유일성·스키마 같은 품질 규칙을 선언해 검증.

GX의 기대조건·검증 흐름을 사용한다. 데이터 정제를 수행하는 것과 정해진 품질 규칙을 검사하는 것은 다른 일이다.
근거: [공식 문서·저자 안내](https://docs.greatexpectations.io/docs/core/introduction/).

## playwright

**Playwright** — 브라우저 조작과 화면·동작 검증을 자동화; 실제 사용자 경험 평가는 별도.

공식 Python 안내를 근거로 한다. 자동화된 동작 검증과 사람이 과업을 이해하는지 확인하는 사용성 테스트를 구분한다.
근거: [공식 문서·저자 안내](https://playwright.dev/python/docs/intro).

## 서로 구별할 방법

| 과제 조건 | 우선 검토 | 다른 조건일 때 |
|---|---|---|
| 처치를 무작위 배정할 수 있음 | 무작위 대조 실험 | 이미 관찰된 자료는 DAG로 가정 검토 후 DiD·매칭 등 |
| 부품 고장에서 영향으로 올라감 | FMEA | 특정 실패에서 원인 조합을 내려가면 FTA |
| 메뉴의 자연스러운 묶음을 찾음 | 카드 소팅 | 실제 과업에서 막힘을 찾으면 사용성 테스트 |
| 입력에 대해 성립할 속성이 있음 | 속성 기반 테스트 | 조작 순서가 중요하면 상태 기반 테스트 |
| 철자 차이의 유사 후보를 찾음 | RapidFuzz | 여러 필드로 동일인을 연결하면 Splink |
| 공정의 낭비·대기를 관찰함 | 가치흐름도 | 사건·자원 변동을 모의실험하면 이산사건 시뮬레이션 |
| 여러 기준의 선호를 명시함 | MCDA | 선호 확정 전 절충 대안 집합은 파레토 최적화 |

이 대조표는 사람과 모델이 상세 원본을 읽을 때 쓰는 조건표다. 현재 키워드 선택기가 조건을 자동 추론하거나 부정문을 이해한다는 뜻이 아니다.

## source_recovered_tools

기존 `data/guides/world_tools.md`에는 있었으나 짧은 카탈로그에서 누락됐던 기본 도구를 복원했다.
2026-09-16 공식 문서로 기능을 확인했다. 설치 여부·로컬 실행 성공·속도를 측정했다는 뜻은 아니다.
아래 도구의 실행 통로는 기존 가이드 표를 따른다.

| 이름 | 맡는 연산 | 공식 근거 |
|---|---|---|
| NumPy | 다차원 배열의 벡터 연산·선형대수·수치 계산 | [공식 문서](https://numpy.org/doc/stable/user/whatisnumpy.html) |
| Matplotlib | 축·범례·여러 패널을 갖춘 정적 그래프와 출판용 도표 작성 | [공식 문서](https://matplotlib.org/stable/users/index.html) |
| Pillow | 래스터 그림의 자르기·크기 변경·합성·파일 형식 변환 | [공식 문서](https://pillow.readthedocs.io/en/stable/handbook/overview.html) |
| pdfplumber | 문자로 생성된 PDF의 글자 좌표·표 구조 추출 | [공식 문서](https://github.com/jsvine/pdfplumber) |
| PyArrow | Arrow 열 기반 메모리와 Parquet 파일 간 데이터 교환 | [공식 문서](https://arrow.apache.org/docs/python/index.html) |
| Trimesh | 삼각형 메시의 기하·부피·수밀성 분석과 가공 | [공식 문서](https://trimesh.org/) |
| Skyfield | 천체력으로 행성·별·인공위성의 위치와 좌표 계산 | [공식 문서](https://rhodesmill.org/skyfield/) |
| Qiskit | 양자 회로 구성·변환과 양자 계산 실험 설계 | [공식 문서](https://quantum.cloud.ibm.com/docs/en/guides) |
| Gmsh | 유한요소 해석을 위한 기하 모델과 계산 격자 생성 | [공식 문서](https://gmsh.info/) |
| PyVista | 3차원 메시·체적 데이터의 과학 시각화와 후처리 | [공식 문서](https://docs.pyvista.org/) |
| Cantera | 화학 반응속도·열역학·수송과 반응기 모형 계산 | [공식 문서](https://cantera.org/) |
| Lean 4 | 형식 언어로 작성한 수학 정리와 증명을 기계로 검사 | [공식 문서](https://lean-lang.org/theorem_proving_in_lean4/) |

pdfplumber는 문자로 생성된 PDF에 적합하며 스캔 OCR 엔진이 아니다. Pillow는 픽셀 가공 도구다.
Gmsh는 격자를 만들고 PyVista는 해석 결과를 시각화한다. Qiskit의 외부 실행 자원과 Skyfield의 천체력은 별도 확인한다.
Lean은 형식화된 명제·증명을 검사하므로 자연어 주장의 사실 여부를 자동 판정하는 도구로 취급하지 않는다.
