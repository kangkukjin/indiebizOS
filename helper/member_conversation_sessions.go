package main

import "time"

// Older member records had no task owner. Attach them once without rewriting their text.
func (m *MemberRuntime) migrateConversationSessions() error {
	root := m.workspace()
	tx, err := m.store.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var count int
	if err = tx.QueryRow("SELECT count(*) FROM conversations WHERE coalesce(task_id,'')=''").Scan(&count); err != nil {
		return err
	}
	if count == 0 {
		return tx.Commit()
	}
	stamp := time.Now().Unix()
	const sid = "legacy-conversation"
	if _, err = tx.Exec("INSERT OR IGNORE INTO tasks VALUES(?, '기존 대화', ?, 'idle', '{}', ?, ?)", sid, root, stamp, stamp); err != nil {
		return err
	}
	// JSON strings use the same event representation as live member conversations.
	if _, err = tx.Exec(`INSERT INTO task_events(task_id,kind,content)
        SELECT ?,kind,json_quote(content) FROM (
            SELECT rowid AS position,0 AS part,'user' AS kind,user AS content FROM conversations WHERE coalesce(task_id,'')=''
            UNION ALL SELECT rowid,1,'assistant',assistant FROM conversations WHERE coalesce(task_id,'')=''
        ) WHERE coalesce(content,'')!='' ORDER BY position,part`, sid); err != nil {
		return err
	}
	if _, err = tx.Exec("UPDATE conversations SET task_id=? WHERE coalesce(task_id,'')=''", sid); err != nil {
		return err
	}
	return tx.Commit()
}
