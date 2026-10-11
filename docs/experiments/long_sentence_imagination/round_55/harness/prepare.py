"""55회차 합성 자료 생성 — 사용: prepare.py <mode: base|a|b|c> [--who trainer]
전부 합성(실제 사람·기록 없음). 정답표는 입력 폴더 밖 `_oracle/` 에 둔다(실행자에게 안 보임).
base: 접수 10건 + 측정 약 1,500행 / a: 다른 묶음 4건(역순 id·전건 측정 불량 1건) / b: base 와 같은 자료, 상담일만 2026-10-12 / c: 접수 0건."""
import argparse, csv, json, random, shutil
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-11_55회차'
TH = {'혈압': {'sys': 140, 'dia': 90}, '혈당': 126, '체온': 38.0}

BASE = {
 'H01': dict(kinds={'체온': (37.6, 0.6)}, urgent=False, text="""접수일 2026-10-12. 가명 김가온(41세).
나흘 전부터 열이 오르내리고 목이 아프다. 체온계가 집에 두 개라 하나는 화씨로 찍힌다.
먹는 약: 타이레놀정500밀리그람 1회 2정 하루 3번(10월 8일부터), 타이레놀콜드-에스정 1회 2정 하루 3번(10월 9일부터). 둘 다 약국에서 샀다.
기침은 심하지 않고 밥은 먹는다."""),
 'H02': dict(kinds={'혈압': (138, 86, 9)}, urgent=False, text="""접수일 2026-10-12. 가명 박나래(63세).
3년 전부터 혈압약을 먹는다. 요즘 아침 혈압이 예전보다 높게 나오는 것 같아 걱정이다. 두통은 없다.
먹는 약: 노바스크정5밀리그램 하루 1정(병원 처방, 2023년부터).
아침·저녁으로 재서 적어 두었다."""),
 'H03': dict(kinds={'혈당': (121, 11)}, urgent=False, text="""접수일 2026-10-12. 가명 이다솜(55세).
건강검진에서 공복혈당이 높다는 말을 듣고 8월 말부터 아침마다 재고 있다. 해외에서 산 측정기는 mmol/L 로 나온다.
환절기 비염이 있어 지르텍정을 하루 1정 먹는다(9월 15일부터).
체중은 변화 없다."""),
 'H04': dict(kinds={'혈압': (147, 92, 10)}, urgent=True, text="""접수일 2026-10-12. 가명 최라온(58세).
어깨와 허리가 아파서 왔다. 이삿짐을 나른 뒤로 2주째 쑤신다. 파스도 붙인다.
먹는 약: 이지엔6애니연질캡슐 1회 1캡슐 하루 3번(10월 1일부터), 탁센연질캡슐 1회 1캡슐 하루 2번(10월 5일부터).
그런데 어제저녁 계단을 오르다 가슴이 꽉 조이듯 답답하고 식은땀이 났고 왼팔이 저렸다. 10분쯤 쉬니 나아져서 그냥 잤다. 근육통 때문인 것 같다.
혈압은 가끔 잰다."""),
 'H05': dict(kinds={'체온': (37.2, 0.4)}, urgent=False, text="""접수일 2026-10-12. 가명 정마루(34세).
일주일째 콧물과 기침이 있다. 열은 심하지 않다.
먹는 약: 하늘맑음정 하루 2번 1정씩(지인이 준 것, 10월 6일부터), 판콜에스내복액 1회 1병 하루 3번(10월 7일부터).
잠은 잘 잔다."""),
 'H06': dict(kinds={'체온': (36.9, 0.3)}, urgent=False, text="""접수일 2026-10-12. 가명 한바다(47세).
한 달 넘게 두통이 잦다. 오후에 심해진다.
먹는 약: 게보린정은 1회 1정씩 먹다가 9월 30일에 끊었고, 지금은 타이레놀정500밀리그람을 아플 때 1회 1정 먹는다(10월 1일부터).
커피를 하루 넉 잔 마신다."""),
 'H07': dict(kinds={'체온': (37.4, 0.5)}, urgent=False, text="""접수일 2026-10-12. 가명 서사랑(29세).
감기 기운과 생리통이 겹쳤다. 사흘째다.
먹는 약: 게보린정(몇 알씩 먹는지 기억 안 남, 아플 때마다), 판콜에스내복액 1회 1병 하루 3번. 둘 다 10월 10일부터.
속이 조금 쓰리다."""),
 'H08': dict(kinds={'혈압': (151, 94, 11)}, urgent=True, text="""접수일 2026-10-12. 가명 윤아라(71세).
혈압이 높다는 말을 들은 지 오래됐다. 요즘 어지러울 때가 있다.
먹는 약: 아스피린프로텍트정100밀리그람 하루 1정(5년 전부터).
오늘 아침 세수하다가 갑자기 오른손에 힘이 빠져 수건을 떨어뜨렸고 말이 어눌하게 나왔다고 딸이 그랬다. 20분쯤 지나니 괜찮아져서 예약한 날 가면 될 것 같다.
혈압은 딸이 재서 적어 준다."""),
 'H09': dict(kinds={'혈당': (133, 13)}, urgent=False, text="""접수일 2026-10-12. 가명 임자람(52세).
당뇨 전단계라는 말을 듣고 식단을 조절하고 있다. 아침 공복혈당을 재고 있다.
내가 먹는 약은 지르텍정 하루 1정뿐이다(10월 3일부터, 두드러기 때문).
같이 사는 어머니는 아스피린프로텍트정100밀리그람을 매일 드시는데 그건 내 약이 아니다.
다리에 쥐가 자주 난다."""),
 'H10': dict(kinds={}, urgent=False, text="""접수일 2026-10-12. 가명 조차미(38세).
지난주 화요일부터 오른쪽 무릎이 붓고 계단을 내려갈 때 아프다. 넘어진 적은 없다.
먹는 약은 없다. 잰 기록도 없다.
주말에 등산을 다녀왔다."""),
}
VAR_A = {
 'K04': dict(kinds={'체온': (38.3, 0.5)}, urgent=False, text="""접수일 2026-10-12. 가명 구하람(8세, 보호자 작성).
이틀째 열이 난다. 잘 놀다가도 처진다.
먹는 약: 어린이타이레놀현탁액 1회 10mL 하루 4번(10월 11일부터), 판콜에스내복액도 반 병씩 먹였다(10월 11일부터).
물은 잘 마신다."""),
 'K03': dict(kinds={'혈압': (128, 80, 7)}, urgent=False, bad_all=True, text="""접수일 2026-10-12. 가명 남보라(60세).
혈압계를 새로 샀는데 재는 법을 모르겠다. 적어 온 숫자가 맞는지 모르겠다.
먹는 약: 없음.
어지럽지는 않다."""),
 'K02': dict(kinds={'혈당': (118, 9)}, urgent=True, text="""접수일 2026-10-12. 가명 도새벽(66세).
혈당을 재고 있다. 요즘 숨이 좀 차다.
먹는 약: 탁센연질캡슐 1회 1캡슐 하루 2번(무릎 때문, 9월 20일부터).
사흘 전부터 가만히 누워 있어도 숨이 차서 베개를 세 개 받치고 자고, 어젯밤에는 숨이 막혀 깨서 창문을 열고 한참 앉아 있었다. 입술이 파랗다는 말을 들었다. 나이 탓인 것 같다."""),
 'K01': dict(kinds={}, urgent=False, text="""접수일 2026-10-12. 가명 류시내(45세).
그저께부터 눈이 가렵고 재채기가 난다.
먹는 약: 지르텍정 하루 1정(10월 10일부터), 달빛고요캡슐 하루 1캡슐(인터넷에서 삼).
다른 불편은 없다."""),
}


def gen_rows(cid, spec, rng, start, end):
    rows = []
    d = start
    while d <= end:
        if rng.random() < 0.12:            # 빠진 날
            d += timedelta(days=1); continue
        for kind, p in spec['kinds'].items():
            times = ['07:30', '21:10'] if kind == '혈압' else ['07:10'] if kind == '혈당' else ['08:00', '20:30']
            for t in times:
                if rng.random() < 0.08: continue
                bad = spec.get('bad_all') or rng.random() < 0.03
                if kind == '혈압':
                    s = round(rng.gauss(p[0], p[2])); di = round(rng.gauss(p[1], p[2] * 0.6))
                    val, unit = f'{s}/{di}', 'mmHg'
                elif kind == '혈당':
                    v = round(rng.gauss(p[0], p[1]))
                    if rng.random() < 0.3: val, unit = f'{v / 18:.1f}', 'mmol/L'
                    else: val, unit = str(v), 'mg/dL'
                else:
                    v = round(rng.gauss(p[0], p[1]), 1)
                    if rng.random() < 0.35: val, unit = f'{v * 9 / 5 + 32:.1f}', '℉'
                    else: val, unit = f'{v:.1f}', '℃'
                if bad: val = rng.choice(['측정 실패', '', '약 130', 'Err'])
                rows.append([cid, f'{d.isoformat()} {t}', kind, val, unit])
        d += timedelta(days=1)
    return rows


def stats(rows, consult):
    """정답 계산 — 프로그램과 독립. 단위 환산: mmol/L×18, (℉-32)×5/9. 최근 7일 = 상담일 전 7일(상담일 제외)."""
    cd = date.fromisoformat(consult)
    out = {}
    for cid, at, kind, val, unit in rows:
        st = out.setdefault(cid, {}).setdefault(kind, {'vals': [], 'invalid': 0})
        try:
            if kind == '혈압':
                s, di = val.split('/'); v = (float(s), float(di))
            else:
                v = float(val)
                if unit == 'mmol/L': v = v * 18
                if unit == '℉': v = (v - 32) * 5 / 9
                v = (v,)
        except ValueError:
            st['invalid'] += 1; continue
        st['vals'].append((date.fromisoformat(at[:10]), v))
    res = {}
    for cid, kinds in out.items():
        for kind, st in kinds.items():
            vals = st['vals']
            if not vals:
                res.setdefault(cid, {})[kind] = {'n': 0, 'invalid': st['invalid']}; continue
            mean = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
            rec = [v for d, v in vals if cd - timedelta(days=7) <= d < cd]
            pri = [v for d, v in vals if d < cd - timedelta(days=7)]
            if kind == '혈압':
                over = {d for d, v in vals if v[0] >= TH['혈압']['sys'] or v[1] >= TH['혈압']['dia']}
                r = {'n': len(vals), 'invalid': st['invalid'], 'mean_sys': mean([v[0] for _, v in vals]), 'mean_dia': mean([v[1] for _, v in vals]),
                     'recent7': mean([v[0] for v in rec]), 'prior': mean([v[0] for v in pri]), 'over_days': len(over)}
            else:
                over = {d for d, v in vals if v[0] >= TH[kind]}
                r = {'n': len(vals), 'invalid': st['invalid'], 'mean': mean([v[0] for _, v in vals]),
                     'recent7': mean([v[0] for v in rec]), 'prior': mean([v[0] for v in pri]), 'over_days': len(over)}
            res.setdefault(cid, {})[kind] = r
    return res


def main():
    p = argparse.ArgumentParser(); p.add_argument('mode'); p.add_argument('--who', default='trainer'); a = p.parse_args()
    cases = {'base': BASE, 'b': BASE, 'a': VAR_A, 'c': {}}[a.mode]
    consult = '2026-10-12' if a.mode == 'b' else '2026-10-19'
    base = OUT / a.who / a.mode
    shutil.rmtree(base, ignore_errors=True)
    (base / 'input/intake').mkdir(parents=True); (base / 'out').mkdir(); (base / '_oracle').mkdir()
    rng = random.Random(5500 + (7 if a.mode == 'a' else 0))
    rows = []
    for cid, spec in cases.items():
        (base / 'input/intake' / f'{cid}.md').write_text(spec['text'] + '\n')
        rows += gen_rows(cid, spec, rng, date(2026, 8, 20), date(2026, 10, 18))
    rng.shuffle(rows)
    with open(base / 'input/measurements.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['case_id', 'measured_at', 'kind', 'value', 'unit']); w.writerows(rows)
    job = {'office': '느티나무 마을 건강상담 창구', 'consult_date': consult, 'note': '의료 자문·진단이 아니라 진료 전 준비 자료',
           'thresholds': TH, 'unit_note': '혈당 1 mmol/L = 18 mg/dL, 체온 ℃ = (℉ - 32) × 5/9. 최근 7일 = 상담일 전 7일(상담일 제외), 그 전 = 그보다 앞선 모든 날.'}
    (base / 'input/job.json').write_text(json.dumps(job, ensure_ascii=False, indent=1))
    st = stats(rows, consult)
    total_over = lambda cid: sum(k.get('over_days', 0) for k in st.get(cid, {}).values())
    order = sorted(cases, key=lambda c: (not cases[c]['urgent'], -total_over(c), c))
    exp = {'consult_date': consult, 'ids': sorted(cases), 'urgent': sorted(c for c in cases if cases[c]['urgent']), 'stats': st, 'order': order, 'rows': len(rows)}
    (base / '_oracle/expected.json').write_text(json.dumps(exp, ensure_ascii=False, indent=1))
    print(a.who, a.mode, 'cases', len(cases), 'rows', len(rows), 'order', order)


if __name__ == '__main__':
    main()
