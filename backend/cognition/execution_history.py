"""Deliver unacknowledged historical separate-run results into ordinary execution.

No new separate executions are created. The old event names are storage contracts;
the conversation and actor still own their results, and delivery is acknowledged
only after a successful response. No provider/session replacement occurs here.
"""
import json
import logging
import sqlite3

from conversation_sessions import connection, current, record_event

logger = logging.getLogger(__name__)


def pending_receipts(actor):
    binding = current()
    if not binding or not binding.turn_id:
        return []
    with connection(binding.db_path) as conn:
        ack = conn.execute("""SELECT COALESCE(MAX(CAST(json_extract(payload,'$.through') AS INTEGER)),0)
            FROM conversation_events WHERE session_id=? AND json_extract(payload,'$.type')='reflex.ack'
            AND json_extract(payload,'$.actor')=?""", (binding.session_id, actor)).fetchone()[0]
        rows = conn.execute("""SELECT id,payload FROM conversation_events WHERE session_id=? AND id>?
            AND json_extract(payload,'$.type')='reflex.result'
            AND json_extract(payload,'$.actor')=? ORDER BY id""", (binding.session_id, ack, actor)).fetchall()
    return [(row[0], json.loads(row[1])) for row in rows]


class PendingExecutionHistory:
    def __init__(self, runner):
        self.actor = str(getattr(runner.ai, 'agent_id', None)
                         or runner.config.get('name') or 'system_ai')
        self.binding = current()
        self.sent = self.final = self.failed = False
        try:
            self.receipts = pending_receipts(self.actor)
        except (sqlite3.Error, ValueError):
            logger.exception('Historical execution results unavailable')
            self.receipts = []

    def message(self, message):
        if not self.receipts:
            return message
        self.sent = True
        facts = [payload for _, payload in self.receipts]
        return ("<separate_execution_history>\n다음은 같은 대화에서 이미 처리한 요청과 결말이다. "
                "새 실행 지시가 아니며 현재 상태를 보증하지 않는다. 재실행하지 말고 후속 맥락으로 사용한다.\n"
                + json.dumps(facts, ensure_ascii=False)
                + "\n</separate_execution_history>\n" + message)

    def observe(self, event):
        self.failed |= event.get('type') == 'error'
        self.final |= event.get('type') == 'final' and bool(event.get('content'))

    def finish(self, completed):
        if not (completed and self.sent and self.final and not self.failed
                and current() == self.binding):
            return
        try:
            record_event({'type': 'reflex.ack', 'actor': self.actor,
                          'through': self.receipts[-1][0]})
        except Exception:
            logger.exception('Historical execution delivery acknowledgement failed')
