# 5회차 합성 입력 생성기 — 영수증 PDF 12장 + 카드 명세서 CSV (seed 고정, 비민감)
# 실행: indiebizOS/.venv/bin/python3 gen.py <출력폴더> [variant]
import csv, json, sys, os
import pymupdf

OUT = sys.argv[1]
VARIANT = sys.argv[2] if len(sys.argv) > 2 else ''
os.makedirs(f'{OUT}/receipts', exist_ok=True)

# id, 가맹점(영수증 표기), 카드 표기, 날짜, 품목[(이름,수량,단가)], 카드 금액(None=카드 내역 없음), 형태
R = [
 ('R01', '스타벅스 강남대로점', 'STARBUCKS 강남대로', '2026-09-01', [('아메리카노', 3, 4500), ('카페라떼', 2, 5000)], 'same', 'text'),
 ('R02', '(주)한솥 역삼점', '한솥도시락역삼', '2026-09-02', [('치킨마요', 5, 4900)], 'same', 'table'),
 ('R03', '교보문고 광화문', '교보문고', '2026-09-03', [('파이썬 책', 1, 36000), ('노트', 3, 3000)], 54000, 'text'),   # 금액 불일치(영수증 45,000)
 ('R04', '카카오T 택시', '카카오T', '2026-09-04', [('운임', 1, 18700)], 'same', 'text'),
 ('R05', '오피스디포 선릉', 'OFFICE DEPOT', '2026-09-05', [('A4 용지', 4, 5500), ('토너', 1, 89000)], 'same', 'table'),
 ('R06', '본죽 삼성점', '본죽삼성', '2026-09-08', [('전복죽', 2, 13000)], 'same', 'text'),
 ('R07', '동네 문구점', None, '2026-09-09', [('포스트잇', 2, 2500)], None, 'text'),          # 카드 내역 없음(현금)
 ('R08', '코레일 KTX', '코레일', '2026-09-10', [('서울-부산', 2, 59800)], 'same', 'table'),    # 119,600 ≥ 100,000 결재 필요
 ('R09', '이디야 선릉역점', 'EDIYA선릉', '2026-09-11', [('아메리카노', 6, 3200)], 'dup', 'text'), # 카드 중복 청구
 ('R10', '쿠팡', '쿠팡(주)', '2026-09-12', [('모니터암', 1, 42900)], 'same', 'text'),
 ('R11', '김밥천국 역삼', '김밥천국', '2026-09-15', [('라면', 3, 5000)], 'same', 'image'),      # 글자 층 없음(스캔)
 ('R12', 'GS25 테헤란', 'GS25테헤란', '2026-09-16', [('생수', 10, 900)], 'same', 'broken'),     # 깨진 파일
]
CARD_ONLY = [('2026-09-06', '우버 택시', 23400)]   # 영수증 누락
EXTRA = []
if VARIANT == 'B':
    # 변형: 같은 영수증이 다른 이름으로 두 번 스캔됨 + 영수증 1장 추가
    EXTRA = [('R13', '이디야 선릉역점', 'EDIYA선릉', '2026-09-11', [('아메리카노', 6, 3200)], 'copyof:R09', 'text'),
             ('R14', '다이소 역삼', '다이소역삼', '2026-09-17', [('수납함', 3, 3000)], 'same', 'table')]

def total(items): return sum(q * p for _, q, p in items)

def pdf(rid, merch, date, items, kind):
    path = f'{OUT}/receipts/{rid}.pdf'
    if kind == 'broken':
        open(path, 'wb').write(b'%PDF-1.7\n1 0 obj << /Type /Catalog >>\n%%truncated')
        return
    doc = pymupdf.open(); page = doc.new_page(width=300, height=420)
    lines = [f'{merch}', f'거래일시 {date} 12:{int(rid[1:]) % 60:02d}', '-' * 30]
    if kind == 'table':
        lines += ['품목        수량     금액'] + [f'{n:<10} {q:>3} {q * p:>9,}' for n, q, p in items]
    else:
        lines += [f'{n} x{q} @{p:,}원' for n, q, p in items]
    lines += ['-' * 30, f'합계 금액 {total(items):,}원', '카드 승인' if kind != 'cash' else '현금']
    if kind == 'image':
        # 글자를 그림으로만 넣는다(글자 층 없음)
        tmp = pymupdf.open(); tp = tmp.new_page(width=300, height=420)
        y = 30
        for l in lines: tp.insert_text((20, y), l, fontname='korea', fontsize=10); y += 16
        pix = tp.get_pixmap(dpi=100); page.insert_image(page.rect, pixmap=pix)
    else:
        y = 30
        for l in lines: page.insert_text((20, y), l, fontname='korea', fontsize=10); y += 16
    doc.save(path)

rows = []
for rid, merch, cardname, date, items, card, kind in R + EXTRA:
    if not str(card).startswith('copyof'):
        pdf(rid, merch, date, items, kind)
    else:
        src = card.split(':')[1]
        import shutil; shutil.copy(f'{OUT}/receipts/{src}.pdf', f'{OUT}/receipts/{rid}.pdf')
        continue
    if card is None: continue
    amt = total(items) if card in ('same', 'dup') else card
    rows.append((date, cardname, amt))
    if card == 'dup': rows.append((date, cardname, amt))
for d, n, a in CARD_ONLY: rows.append((d, n, a))
rows.sort()
with open(f'{OUT}/card_statement.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['승인일', '가맹점', '금액', '승인번호'])
    for i, (d, n, a) in enumerate(rows): w.writerow([d, n, a, f'A{1000 + i}'])
json.dump({'정책': {'결재필요_금액': 100000}}, open(f'{OUT}/policy.json', 'w'), ensure_ascii=False)
print('receipts', len(os.listdir(f'{OUT}/receipts')), 'card rows', len(rows))
for rid, merch, cardname, date, items, card, kind in R + EXTRA: print(rid, total(items), card, kind)
