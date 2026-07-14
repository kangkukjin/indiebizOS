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

## 바스켓 = 공개 주소 (bare 루트는 잠금)

**모든 갤러리는 바스켓 하나 = 주소 하나**(`<base>/s/<slug>`). `slug` 는 5자 대문자
코드(A-Z, 26⁵≈1180만). **bare 루트(`<base>/`)는 항상 잠겨** 콘텐츠·썸네일 전부 404 —
그래서 어떤 주소의 코드를 지워도(=bare 루트) 아무것도 안 새어 나간다. 널리 공유하면
공개 갤러리, 아는 사람만 주면 비밀 갤러리 — 구조는 동일.

```
[others:showcase]{op: "basket_list"}                                  # 주소(바스켓) 목록
[others:showcase]{op: "basket_save", title: "가족에게"}                # 생성(5자 코드 발급)
[others:showcase]{op: "basket_save", title: "전체 공개", all_folders: true}  # 전체 폴더 자동 포함 갤러리
[others:showcase]{op: "basket_save", basket_id: "bsk_…", title: "새 이름"}   # 개명
[others:showcase]{op: "basket_detail", basket_id: "bsk_…"}            # 담긴 폴더 + 담기/빼기
[others:showcase]{op: "basket_toggle", basket_id: "bsk_…", folder_id: "fld_…"}  # 담기/빼기
[others:showcase]{op: "basket_delete", basket_id: "bsk_…"}            # 주소 삭제(폴더 보존)
```

- **폴더는 바스켓에 담겨야 공개** — 어떤 바스켓에도 없는 폴더는 어디에도 안 보인다
  (bare 루트 잠금이라 '루트 공개' 개념 폐기). 폴더 추가·동기화는 준비일 뿐, 공개는 바스켓.
- **전체 공개 갤러리** = `all_folders: true` 바스켓. 모든 폴더 자동 포함, 폴더 추가 시
  자동 반영. 이것도 자기 slug 주소를 가져 bare 루트엔 안 뜬다.
- **버킷은 하나** — 바스켓은 R2 버킷이 아니라 `spaces/<slug>/manifest.json` 네임스페이스.
  썸네일·원본은 전역(`thumbs/<fid>`·`media/<fid>`) 공유. 썸네일은 동기화 시 항상 올려두고
  (bare 는 잠겨 안 샘) 바스켓에 담는 순간 그 주소에서 바로 보인다.
- **게이팅(Worker)**: `spaces/<slug>/fids.json`(담긴 folder_id 화이트리스트)로 스코프
  접근 제한 — 잘못된 slug·비소속 폴더의 썸네일/원본은 404. bare `/thumbs`·`/media` 는
  루트 `fids.json`(=빈 배열)이라 전부 404. 원본 서빙(`api_showcase.py`)도 '어떤 바스켓에
  담김'만 허용.

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
