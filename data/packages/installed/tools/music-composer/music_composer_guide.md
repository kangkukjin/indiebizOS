# Music Composer 가이드

ABC Notation 기반 음악 작곡 도구. LLM이 ABC Notation을 작성하면 MIDI → 오디오(WAV/MP3)로 변환합니다.

## ABC Notation 작성법

ABC Notation은 텍스트로 악보를 표현하는 형식입니다.

### 기본 구조
```
X:1              ← 곡 번호 (필수)
T:곡 제목         ← 제목
C:작곡가          ← 작곡가
M:4/4            ← 박자 (4/4, 3/4, 6/8 등)
L:1/8            ← 기본 음표 길이
Q:1/4=120        ← 템포 (BPM)
K:C              ← 조성 (C, G, Dm, Am 등)
```

### 음표 표기
- `C D E F G A B` — 낮은 옥타브
- `c d e f g a b` — 높은 옥타브
- `C,` — 한 옥타브 아래, `c'` — 한 옥타브 위
- `C2` — 2배 길이, `C/2` — 절반 길이
- `z` — 쉼표, `z2` — 2배 쉼표

### 다성부 (멀티 파트)
```
V:1 name="Melody"
|: C2 DE FG AB | c4 B2 A2 :|
V:2 name="Harmony"
|: E,2 G,2 C2 E2 | G4 F2 E2 :|
V:3 name="Bass"
|: C,4 G,,4 | C,4 G,,4 :|
```

### 주요 기호
- `|` 마디선, `||` 겹세로줄, `|]` 종지선
- `|:` `:` 도돌이표
- `(3CDE` 셋잇단음, `[CEG]` 화음
- `^C` 올림(#), `_B` 내림(b), `=C` 제자리표

### 작곡 팁
- 멜로디를 V:1에, 반주를 V:2 이하에 배치
- 모든 파트의 마디 수를 동일하게 유지
- 템포: 느린곡 60-80, 보통 100-120, 빠른곡 140+

---

## 악기 (General MIDI)

V:1부터 순서대로 instruments 리스트에 매칭됩니다.

### 피아노/건반
piano, bright_acoustic_piano, electric_piano, harpsichord, clavinet, celesta, music_box, vibraphone, marimba, xylophone, organ, church_organ, accordion, harmonica

### 현악기
violin, viola, cello, contrabass, harp, strings (앙상블), string_ensemble, pizzicato_strings, tremolo_strings

### 목관
flute, piccolo, recorder, pan_flute, oboe, english_horn, clarinet, bassoon, shakuhachi, ocarina

### 금관
trumpet, trombone, french_horn, tuba, brass_section, muted_trumpet

### 기타/베이스
guitar, acoustic_guitar_nylon, acoustic_guitar_steel, electric_guitar_jazz, electric_guitar_clean, overdriven_guitar, distortion_guitar, bass, acoustic_bass, electric_bass_finger, fretless_bass, slap_bass

### 보컬/합창
choir, choir_aahs, voice_oohs, synth_voice

### 관악기
soprano_sax, alto_sax, tenor_sax, baritone_sax

### 신스/전자
synth_lead, synth_pad, synth_bass, synth_strings, synth_brass

### 민속/타악기
sitar, banjo, shamisen, koto, kalimba, bagpipe, steel_drums, taiko_drum, timpani

---

## 믹싱 옵션

모두 선택사항이며, 생략하면 자동으로 적절한 값이 적용됩니다.

### volumes (파트별 볼륨)
- 범위: 0-127 (0=무음, 127=최대)
- V:1부터 순서대로 매칭
- 생략 시: 멜로디(110) > 베이스(80) > 내성부(70) 자동 밸런스
- 예: `[120, 60, 85]` → 멜로디 크게, 화성 작게, 베이스 중간

### panning (파트별 좌우 배치)
- 범위: 0=완전 좌, 64=중앙, 127=완전 우
- 생략 시: 파트 수에 따라 32~96 범위로 자동 분배
- 예: `[30, 64, 100]` → 멜로디 왼쪽, 화성 중앙, 베이스 오른쪽

### reverb (리버브 깊이)
- 범위: 0-127 (기본값: 60)
- 0=잔향 없음, 60=적당한 공간감, 100+=성당/홀 느낌
- 장르별 권장: 팝 40-60, 클래식/찬송가 70-90, 재즈 50-70, 앰비언트 90-120

### chorus (코러스 깊이)
- 범위: 0-127 (기본값: 30)
- 0=효과 없음, 30=은은한 풍성함, 60+=뚜렷한 코러스
- 현악기/합창에는 높게(50-80), 피아노/타악기에는 낮게(0-20) 권장

### eq_preset (EQ 프리셋)
음색을 조절하는 후처리 프리셋입니다.

| 프리셋 | 특징 | 추천 장르 |
|--------|------|-----------|
| balanced | 자연스러운 보정 (기본값) | 범용 |
| warm | 저음 강조, 고음 억제, 부드러운 | 발라드, 재즈, 어쿠스틱, 피아노 독주 |
| bright | 고음 강조, 저음 억제, 선명한 | 팝, 클래식 독주, 플루트/바이올린 |
| powerful | 저음+고음 모두 강조, 강렬한 | 오케스트라, 찬송가, 록, 브라스 |
| flat | EQ 없음, 원본 그대로 | 원본 확인, 직접 후처리할 때 |

---

## 사용 예시

### 간단한 피아노 곡
```json
{
  "abc_notation": "X:1\nT:Simple Melody\nM:4/4\nL:1/8\nQ:1/4=100\nK:C\nCDEF GABc|c2B2 A2G2|",
  "format": "mp3"
}
```

### 오케스트라 편성 + 믹싱
```json
{
  "abc_notation": "X:1\nT:Orchestra\nM:4/4\nL:1/8\nQ:1/4=80\nK:G\nV:1\nD2GA B2AG|...\nV:2\nB,2DE G2FE|...\nV:3\nG,2B,D E2DC|...\nV:4\nG,,2D,2 G,2D,2|...",
  "instruments": ["flute", "strings", "choir", "contrabass"],
  "volumes": [115, 70, 65, 85],
  "panning": [30, 50, 78, 96],
  "reverb": 80,
  "chorus": 40,
  "eq_preset": "powerful",
  "format": "mp3",
  "title": "My Orchestra"
}
```

### 재즈 트리오 (따뜻한 느낌)
```json
{
  "instruments": ["alto_sax", "piano", "acoustic_bass"],
  "volumes": [110, 75, 90],
  "reverb": 55,
  "chorus": 20,
  "eq_preset": "warm",
  "format": "mp3"
}
```

---

## ABC 악보 검색/가져오기

abcnotation.com (~80만곡)에서 기존 악보를 검색하고 가져올 수 있습니다.

### 검색 → 연주 워크플로우
```
1. search_abc_tunes(query="greensleeves")  → 검색 결과 목록
2. get_abc_tune(tune_id="결과의 tune_id")   → ABC Notation 텍스트
3. compose_and_export(abc_notation=가져온 ABC, instruments=[...])  → 오디오 생성
```

### search_abc_tunes
- **query**: 곡명, 작곡가, 키워드 등 (영문 권장)
- **page**: 페이지 번호 (0부터, 페이지당 10건)
- 반환: results 배열 (title, tune_id, source, url), total, has_more

### get_abc_tune
- **tune_id**: search_abc_tunes 결과의 tune_id 값
- 반환: abc_notation (텍스트), title, metadata
- 가져온 abc_notation을 compose_and_export에 바로 전달 가능

### 검색 팁
- 영문 곡명으로 검색: "amazing grace", "fur elise", "canon in d"
- 장르/스타일: "irish jig", "scottish reel", "waltz"
- 작곡가: "bach", "mozart", "beethoven"
- 결과가 많으면 page 파라미터로 다음 페이지 탐색

---

## 도구별 용도

- **compose_and_export**: 일반적으로 이 도구만 사용. ABC → MIDI → 오디오 한번에 처리
- **abc_to_midi**: MIDI만 필요할 때 (오디오 변환 없이)
- **midi_to_audio**: 이미 생성된 MIDI를 다른 EQ/포맷으로 재변환할 때
- **search_abc_tunes**: 기존 곡의 ABC 악보 검색 (abcnotation.com ~80만곡)
- **get_abc_tune**: 검색된 곡의 ABC Notation 가져오기
