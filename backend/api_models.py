"""
api_models.py - Pydantic 모델 정의
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


# ============ 프로젝트 관련 ============

class ProjectCreate(BaseModel):
    name: str
    icon_position: Optional[tuple] = None
    parent_folder: Optional[str] = None
    template_name: str = "기본"


class FolderCreate(BaseModel):
    name: str
    icon_position: Optional[tuple] = None
    parent_folder: Optional[str] = None


class PositionUpdate(BaseModel):
    x: int
    y: int


class RenameRequest(BaseModel):
    new_name: str


class CopyRequest(BaseModel):
    new_name: Optional[str] = None
    parent_folder: Optional[str] = None


# ============ 스위치 관련 ============

class SwitchCreate(BaseModel):
    name: str
    command: str
    config: Dict[str, Any] = {}
    icon: str = "⚡"
    description: str = ""


# ============ 시스템 AI 관련 ============

class SystemAIConfig(BaseModel):
    enabled: bool = True
    provider: str = "anthropic"  # anthropic, openai, google
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
    role: str = ""


class ChatMessage(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None


# ============ 도구 패키지 관련 ============

class ToolPackage(BaseModel):
    name: str
    description: str
    tools: List[Dict[str, Any]]
    hints: Optional[Dict[str, Any]] = None
    version: str = "1.0.0"
    author: Optional[str] = None


# ============ IndieNet 관련 ============

class IndieNetPostRequest(BaseModel):
    content: str
    extra_tags: Optional[List[str]] = None


class IndieNetDMRequest(BaseModel):
    to_pubkey: str
    content: str


class IndieNetSettingsUpdate(BaseModel):
    relays: Optional[List[str]] = None
    auto_refresh: Optional[bool] = None
    refresh_interval: Optional[int] = None


class IndieNetDisplayNameUpdate(BaseModel):
    display_name: str


class IndieNetImportNsec(BaseModel):
    nsec: str
