# 공개파일 (Public Files)

선택한 폴더를 외부 공개 사이트(Cloudflare R2 + Worker)로 비추는 노출 층. 개인용 NAS 와
달리 **보여줄 것만 고른 창**이다. 설계 전문: `docs/PUBLIC_FILES_APP_DESIGN.md`.

## 어휘

```
[others:showcase]{op: "status"}                              # 공개 폴더·URL·설정
[others:showcase]{op: "add", path: "/Users/.../여행", mode: "media"}
[others:showcase]{op: "sync", path: "/Users/.../여행"}       # 재동기화 (생략=전체)
[others:showcase]{op: "remove", path: "/Users/.../여행"}     # 공개 해제
[others:showcase]{op: "config", access: "link_only", strip_exif: true}
```

- `mode`: `media`(사진·동영상 그리드) / `files`(파일 전체).
- 접근 기본 `link_only`(토큰) — 개인 사진 안전판. `public` 은 명시 선택.
- EXIF/GPS 기본 제거. 폴더 선택이 곧 보안 경계(고른 폴더만 공개 사이트에 존재).

## 바스켓 (여러 비밀 공개주소)

한 폴더 집합을 하나의 공개 사이트로만 비추는 게 아니라, **여러 개의 비밀 주소**를
만들고 각 주소마다 다른 폴더 부분집합을 노출한다. 주소 = `<base>/s/<slug>` 이고
`slug` 는 긴 랜덤 토큰(≈22자)이라 **아는 사람만** 본다(진짜 비밀 링크).

```
[others:showcase]{op: "basket_list"}                                  # 바스켓 목록·비밀 URL
[others:showcase]{op: "basket_save", title: "가족에게"}                # 생성(새 slug 발급)
[others:showcase]{op: "basket_save", basket_id: "bsk_…", title: "새 이름"}   # 개명
[others:showcase]{op: "basket_detail", basket_id: "bsk_…"}            # 전 폴더 + 소속여부
[others:showcase]{op: "basket_toggle", basket_id: "bsk_…", folder_id: "fld_…"}  # 담기/빼기
[others:showcase]{op: "basket_delete", basket_id: "bsk_…"}            # 비밀주소 삭제(폴더 보존)
```

- **버킷은 하나** — 바스켓은 R2 버킷이 아니라 `spaces/<slug>/manifest.json` 네임스페이스.
  썸네일·원본은 전역(`thumbs/<fid>`·`media/<fid>`) 공유라 여러 바스켓이 같은 폴더를
  담아도 중복 업로드 없음.
- **루트 공개(hidden) ↔ 바스켓 소속은 독립.** 폴더를 '루트 비공개'로 두고 바스켓에만
  담으면 그 비밀주소로만 공개된다. 루트(`.../` 전체공개)와 병존.
- **게이팅(Worker)**: `spaces/<slug>/fids.json`(담긴 folder_id 화이트리스트)로 스코프
  접근을 막는다. 잘못된 slug·비소속 폴더의 썸네일/원본은 404. bare `/thumbs`·`/media`
  는 루트 `fids.json`(루트 공개 폴더)로만 게이트 — 바스켓 전용 폴더가 bare 경로로
  안 샘. 원본 서빙(`api_showcase.py`)도 '루트 공개 OR 바스켓 소속'만 허용.

## 이음매 (헌법 1조)

맥(이 패키지)은 썸네일·매니페스트를 만들어 R2 로 push. 공개 Worker 는 `manifest.json`
계약(설계문서 §6)만 안다. 앱을 지워도 사이트는 마지막 상태로 산다. Cloudflare 를 다른
벤더로 갈아치워도 계약만 지키면 이 패키지는 무변경.

## 구현 단계

- P0 ✅ 어휘 골격(상태 파일 CRUD 스텁).
- P1 로컬 동기화(썸네일=self:photo 재사용, manifest 로컬 생성).
- P2 R2 push(cf_api/S3, 증분).
- P3 공개 Worker(정적 그리드 + link_only 토큰 + `<video>` 재생).
- P4 원본·동영상 H.264 변환·EXIF 제거.
- P5 앱 계기 마감(폴더 dialog·설정 form·원격 파리티).
