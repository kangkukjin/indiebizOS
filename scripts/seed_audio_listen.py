"""파일 듣기·전사·음악 검수 용례를 해마와 재학습 코퍼스에 멱등 시딩한다."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

SEEDS = [
    ("이 녹음 파일을 듣고 받아써줘", '[sense:listen]{path:"녹음.m4a", op:"transcribe"}'),
    ("강연 영상에서 발화를 텍스트로 뽑아줘", '[sense:listen]{path:"강연.mp4", op:"transcribe"}'),
    ("인터뷰 음성을 단어별 시각과 함께 전사해줘", '[sense:listen]{path:"인터뷰.wav", timestamps:true}'),
    ("음악 파일을 듣고 노래 사이에 대화가 남았는지 확인해", '[sense:listen]{path:"편집본.mp3", question:"노래와 말하기를 구분하고 대화가 남았는지 확인해줘"}'),
    ("마이크 없이 저장된 소리를 분석해줘", '[sense:listen]{path:"소리.flac", op:"analyze", question:"어떤 소리인가?"}'),
    ("음악의 접합 전후 구간을 들어봐", '[sense:listen]{path:"노래.mp3", question:"노래가 도중에 끊기거나 대화가 남았는가?", start:120, end:140}'),
    ("이 오디오의 시작과 끝 두 구간만 들어봐", '[sense:listen]{path:"음악.wav", ranges:[{start:0,end:7},{start:53,end:60}], question:"대화나 갑작스러운 잘림이 있는가?"}'),
    ("오디오 파일의 무음과 채널별 음량을 측정해줘", '[sense:listen]{path:"음악.wav", op:"inspect"}'),
    ("AI 호출 없이 접합 부분의 신호를 검사해줘", '[sense:listen]{path:"편집본.mp3", op:"inspect", start:120, end:140}'),
    ("전사 중단 후 완료된 구간은 재사용해 이어서 처리해", '[sense:listen]{path:"강연.m4a", op:"transcribe", segment_seconds:120}'),
    ("Listen to this audio file and identify speech versus singing", '[sense:listen]{path:"song.mp3", question:"Identify speech versus singing; mark uncertain intervals"}'),
    ("Transcribe this recording with word timestamps", '[sense:listen]{path:"interview.wav", op:"transcribe", timestamps:true}'),
    ("지금 마이크로 내 말을 받아써", '[sense:listen]{op:"transcribe"}'),
    ("마이크로 5초 녹음해줘", '[sense:listen]{op:"record", duration_sec:5}'),
    ("노래 두 파일의 무음 구간을 각각 확인해줘", '[sense:listen]{path:"첫곡.mp3", op:"inspect"} & [sense:listen]{path:"둘째곡.mp3", op:"inspect"}'),
    ("전사한 긴 본문을 다시 오디오 분석하지 말고 읽어줘", '$audio = [sense:listen]{path:"강연.m4a", op:"transcribe"}\n[self:read]{path:"$audio.transcript_path"}'),
]


def main():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패"
    with sqlite3.connect(ROOT / "data/ibl_usage.db") as conn:
        have = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    rows = [{"intent": intent, "ibl_code": code, "nodes": "sense,self" if "[self:" in code else "sense",
             "source": "manual_seed", "category": "pipeline" if "[self:" in code or " & " in code else "single",
             "tags": "audio-listen,파일청취,전사,음악검수"} for intent, code in SEEDS if intent not in have]
    added = db.add_examples_batch(rows)
    assert added == len(rows), "시드 일부가 거부되었습니다"
    target = ROOT / "data/training/ibl_distilled.json"
    corpus = json.loads(target.read_text())
    known = {(r.get("intent"), r.get("ibl_code")) for r in corpus}
    for intent, code in SEEDS:
        if (intent, code) not in known:
            corpus.append({"intent": intent, "ibl_code": code, "source": "manual_seed"})
    target.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"audio listen: {added} examples added and indexed")
    for query in ("음악 파일을 듣고 대화가 남았는지 확인", "녹음 파일 받아쓰기"):
        hits = db.search_hybrid(query, top_k=3)
        print(query, [(getattr(h, "ibl_code", "")[:100], round(getattr(h, "score", 0), 3)) for h in hits])


if __name__ == "__main__":
    main()
