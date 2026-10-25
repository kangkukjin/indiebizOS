"""Executable-example projection; original rows remain the historical record."""


def ensure_current_examples(conn):
    columns = {row[1] for row in conn.execute('PRAGMA table_info(ibl_examples)')}
    if 'executable' not in columns:
        conn.execute('ALTER TABLE ibl_examples ADD COLUMN executable INTEGER NOT NULL DEFAULT 0')
    conn.execute('CREATE INDEX IF NOT EXISTS ibl_examples_current ON ibl_examples(alias,id) WHERE executable=1')
    conn.execute('CREATE VIEW IF NOT EXISTS ibl_current_examples AS SELECT * FROM ibl_examples WHERE executable=1')


def ensure_search_index(conn):
    """Only admitted examples enter the search index, including after edits."""
    conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS ibl_current_fts USING fts5(
        intent, ibl_code, content='ibl_current_examples', content_rowid='id',
        tokenize='unicode61')""")
    for event, timing, row, operation in (
        ('insert', 'INSERT', 'new', ''),
        ('delete', 'DELETE', 'old', 'delete'),
        ('update_remove', 'UPDATE', 'old', 'delete'),
        ('update_add', 'UPDATE', 'new', ''),
    ):
        columns = 'ibl_current_fts, ' if operation else ''
        values = "'delete', " if operation else ''
        conn.execute(f"""CREATE TRIGGER IF NOT EXISTS ibl_current_{event}
            AFTER {timing} ON ibl_examples WHEN {row}.executable=1 BEGIN
            INSERT INTO ibl_current_fts({columns}rowid, intent, ibl_code)
            VALUES ({values}{row}.id, {row}.intent, {row}.ibl_code); END""")
