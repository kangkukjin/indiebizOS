"""Batch ingestion through the same syntax, signature and ownership gates."""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def add_examples_batch(db, examples, *, owned_vocabulary=False):
    from ibl_usage_db import _syntax_reason, _signature_of, _norm_topic, _tree_refresh
    if not examples:
        return 0

    bad = [(ex['ibl_code'], _syntax_reason(
        ex['ibl_code'], function_body=bool(ex.get('alias')) or ex.get('category') == "phrase"))
        for ex in examples]
    bad = [(c, r) for c, r in bad if r]
    if bad:
        logger.warning(
            f"[IBL Usage DB] 파싱 불가 용례 {len(bad)}건 거부(입구 구문-게이트): "
            + "; ".join(f"{r} / {c[:60]}" for c, r in bad[:5])
            + (" …" if len(bad) > 5 else ""))
        _badset = {c for c, _ in bad}
        examples = [ex for ex in examples if ex['ibl_code'] not in _badset]
        if not examples:
            return 0

    from ibl_registry import code_is_owned
    dropped = [ex['ibl_code'] for ex in examples
               if (not code_is_owned(ex['ibl_code']) if owned_vocabulary
                   else db._is_foreign_vocab(ex['ibl_code']))]
    if dropped:
        logger.warning(
            f"[IBL Usage DB] 남의 어휘 용례 {len(dropped)}건 거부(입구 소유-게이트): "
            + "; ".join(dropped[:5]) + (" …" if len(dropped) > 5 else ""))
        examples = [ex for ex in examples if ex['ibl_code'] not in set(dropped)]
        if not examples:
            return 0

    now = datetime.now().isoformat()
    ids = []

    with db._get_connection() as conn:
        for ex in examples:
            cursor = conn.execute(
                """INSERT INTO ibl_examples
                   (intent, ibl_code, nodes, category, difficulty, source, tags, created_at, updated_at, topic, alias, signature, returns, provenance)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ex['intent'], ex['ibl_code'],
                    ex.get('nodes', ''), ex.get('category', 'single'),
                    ex.get('difficulty', 1), ex.get('source', 'synthetic'),
                    ex.get('tags', ''), now, now, _norm_topic(ex.get('topic', '')),
                    ex.get('alias', ''), _signature_of(ex['ibl_code']), ex.get('returns', ''),
                    json.dumps(ex.get('provenance') or {}, ensure_ascii=False)
                )
            )
            ids.append(cursor.lastrowid)
        conn.commit()

    # 배치 임베딩
    db._index_batch(ids, examples)
    _tree_refresh(*[ex.get('topic', '') for ex in examples])
    logger.info(f"[IBL Usage DB] 배치 추가 완료: {len(ids)}개")
    return len(ids)
