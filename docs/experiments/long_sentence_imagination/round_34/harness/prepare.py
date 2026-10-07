"""Synthetic inputs and independent minute-grid oracle (no IBL implementation)."""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-07_34회차'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def oracle(source):
    rooms = json.loads((source / 'rooms.json').read_text())
    bookings = json.loads((source / 'bookings.json').read_text())
    maintenance = json.loads((source / 'maintenance.json').read_text())
    good, bad = [], []
    for kind, rows in [('booking', bookings), ('maintenance', maintenance)]:
        for row in rows:
            if (row['room'] not in rooms or row['end'] is None or
                    not 0 <= row['start'] < row['end'] <= 1440):
                bad.append({'id': row['id'], 'kind': kind})
            else:
                good.append(dict(row, kind=kind))
    result = []
    for room in rooms:
        b, m = [0] * 1440, [0] * 1440
        for row in good:
            if row['room'] != room:
                continue
            counts = b if row['kind'] == 'booking' else m
            for minute in range(row['start'], row['end']):
                counts[minute] += 1
        result.append({'room': room, 'booked': sum(x > 0 for x in b),
                       'conflict': sum(x > 1 for x in b),
                       'maintenance': sum(x > 0 for x in m),
                       'blocked_booking': sum(x > 0 and y > 0 for x, y in zip(b, m)),
                       'free': sum(x == 0 and y == 0 for x, y in zip(b, m)),
                       'peak': max(b)})
    return {'rooms': result, 'invalid': bad}


def main():
    rng = random.Random(3407)
    rooms = [f'R{i:02}' for i in range(1, 41)]
    bookings, maintenance = [], []
    for i, room in enumerate(rooms[:-1]):
        for j in range(30):
            start = rng.randrange(0, 1380, 15)
            bookings.append({'id': f'B{i:02}-{j:02}', 'room': room,
                             'start': start, 'end': min(1440, start + rng.choice([15, 30, 60, 120]))})
        for j in range(5):
            start = rng.randrange(0, 1380, 30)
            maintenance.append({'id': f'M{i:02}-{j:02}', 'room': room,
                                'start': start, 'end': min(1440, start + 90)})
    bookings += [{'id': 'BAD-null', 'room': 'R01', 'start': 30, 'end': None},
                 {'id': 'BAD-reverse', 'room': 'R02', 'start': 90, 'end': 60},
                 {'id': 'BAD-room', 'room': 'R99', 'start': 30, 'end': 60}]
    for variant in ('base', 'variant', 'new'):
        bs, ms = list(bookings), list(maintenance)
        if variant == 'variant':
            ms = []
            bs = list(reversed(bs))
        if variant == 'new':
            bs = [{'id': 'N1', 'room': 'R01', 'start': 0, 'end': 720},
                  {'id': 'N2', 'room': 'R01', 'start': 720, 'end': 1440},
                  {'id': 'N3', 'room': 'R02', 'start': 60, 'end': 60}]
            ms = [{'id': 'MN1', 'room': 'R01', 'start': 600, 'end': 840}]
        source = OUT / 'source' / variant
        for name, value in [('rooms', rooms), ('bookings', bs), ('maintenance', ms)]:
            dump(source / (name + '.json'), value)
        dump(OUT / ('expected_' + variant + '.json'), oracle(source))


if __name__ == '__main__':
    main()
