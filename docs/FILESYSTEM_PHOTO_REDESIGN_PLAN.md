# 파일시스템·사진 액션 재설계 계획서

*작성: 2026-06-20*
*상태: **Phase 1~4 + Phase 5(해마) 완료**. Phase 5 분별 — 지금: 라이브 해마 stale op-용례 58건 교체+조합용례 추가(연상 검증, 모델 재학습 불요), 문서는 이미 깨끗. **미룸(이해층이 재편하므로 redo 방지)**: photo_db·storage_db 물질화 은퇴 + 풍부창 이관(task#7 deferred). 그 외=일반 table view(task#6)·폰 fs_query(다음 빌드). 다음 큰 방향=파일시스템 "이해층"(별도 설계).*

## 0. 한 줄 요지

사진·파일 조회는 가장 기본적인 능력인데, 현재 구현은 **(1) 맥 전용**이고 **(2) 무거운 선(先)스캔을 모든 조회의 전제로 삼으며 (3) 한 액션이 8가지를 다 하는 "복잡한 일에 대한 스위치"**가 되어 있다. 셋 다 같은 뿌리에서 나온다: *OS가 이미 증분으로 유지하는 미디어/파일 인덱스를 손으로 다시 물질화하고, 그 위에 두꺼운 op 분기를 얹은 것*. 이 계획은 그것을 **OS 네이티브 인덱스 위의 얇은·무상태·하드웨어상대적 질의 프리미티브**로 바꾸고, 파생 조회(타임라인·통계·중복)는 이미 있는 통화 변환자 조합으로 유도한다.

---

## 1. 문제 정의 (코드 근거)

### P1 — 하드웨어 가정 (맥 전용)
- `self:photo`는 `runs_on: mac_only` + `app.phone_render: false`로 못 박혀 있다 (`data/ibl_nodes_src/self.yaml:4, 38`).
- `self:storage`/`self:fs_query`도 맥 파일시스템·`diskutil`/`/Volumes` 가정.
- 반면 **하드웨어상대 라우팅 기반은 이미 있다**: `runs_on` + `ibl_engine._resolve_and_maybe_forward()` + `device_registry` + 핸들러의 `INDIEBIZ_PROFILE` 분기. `limbs:android`(`runs_on: anywhere`, 핸들러가 ADB↔AccessibilityService 분기)와 `sense:see/here/listen`가 "하나의 어휘, 몸별 다른 바인딩"을 이미 시연한다. **사진·파일만 이 버스에 안 탔다.**

### P2 — 선스캔 전제 + 전체 재스캔 (무상태성 결여)
- `self:photo`: `scan: 폴더 인덱싱 (path 필수, 모든 조회의 전제)` (`self.yaml:13`). 스캔은 매번 `photo_db.clear_scan_data()`(= `DELETE FROM media_files`) 후 `os.walk` 전체 재귀 + 전 파일 EXIF/GPS 재추출 (`scanner.py`). **증분·mtime 비교 없음 → 사진 한 장만 바뀌어도 전체 재스캔.**
- `self:storage`도 동일 패턴(`clear_scan_data` → `os.walk` → FTS5 재빌드, `storage_db.scan_directory`).
- 귀결: "지난달 어디 있었나"는 지난달 사진의 GPS만 필요한데, **모델이 전체 선스캔을 강제**한다. 질의 자체(`taken_date` 인덱스 범위 필터)는 멀쩡하지만, *질의 데이터를 갖기 위한 전체 물질화*가 비용이다.

### P3 — 비대해진 액션 = "하나의 복잡한 일에 대한 스위치"
- `self:photo`는 `scan/list_scans/gallery/search/stats/timeline/duplicates/detail` **8 op**의 단일 스위치 (`self.yaml:11-21`). `handler.py`(486줄)+`photo_db.py`(863줄)+`scanner.py`(391줄).
- 그런데 `timeline`(월별 집계) = `groupby`, `stats`(요약) = `count`/`groupby`, `duplicates`(해시 중복) = `groupby … having count>1`, `gallery`/`search` = 같은 질의에 필터만 다름. **즉 8 op 중 다수는 "한 기본 질의 + 통화 변환자 조합"으로 유도되는데, bespoke op으로 고정**되어 다방면 재사용이 막혀 있다.
- 핵심 통찰: **변환자 어휘는 이미 존재한다** — `engines.yaml:295-439`에 `filter/sort/take/select/dedup/groupby/join/union/merge` 9 변환자(통화 대수)가 있다. 사진 레코드가 이 통화에 올라타기만 하면 파생 조회는 공짜다.

---

## 2. 설계 원칙 (헌법 정합)

1. **상부구조/하부구조 이음매** (헌법1조): 어휘 "사진을 보여줘"는 몸 독립(상부구조), "사진이 어디 살고 어떻게 열거되는가"는 몸별 바인딩(하부구조). 맥=Spotlight/`~/Pictures`, 폰=MediaStore — 같은 어휘가 가리키는 *서로 다른 진짜 몸*.
2. **몸 vs 흡수 가능성**: 직접 쌓은 스캔 인덱스 = 흡수되는 죽은 무게. OS가 시스템 전역·증분·항상최신으로 유지하는 미디어 인덱스 = *몸*. **스캐폴드는 얇게, 인덱스는 OS(몸)에 맡긴다.**
3. **명사는 곱하고 필드는 쌓인다** (records 통화): 좋은 IBL 척도 = 조합 밀도. 사진 질의가 records 통화를 말하면 모든 변환자와 곱해진다. op는 *서로 다른 연산*에만 쓰고, *같은 데이터에 대한 다른 질의*에는 쓰지 않는다.
4. **IBL 액션 4기준** 중 **실시간성**: 선스캔 모델은 구조적으로 stale → 미달. 무상태 라이브 질의가 기준을 만족한다.
5. **어휘는 버리지 않는다** (IBL=어휘 명제): "그냥 python+쉘로" 결론은 코퍼스 일관성·교차몸 라우팅·해마 기억을 깬다. 수술은 *어휘 유지 + 구현을 얇게*.
6. **임시방편 금지**: 호환층/별칭은 은퇴까지 끝낼 때만. 옛 op 은퇴는 코퍼스 재라벨·해마 재빌드·문서 7표면까지 완수.

> **op에 대한 정밀화** (기존 단일-액션+op 패턴과의 관계): op 분기를 폐기하는 게 아니다. *유도 가능한* 조회(timeline/stats/duplicates)는 op에서 빼 변환자 조합으로 보내고, op는 *환원 불가능한 다른 연산*(예: 무상태 query vs. 부수효과 있는 유지보수 scan)에만 남긴다.

---

## 3. 목표 아키텍처

### 3.1 몸 = OS 네이티브 인덱스 (라이브·무상태)
| 몸 | 미디어 인덱스 | 질의 수단 | GPS/메타 |
|----|--------------|-----------|----------|
| 맥 | Spotlight | `mdfind`(날짜·타입·범위 질의), `mdls`(파일별 메타) | `kMDItemContentCreationDate`, `kMDItemLatitude/Longitude`, `kMDItemAcquisitionMake/Model` |
| 폰 | MediaStore | `ContentResolver.query`(`DATE_TAKEN`/`MIME_TYPE`/`SIZE` selection) | EXIF GPS는 `ACCESS_MEDIA_LOCATION` + `ExifInterface` (열린 질문, §6) |

- **선스캔 폐기.** 질의는 호출 시점에 OS 라이브 인덱스를 친다 → 항상 최신, 증분 0비용.
- 자체 SQLite 스캔(`photo_db`/`storage_db`)은 **기본 경로에서 제거**, 비색인 볼륨(꺼둔 외장드라이브 등) 폴백으로만 옵트인.

### 3.2 얇은 질의 프리미티브 + 통화 조합
**사진의 환원 불가능한 프리미티브 = "필터에 맞는 미디어를 records로 열거"** 하나다.

```
[self:photo]{ filter…, limit }  →  records[{title, meta, summary, url, image, taken_at, lat, lng, kind, size, camera}]
```

파생 조회는 전부 조합으로 유도 (bespoke op 아님):

| 옛 op | 새 표현 (조합) |
|-------|----------------|
| gallery | `[self:photo]{}` (무필터 질의) |
| search | `[self:photo]{q, kind, start, end}` (필터만 다름) |
| timeline | `[self:photo]{…} >> [engines:groupby]{by: month}` |
| stats | `[self:photo]{…} >> [engines:groupby]{by: kind}` (+count) |
| duplicates | `[self:photo]{…} >> [engines:groupby]{by: hash, having: count>1}` |
| detail | `[self:photo]{id}` (단일 레코드 질의) |
| **"지난달 어디 있었나"** | `[self:photo]{start, end, has_gps:true} >> map_data 투영 >> 지도 렌더` |

- records 통화는 위치 표준(`{lat,lng}` float, `map_data` 봉투)을 따라 GPS 필드를 실어 지도/차트 변환자와 직결.
- **결과: 8 op 스위치 → 무상태 질의 1 프리미티브 + 기존 변환자.** 다방면 재사용이 열린다.

### 3.3 하드웨어상대 라우팅 (limbs:android 패턴 복제)
- `self:photo`: `runs_on: anywhere`. 핸들러가 `INDIEBIZ_PROFILE`로 분기 — 맥=mdfind/mdls 어댑터, 폰=MediaStore 어댑터.
- 무주소 호출은 *실행되는 몸*의 미디어를 가리킨다(자동). `@폰2` 명시 시 그 노드로 포워드(기존 분산 IBL 그대로), 결과 파일은 `_pull_remote_artifacts`로 회수.

### 3.4 보편 질의의 단일 출처 — `backend/file_index.py` (중복 제거의 핵심)
**사진은 파일의 한 종류일 뿐**(mp3·pdf·docx와 같은 층위). "OS 색인을 질의한다"는 *보편적인 일*(필터 조립·mdfind 실행·mdls 메타 투영·정렬·몸 분기)은 **한 곳에서만** 한다 → `backend/file_index.py`. 이것이 [읽기=수렴 원칙](self:read{format})의 *질의 버전*이다.
- `file_index.query(kind, q, start, end, has_gps, ext, path, limit, sort, facets)` → 보편 필드(path/name/ext/size/mtime/kind) + 요청 facet 만 담은 **순수 데이터**. 표시·렌더링(썸네일·meta 라인)은 호출자 몫 → 그래서 preset 마다 보편 질의가 중복되지 않는다.
- **몸 분기가 사는 유일한 곳**: `detect_body()` 능력게이트로 맥(Spotlight)↔폰(MediaStore) 분기. 환경변수 직접 분기가 없어 fork-guard 통과(allowlist 불필요).
- facet 사전(`_FACET_KEY`)에 종류별 메타: 이미지=taken_at/lat/lng/camera/width/height, 음악=duration/genre, 문서=authors/pages/title. 종류가 늘면 facet만 추가.

### 3.5 얇은 preset 들 (특수함만 얹음)
- `self:photo` = `kind=media` + 썸네일 `image` + GPS·기종 meta. **보편 질의는 file_index 위임.** (사진은 빈도·렌더링 특수성으로 전용 동사 유지 — 명명법 정합.)
- `self:fs_query`(Phase 4) = 보편 필드만, 종류 무관. file_index 재사용 → mdfind 어댑터 **재구현 없음**.
- 미래 `self:music`·문서 질의도 facet 만 다른 얇은 preset.
- `self:list`/`file_find`/`grep`: 라이브 순회(색인 아닌 즉석) 프리미티브 → **유지**. file_index(색인 질의)와 상보적.
- `self:storage`의 무거운 `scan`은 비색인 볼륨 폴백으로 격하(file_index 안 `_walk_fallback`이 이미 그 역할).

---

## 4. 일반 원리 (이번 건을 넘어서)

이 재설계는 **"흡수 가능한 인덱스를 자체 물질화하던 액션 → OS/외부 몸 위의 얇은 무상태 어댑터"** 라는 재사용 가능한 템플릿이다. 같은 냄새(선스캔 전제 + 전체 재빌드 + 비대 op)를 가진 다른 액션에도 적용 후보. 사진/파일이 "가장 기본"이므로 여기서 패턴을 못 박고 표준으로 삼는다.

---

## 5. 단계별 실행 계획 (검증 게이트 포함)

각 단계는 게이트를 통과해야 다음으로 간다.

### Phase 0 — 설계 동결 & 통화 계약 정의
- 미디어 records 통화 필드 확정(`title/meta/summary/url/image` + `taken_at/lat/lng/kind/size/camera`), 필터 파라미터 어휘 확정(`q/kind/start/end/has_gps/path/id/limit`).
- 새 op 어휘 vs 은퇴 op 매핑표 동결(§3.2). `new_action_checklist` 작성.
- **게이트**: 사용자 승인.

### Phase 1 — 맥 어댑터 (무상태 질의)
- `self:photo`를 `mdfind`/`mdls` 기반 무상태 핸들러로 재구현. records 통화 방출. `scan` op은 일단 폴백으로만 보존(은퇴는 Phase 5).
- **게이트**: `[self:photo]{start,end,has_gps}` 라이브 질의가 선스캔 없이 즉시 반환. 한 장 추가→재스캔 0으로 즉시 반영. `build --check` + 종단 `/ibl/execute`.

### Phase 2 — 통화 조합 검증
- timeline/stats/duplicates를 `engines:groupby`/`filter` 조합으로 재현. "지난달 GPS → 지도" 종단 시나리오 실행.
- **게이트**: 옛 op 산출과 동등 결과를 조합으로 재현. 데스크탑 풍부 photo 창(STATIC) 정합 유지(매니페스트만 교체 대상).

### Phase 3 — 폰 어댑터
- `runs_on: anywhere` 전환 + `INDIEBIZ_PROFILE=phone` 분기 → MediaStore 질의(PhoneActions Kotlin 브리지). GPS는 §6 해결책 적용.
- **게이트**: A36 실기기에서 무주소 `[self:photo]{…}`가 폰 미디어를 질의. 맥에서 `@폰` 포워드 왕복.

### Phase 4 — 파일 측 대칭화 (file_index 재사용)
- `self:fs_query`를 `file_index.query`(보편 필드, 종류 무관) 위의 얇은 preset으로 재작성 — **mdfind 어댑터 재구현 없음**(Phase 1에서 만든 단일 출처 재사용). `self:storage`의 무거운 scan 격하. 가벼운 file 프리미티브 폰 분기.
- **게이트**: `fs_query`가 선스캔 없이 반환. file_index 코드 중복 0(diff로 확인). 비색인 볼륨만 walk 폴백.

### Phase 5 — 은퇴·코퍼스·해마·문서
- 옛 op/`photo_db`·`scanner`·`storage_db` 물질화 경로 은퇴(`data/packages/_archive/` 백업). app 매니페스트(modes) 새 어휘로 교체. 코퍼스 재라벨 + 해마 `rebuild_index`. 문서 7표면 갱신(CLAUDE.md·system_docs·이 문서). `build --check` 삼각 통과.
- **게이트**: 해마 연상 정확도 회귀 없음. self-check 정적 정합성 통과. 잔여 옛 op 참조 0.

---

## 6. 리스크 · 열린 질문

1. **폰 MediaStore GPS redaction**: Android 10+는 미디어 위치를 기본 가린다. `ACCESS_MEDIA_LOCATION` 권한 + `MediaStore.setRequireOriginal` + `ExifInterface`로 파일별 추출 필요 → 대량 질의 시 성능. (정책: 날짜/타입/크기는 MediaStore 네이티브, GPS는 `has_gps`/범위 좁힌 뒤 per-file EXIF.)
2. **Spotlight 비활성/비색인 볼륨**: 외장드라이브·`mdutil` off 시 mdfind 공백. → `scan` 폴백 경로 유지(옵트인), 공백 시 안내.
3. **대용량 결과 상한**: records 페이징/limit 계약 필요(기존 200 상한 관행 준용).
4. **데스크탑 풍부 photo 창**: STATIC 풍부창은 유지(지도·줌타임라인·라이트박스). 매니페스트만 새 어휘로. `STATIC_INSTRUMENT_IDS` 차폐 그대로.
5. **perceptual 중복**: OS 인덱스에 없음(해시는 있어도 지각적 유사도는 별개). → 별도 얇은 액션 또는 보류로 분리(중복 op을 통째로 조합으로 못 옮길 수 있음).
6. **기존 스캔 DB 사용자 데이터**: 재질의가 즉시 가능하므로 마이그레이션 불필요(폐기 가능). 다만 사용자 스캔 목록/별칭이 있으면 안내 후 폐기.

---

## 7. 영향 받는 파일 (초안)

- `data/ibl_nodes_src/self.yaml` — `photo`/`storage`/`fs_query` 블록, app 매니페스트
- `data/packages/installed/tools/photo-manager/` — handler 재작성, `photo_db`/`scanner` 은퇴
- `data/packages/installed/tools/pc-manager/` — `storage_db` 무상태화
- `android/`(phone-companion) Kotlin `PhoneActions` — MediaStore 질의 브리지
- `backend/ibl_engine.py` — (라우팅은 기존 그대로, 변경 최소)
- 코퍼스/해마: `data/training/ibl_distilled.json`, `rebuild_index`
- 문서: `CLAUDE.md`, `data/system_docs/ibl.md` 외 7표면

---

## 8. 성공 기준

- [ ] 사진/파일 조회가 **선스캔 없이** 라이브로 응답한다.
- [ ] 사진 한 장 변경이 **재스캔 0**으로 반영된다.
- [ ] "지난달 GPS→지도"가 전체 인덱스 없이 **질의+조합**으로 된다.
- [ ] 같은 어휘가 **맥과 폰에서** 각자의 미디어를 가리킨다.
- [ ] `self:photo`가 **8 op 스위치 → 무상태 질의 1 프리미티브 + 변환자 조합**으로 축소된다.
- [ ] 해마 연상 회귀 없음, `build --check`·self-check 통과.
