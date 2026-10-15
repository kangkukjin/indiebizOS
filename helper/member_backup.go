package main

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Snapshot before candidate schema initialization. Includes committed WAL pages.
func memberDatabaseBackup(source, target string) error {
	if info, e := os.Stat(source); e != nil || !info.Mode().IsRegular() {
		return fmt.Errorf("회원 DB를 확인할 수 없습니다")
	}
	if _, e := os.Lstat(target); !os.IsNotExist(e) {
		return fmt.Errorf("백업 대상은 새 파일이어야 합니다")
	}
	if e := os.MkdirAll(filepath.Dir(target), 0700); e != nil {
		return e
	}
	db, e := sql.Open("sqlite", source)
	if e != nil {
		return e
	}
	defer db.Close()
	var check string
	if e = db.QueryRow("PRAGMA quick_check").Scan(&check); e != nil || check != "ok" {
		return fmt.Errorf("회원 DB 무결성 검사 실패")
	}
	if _, e = db.Exec("VACUUM INTO '" + strings.ReplaceAll(target, "'", "''") + "'"); e != nil {
		return e
	}
	return os.Chmod(target, 0600)
}
