"""
skill_db.py - 스킬 시스템 SQLite 저장소
도메인 지식(스킬)을 DB에 저장하고 키워드 기반으로 검색
"""
import os
import re
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict

# 경로 설정
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
# data/packages/installed/tools/skill-system/ → data/
_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_PACKAGE_DIR)))),
)
SKILLS_DIR = os.path.join(_DATA_DIR, 'skills')
DB_PATH = os.path.join(SKILLS_DIR, 'skills.db')


def get_db():
    """DB 연결 및 테이블 초기화"""
    os.makedirs(SKILLS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.executescript('''
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            description TEXT DEFAULT '',
            content TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_skills_keywords ON skills(keywords);
        CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
        CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
    ''')
    return conn


def search(query: str, category: str = None, limit: int = 10) -> List[Dict]:
    """키워드 기반 스킬 검색

    query를 공백으로 분리, 각 단어를 keywords/name/description에 LIKE 검색 (OR)
    """
    conn = get_db()
    try:
        words = query.strip().split()
        if not words:
            return []

        conditions = []
        params = []
        for word in words:
            w = f"%{word}%"
            conditions.append("(keywords LIKE ? OR name LIKE ? OR description LIKE ?)")
            params.extend([w, w, w])

        where = " OR ".join(conditions)

        if category:
            where = f"({where}) AND category = ?"
            params.append(category)

        first = f"%{words[0]}%"
        sql = f"""
            SELECT id, name, category, keywords, description, source, created_at
            FROM skills
            WHERE {where}
            ORDER BY
                CASE
                    WHEN name LIKE ? THEN 1
                    WHEN keywords LIKE ? THEN 2
                    ELSE 3
                END,
                updated_at DESC
            LIMIT ?
        """
        params.extend([first, first, limit])

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def read(skill_id: int) -> Optional[Dict]:
    """스킬 전문 조회"""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add(name: str, content: str, keywords: str = "",
        description: str = "", category: str = "",
        source: str = "manual") -> int:
    """스킬 추가 (같은 name이면 업데이트)"""
    conn = get_db()
    try:
        now = datetime.now().isoformat()
        conn.execute("""
            INSERT INTO skills (name, category, keywords, description, content, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                category = excluded.category,
                keywords = excluded.keywords,
                description = excluded.description,
                content = excluded.content,
                source = excluded.source,
                updated_at = excluded.updated_at
        """, (name, category, keywords, description, content, source, now, now))
        conn.commit()

        row = conn.execute("SELECT id FROM skills WHERE name = ?", (name,)).fetchone()
        return row['id'] if row else -1
    finally:
        conn.close()


def delete(skill_id: int) -> bool:
    """스킬 삭제"""
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def count() -> int:
    """스킬 총 개수"""
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
    finally:
        conn.close()


def parse_md(file_path: str) -> Dict[str, str]:
    """SKILL.md 파일 파싱 (frontmatter + content 분리)

    지원 형식:
    1. YAML frontmatter (---로 감싼 블록) - Claude knowledge-work-plugins 호환
    2. 일반 마크다운 (첫 # 제목을 name으로)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()

    result = {
        'name': '',
        'description': '',
        'keywords': '',
        'category': '',
        'content': text,
        'source': f'file:{os.path.basename(file_path)}'
    }

    # YAML frontmatter 파싱
    fm = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', text, re.DOTALL)
    if fm:
        for line in fm.group(1).split('\n'):
            line = line.strip()
            if ':' in line:
                key, val = line.split(':', 1)
                key = key.strip().lower()
                val = val.strip().strip('"').strip("'")
                if key in result:
                    result[key] = val
        result['content'] = fm.group(2).strip()
    else:
        # frontmatter 없으면 첫 # 제목을 name으로
        title = re.match(r'^#\s+(.+)', text, re.MULTILINE)
        if title:
            result['name'] = title.group(1).strip()

    # name이 없으면 파일명에서 추출
    if not result['name']:
        result['name'] = os.path.splitext(os.path.basename(file_path))[0]

    return result
