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
