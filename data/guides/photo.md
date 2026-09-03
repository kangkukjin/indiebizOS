# 사진·동영상 가이드

`[self:photo]` 하나로 사진·동영상을 **라이브 질의**한다. op 도, 선스캔도 없다 — OS 미디어 색인
(맥 Spotlight / 폰 MediaStore)을 그때그때 읽으므로 결과는 항상 최신이다.

기술 깊이(스캔 DB 스키마·직접 SQL)는 패키지 [`photo-manager/guide.md`](../packages/installed/tools/photo-manager/guide.md).
스캔 DB 는 데스크탑 풍부창(중복·타임라인·지도)이 쓰는 별개 층이고, `[self:photo]` 는 거기 안 기댄다.

---

## 파라미터

| 키 | 뜻 |
|---|---|
| `q` | 파일명·기종 키워드 부분일치 |
| `kind` | `photo` / `video` / `all`(기본) |
| `start`·`end` | 촬영일 범위 — `YYYY-MM` 또는 `YYYY-MM-DD` |
| `has_gps` | true 면 위치 정보를 가진 것만 |
| `path` | 검색 루트 (생략 시 홈 전체) |
| `file` | 단일 파일 절대경로 상세 |
| `limit` | 개수 (기본 50) |
| `source` | `self`(기본)=실행되는 몸 / `usb`=USB 로 연결된 안드로이드 폰 |

결과 items 에 표시 필드(`title`/`meta`/`image`/`url`)와 구조 필드(`path`/`taken_at`/`month`/`kind`/
`size`/`camera`/`lat`/`lng`/`source`)가 함께 실린다 → 타임라인·통계·지도는 **table 변환자로 조합**한다.

---

## 기본 사용

```
[self:photo]{limit:40}                                  # 최근 사진·동영상
[self:photo]{q:"iPhone"}                                # 기종·파일명 검색
[self:photo]{kind:"video", start:"2026-03", end:"2026-03"}
[self:photo]{has_gps:true, limit:100}                   # 위치 가진 사진
[self:photo]{path:"/Volumes/<외장 라벨>/사진", limit:50} # 특정 폴더만
```

파생 조회는 별도 op 가 아니라 조합이다:

```
[self:photo]{limit:500} >> [table:groupby]{by:"month"}   # 타임라인
[self:photo]{limit:500} >> [table:groupby]{by:"kind"}    # 통계
[self:photo]{has_gps:true} >> [limbs:show_map]{}         # 지도
```

---

## USB 로 연결된 폰 사진 — `source:"usb"`

PC 는 안드로이드 저장소를 **볼륨으로 마운트하지 않는다**(MTP). 그래서 Spotlight·파일 순회로는
폰 사진을 원리적으로 못 본다. `source:"usb"` 는 대신 adb 로 폰의 MediaStore 를 그 자리에서 읽는다.

```
[self:photo]{source:"usb", limit:40}                     # 폰 안의 최신 사진
[self:photo]{source:"usb", q:"20260731"}                 # 파일명 검색
[self:photo]{source:"usb", start:"2026-07", end:"2026-07"}
[self:photo]{source:"usb", path:"DCIM/Camera"}           # 폰 안의 경로 부분일치
```

### 파일은 안 옮긴다

목록은 **경로와 메타만** 가져온다(복사 0). 실제 바이트는 볼 때만 넘어온다 —
썸네일 `/photo/usb-thumbnail?path=`, 원본 `/photo/usb-image?path=`, 동영상 `/photo/usb-video?path=`.
한 번 당긴 파일은 `data/usb_media_cache/` 에 남아 다시 볼 때 즉시 뜨고, 1GB 를 넘으면 오래된 것부터
버린다(원본은 폰에 있으니 언제든 다시 당긴다).

items 의 `path` 는 **폰 안의 경로**(`/storage/emulated/0/…`)라 PC 의 파일 도구로는 못 연다 —
`source` 필드가 `usb` 인 항목은 위 엔드포인트로만 열린다.

### 전제와 한계

- **PC 에서만.** 폰 자신에서 `source:"usb"` 를 부르면 거절된다(폰 사진은 `source` 없이 조회).
- **adb 필요.** Android platform-tools 가 있어야 하고, USB 연결 + 폰에서 USB 디버깅 승인이 필요하다.
  못 하면 "연결된 폰이 없습니다" 같은 **할 일이 적힌 문장**이 돌아온다 — 빈 결과가 아니다.
- **`has_gps` 미지원.** 안드로이드 10+ 는 MediaStore 의 위치를 가린다(전부 NULL). 위치는 파일을
  직접 열어 EXIF 를 봐야 나오는데 그러려면 후보 전부를 당겨야 하므로 필터로 쓸 수 없다 — 그렇다고 말하고 거절한다.
- **기종(`camera`) 없음.** MediaStore 에 그 컬럼이 없다.
- 사진·동영상 둘 다 본다(`kind`). 시스템 썸네일 캐시(`.thumbnails`)는 제외된다.

---

## 고른 사진을 저장하기

저장은 새 동사가 아니라 **조합**이다 — 고르는 일은 앞 액션과 table 변환자가 하고,
`[self:copy]` 는 받은 것을 그대로 옮긴다(`src` 를 생략하면 파이프로 온 items 를 저장한다).

```
[self:photo]{source:"usb", limit:10} >> [self:copy]{dest:"~/Desktop/폰사진"}
[self:photo]{source:"usb", limit:50} >> [table:take]{n:10} >> [self:copy]{dest:"~/Desktop"}
[self:photo]{source:"usb", start:"2026-07"} >> [self:copy]{dest:"~/Pictures/7월"}
[self:photo]{has_gps:true} >> [table:take]{n:20} >> [self:copy]{dest:"~/Desktop/위치사진"}
```

- 대상은 **폴더**다. 없으면 만든다.
- 원본 파일명을 유지하고, 겹치면 `이름 (2).jpg` — **덮어쓰지 않는다**.
- usb 항목은 폰에서 당겨 오고, 내 사진은 로컬 복사다(호출자는 구분할 필요 없다).

표면에서는 두 가지로 같은 일을 한다:

- **끌어 저장** — 썸네일을 창 밖(바탕화면·파인더 폴더)으로 끌면 원본이 거기 저장된다.
  데스크탑 앱(Electron)에서만 가능하다 — 브라우저는 창 밖으로 파일을 못 내보낸다.
- **골라 저장** — 썸네일 좌상단 체크로 고르고(**shift 클릭 = 여기까지 한꺼번에**) "폴더에 저장".
  실제 복사는 `[self:copy]` 와 **같은 코드**(`file_index.save_media_files`)를 쓴다.

---

## 표면

- **앱 계기 📷 사진** 4탭: 갤러리 / 검색 / 위치 / **폰(USB)**. 폰 네이티브 표면에선 폰(USB) 탭이 숨는다
  (자기 자신을 USB 로 볼 수는 없다).
- **데스크탑 풍부창**(사진 아이콘 → 별도 창): 사이드바 "연결된 기기 → 폰 (USB)". 폰은 인덱싱하지
  않는 라이브 소스라 갤러리 탭만 뜬다(타임라인·중복·통계·지도는 스캔 DB 위에서 도는 뷰).

---

## 자주 하는 실수

- **`source:"usb"` 를 폰에서 호출** — 폰 자신의 사진은 `source` 없이 조회한다(몸이 곧 소스).
- **`has_gps` 를 usb 와 같이** — 미지원. 위치로 거르려면 사진을 PC 로 가져온 뒤 조회한다.
- **usb 항목의 `path` 를 파일 도구에 넘김** — 폰 안의 경로다. `[self:read]`·`[limbs:os_open]` 으로 못 연다.
- **`start`/`end` 형식** — `YYYY-MM` 또는 `YYYY-MM-DD`. `2026/07/01` 은 안 된다.
- **첫 조회가 느리다** — 폰 사진 썸네일은 그때 당겨 오므로 첫 화면만 몇 초 걸리고, 이후엔 캐시로 즉시 뜬다.

## 관련

- [`photo-manager/guide.md`](../packages/installed/tools/photo-manager/guide.md) — 스캔 DB 스키마·직접 SQL
- `[table:groupby]`·`[table:chart]` — 타임라인·통계 조합
- `[limbs:show_map]` — GPS 사진 지도 표시
- `[others:family_news]` — USB 폰 사진으로 가족신문 조판(같은 adb 경로를 쓰는 이웃 어휘)
