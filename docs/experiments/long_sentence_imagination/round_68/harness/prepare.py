"""68회차 합성 자료 생성 — 사진(EXIF)·중복·손상·스크린샷·음성 메모. 실제 개인 자료는 쓰지 않는다."""
import json, os, shutil, subprocess, time, hashlib
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ExifTags

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-14_68회차'
DOC = Path(__file__).resolve().parents[1]
DUMP = OUT / 'inputs/dump'
FONT = '/System/Library/Fonts/AppleSDGothicNeo.ttc'

def font(sz):
    return ImageFont.truetype(FONT, sz)

def scene(kind, title, sub, w=960, h=720):
    im = Image.new('RGB', (w, h), {'cake': (255, 240, 220), 'park': (190, 225, 255), 'menu': (250, 250, 245), 'sea': (200, 230, 255)}[kind])
    d = ImageDraw.Draw(im)
    if kind == 'cake':
        d.rounded_rectangle((280, 380, 680, 600), 30, fill=(245, 200, 160), outline=(120, 70, 40), width=6)
        d.rounded_rectangle((300, 320, 660, 400), 20, fill=(255, 255, 255), outline=(120, 70, 40), width=4)
        for x in range(340, 640, 60):
            d.rectangle((x, 250, x + 14, 320), fill=(255, 90, 90)); d.ellipse((x - 4, 225, x + 18, 252), fill=(255, 200, 50))
        d.text((250, 80), 'HAPPY BIRTHDAY', fill=(200, 40, 60), font=font(60))
    elif kind == 'park':
        d.rectangle((0, 450, w, h), fill=(110, 180, 90))
        d.rectangle((460, 300, 500, 470), fill=(110, 70, 40)); d.ellipse((360, 150, 600, 340), fill=(40, 140, 60))
        d.ellipse((80, 60, 200, 180), fill=(255, 220, 80))
    elif kind == 'menu':
        d.rectangle((120, 80, 840, 660), outline=(60, 60, 60), width=5)
        y = 130
        for name, price in [('김치찌개', '9,000원'), ('된장찌개', '9,000원'), ('제육볶음', '11,000원'), ('비빔밥', '10,000원'), ('공기밥 추가', '1,000원')]:
            d.text((170, y), name, fill=(20, 20, 20), font=font(40)); d.text((600, y), price, fill=(20, 20, 20), font=font(40)); y += 90
    elif kind == 'sea':
        d.rectangle((0, 380, w, h), fill=(40, 110, 200)); d.ellipse((700, 70, 820, 190), fill=(255, 240, 150))
        d.polygon([(300, 380), (330, 300), (360, 380)], fill=(255, 255, 255))
    d.text((40, h - 90), title, fill=(30, 30, 30), font=font(44))
    d.text((40, h - 46), sub, fill=(90, 90, 90), font=font(28))
    return im

def exif_for(dt, make, model, gps=None):
    ex = Image.Exif()
    ex[0x010F] = make; ex[0x0110] = model
    ex.get_ifd(ExifTags.IFD.Exif)[0x9003] = dt
    ex.get_ifd(ExifTags.IFD.Exif)[0x9004] = dt
    if gps:
        g = ex.get_ifd(ExifTags.IFD.GPSInfo); g[1] = 'N'; g[2] = gps[0]; g[3] = 'E'; g[4] = gps[1]
    return ex

def set_mtime(p, s):
    t = time.mktime(datetime.strptime(s, '%Y-%m-%d %H:%M:%S').timetuple()); os.utime(p, (t, t))

if DUMP.exists():
    shutil.rmtree(OUT / 'inputs')
DUMP.mkdir(parents=True)
photos = [
    ('IMG_0001.jpg', 'cake', '할머니 생신 케이크', '거실 식탁', '2026:10:03 11:05:12', 'samsung', 'SM-J700F', None),
    ('IMG_0002.jpg', 'cake', '촛불 끄기 전', '가족 모두 모임', '2026:10:03 11:08:40', 'samsung', 'SM-J700F', None),
    ('IMG_0003.jpg', 'cake', '선물 상자와 꽃다발', '생신 모임', '2026:10:03 12:30:05', 'samsung', 'SM-J700F', None),
    ('IMG_0004.jpg', 'park', '점심 뒤 산책', '아파트 앞 공원', '2026:10:03 14:10:00', 'Apple', 'iPhone 12', ((37, 33, 0), (126, 58, 0))),
    ('IMG_0005.jpg', 'park', '호수공원 벤치', '일요일 오후', '2026:10:04 15:20:33', 'Apple', 'iPhone 12', ((37, 39, 0), (126, 46, 0))),
    ('IMG_0006.jpg', 'park', '단풍 든 나무', '호수공원', '2026:10:04 15:41:10', 'Apple', 'iPhone 12', None),
    ('IMG_0007.jpg', 'park', '산책로 끝', '해 질 무렵', '2026:10:04 17:05:59', 'Apple', 'iPhone 12', None),
    ('IMG_0008.jpg', 'menu', '동네 식당 메뉴판', '가격 참고용', '2026:10:10 18:32:14', 'samsung', 'SM-J700F', None),
    ('IMG_0009.jpg', 'sea', '저녁 바다', '식당 창밖', '2026:10:10 19:02:47', 'samsung', 'SM-J700F', None),
]
manifest = []
for name, kind, title, sub, dt, make, model, gps in photos:
    im = scene(kind, title, sub)
    p = DUMP / name
    im.save(p, 'JPEG', quality=88, exif=exif_for(dt, make, model, gps).tobytes())
    set_mtime(p, '2026-10-12 09:00:00')  # 복사 시각(촬영일과 다름) — EXIF 가 먼저여야 한다
    manifest.append({'name': name, 'kind': 'photo', 'taken': dt, 'title': title, 'expect': 'album'})
# 정확 중복(바이트 동일, 다른 이름) 2건
shutil.copyfile(DUMP / 'IMG_0002.jpg', DUMP / 'IMG_0002 복사본.jpg'); set_mtime(DUMP / 'IMG_0002 복사본.jpg', '2026-10-12 09:00:00')
shutil.copyfile(DUMP / 'IMG_0006.jpg', DUMP / 'KakaoTalk_20261004_154110.jpg'); set_mtime(DUMP / 'KakaoTalk_20261004_154110.jpg', '2026-10-12 09:00:00')
manifest += [{'name': 'IMG_0002 복사본.jpg', 'kind': 'photo', 'expect': 'exact_duplicate_of IMG_0002.jpg'},
             {'name': 'KakaoTalk_20261004_154110.jpg', 'kind': 'photo', 'expect': 'exact_duplicate_of IMG_0006.jpg'}]
# 유사 중복(같은 촬영시각·같은 크기, 다른 바이트 — 재압축본): 옮기지 않고 보고만
im = Image.open(DUMP / 'IMG_0003.jpg'); ex = Image.open(DUMP / 'IMG_0003.jpg').getexif()
im.save(DUMP / 'IMG_0003_edit.jpg', 'JPEG', quality=60, exif=ex.tobytes()); set_mtime(DUMP / 'IMG_0003_edit.jpg', '2026-10-12 09:00:00')
manifest.append({'name': 'IMG_0003_edit.jpg', 'kind': 'photo', 'taken': '2026:10:03 12:30:05', 'expect': 'near_duplicate_candidate_of IMG_0003.jpg (not moved)'})
# EXIF 없는 스크린샷(PNG): 파일 시각으로 날짜, 표식 필요
im = Image.new('RGB', (800, 500), (30, 30, 30)); d = ImageDraw.Draw(im)
d.text((40, 40), '가족 단톡방', fill=(255, 255, 255), font=font(36)); d.text((40, 120), '엄마: 10월 3일 11시 집에서 모여요', fill=(255, 255, 200), font=font(30))
d.text((40, 180), '누나: 케이크는 내가 사갈게', fill=(200, 255, 255), font=font(30))
im.save(DUMP / 'Screenshot_2026-10-01.png'); set_mtime(DUMP / 'Screenshot_2026-10-01.png', '2026-10-01 20:15:00')
manifest.append({'name': 'Screenshot_2026-10-01.png', 'kind': 'photo', 'taken': None, 'expect': 'date_from_file_time 2026-10-01 flagged'})
# 손상 JPEG: 앞 2KB 만
data = (DUMP / 'IMG_0009.jpg').read_bytes()[:2048]
(DUMP / 'IMG_0099.jpg').write_bytes(data); set_mtime(DUMP / 'IMG_0099.jpg', '2026-10-12 09:00:00')
manifest.append({'name': 'IMG_0099.jpg', 'kind': 'photo', 'expect': 'unreadable (truncated) — reported, left in place'})
# 비매체 파일
(DUMP / 'notes.txt').write_text('생신 모임 장보기: 케이크, 과일, 초\n', encoding='utf-8')
manifest.append({'name': 'notes.txt', 'kind': 'other', 'expect': 'ignored but listed'})
# 음성 메모(say → m4a). 파일 시각으로 날짜
memos = [
    ('memo_01.m4a', '오늘 10월 3일 할머니 생신 모임. 케이크 촛불 끄고 사진 여러 장 찍었고 점심 먹고 공원 산책했다. 선물은 꽃다발과 스카프.', '2026-10-03 16:40:00'),
    ('memo_02.m4a', '10월 10일 저녁, 동네 식당에서 메뉴판 찍어 뒀다. 김치찌개 구천 원, 제육볶음 만 천 원. 창밖으로 바다가 보였다.', '2026-10-10 19:30:00'),
]
for name, text, mt in memos:
    aiff = DUMP / (name + '.aiff')
    subprocess.run(['say', '-v', 'Yuna', '-o', str(aiff), text], check=True)
    subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', str(aiff), str(DUMP / name)], check=True, capture_output=True)
    aiff.unlink(); set_mtime(DUMP / name, mt)
    manifest.append({'name': name, 'kind': 'audio', 'text': text, 'expect': 'transcribed → 음성/<date>'})
# 무음 메모 3초
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono', '-t', '3', '-c:a', 'aac', str(DUMP / 'memo_03.m4a')], check=True)
set_mtime(DUMP / 'memo_03.m4a', '2026-10-11 08:00:00')
manifest.append({'name': 'memo_03.m4a', 'kind': 'audio', 'text': '', 'expect': 'no speech → 음성/미분류 with reason'})
# 지문 기록(검증기용 — 독립 AI 입력 사본에는 넣지 않음)
for m in manifest:
    p = DUMP / m['name']; m['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest(); m['size'] = p.stat().st_size
(OUT / 'inputs/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
# 독립 AI 용 입력 사본(정답 없음)과 변형용 증분 파일은 run 시점에 만든다
(OUT / 'task.md').write_text((DOC / 'task.md').read_text())
print(OUT, len(manifest), 'files')
