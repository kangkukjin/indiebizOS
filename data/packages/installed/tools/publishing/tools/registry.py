"""출판 프로젝트 레지스트리 — 출판 프로젝트(책) 목록 관리 (플랜/버전 구조)"""

import json
import os
import re
import yaml
from datetime import datetime
from pathlib import Path

# indiebizOS 루트에서 projects/출판사/outputs/books 로 접근
# __file__: data/packages/installed/tools/publishing/tools/registry.py → 6번 올라가야 루트
_INDIEBIZ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", ".."))
BOOKS_DIR = os.path.join(_INDIEBIZ_ROOT, "projects", "출판사", "outputs", "books")


def _ensure_books_dir():
    os.makedirs(BOOKS_DIR, exist_ok=True)


def _make_id(name: str) -> str:
    """한글/영문 이름으로 폴더명 생성"""
    slug = re.sub(r'[^\w가-힣-]', '-', name.strip())
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug or f"book-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def _load_book_registry(book_path: str) -> dict:
    reg_path = os.path.join(book_path, "book_registry.yaml")
    if os.path.exists(reg_path):
        with open(reg_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_book_registry(book_path: str, data: dict):
    reg_path = os.path.join(book_path, "book_registry.yaml")
    with open(reg_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def _count_chapters(version_path: str) -> tuple:
    """버전 폴더 내 챕터 수와 draft 있는 챕터 수 반환"""
    chapters_dir = os.path.join(version_path, "chapters")
    total = 0
    with_draft = 0
    if os.path.isdir(chapters_dir):
        for ch in os.listdir(chapters_dir):
            ch_path = os.path.join(chapters_dir, ch)
            if os.path.isdir(ch_path):
                total += 1
                if os.path.exists(os.path.join(ch_path, "draft.md")):
                    with_draft += 1
    return with_draft, total


def list_books() -> dict:
    """등록된 출판 프로젝트 목록 반환"""
    _ensure_books_dir()
    books = []

    for entry in sorted(os.listdir(BOOKS_DIR)):
        book_path = os.path.join(BOOKS_DIR, entry)
        if not os.path.isdir(book_path):
            continue

        reg = _load_book_registry(book_path)
        if not reg:
            continue

        active_plan = reg.get("active_plan", "")
        active_version = reg.get("active_version", "")

        # 활성 버전의 챕터 현황
        chapters_str = "-"
        if active_plan and active_version:
            version_path = os.path.join(book_path, "plans", active_plan, active_version)
            with_draft, total = _count_chapters(version_path)
            chapters_str = f"{with_draft}/{total}"

        # 플랜 목록
        plans_dir = os.path.join(book_path, "plans")
        plan_list = []
        if os.path.isdir(plans_dir):
            for p in sorted(os.listdir(plans_dir)):
                if os.path.isdir(os.path.join(plans_dir, p)):
                    # 각 플랜의 버전 목록
                    versions = [v for v in sorted(os.listdir(os.path.join(plans_dir, p)))
                                if os.path.isdir(os.path.join(plans_dir, p, v)) and v.startswith("v")]
                    plan_list.append({"plan": p, "versions": versions})

        # 조각글 수
        fragments_dir = os.path.join(book_path, "fragments")
        fragment_count = 0
        if os.path.isdir(fragments_dir):
            fragment_count = len([f for f in os.listdir(fragments_dir) if f.endswith('.md')])

        books.append({
            "id": reg.get("id", entry),
            "title": reg.get("title", entry),
            "status": reg.get("status", "unknown"),
            "author": reg.get("author", ""),
            "path": book_path,
            "active_plan": active_plan,
            "active_version": active_version,
            "chapters": chapters_str,
            "plans": plan_list,
            "fragments": fragment_count,
            "updated_at": reg.get("updated_at", ""),
        })

    return {
        "success": True,
        "books": books,
        "total": len(books),
        "books_dir": BOOKS_DIR,
    }


def create_book(tool_input: dict) -> dict:
    """새 출판 프로젝트 생성 — 플랜/버전 구조로 초기화"""
    _ensure_books_dir()

    title = tool_input.get("title", "").strip()
    if not title:
        return {"success": False, "error": "제목(title)은 필수입니다."}

    book_id = tool_input.get("id") or _make_id(title)
    book_path = os.path.join(BOOKS_DIR, book_id)

    if os.path.exists(book_path):
        return {"success": False, "error": f"이미 존재하는 프로젝트: {book_id}"}

    # 공유 폴더 생성
    for sub in ["fragments", "references/papers", "references/clippings", "images"]:
        os.makedirs(os.path.join(book_path, sub), exist_ok=True)

    # 첫 번째 플랜 + 버전 생성
    plan_dir = os.path.join(book_path, "plans", "plan_v1")
    version_dir = os.path.join(plan_dir, "v1", "chapters")
    os.makedirs(version_dir, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d")

    # book_registry.yaml
    registry = {
        "id": book_id,
        "title": title,
        "subtitle": tool_input.get("subtitle", ""),
        "author": tool_input.get("author", ""),
        "status": "planning",
        "created_at": now,
        "updated_at": now,
        "target_length": tool_input.get("target_length", ""),
        "genre": tool_input.get("genre", ""),
        "description": tool_input.get("description", ""),
        "style_reference": tool_input.get("style_reference", ""),
        "active_plan": "plan_v1",
        "active_version": "v1",
    }
    _save_book_registry(book_path, registry)

    # plan.md (플랜 폴더 안에)
    plan_content = f"""# {title}

## 개요
(이 책이 무엇인지, 누구를 위한 것인지 작성)

## 구성 방침
- 각 챕터 예상 분량:
- 문체:
- 문체 참고 원고: {tool_input.get('style_reference', '(지정 필요)')}
- 특수 요소:
- 부록:

## 목차

### Chapter 1: (제목)
- **의도**:
- **핵심 내용**:
- **상태**: 미착수
"""
    with open(os.path.join(plan_dir, "plan.md"), 'w', encoding='utf-8') as f:
        f.write(plan_content)

    # progress.md (프로젝트 루트)
    progress_content = f"""# 진척 기록

## 현재 상태
- 활성 플랜: plan_v1
- 활성 버전: v1
- 전체 진행률: 기획 단계
- 현재 작업: 목차 구성 중
- 다음 할 일: plan.md 완성

## 플랜/버전 이력
- [{now}] plan_v1 생성

## 결정 사항
- [{now}] 프로젝트 생성

## 변경 이력
- [{now}] 프로젝트 "{title}" 생성
"""
    with open(os.path.join(book_path, "progress.md"), 'w', encoding='utf-8') as f:
        f.write(progress_content)

    # references/urls.md
    with open(os.path.join(book_path, "references", "urls.md"), 'w', encoding='utf-8') as f:
        f.write("# 참고 URL 목록\n\n")

    return {
        "success": True,
        "message": f"출판 프로젝트 '{title}' 생성 완료 (plan_v1/v1)",
        "book_id": book_id,
        "path": book_path,
        "active_plan": "plan_v1",
        "active_version": "v1",
    }


def book_status(tool_input: dict) -> dict:
    """특정 출판 프로젝트의 상세 상태 반환"""
    _ensure_books_dir()

    book_id = tool_input.get("book_id", "").strip()
    if not book_id:
        return {"success": False, "error": "book_id는 필수입니다."}

    book_path = os.path.join(BOOKS_DIR, book_id)
    if not os.path.isdir(book_path):
        return {"success": False, "error": f"프로젝트를 찾을 수 없음: {book_id}"}

    reg = _load_book_registry(book_path)
    active_plan = reg.get("active_plan", "")
    active_version = reg.get("active_version", "")

    # 플랜/버전 트리
    plans_info = []
    plans_dir = os.path.join(book_path, "plans")
    if os.path.isdir(plans_dir):
        for p in sorted(os.listdir(plans_dir)):
            p_path = os.path.join(plans_dir, p)
            if not os.path.isdir(p_path):
                continue
            has_plan_md = os.path.exists(os.path.join(p_path, "plan.md"))
            versions = []
            for v in sorted(os.listdir(p_path)):
                v_path = os.path.join(p_path, v)
                if os.path.isdir(v_path) and v.startswith("v"):
                    with_draft, total = _count_chapters(v_path)
                    is_active = (p == active_plan and v == active_version)
                    versions.append({
                        "version": v,
                        "chapters": f"{with_draft}/{total}",
                        "active": is_active,
                    })
            plans_info.append({
                "plan": p,
                "has_plan_md": has_plan_md,
                "active": p == active_plan,
                "versions": versions,
            })

    # 활성 버전의 챕터 상세
    chapters = []
    if active_plan and active_version:
        version_path = os.path.join(book_path, "plans", active_plan, active_version)
        chapters_dir = os.path.join(version_path, "chapters")
        if os.path.isdir(chapters_dir):
            for ch in sorted(os.listdir(chapters_dir)):
                ch_path = os.path.join(chapters_dir, ch)
                if not os.path.isdir(ch_path):
                    continue
                draft_path = os.path.join(ch_path, "draft.md")
                has_draft = os.path.exists(draft_path)
                draft_size = os.path.getsize(draft_path) if has_draft else 0
                chapters.append({
                    "name": ch,
                    "has_draft": has_draft,
                    "draft_chars": draft_size,
                    "has_notes": os.path.exists(os.path.join(ch_path, "notes.md")),
                    "image_count": len(os.listdir(os.path.join(ch_path, "images"))) if os.path.isdir(os.path.join(ch_path, "images")) else 0,
                })

    # 조각글 목록
    fragments = []
    fragments_dir = os.path.join(book_path, "fragments")
    if os.path.isdir(fragments_dir):
        for f in sorted(os.listdir(fragments_dir)):
            if f.endswith('.md'):
                fragments.append(f)

    # progress.md 내용
    progress = ""
    progress_path = os.path.join(book_path, "progress.md")
    if os.path.exists(progress_path):
        with open(progress_path, 'r', encoding='utf-8') as f:
            progress = f.read()

    return {
        "success": True,
        "book_id": book_id,
        "registry": reg,
        "path": book_path,
        "active_plan": active_plan,
        "active_version": active_version,
        "plans": plans_info,
        "active_chapters": chapters,
        "fragments": fragments,
        "progress_summary": progress[:1500] if progress else "(진척 기록 없음)",
    }


def run(tool_input: dict) -> dict:
    """디스패처"""
    action = tool_input.get("action", "list")

    action_map = {
        "list": list_books,
        "목록": list_books,
        "create": lambda: create_book(tool_input),
        "생성": lambda: create_book(tool_input),
        "status": lambda: book_status(tool_input),
        "상태": lambda: book_status(tool_input),
    }

    fn = action_map.get(action)
    if not fn:
        return {"success": False, "error": f"알 수 없는 action: {action}. 사용 가능: list, create, status"}

    return fn() if callable(fn) else fn
