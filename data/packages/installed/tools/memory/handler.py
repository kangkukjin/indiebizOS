"""
Memory & Skill Handler - 에이전트 메모리 + 도메인 지식 관리
"""
import json
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


def _get_agent_id():
    """현재 에이전트 ID 가져오기"""
    from thread_context import get_current_context
    ctx = get_current_context()
    return ctx.get("agent_id", "") if ctx else ""


def execute(tool_name: str, args: dict, project_path: str = ".") -> str:
    """메모리 & 스킬 도구 실행"""
    try:
        # 에이전트 메모리 도구
        if tool_name in ("memory_save", "memory_search", "memory_read", "memory_delete"):
            import memory_db
            agent_id = _get_agent_id()

            if tool_name == "memory_save":
                return _memory_save(memory_db, args, project_path, agent_id)
            elif tool_name == "memory_search":
                return _memory_search(memory_db, args, project_path, agent_id)
            elif tool_name == "memory_read":
                return _memory_read(memory_db, args, project_path, agent_id)
            elif tool_name == "memory_delete":
                return _memory_delete(memory_db, args, project_path, agent_id)

        # 스킬 도구
        import skill_db

        if tool_name == "skill_search":
            return _skill_search(skill_db, args)
        elif tool_name == "skill_read":
            return _skill_read(skill_db, args)
        elif tool_name == "skill_add":
            return _skill_add(skill_db, args)
        elif tool_name == "skill_delete":
            return _skill_delete(skill_db, args)
        elif tool_name == "skill_import_md":
            return _skill_import_md(skill_db, args)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============ 에이전트 메모리 도구 ============

def _memory_save(db, args, project_path, agent_id):
    content = args.get("content", "")
    if not content.strip():
        return json.dumps({"error": "content가 필요합니다."}, ensure_ascii=False)

    memory_id = db.save(
        project_path=project_path,
        agent_id=agent_id,
        content=content,
        keywords=args.get("keywords", ""),
        category=args.get("category", "")
    )

    return json.dumps({
        "memory_id": memory_id,
        "message": f"메모리 저장 완료 (ID: {memory_id})"
    }, ensure_ascii=False, indent=2)


def _memory_search(db, args, project_path, agent_id):
    query = args.get("query", "")
    if not query.strip():
        return json.dumps({"error": "query가 필요합니다."}, ensure_ascii=False)

    results = db.search(
        project_path=project_path,
        agent_id=agent_id,
        query=query,
        category=args.get("category"),
        limit=args.get("limit", 10)
    )

    return json.dumps({
        "count": len(results),
        "memories": results
    }, ensure_ascii=False, indent=2)


def _memory_read(db, args, project_path, agent_id):
    memory_id = args.get("memory_id")
    if not memory_id:
        return json.dumps({"error": "memory_id가 필요합니다."}, ensure_ascii=False)

    memory = db.read(project_path, agent_id, memory_id)
    if not memory:
        return json.dumps({"error": f"ID {memory_id} 메모리 없음"}, ensure_ascii=False)

    parts = [memory['content']]
    meta = []
    if memory.get('created_at'):
        meta.append(f"작성: {memory['created_at']}")
    if memory.get('used_at'):
        meta.append(f"최근참조: {memory['used_at']}")
    if memory['category']:
        meta.append(f"카테고리: {memory['category']}")
    if memory['keywords']:
        meta.append(f"키워드: {memory['keywords']}")
    if meta:
        parts.append(f"[{' | '.join(meta)}]")

    return "\n".join(parts)


def _memory_delete(db, args, project_path, agent_id):
    memory_id = args.get("memory_id")
    if not memory_id:
        return json.dumps({"error": "memory_id가 필요합니다."}, ensure_ascii=False)

    deleted = db.delete(project_path, agent_id, memory_id)
    return json.dumps({
        "deleted": deleted,
        "message": f"메모리 ID {memory_id} 삭제 완료" if deleted else "삭제 실패"
    }, ensure_ascii=False, indent=2)


# ============ 스킬 도구 ============

def _skill_search(db, args):
    query = args.get("query", "")
    if not query.strip():
        return json.dumps({"error": "query가 필요합니다."}, ensure_ascii=False)

    results = db.search(
        query,
        category=args.get("category"),
        limit=args.get("limit", 10)
    )

    return json.dumps({
        "count": len(results),
        "skills": results
    }, ensure_ascii=False, indent=2)


def _skill_read(db, args):
    skill_id = args.get("skill_id")
    if not skill_id:
        return json.dumps({"error": "skill_id가 필요합니다."}, ensure_ascii=False)

    skill = db.read(skill_id)
    if not skill:
        return json.dumps({"error": f"ID {skill_id} 스킬 없음"}, ensure_ascii=False)

    header = f"# {skill['name']}\n"
    if skill['description']:
        header += f"> {skill['description']}\n\n"
    meta = []
    if skill.get('updated_at'):
        meta.append(f"**업데이트**: {skill['updated_at']}")
    elif skill.get('created_at'):
        meta.append(f"**작성**: {skill['created_at']}")
    if skill['category']:
        meta.append(f"**카테고리**: {skill['category']}")
    if skill['keywords']:
        meta.append(f"**키워드**: {skill['keywords']}")
    if meta:
        header += " | ".join(meta) + "\n"
    header += "\n---\n\n"

    return header + skill['content']


def _skill_add(db, args):
    name = args.get("name")
    content = args.get("content")
    if not name or not content:
        return json.dumps({"error": "name과 content는 필수입니다."}, ensure_ascii=False)

    skill_id = db.add(
        name=name,
        content=content,
        keywords=args.get("keywords", ""),
        description=args.get("description", ""),
        category=args.get("category", ""),
        source=args.get("source", "manual")
    )

    return json.dumps({
        "skill_id": skill_id,
        "message": f"스킬 '{name}' 저장 완료 (ID: {skill_id})"
    }, ensure_ascii=False, indent=2)


def _skill_delete(db, args):
    skill_id = args.get("skill_id")
    if not skill_id:
        return json.dumps({"error": "skill_id가 필요합니다."}, ensure_ascii=False)

    skill = db.read(skill_id)
    if not skill:
        return json.dumps({"error": f"ID {skill_id} 스킬 없음"}, ensure_ascii=False)

    deleted = db.delete(skill_id)
    return json.dumps({
        "deleted": deleted,
        "message": f"스킬 '{skill['name']}' (ID: {skill_id}) 삭제 완료" if deleted else "삭제 실패"
    }, ensure_ascii=False, indent=2)


def _skill_import_md(db, args):
    import_all = args.get("import_all", False)

    if import_all:
        return _import_all(db, args)

    file_path = args.get("file_path")
    if not file_path:
        return json.dumps({"error": "file_path 또는 import_all=true가 필요합니다."}, ensure_ascii=False)

    if not os.path.isabs(file_path):
        file_path = os.path.join(db.SKILLS_DIR, file_path)

    if not os.path.exists(file_path):
        return json.dumps({"error": f"파일 없음: {file_path}"}, ensure_ascii=False)

    result = _import_single(db, file_path, args.get("category"), args.get("keywords"))
    return json.dumps({
        "message": f"스킬 '{result['name']}' 임포트 완료 (ID: {result['skill_id']})",
        **result
    }, ensure_ascii=False, indent=2)


def _import_all(db, args):
    skills_dir = db.SKILLS_DIR
    if not os.path.exists(skills_dir):
        return json.dumps({"error": f"디렉토리 없음: {skills_dir}"}, ensure_ascii=False)

    imported = []
    errors = []
    for fname in sorted(os.listdir(skills_dir)):
        if fname.endswith('.md'):
            fpath = os.path.join(skills_dir, fname)
            try:
                result = _import_single(db, fpath, args.get("category"), args.get("keywords"))
                imported.append(result)
            except Exception as e:
                errors.append(f"{fname}: {str(e)}")

    return json.dumps({
        "imported": len(imported),
        "errors": errors,
        "skills": imported
    }, ensure_ascii=False, indent=2)


def _import_single(db, file_path, category_override=None, extra_keywords=None):
    parsed = db.parse_md(file_path)

    if category_override:
        parsed['category'] = category_override
    if extra_keywords:
        existing = parsed.get('keywords', '')
        parsed['keywords'] = f"{existing},{extra_keywords}" if existing else extra_keywords

    skill_id = db.add(
        name=parsed['name'],
        content=parsed['content'],
        keywords=parsed.get('keywords', ''),
        description=parsed.get('description', ''),
        category=parsed.get('category', ''),
        source=parsed.get('source', f'file:{os.path.basename(file_path)}')
    )

    return {
        "skill_id": skill_id,
        "name": parsed['name'],
        "category": parsed.get('category', ''),
        "source": file_path
    }
