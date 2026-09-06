# D. 과학·공학·수치 계산 (조사 2026-09-06)

## 요약 (가장 강력한 5개와 이유)
1. **OR-Tools + CVXPY** — 조합/경로/스케줄(OR-Tools, 9.15 2026-01)과 볼록·비선형 모델링(CVXPY 1.9 DNLP 2026-05) 두 축이 파이썬 최적화의 사실상 표준. 둘 다 pip 휠, 맥 arm64 즉시.
2. **xarray + netCDF4 + cdsapi(ERA5)** — 기후·해양·대기 자료의 유일한 파이프(라벨 N-D 배열 + 파일규격 + 공식 다운로드 클라이언트). 날씨 어휘(`sense:weather`)가 못 하는 '과거 40년 재분석' 이 여기서 열린다.
3. **Gmsh → (CalculiX/FEniCSx/OpenFOAM) → VTK/PyVista** — 공학 시뮬 3단 파이프의 입구(메시)와 출구(후처리)는 pip 한 줄(gmsh 4.15, vtk 9.5 헤드리스 기본). 솔버만 사용자 설치.
4. **ASE + pymatgen/mp-api + LAMMPS(pip)** — 재료·원자 시뮬 표준 3종이 2026년엔 전부 pip 휠(LAMMPS 2025.7 arm64 휠 2026-04). Materials Project 는 무료 API 키.
5. **Z3(SMT) · Lean 4/Mathlib · passagemath** — 기호·증명 층. Z3 는 pip 5.1(2026-08), Lean 4.33(2026-08)+Mathlib 이 형식수학 표준(Coq→Rocq 개명), SageMath 는 passagemath 로 pip 설치 가능해짐(2025-05~).

## 표 (새 항목)
| 등급 | 리소스 | 한 줄(무엇을 하나) | 통로(pip 이름/import·brew·파일규격) | 맥 설치 난이도 | 왜 표준인가 | 어휘 후보 형태 | 근거 URL | 확인일 |
|---|---|---|---|---|---|---|---|---|
| A | JAX | 자동미분·JIT·GPU/TPU 수치 계산(NumPy 호환) | `pip:jax` · import `jax` (CPU 휠) · 맥 GPU 는 커뮤니티 PJRT `jax-mlx-plugin` | 쉬움(CPU) | 구글 계열 ML·과학 계산의 2대 프레임워크(PyTorch 와 함께) · 0.11.1 2026-08-17 | 어휘 아님 — `[self:script]` | https://pypi.org/project/jax/ | 2026-09-06 |
| A | PyMC | 베이지안 확률 프로그래밍(MCMC/NUTS·변분) 파이썬 정본 | `pip:pymc` · import `pymc` | 쉬움 | Stan 과 함께 2대 PPL · 5.27.1 2026-01-26 | 어휘 아님 — `[self:script]` | https://discourse.pymc.io/t/release-v5-26-0/17386 | 2026-09-06 |
| A | Stan (CmdStanPy) | 베이지안 모델 언어 Stan 의 파이썬 통로 | `pip:cmdstanpy` · import `cmdstanpy` · `install_cmdstan()` 이 C++ 툴체인으로 빌드 | 중(Xcode CLT 필요, 첫 빌드 수 분) | 통계학계 표준 PPL · 1.3.0 · 2.0 예고 | 어휘 아님 | https://mc-stan.org/cmdstanpy/ | 2026-09-06 |
| S | OR-Tools | 조합 최적화(CP-SAT·경로·스케줄·MIP) | `pip:ortools` · import `ortools` | 쉬움(휠 3.9~3.14, macOS arm64) | 구글 OR 표준 · 9.15.6755 2026-01-14 | 어휘 아님 — 반복되면 `[self:script]` | https://pypi.org/project/ortools/ | 2026-09-06 |
| S | CVXPY | 볼록(+1.9 비선형 DNLP) 최적화 모델링 언어 | `pip:cvxpy` · import `cvxpy` | 쉬움 | 파이썬 볼록 최적화의 유일 표준 · 1.9.2 2026-06-22 | 어휘 아님 | https://github.com/cvxpy/cvxpy/releases | 2026-09-06 |
| A | Numba | 파이썬 수치 루프 JIT(LLVM) | `pip:numba` · import `numba` | 쉬움 | NumPy 코드 가속의 표준 · 0.63 (Py3.14 지원) 2025-12-08 | 어휘 아님 | https://numba.readthedocs.io/en/stable/release/0.63.0-notes.html | 2026-09-06 |
| S | xarray (+netCDF4) | 라벨 붙은 N-D 배열·NetCDF/Zarr 읽기·기후 자료 표준 | `pip:xarray` `pip:netCDF4` · import `xarray`, `netCDF4` · 규격 `.nc`(NetCDF4/HDF5) | 쉬움 | 기후·해양·대기·위성 자료의 유일 파이썬 표준 · 2026.7.0 2026-07-09 | 어휘 아님(자료는 cdsapi 와 짝) | https://pypi.org/project/xarray/ | 2026-09-06 |
| A | Dask | 메모리 초과 배열·표 병렬(xarray/pandas 확장) | `pip:dask[complete]` · import `dask` | 쉬움 | PyData 병렬 표준 · 2026.8.0 2026-08-24 | 어휘 아님 | https://pypi.org/project/dask/ | 2026-09-06 |
| S | cdsapi (Copernicus CDS, ERA5) | ERA5 재분석 등 기후 자료 공식 다운로드 클라이언트 | `pip:cdsapi` · import `cdsapi` · `~/.cdsapirc` 키(무료 계정) · 후계 `ecmwf-datastores-client`(이전 요구 없음) | 쉬움 | 기후 자료 접근의 유일 공식 통로 · 0.7.7 2025-09-30 · ERA5 신규 시계열 2026-08 | **`[sense:climate]` 후보**(도시·기간→변수 items; 반복 흐름) | https://cds.climate.copernicus.eu/how-to-api | 2026-09-06 |
| S | Gmsh | 3D 유한요소 메시 생성기(.geo/.msh 규격) | `pip:gmsh` · import `gmsh` · 규격 `.msh` | 쉬움(macosx_12_0_arm64 휠) | 오픈 FEM 메시의 사실상 표준 · 4.15.2 2026-03-24 | 어휘 아님 | https://pypi.org/project/gmsh/ | 2026-09-06 |
| S | VTK / PyVista | 과학 3D 시각화·메시 후처리(.vtk/.vtu 규격) | `pip:vtk` `pip:pyvista` · import `vtk`, `pyvista` · VTK 9.5 부터 헤드리스 오프스크린 기본 | 쉬움 | ParaView 의 코어 · 과학 시각화 규격 자체 | 어휘 아님 — 산출 PNG 는 `[engines:render]` 로 지각 | https://docs.pyvista.org/getting-started/installation.html | 2026-09-06 |
| A | ParaView (pvpython) | 대규모 CFD/FEM 결과 배치 후처리 | 🔧 `brew install --cask paraview` → `pvpython script.py` (윈도우: installer) | 쉬움(캐스크) | CFD/FEM 후처리 표준 · 6.0.1 2025-09 | 어휘 아님 | https://en.wikipedia.org/wiki/ParaView | 2026-09-06 |
| A | CalculiX (ccx) | Abaqus 입력 호환 구조 FEM 솔버 | 🔧 `brew install calculix-ccx`(비공식 탭·소스빌드 가능성) · 규격 `.inp` · FreeCAD FEM 워크벤치가 이걸 부름 | 중~어려움(맥 공식 바이너리 없음) | 오픈 구조 FEM 의 실무 표준(FreeCAD 내장) · 2.23 2025-10-19 | 어휘 아님 | https://en.wikipedia.org/wiki/Calculix | 2026-09-06 |
| A | Elmer FEM | 다물리(열·전자기·유체) FEM | 🔧 소스빌드/도커(CSC, 연 1회 릴리스) · 윈도우: installer | 어려움 | 다물리 오픈 FEM 대표 | 어휘 아님 | https://sourceforge.net/projects/elmerfem/ | 2026-09-06 |
| A | OpenModelica (OMPython) | Modelica 언어 시스템 시뮬(제어·에너지·기계 동역학) | `pip:OMPython` · import `OMPython` · 🔧 `omc` 바이너리 필요(맥은 도커/소스 권장) | 어려움(맥 공식 빌드 불안정) | Modelica 표준의 유일 오픈 구현 · OMPython 4.0.1 2026-04-15 | 어휘 아님 | https://github.com/OpenModelica/OMPython/releases | 2026-09-06 |
| S | Cantera | 화학 반응속도·열역학·연소 1D 화염·반응기 | `pip:cantera` · import `cantera` · 규격 `.yaml` 메커니즘 | 쉬움(휠) | 연소·반응공학의 유일 오픈 표준 · 3.2.0 2025-11-17 | 어휘 아님 | https://cantera.org/ | 2026-09-06 |
| S | KiCad (kicad-cli) | 회로도/PCB 헤드리스 내보내기(거버·BOM·ERC/DRC·PDF/SVG) | 🔧 `brew install --cask kicad` → `kicad-cli pcb export gerbers x.kicad_pcb` · 규격 `.kicad_sch/.kicad_pcb` | 쉬움(캐스크) | 오픈 EDA 유일 표준 · 9.0 CLI 6 서브커맨드 | 어휘 아님 | https://docs.kicad.org/9.0/en/cli/cli.html | 2026-09-06 |
| S | ngspice | SPICE 회로 시뮬 배치(`ngspice -b`) | 🔧 `brew install ngspice`(공유 라이브러리 포함) · 규격 `.cir/.sp` · 파이썬 래퍼 `pip:PySpice`(정체 의심 — 표 하단 참조) | 쉬움 | 오픈 SPICE 표준(KiCad 내장) · 47 2026-08-11 | 어휘 아님 | https://ngspice.sourceforge.io/news.html | 2026-09-06 |
| A | CadQuery | 코드 CAD(OCCT 커널, STEP/STL 출력) | `pip:cadquery` · import `cadquery` (`cadquery-ocp` macosx_11_0_arm64 휠) | 쉬움~중 | 코드 CAD 2대 표준 · 2.8.0 2026-06-21 | 어휘 아님 | https://pypi.org/project/cadquery/ | 2026-09-06 |
| A | build123d | CadQuery 후계형 코드 CAD(파이썬다운 API, 상호 변환) | `pip:build123d` · import `build123d` | 쉬움~중 | 2025~26 코드 CAD 의 상승 표준 · 0.11.1 2026-07-02 | 어휘 아님(OpenSCAD 와 병기) | https://pypi.org/project/build123d/ | 2026-09-06 |
| S | LAMMPS | 고전 분자동역학(재료·고분자) | `pip:lammps` · import `lammps` (2025.7.22.4.0, macosx_11_0_arm64 휠 74MB) · 규격 `in.*`/`data` | 쉬움(휠) | 재료 MD 표준 · 휠 2026-04-19 | 어휘 아님 | https://pypi.org/project/lammps/ | 2026-09-06 |
| S | GROMACS | 생체분자 분자동역학 | 🔧 `brew install gromacs` → `gmx` CLI · 파이썬 `gmxapi` 는 소스빌드 | 중(brew 로 CLI 는 쉬움, gmxapi 어려움) | 생체 MD 표준 · 2026.3 | 어휘 아님 | https://manual.gromacs.org/current/gmxapi/userguide/install.html | 2026-09-06 |
| S | ASE | 원자 구조 조작·계산기(DFT/MD 코드) 통합 프론트 | `pip:ase` · import `ase` (순수 파이썬) | 쉬움 | 원자 시뮬 파이썬 공용어 · 3.29.0 2026-06-21 | 어휘 아님 | https://pypi.org/project/ase/ | 2026-09-06 |
| S | pymatgen + Materials Project API | 결정 구조 분석·상도(phase diagram)·MP 데이터베이스 질의 | `pip:pymatgen` `pip:mp-api` · import `pymatgen`, `mp_api.client` · 무료 API 키 | 쉬움(휠) | 재료정보학 표준 · pymatgen 2026.4.16 · MP DB 대개편 2026-06-08 | **`[sense:material]` 후보**(화학식→구조·밴드갭 items) | https://docs.materialsproject.org/changes/database-versions | 2026-09-06 |
| A | PySCF (Psi4 대체) | 양자화학(DFT/CC) 파이썬 모듈 | `pip:pyscf` · import `pyscf` (macosx_11_0_arm64 휠) · Psi4 1.11(2026-06-29) 는 conda 전용 | 쉬움(PySCF) / 중(Psi4 conda) | pip 가능한 양자화학 표준 · 2.14.0 2026-07-18 | 어휘 아님 | https://pypi.org/project/pyscf/ | 2026-09-06 |
| S | RCSB PDB API (+UniProt REST) | 단백질 구조 검색·데이터·서열/기능 조회 | `pip:rcsb-api` · import `rcsbapi` · UniProt 는 순수 REST(`rest.uniprot.org`) · 규격 `.pdb/.cif` | 쉬움 | 구조생물학의 유일 정본 DB · JMB 2025 논문 | **`[sense:protein]` 후보**(이름/서열→PDB ID·구조 items) | https://rcsbapi.readthedocs.io/en/latest/ | 2026-09-06 |
| B | SunPy | 태양물리 자료(SDO 등) 조회·좌표 | `pip:sunpy[all]` · import `sunpy` | 쉬움 | 태양물리 표준(Astropy 계열) · 7.1 · 연 2회 릴리스 | 어휘 아님 | https://docs.sunpy.org/en/stable/whatsnew/index.html | 2026-09-06 |
| A | healpy (HEALPix) | 전천(全天) 픽셀화·CMB/전천 지도 규격 | `pip:healpy` · import `healpy` · 규격 HEALPix FITS | 중(arm64 휠 여부 문서 불일치 — 소스빌드 대비) | 우주론 전천 지도 유일 규격 | 어휘 아님 | https://healpy.readthedocs.io/en/latest/install.html | 2026-09-06 |
| S | H3 | 육각 계층 지리 색인(Uber) | `pip:h3` · import `h3` (v4, h3lib 4.3) | 쉬움 | 지리 집계 그리드 표준 | 어휘 아님 — `[table:compute]` 파생열로 | https://uber.github.io/h3-py/_changelog.html | 2026-09-06 |
| A | QGIS (qgis_process) | GIS 처리 알고리즘 헤드리스 실행·PyQGIS | 🔧 `brew install --cask qgis` → `qgis_process run <alg>` (윈도우: OSGeo4W) | 쉬움(캐스크, 무거움) | 데스크톱 GIS 유일 오픈 표준 · 4.0 Norrköping 2026-03-06(Qt6) · LTR 4.2 2026-10 | 어휘 아님(GeoPandas 가 먼저) | https://blog.qgis.org/2026/03/09/qgis-4-0-norrkoping-is-released/ | 2026-09-06 |
| B | PostGIS | 공간 DB(다중 사용자) | 🔧 `brew install postgis` · 개인 몸은 DuckDB `spatial` 확장으로 족함 | 쉬움 | 공간 DB 표준 | 어휘 아님 | https://postgis.net/ | 2026-09-06 |
| B | chDB | 임베디드 ClickHouse(서버 없는 OLAP, 60+ 포맷) | `pip:chdb` · import `chdb` | 쉬움(휠) | DuckDB 의 대체 후보 · 4.2 2026-07 | 어휘 아님(DuckDB 가 먼저) | https://pypi.org/project/chdb/ | 2026-09-06 |
| A | passagemath (SageMath pip) | 정수론·대수·조합론 등 Sage 전체를 pip 로 | `pip:passagemath-standard` · import `sage.all` (Py3.11~3.14) | 중(휠 다수, 크기 큼) | SageMath 의 pip 가능 호환 포크 · 10.8.x 2026 | 어휘 아님(SymPy 가 먼저) | https://github.com/passagemath/passagemath | 2026-09-06 |
| A(유료) | Wolfram Engine | Mathematica 커널(기호·수치·지식) | 🔧 `brew install --cask wolfram-engine` + `pip:wolframclient` · 개발자용 무료 라이선스(비생산용), 정식은 유료 | 쉬움(계정 필요) | 기호계산 상용 표준 · 14.3 2025-08 | 어휘 아님 | https://www.wolfram.com/engine/faq/ | 2026-09-06 |
| S | Lean 4 + Mathlib | 정리 증명 보조(형식수학 2026 표준) | 🔧 `brew install elan-init` → `lake` · pip 아님(`pip:lean-dojo` 등은 도구) · Coq 는 Rocq 로 개명(9.2 2026-03) | 중 | 2026 형식수학·AI 증명의 사실상 표준 · Lean 4.33.1 2026-08-21 | 어휘 아님 | https://en.wikipedia.org/wiki/Lean_(proof_assistant) | 2026-09-06 |
| S | Z3 | SMT 솔버(제약·검증·퍼즐) | `pip:z3-solver` · import `z3` | 쉬움(휠) | SMT 유일 표준 · 5.1.0.0 2026-08-16 | 어휘 아님 | https://pypi.org/project/z3-solver/ | 2026-09-06 |
| A | PennyLane | 양자 미분 프로그래밍(QML) | `pip:pennylane` · import `pennylane` | 쉬움 | Qiskit/Cirq 다음 3위, QML 은 1위 · 0.45.1 2026-06-26 | 어휘 아님 | https://pypi.org/project/pennylane/ | 2026-09-06 |
| A | igraph | 대규모 그래프 알고리즘(C 코어, NetworkX 보다 빠름) | `pip:igraph` · import `igraph` (구 `python-igraph` 개명) | 쉬움(휠) | 그래프 2대 표준 · 1.0 2026 | 어휘 아님 | https://igraph.org/news.html | 2026-09-06 |
| S | Graphviz | 그래프 자동 배치(dot 규격→SVG/PNG) | 🔧 `brew install graphviz` + `pip:graphviz` · import `graphviz` · 규격 `.dot` | 쉬움 | 다이어그램 규격 자체 · 16.0.0 2026-08-14 | 어휘 아님 — 산출은 `[engines:render]` | https://en.wikipedia.org/wiki/Graphviz | 2026-09-06 |
| A | Altair (+vl-convert) | 선언형 통계 차트(Vega-Lite) | `pip:altair` `pip:vl-convert-python` · import `altair` | 쉬움 | 선언형 시각화 표준 · 6.2.2 | 어휘 아님(`[table:chart]` 가 먼저) | https://altair-viz.github.io/releases/changes.html | 2026-09-06 |
| B | Bokeh | 대화형 웹 차트·스트리밍 | `pip:bokeh` · import `bokeh` | 쉬움 | Plotly 대체 · 3.10.0 2026-08-18 | 어휘 아님 | https://pypi.org/project/bokeh/ | 2026-09-06 |
| S | Manim (Community) | 수학 설명 애니메이션(3Blue1Brown 계열) | `pip:manim` · import `manim` · 🔧 ffmpeg(+LaTeX 텍스트 시) | 쉬움~중 | 수학 애니메이션 유일 표준 · 0.21 2026-08-10 | 어휘 아님 — 강의 데크 나레이션과 짝 | https://pypi.org/project/manim/ | 2026-09-06 |
| S | Quarto | 과학·기술 출판(md/ipynb→HTML/PDF/docx/reveal) | 🔧 `brew install --cask quarto` → `quarto render` (윈도우: installer) | 쉬움 | R/Python 재현 출판 표준 · 1.8 2026-02-11 · 2.0(Rust) 2026 말 예고 | 어휘 아님(`[table:document]` 가 먼저) | https://quarto.org/docs/prerelease/1.8/ | 2026-09-06 |
| A | marimo | 반응형 파이썬 노트북(.py 저장·앱 배포) | `pip:marimo` · import `marimo` · `marimo run x.py` | 쉬움 | 2026 Jupyter 도전자(20K★, 재현성) | 어휘 아님 | https://docs.marimo.io/faq/ | 2026-09-06 |
| A | scikit-image | 과학 이미지 처리(분할·측정·필터, OpenCV 보다 연구용) | `pip:scikit-image` · import `skimage` | 쉬움 | 연구 영상처리 표준 | 어휘 아님 | https://pypi.org/project/scikit-image/ | 2026-09-06 |
| B | MDAnalysis · OpenMM | MD 궤적 분석 / GPU 생체 MD 엔진(파이썬 우선) | `pip:MDAnalysis`(import `MDAnalysis`) · `pip:openmm` | 쉬움 | GROMACS 짝(분석)·파이썬 MD 표준 | 어휘 아님 | https://pypi.org/project/MDAnalysis/ | 2026-09-06 |
| B | Snakemake | 생명정보 워크플로우(재현 파이프라인) | `pip:snakemake` · CLI | 쉬움 | 바이오 파이프라인 표준(Nextflow 와 2강) | 어휘 아님 — 몸엔 `[self:workflow]` 있음 | https://pypi.org/project/snakemake/ | 2026-09-06 |
| — | Julia · R/tidyverse | 다른 언어 — Julia 1.12.7(2026-08-15, 1.13 rc) 과학계산 / R 4.6.1(2026-06-24) 통계 | 🔧 `brew install julia` / `brew install --cask r` · 파이썬 브리지 `pip:juliacall`, `pip:rpy2` | 쉬움 | 통계·수치 분야의 병행 언어 | 어휘 아님 | https://stat.ethz.ch/pipermail/r-announce/2026/000722.html | 2026-09-06 |

## 초안 지도 검증 (world_tools.md 항목별 — 틀린 것만)
- **FEniCS** "conda/도커 전용" → 현 이름 **FEniCSx(dolfinx) 0.11 (2026-06)**, 맥 권장 = conda(`fenics-dolfinx`), pip 은 C++ 코어 선빌드 후에만. 통로 표기는 맞고 이름만 정정.
- **OpenFOAM** "도커 이미지" → 맥 arm64 는 **`brew install --no-quarantine gerlero/openfoam/openfoam`** (v2506, v2606 앱) 이 사실상 표준 통로. 도커는 차선.
- **Open Babel** `pip:openbabel-wheel` → arm64 휠은 **Py3.8~3.13, macOS≥13** 까지만 확인(3.14 미확인). brew 통로가 안전.
- **Blender** "bpy 파이썬 제약 큼" → 맞음. 현 Blender 5.2(2026-07-14), bpy 휠은 LTS 밖 버전이 PyPI 에서 삭제되고 download.blender.org/pypi 로 이동 — 바이너리 헤드리스 권고 유지.
- **Jupyter** 비고 → **marimo** 를 병기할 것(표 참조).
- **Qiskit/Cirq/NetworkX/Astropy/Skyfield/GeoPandas/Rasterio/GDAL/RDKit/Biopython/Polars/DuckDB/SymPy/statsmodels(0.15.0 2026-08-27)/sklearn/Plotly** — 모두 살아 있음, 통로 그대로. 등급 메모: NetworkX 는 A(대규모는 igraph), Plotly 정적 PNG 는 kaleido 유지.
- **PostgreSQL** 행 → 공간이면 PostGIS(표 B) 지만 개인 몸은 **DuckDB `spatial` 확장** 한 줄이 먼저 — 비고에 추가 권고.
- **PySpice** (초안엔 없음, 회로 절 추가 시) → PyPI 마지막 릴리스 2021 이후 정체 의심. ngspice 자체는 활발(47). 배치는 `ngspice -b` CLI 로.

## 겹침 메모 (기존 어휘와 겹쳐 뺀 것)
- **pyproj/shapely** — GeoPandas 행이 이미 동반 표기. **PyArrow/Parquet** — 초안 데이터 절에 있음. **NumPy/SciPy/SymPy/statsmodels/sklearn/Pandas/Polars/DuckDB** — 초안 그대로.
- **SQLite 확장(sqlite-vec·spatialite)** — 몸이 이미 `[sense:sqlite]`·해마 vec0 로 쓰는 중, 지도 항목 아님.
- **날씨(현재·예보)** — `[sense:weather]` 가 있음. cdsapi 는 '재분석·과거 기후' 라 겹치지 않음(표 유지).
- **논문 검색** — `[sense:paper]`. **Wikidata** — `[sense:entity]`. 재료·단백질 DB 는 이들과 다른 정본이라 후보로 남김.
- **Jupyter** — 초안에 있음, 검증만. **Typst/LaTeX** — 초안에 있음; Quarto 는 그 위층이라 별도 행.
- **워크플로우 엔진(Snakemake)** — `[self:workflow]`·`[self:script]` 가 몸의 결정화 통로라 B 로 격하.

## 죽었거나 후계로 대체된 것
- **Coq → Rocq Prover** (9.0 2025-03-12 개명 완료, 9.2 2026-03-30). 이름으로 찾으면 못 찾는다.
- **python-igraph → igraph** (PyPI 이름 개명, 1.0).
- **PySpice** — 릴리스 정체(2021~), ngspice CLI 직접 호출 또는 `spicelib` 계열로.
- **healpy 문서의 "Apple Silicon 바이너리 없음"** — 옛 판(1.16) 문구가 최신 문서에 잔류. 실제 휠 여부는 설치로 확인 필요.
- **cdsapi** — 후계 `ecmwf-datastores-client` 가 나왔으나 공식적으로 "이전 요구 안 함". 당분간 cdsapi 유지.
- **Blender bpy(LTS 밖 판)** — PyPI 에서 삭제, 아카이브 URL 로만.
- **applejax / jax-metal 계열** — 애플 공식 Metal 플러그인 정체, 커뮤니티 `jax-mlx-plugin`(2026-03) 으로 교체.
- **Quarto 1.x** — 2.0(Rust 재작성) 2026 말 예고, 호환 약속. 지도엔 1.8 기준.
- **pystan** — Stan 파이썬 통로는 CmdStanPy 로 이동(pystan 은 사실상 유지 중단).
