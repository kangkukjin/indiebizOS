# 세상의 도구 지도 (World Tools Map)

몸 밖에 있는 우수한 도구(파이썬 라이브러리·프로그램·웹 라이브러리)의 **목차**다. 어휘(IBL 액션)는 몸의 능력이고,
이 지도는 세상의 능력이다. 모델은 아는 것이 아니라 **보이는 것**으로 행동하므로, 지도가 없으면 다 알면서도
표준 라이브러리로 30줄을 새로 짠다. 지도가 있으면 후보에 오르고, 없는 것은 **승인을 받아** 깐다.

★**자동 설치는 없다.** pip 설치는 `[self:install_lib]` 의 사람 승인 게이트를 거치고, 프로그램(바이너리)은 사용자가
직접 깐다. 승인은 조종실 **도구 관리 창의 '라이브러리 설치 승인'** 에서 사용자가 누른다 — AI 가 대신 누를 수 없고
셸(curl 등)로 우회하지 않는다.

## 0. 언제 여는가

- 계산·시뮬레이션·변환·렌더를 **표준 라이브러리로 새로 짜려는 순간** — 먼저 아래 표에 그 일을 잘하는 도구가 있는지 본다.
- 전문 포맷이 보일 때: 분자(SMILES/SDF)·천체 좌표·행렬/미분방정식·메시(STL/OBJ)·래스터/벡터 지리·회로·LaTeX.
- 사용자가 도구 이름을 직접 말했을 때(예: "블렌더로", "듀크DB로") — 표에서 통로를 찾는다.

## 1. 확인 → 승인 → 사용 (골격)

```
[self:install_lib]{package: "<pip 이름>", check: true}           # 확인만 — 등록·설치 없음. installed / pending / approved / missing
[self:install_lib]{package: "<pip 이름>", reason: "<이 일에 왜>"}   # missing 이면 승인 요청 → approval_required (알림 발송)
# 사용자가 도구 관리 창에서 승인 → 같은 호출을 다시 → 설치 → 곧바로 import 가능(재기동 불요)
[self:write]{path: "/tmp/<일>.py", content: "<import 후 계산>"} ; run_command("python3 /tmp/<일>.py")
```

- `check: true` 는 **부작용 0** — 후보를 고를 때 여러 개 물어도 된다. 이미 있으면 승인 없이 `installed` 로 답한다.
- 승인 대기 중이면 그 작업은 **다른 방법으로 이어가거나 정직하게 멈춘다**. 재촉하지 말고, 사용자에게 *왜 필요한지 한 줄* 을 남긴다.
- pip 이름은 **이 지도의 것을 그대로** 쓴다(typosquat 방어 — 비슷한 이름을 지어내지 말 것).
- 바이너리(🔧)는 `run_command("which <명령>")` 으로 확인하고, 없으면 사용자에게 설치 명령을 **안내만** 한다.
- 웹 라이브러리(🌐)는 설치가 아니다 — 앱/HTML 에 `<script src="CDN">` 한 줄.

## 2. 지도 — 무엇을 잘하나 · 통로

통로 표기: `pip:이름` = `[self:install_lib]` 승인 경로 · 🔧 = 사용자가 직접 설치하는 프로그램 · 🌐 = 브라우저 CDN.
**"있음"은 이 지도에 적지 않는다** — 몸마다 다르니 `check: true` 가 정본이다.

### 수치·기호·통계
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| NumPy | 배열·선형대수·FFT | `pip:numpy` | 코어 요구사항 |
| SciPy | 최적화·적분·ODE·신호·희소행렬·통계검정 | `pip:scipy` | |
| SymPy | 기호 미적분·방정식 풀이·LaTeX 출력 | `pip:sympy` | 수식 정확 답이 필요할 때 |
| statsmodels | 회귀·시계열(ARIMA)·가설검정 표 | `pip:statsmodels` | |
| scikit-learn | 분류·회귀·군집·차원축소 | `pip:scikit-learn` | import 이름 `sklearn` |

### 데이터·DB
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| Pandas | 표 가공·CSV/Excel·시계열 | `pip:pandas` | 작은 표는 `[table:*]` 변환자가 먼저 |
| Polars | 큰 표(수백만 행) 빠른 가공·lazy | `pip:polars` | Pandas 보다 5~10배 |
| DuckDB | 파일(CSV/Parquet) 위 SQL 분석, 메모리 내 OLAP | `pip:duckdb` | 서버 없음 · `[sense:sqlite]` 는 원장용 |
| SQLite | 내장 | (표준) | 몸의 원장(.db) 읽기는 `[sense:sqlite]` 낱말 |
| PostgreSQL | 다중 사용자·동시성 DB | 🔧 `brew install postgresql@16` + `pip:psycopg[binary]` | 개인 몸에선 DuckDB/SQLite 로 족함 · 공간 질의도 DuckDB `spatial` 확장이 PostGIS 보다 먼저 |
| PyArrow | Parquet·Arrow 교환 | `pip:pyarrow` | |

### 시각화·이미지
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| Matplotlib | 정적 그림 전반 | `pip:matplotlib` | `[table:chart]` 가 먼저 |
| Seaborn | 통계 그림(분포·상관·히트맵) 한 줄 | `pip:seaborn` | |
| Plotly | 대화형 HTML 그림·3D 산점 | `pip:plotly` | 정적 PNG 는 `pip:kaleido` |
| Pillow | 이미지 열기·자르기·합성·EXIF | `pip:pillow` | import `PIL` |
| OpenCV | 영상 처리·특징점·카메라·도형 검출 | `pip:opencv-python` | import `cv2` · 얼굴 등은 무거움 |
| ffmpeg | 영상/음성 변환·자르기·합치기 | 🔧 `brew install ffmpeg` | moviepy 가 이걸 부른다 |

### 3D·CAD·게임 엔진
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| Blender (bpy) | 모델링·렌더·애니메이션 스크립팅 | 🔧 `brew install --cask blender` → `blender -b -P <스크립트.py>` | `pip:bpy` 는 파이썬 버전 제약 큼 — 바이너리 헤드리스가 안전 |
| trimesh | STL/OBJ 로드·부피·교차·단순 메시 연산 | `pip:trimesh` | 가벼운 메시 계산은 이걸로 |
| OpenSCAD | 코드→CAD(파라메트릭 부품) | 🔧 `brew install --cask openscad` → `openscad -o out.stl in.scad` | |
| FreeCAD | GUI CAD·STEP 변환 | 🔧 `brew install --cask freecad` | 스크립팅은 내장 파이썬 |
| Three.js / Babylon.js | 브라우저 3D 표시 | 🌐 CDN | 앱(`[engines:*]`/웹앱) 에 넣는다 |
| WebGPU | 브라우저 GPU 계산·렌더 | 🌐 (브라우저 API) | 설치 없음 |

### 물리·공학 시뮬레이션
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| PyBullet | 강체 물리·로봇 시뮬 | `pip:pybullet` | |
| MuJoCo | 정밀 다관절 물리(로봇·생체) | `pip:mujoco` | |
| FEniCSx (dolfinx 0.11) | 유한요소(PDE) | 🔧 conda `fenics-dolfinx` | pip 은 C++ 코어 선빌드 후에만 · 구 이름 FEniCS |
| deal.II | C++ 유한요소 | 🔧 소스 빌드 | 파이썬 몸에선 비추천 |
| OpenFOAM | CFD(유체) | 🔧 `brew install --no-quarantine gerlero/openfoam/openfoam` (차선 도커) | 대규모 · 사용자 몫 · 메시=`pip:gmsh`, 후처리=`pip:pyvista` |

### 화학·생명
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| RDKit | SMILES 파싱·분자 그림·물성·유사도 | `pip:rdkit` | |
| Open Babel | 분자 포맷 상호변환 | 🔧 `brew install open-babel` (또는 `pip:openbabel-wheel`, py≤3.13 휠) | |
| Biopython | 서열·PDB | `pip:biopython` | |

### 천문·지구·지리
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| Astropy | 천체 좌표·단위·FITS·시간계 | `pip:astropy` | |
| Skyfield | 행성·위성 위치, 일출·월령 계산 | `pip:skyfield` | 첫 실행에 천체력 파일 다운로드 |
| GeoPandas | 벡터 지리(shapefile/GeoJSON) 공간 연산 | `pip:geopandas` | shapely·pyproj 동반 |
| Rasterio | 래스터(GeoTIFF) 읽기·재투영 | `pip:rasterio` | GDAL 휠 동반 — 빌드 실패 시 🔧 `brew install gdal` |
| GDAL | 지리 포맷 만능 변환기 | 🔧 `brew install gdal` | 파이썬 바인딩 import `osgeo` |
| folium | 지도 HTML | `pip:folium` | 몸의 `[sense:place]`·지도 앱이 먼저 |

### 양자·그래프·네트워크
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| Qiskit | 양자 회로 작성·시뮬레이션 | `pip:qiskit` | 시뮬레이터 `pip:qiskit-aer` |
| Cirq | 양자 회로(구글 계열) | `pip:cirq` | |
| NetworkX | 그래프 알고리즘(최단·중심성·커뮤니티) | `pip:networkx` | |

### 문서·조판·노트북
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| Typst | 조판 PDF(가볍고 빠름) | `[table:document]{format: "typst"}` 낱말 | LaTeX 보다 먼저 |
| LaTeX | 논문·수식 조판 | 🔧 `brew install --cask basictex` (`pdflatex`) | 무거움(수 GB) |
| MathJax / KaTeX | 웹 수식 렌더 | 🌐 CDN | |
| Jupyter / marimo | 대화형 노트북 / 반응형 .py 노트북 | `pip:jupyterlab` · `pip:marimo` | 몸 안에선 `[self:script]`·run_command 로 족함 |
| pypdf / pdfplumber | PDF 텍스트·표 추출 | `pip:pypdf` · `pip:pdfplumber` | `[self:read]` 가 PDF 를 읽으면 그게 먼저 |

### 조사로 확인된 추가 표준 (2026-09-06, 상세·근거=`docs/world_map/D_science_engineering.md`)
| 도구 | 잘하는 일 | 통로 | 비고 |
|---|---|---|---|
| OR-Tools / CVXPY | 조합·경로·스케줄 최적화 / 볼록·비선형 모델링 | `pip:ortools` · `pip:cvxpy` | 파이썬 최적화 2대 표준 |
| xarray + netCDF4 · cdsapi | 라벨 N-D 배열·기후 자료(.nc) · ERA5 재분석 다운로드 | `pip:xarray netCDF4` · `pip:cdsapi`(무료 계정 키) | `[sense:weather]` 는 예보, 이건 과거 40년 |
| Gmsh · VTK/PyVista | FEM 메시 생성 · 과학 3D 후처리 | `pip:gmsh` · `pip:pyvista` | 시뮬 파이프의 입구·출구 |
| Cantera · KiCad `kicad-cli` · ngspice | 연소·반응 / 회로도·PCB 내보내기 / SPICE 배치 | `pip:cantera` · 🔧 `brew install --cask kicad` · 🔧 `brew install ngspice` | PySpice 는 정체 — ngspice -b 직접 |
| CadQuery / build123d | 코드 CAD(STEP/STL) | `pip:cadquery` · `pip:build123d` | OpenSCAD 의 파이썬 짝 |
| LAMMPS · ASE · pymatgen | 분자동역학 · 원자 구조 공용어 · 결정 분석(Materials Project API) | `pip:lammps` · `pip:ase` · `pip:pymatgen mp-api` | 전부 arm64 휠 |
| Z3 · Lean 4 | SMT 솔버 · 정리 증명(Coq→Rocq 개명) | `pip:z3-solver` · 🔧 `brew install elan-init` | |
| H3 · Graphviz · Manim · Quarto | 육각 지리 색인 · 그래프 배치(.dot) · 수학 애니메이션 · 과학 출판 | `pip:h3` · 🔧 `brew install graphviz`+`pip:graphviz` · `pip:manim` · 🔧 `brew install --cask quarto` | |
| Kiwi (kiwipiepy) | 한국어 형태소·품사·문장 분리 | `pip:kiwipiepy` | Java 불요 — KoNLPy 대체 현 표준 |

**연결(API·프로토콜·플랫폼)의 지도는 아직 이 문서에 없다** — 1차 조사 결과는 `docs/WORLD_MAP_CANDIDATES_2026-09-06.md`(1층 12개 구멍·2층 어휘 후보·쓰지 말 것). 형태는 사용자 판정 대기.

## 3. 지도 갱신 규약 — AI 가 쓰고 사람이 고친다

- 지도에 없는 도구로 **성공**했으면 그 자리에서 표에 한 줄 더한다: `[self:edit]{path: "data/guides/world_tools.md", ...}` — 도구·잘하는 일·통로·비고.
- 통로가 **틀렸음**(pip 빌드 실패·이름 변경·바이너리 필요)을 알았으면 비고를 고친다. 지우지 않고 사실을 적는다.
- 몸에 있음/없음은 적지 않는다(§2 첫 줄). 예산 36KB — 넘치면 드문 부류부터 압축.
