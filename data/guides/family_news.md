# 가족신문 가이드

`[others:family_news]{op: ...}` — 폰(USB) 사진으로 신문 판을 조판해 공개 주소(/n/<5자 코드>)에
누적 발행하는 가족용 정기간행물. handler 도구라 /ibl/execute 직접 호출 시 project_id 필요.

## op 요약

| op | 설명 |
|----|------|
| status (기본) | 판 목록(초안/발행)·공개 주소·가족이 보낸 새 사진 수·제작 진행 상황 |
| create | 폰 사진으로 새 판 초안 제작. **백그라운드 조판** — 즉시 반환, 진행은 status. `photo_limit`(기본 48), `days`(비우면 지난 발행 이후, 첫 판 7일) |
| photos | **초안 사진 목록(편집용)** — 날짜·시간·장소·썸네일 + 남은 후보 수(pool_left) |
| remove_photo | **초안에서 `file` 사진 빼기** — 안 뽑혔던 후보 중 촬영 시각이 가까운 사진을 폰에서 당겨 자동 보충(폰 USB 연결 시), 신문 재조판. 발행 전에만 |
| publish | 초안을 공개 주소로 발행. 첫 발행 때 주소 생성. `edition_id` 생략 시 초안 하나면 그 판 |
| detail / delete | 판 상세 / 삭제(발행판은 `force:true`) |
| comments / uploads | 공개 페이지 방명록 / 가족이 보낸 사진(다음 판에 자동 합류) |
| config | `title` 제호, `photo_limit`, `public_base` |

## 흐름과 함정

1. **폰 USB 연결 필수** — create 는 adb MediaStore 로 DCIM 사진만 조회(스크린샷 폴더 제외).
   미연결이면 즉시 거부 메시지.
2. **구간**: 지난 발행판의 수집 종료 시점부터 지금까지. 첫 판은 최근 7일. `days` 로 재정의.
3. **캡**: 날짜별 비례 배분 + 날 내부 균등 스트라이드 — 하루 폭주가 판을 독점하지 않음.
4. **장소**: EXIF GPS → Kakao 역지오코딩("시군구 동"). **폰 카메라 위치태그가 꺼져 있으면
   장소가 빈다**(코드 문제 아님). 웹판 사진은 EXIF/GPS 전부 제거 — 장소는 텍스트로만.
5. **미리보기 → 발행**: 초안은 `http://localhost:8765/family-news/preview/<eid>/` (맥 로컬
   전용, 터널 401). 발행 전 판은 절대 공개되지 않는다.
6. **create 는 미발행 초안을 갈아엎는다**(호수 재사용). 발행판은 불변.
7. **가족 업로드**: 공개 페이지 '사진 보내기' → 공개되지 않고 다음 create 때 "가족이 보내온
   사진" 섹션으로 실림(발행 전 검수 구조).
8. **편집(빼기·보충)**: 초안의 안 뽑힌 후보(pool)가 edition.json 에 동봉된다 —
   `remove_photo` 는 뺀 사진과 촬영 시각이 가까운 후보를 adb 로 당겨 그 날짜 자리에 끼운다.
   뺀 사진의 원본 경로는 excluded 로 기록되어 다시 안 실린다. 가족 업로드 사진을 빼면
   보충 없이 그 업로드가 `rejected` 로 표시되어 다음 판 후보에서도 빠진다. create 로
   갈아엎으면 편집 이력(excluded)도 초기화. 옛 초안(pool 없음)은 빼기만 된다.
9. **장소 표기**: 장소가 있는 사진은 신문에서 사진 아래 항상 보이는 캡션(📍)으로 표기
   (호버 캡션은 폰에서 안 보여 정적 캡션으로).

## 예시

```
[others:family_news]{op: "create"}                          # 지난 발행 이후 사진으로 초안
[others:family_news]{op: "create", days: 30, photo_limit: 24}
[others:family_news]{op: "photos"}                          # 초안 사진 목록(편집용)
[others:family_news]{op: "remove_photo", file: "003.jpg"}   # 사진 빼기 — 후보에서 자동 보충
[others:family_news]{op: "publish"}                         # 초안 발행 → 공개 주소 반환
[others:family_news]{op: "comments"}                        # 방명록
[others:family_news]{op: "config", title: "강씨네 소식"}
```

기술 상세(서빙 구조·Worker /n/ 네임스페이스)는 패키지 가이드
`data/packages/installed/tools/family-news/guide.md` 참조.
