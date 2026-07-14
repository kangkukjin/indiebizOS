# 공개파일 (Public Files)

선택한 폴더를 외부 공개 사이트(Cloudflare)로 **라이브 서빙**하는 노출 층. 개인용 NAS 와
달리 **보여줄 것만 고른 창**이다. **인덱싱이 없다** — 맥이 요청 시 그 디렉토리를 즉석에서
훑고 썸네일을 그 자리에서 생성하므로, 파일을 옮기거나 지우면 다음 조회에 즉시 반영된다.

## 어휘

```
[others:showcase]{op: "status"}                              # 추가한 폴더 + 각 폴더가 담긴 주소
[others:showcase]{op: "add", path: "/Users/.../여행", mode: "media"}   # 폴더 추가(공개는 바스켓에서)
[others:showcase]{op: "remove", path: "/Users/.../여행"}     # 폴더 제거(모든 주소에서)
[others:showcase]{op: "config", strip_exif: true, transcode_video: true}   # 전역 설정
```

- `mode`: `media`(사진·동영상 그리드) / `files`(파일 전체).
- 폴더 추가만으론 **비공개** — '바스켓'(주소)에 담아야 공개. 담는 즉시 라이브.
- EXIF/GPS 는 원본 서빙 시 기본 제거. 동영상은 브라우저 비재생 컨테이너면 H.264 변환.

## 바스켓 = 공개 주소 (bare 루트는 잠금)

**모든 갤러리는 바스켓 하나 = 주소 하나**(`<base>/s/<slug>`). `slug` 는 5자 대문자
코드(A-Z). **bare 루트(`<base>/`)는 항상 잠겨** 콘텐츠가 전혀 없다 — 어떤 주소의 코드를
지워도(=bare 루트) 아무것도 안 보인다. 널리 공유하면 공개 갤러리, 아는 사람만 주면 비밀.

```
[others:showcase]{op: "basket_list"}                                  # 주소 목록
[others:showcase]{op: "basket_save", title: "가족에게"}                # 생성(5자 코드 발급)
[others:showcase]{op: "basket_save", title: "전체 공개", all_folders: true}  # 전체 폴더 자동 포함
[others:showcase]{op: "basket_save", basket_id: "bsk_…", title: "새 이름"}   # 개명
[others:showcase]{op: "basket_detail", basket_id: "bsk_…"}            # 담긴 폴더 + 담기/빼기
[others:showcase]{op: "basket_toggle", basket_id: "bsk_…", folder_id: "fld_…"}  # 담기/빼기
[others:showcase]{op: "basket_delete", basket_id: "bsk_…"}            # 주소 삭제(폴더 보존)
```

- **전체 공개 갤러리** = `all_folders: true` 바스켓. 모든 폴더 자동 포함, 폴더 추가 시 자동
  반영. 이것도 자기 slug 주소를 가져 bare 루트엔 안 뜬다.
- 폴더가 어느 주소에 담기느냐가 곧 보안 경계. 담기/빼기는 즉시 반영(동기화 없음).

## 아키텍처 (라이브 서빙)

```
맥 (superstructure, api_showcase.py)          Cloudflare (substrate = 멍청한 프록시 + 캐시)
────────────────────────────────             ──────────────────────────────────────────
[others:showcase] handler                     Worker (worker.js)
  상태(폴더·바스켓)만 관리                        /s/<slug>/list?path=  → 맥에 프록시(캐시 안 함=항상 최신)
  showcase_state.json                          /s/<slug>/thumb/<fid>?rel=&v= → R2 캐시 or 맥 생성
                                               /s/<slug>/media/<fid>?rel=&v= → R2 캐시 or 맥 원본(Range)
  /showcase/list   디렉토리 즉석 walk            그 외 → index.html(SPA)
  /showcase/thumb  썸네일 즉석 생성              bare / → 잠금 안내
  /showcase/media  원본(EXIF strip·트랜스코드)
     ▲ finder.kukjinkang.uk(터널) + X-Showcase-Secret
```

**핵심 불변식**:
- **인덱싱·manifest·썸네일 사전 push 없음.** 파일시스템이 곧 진실 — 파일 변경은 즉시 반영.
- `v=<mtime>` 가 캐시 버전키 — 파일 내용이 바뀌면 mtime 이 바뀌어 새 캐시 키로 자동 재생성.
- **맥이 켜져 있어야 갤러리가 열린다**(원본은 이미 그랬음). 맥이 꺼지면 SPA 가 안내.
- 게이트: 맥이 slug→바스켓→folder 소속 + 경로 이탈을 검증. raw 절대경로 안 받음(folder_id + rel).
- R2 는 SPA 호스팅 + 썸네일/원본 지연 캐시로만. 옛 manifest·thumbs·spaces 는 고아(무해).
