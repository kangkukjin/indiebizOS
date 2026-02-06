"""
원격 런처 웹앱 API
- Cloudflare Tunnel을 통해 외부에서 IndieBiz OS를 제어
- 시스템 AI 채팅, 프로젝트 에이전트 채팅, 스위치 실행
"""

from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import os
import json
import uuid
from datetime import datetime

router = APIRouter(prefix="/launcher")

# 설정 파일 경로
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "launcher_web_config.json")

# 세션 저장소 (메모리)
sessions = {}

def load_config():
    """설정 로드"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "enabled": False,
        "password": "",
    }

def save_config(config):
    """설정 저장"""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def verify_session(request: Request) -> bool:
    """세션 검증"""
    session_id = request.cookies.get("launcher_session")
    if not session_id:
        session_id = request.headers.get("X-Launcher-Session")
    return session_id in sessions

# === API 엔드포인트 ===

class ConfigModel(BaseModel):
    enabled: bool
    password: str

class LoginModel(BaseModel):
    password: str

@router.get("/config")
async def get_config():
    """설정 조회"""
    config = load_config()
    return {
        "enabled": config.get("enabled", False),
        "has_password": bool(config.get("password", ""))
    }

@router.post("/config")
async def set_config(config: ConfigModel):
    """설정 저장"""
    save_config(config.dict())
    return {"success": True}

@router.post("/auth/login")
async def login(data: LoginModel, response: Response):
    """로그인"""
    config = load_config()

    if not config.get("enabled"):
        raise HTTPException(status_code=403, detail="원격 런처가 비활성화되어 있습니다")

    if data.password != config.get("password"):
        raise HTTPException(status_code=401, detail="비밀번호가 틀렸습니다")

    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "created": datetime.now().isoformat()
    }

    response.set_cookie(
        key="launcher_session",
        value=session_id,
        httponly=True,
        samesite="strict"
    )

    return {"success": True, "session_id": session_id}

@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """로그아웃"""
    session_id = request.cookies.get("launcher_session")
    if session_id and session_id in sessions:
        del sessions[session_id]
    response.delete_cookie("launcher_session")
    return {"success": True}

@router.get("/app", response_class=HTMLResponse)
async def get_webapp():
    """원격 런처 웹앱"""
    return get_launcher_webapp_html()


def get_launcher_webapp_html():
    """원격 런처 웹앱 HTML"""
    return """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IndieBiz OS - Remote Launcher</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-tertiary: #0f3460;
            --accent: #e94560;
            --accent-light: #ff6b6b;
            --text-primary: #eee;
            --text-secondary: #aaa;
            --border: #333;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }

        /* 로그인 화면 */
        .login-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
        }

        .login-box {
            background: var(--bg-secondary);
            padding: 40px;
            border-radius: 16px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }

        .login-title {
            text-align: center;
            margin-bottom: 30px;
        }

        .login-title h1 {
            font-size: 24px;
            margin-bottom: 8px;
        }

        .login-title p {
            color: var(--text-secondary);
            font-size: 14px;
        }

        .login-input {
            width: 100%;
            padding: 14px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 16px;
            margin-bottom: 16px;
        }

        .login-input:focus {
            outline: none;
            border-color: var(--accent);
        }

        .login-btn {
            width: 100%;
            padding: 14px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }

        .login-btn:hover {
            background: var(--accent-light);
        }

        .login-error {
            color: var(--accent);
            text-align: center;
            margin-top: 16px;
            font-size: 14px;
        }

        /* 메인 앱 */
        .app-container {
            display: none;
            height: 100vh;
        }

        .app-container.active {
            display: flex;
            flex-direction: column;
        }

        /* 헤더 */
        .header {
            background: var(--bg-secondary);
            padding: 12px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border);
        }

        .header-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .header-title h1 {
            font-size: 18px;
            font-weight: 600;
        }

        .header-badge {
            background: var(--accent);
            color: white;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }

        .header-actions {
            display: flex;
            gap: 12px;
        }

        .header-btn {
            padding: 8px 16px;
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: none;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
            transition: background 0.2s;
        }

        .header-btn:hover {
            background: var(--accent);
        }

        /* 메인 영역 */
        .main {
            flex: 1;
            display: flex;
            overflow: hidden;
        }

        /* 사이드바 */
        .sidebar {
            width: 280px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .sidebar-section {
            padding: 16px;
            border-bottom: 1px solid var(--border);
        }

        .sidebar-section h3 {
            font-size: 12px;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 12px;
            letter-spacing: 0.5px;
        }

        .sidebar-item {
            padding: 10px 12px;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 4px;
            transition: background 0.2s;
        }

        .sidebar-item:hover {
            background: var(--bg-tertiary);
        }

        .sidebar-item.active {
            background: var(--accent);
        }

        .sidebar-item-icon {
            font-size: 18px;
        }

        .sidebar-item-text {
            flex: 1;
            font-size: 14px;
        }

        .sidebar-list {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
        }

        /* 채팅 영역 */
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--bg-primary);
        }

        .chat-header {
            padding: 16px 20px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
        }

        .chat-header h2 {
            font-size: 16px;
            font-weight: 600;
        }

        .chat-header p {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }

        .message {
            margin-bottom: 16px;
            display: flex;
            gap: 12px;
        }

        .message-avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: var(--bg-tertiary);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            flex-shrink: 0;
        }

        .message-content {
            flex: 1;
            background: var(--bg-secondary);
            padding: 12px 16px;
            border-radius: 12px;
            border-top-left-radius: 4px;
        }

        .message.user .message-content {
            background: var(--accent);
            border-radius: 12px;
            border-top-right-radius: 4px;
        }

        .message.user {
            flex-direction: row-reverse;
        }

        .message-text {
            font-size: 14px;
            line-height: 1.5;
            white-space: pre-wrap;
        }

        .chat-input-area {
            padding: 16px 20px;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border);
        }

        .chat-input-wrapper {
            display: flex;
            gap: 12px;
        }

        .chat-input {
            flex: 1;
            padding: 12px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 14px;
            resize: none;
        }

        .chat-input:focus {
            outline: none;
            border-color: var(--accent);
        }

        .chat-send-btn {
            padding: 12px 24px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }

        .chat-send-btn:hover {
            background: var(--accent-light);
        }

        .chat-send-btn:disabled {
            background: var(--border);
            cursor: not-allowed;
        }

        /* 스위치 영역 */
        .switches-area {
            display: none;
            flex: 1;
            flex-direction: column;
            background: var(--bg-primary);
        }

        .switches-area.active {
            display: flex;
        }

        .switches-header {
            padding: 16px 20px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
        }

        .switches-list {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }

        .switch-item {
            background: var(--bg-secondary);
            padding: 16px;
            border-radius: 12px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .switch-icon {
            font-size: 24px;
        }

        .switch-info {
            flex: 1;
        }

        .switch-name {
            font-weight: 600;
            margin-bottom: 4px;
        }

        .switch-prompt {
            font-size: 12px;
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 300px;
        }

        .switch-run-btn {
            padding: 10px 20px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }

        .switch-run-btn:hover {
            background: var(--accent-light);
        }

        /* 로딩 */
        .loading {
            display: none;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 12px;
            color: var(--text-secondary);
        }

        .loading.active {
            display: flex;
        }

        .loading-spinner {
            width: 20px;
            height: 20px;
            border: 2px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* 반응형 */
        @media (max-width: 768px) {
            .sidebar {
                position: fixed;
                left: -280px;
                top: 0;
                bottom: 0;
                z-index: 100;
                transition: left 0.3s;
            }

            .sidebar.open {
                left: 0;
            }

            .sidebar-overlay {
                display: none;
                position: fixed;
                inset: 0;
                background: rgba(0,0,0,0.5);
                z-index: 99;
            }

            .sidebar-overlay.active {
                display: block;
            }

            .header-menu-btn {
                display: block;
            }
        }

        @media (min-width: 769px) {
            .header-menu-btn {
                display: none;
            }
        }
    </style>
</head>
<body>
    <!-- 로그인 화면 -->
    <div class="login-container" id="loginScreen">
        <div class="login-box">
            <div class="login-title">
                <h1>🚀 IndieBiz OS</h1>
                <p>Remote Launcher</p>
            </div>
            <input type="password" class="login-input" id="passwordInput" placeholder="비밀번호 입력" autofocus>
            <button class="login-btn" onclick="login()">로그인</button>
            <p class="login-error" id="loginError"></p>
        </div>
    </div>

    <!-- 메인 앱 -->
    <div class="app-container" id="appContainer">
        <header class="header">
            <div class="header-title">
                <button class="header-btn header-menu-btn" onclick="toggleSidebar()">☰</button>
                <h1>🚀 IndieBiz OS</h1>
                <span class="header-badge">REMOTE</span>
            </div>
            <div class="header-actions">
                <button class="header-btn" onclick="refreshData()">🔄 새로고침</button>
                <button class="header-btn" onclick="logout()">로그아웃</button>
            </div>
        </header>

        <main class="main">
            <div class="sidebar-overlay" onclick="toggleSidebar()"></div>
            <aside class="sidebar" id="sidebar">
                <div class="sidebar-section">
                    <h3>시스템</h3>
                    <div class="sidebar-item active" onclick="selectChat('system')">
                        <span class="sidebar-item-icon">🤖</span>
                        <span class="sidebar-item-text">시스템 AI</span>
                    </div>
                    <div class="sidebar-item" onclick="showSwitches()">
                        <span class="sidebar-item-icon">⚡</span>
                        <span class="sidebar-item-text">스위치</span>
                    </div>
                </div>

                <div class="sidebar-section">
                    <h3>프로젝트</h3>
                </div>
                <div class="sidebar-list" id="projectList">
                    <!-- 프로젝트 목록 동적 로드 -->
                </div>
            </aside>

            <section class="chat-area" id="chatArea">
                <div class="chat-header">
                    <h2 id="chatTitle">시스템 AI</h2>
                    <p id="chatSubtitle">IndieBiz OS 전체를 관리하는 시스템 AI입니다</p>
                </div>
                <div class="chat-messages" id="chatMessages">
                    <!-- 메시지 동적 로드 -->
                </div>
                <div class="loading" id="chatLoading">
                    <div class="loading-spinner"></div>
                    <span>AI가 응답 중...</span>
                </div>
                <div class="chat-input-area">
                    <div class="chat-input-wrapper">
                        <textarea class="chat-input" id="chatInput" rows="1" placeholder="메시지를 입력하세요..." onkeydown="handleInputKeydown(event)"></textarea>
                        <button class="chat-send-btn" id="sendBtn" onclick="sendMessage()">보내기</button>
                    </div>
                </div>
            </section>

            <section class="switches-area" id="switchesArea">
                <div class="switches-header">
                    <h2>⚡ 스위치</h2>
                    <p>원클릭으로 자동화된 작업을 실행합니다</p>
                </div>
                <div class="switches-list" id="switchesList">
                    <!-- 스위치 목록 동적 로드 -->
                </div>
            </section>
        </main>
    </div>

    <script>
        // 상태
        let currentChat = { type: 'system', projectId: null, agentName: null };
        let messages = [];
        let projects = [];
        let switches = [];

        // API 베이스 URL
        const API_BASE = '';

        // 초기화
        document.addEventListener('DOMContentLoaded', () => {
            checkSession();

            // Enter 키 처리
            document.getElementById('passwordInput').addEventListener('keydown', (e) => {
                if (e.key === 'Enter') login();
            });
        });

        // 세션 체크
        async function checkSession() {
            try {
                const res = await fetch(API_BASE + '/projects');
                if (res.ok) {
                    showApp();
                    loadData();
                }
            } catch (e) {
                // 세션 없음 - 로그인 화면 유지
            }
        }

        // 로그인
        async function login() {
            const password = document.getElementById('passwordInput').value;
            const errorEl = document.getElementById('loginError');

            try {
                const res = await fetch(API_BASE + '/launcher/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });

                if (res.ok) {
                    showApp();
                    loadData();
                } else {
                    const data = await res.json();
                    errorEl.textContent = data.detail || '로그인 실패';
                }
            } catch (e) {
                errorEl.textContent = '서버 연결 실패';
            }
        }

        // 로그아웃
        async function logout() {
            await fetch(API_BASE + '/launcher/auth/logout', { method: 'POST' });
            location.reload();
        }

        // 앱 화면 표시
        function showApp() {
            document.getElementById('loginScreen').style.display = 'none';
            document.getElementById('appContainer').classList.add('active');
        }

        // 데이터 로드
        async function loadData() {
            await loadProjects();
            await loadSwitches();
        }

        // 새로고침
        function refreshData() {
            loadData();
        }

        // 프로젝트 로드
        async function loadProjects() {
            try {
                const res = await fetch(API_BASE + '/projects');
                if (res.ok) {
                    const data = await res.json();
                    projects = data.projects || [];
                    renderProjects();
                }
            } catch (e) {
                console.error('프로젝트 로드 실패:', e);
            }
        }

        // 프로젝트 렌더링
        function renderProjects() {
            const list = document.getElementById('projectList');
            list.innerHTML = projects.map(p => `
                <div class="sidebar-item" onclick="selectProject('${p.id}')">
                    <span class="sidebar-item-icon">${p.icon || '📁'}</span>
                    <span class="sidebar-item-text">${p.name}</span>
                </div>
            `).join('');
        }

        // 스위치 로드
        async function loadSwitches() {
            try {
                const res = await fetch(API_BASE + '/switches');
                if (res.ok) {
                    const data = await res.json();
                    switches = data.switches || [];
                }
                renderSwitches();
            } catch (e) {
                console.error('스위치 로드 실패:', e);
            }
        }

        // 스위치 렌더링
        function renderSwitches() {
            const list = document.getElementById('switchesList');
            if (switches.length === 0) {
                list.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 40px;">스위치가 없습니다</p>';
                return;
            }
            list.innerHTML = switches.map(s => `
                <div class="switch-item">
                    <span class="switch-icon">⚡</span>
                    <div class="switch-info">
                        <div class="switch-name">${s.name}</div>
                        <div class="switch-prompt">${s.prompt || ''}</div>
                    </div>
                    <button class="switch-run-btn" onclick="runSwitch('${s.id}')">실행</button>
                </div>
            `).join('');
        }

        // 채팅 선택 (시스템 AI)
        function selectChat(type) {
            currentChat = { type, projectId: null, agentName: null };
            messages = [];

            document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
            event.target.closest('.sidebar-item').classList.add('active');

            document.getElementById('chatArea').style.display = 'flex';
            document.getElementById('switchesArea').classList.remove('active');

            document.getElementById('chatTitle').textContent = '시스템 AI';
            document.getElementById('chatSubtitle').textContent = 'IndieBiz OS 전체를 관리하는 시스템 AI입니다';
            document.getElementById('chatMessages').innerHTML = '';

            closeSidebar();
        }

        // 프로젝트 선택
        async function selectProject(projectId) {
            const project = projects.find(p => p.id === projectId);
            if (!project) return;

            // 에이전트 목록 로드
            try {
                const res = await fetch(API_BASE + `/projects/${projectId}/agents`);
                if (res.ok) {
                    const agents = await res.json();
                    if (agents.length > 0) {
                        currentChat = {
                            type: 'agent',
                            projectId,
                            agentName: agents[0].name
                        };

                        document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
                        event.target.closest('.sidebar-item').classList.add('active');

                        document.getElementById('chatArea').style.display = 'flex';
                        document.getElementById('switchesArea').classList.remove('active');

                        document.getElementById('chatTitle').textContent = `${project.name} - ${agents[0].name}`;
                        document.getElementById('chatSubtitle').textContent = agents[0].role?.substring(0, 100) || '';
                        document.getElementById('chatMessages').innerHTML = '';
                        messages = [];
                    }
                }
            } catch (e) {
                console.error('에이전트 로드 실패:', e);
            }

            closeSidebar();
        }

        // 스위치 화면 표시
        function showSwitches() {
            document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
            event.target.closest('.sidebar-item').classList.add('active');

            document.getElementById('chatArea').style.display = 'none';
            document.getElementById('switchesArea').classList.add('active');

            closeSidebar();
        }

        // 스위치 실행
        async function runSwitch(switchId) {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '실행 중...';

            try {
                const res = await fetch(API_BASE + `/switches/${switchId}/execute`, {
                    method: 'POST'
                });

                if (res.ok) {
                    alert('스위치가 실행되었습니다!');
                } else {
                    alert('스위치 실행 실패');
                }
            } catch (e) {
                alert('오류: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '실행';
            }
        }

        // 메시지 전송
        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;

            // UI에 사용자 메시지 추가
            addMessageToUI('user', message);
            input.value = '';

            // 로딩 표시
            document.getElementById('chatLoading').classList.add('active');
            document.getElementById('sendBtn').disabled = true;

            try {
                let res;

                if (currentChat.type === 'system') {
                    // 시스템 AI 채팅
                    res = await fetch(API_BASE + '/system-ai/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message })
                    });
                } else {
                    // 프로젝트 에이전트 채팅
                    res = await fetch(API_BASE + `/projects/${currentChat.projectId}/chat`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message,
                            agent_name: currentChat.agentName
                        })
                    });
                }

                if (res.ok) {
                    const data = await res.json();
                    addMessageToUI('assistant', data.response || data.message || '응답을 받았습니다.');
                } else {
                    let errorMsg = '오류가 발생했습니다.';
                    try {
                        const errData = await res.json();
                        errorMsg = errData.detail || errData.error || errorMsg;
                    } catch(e) {}
                    addMessageToUI('assistant', `[${res.status}] ${errorMsg}`);
                }
            } catch (e) {
                addMessageToUI('assistant', '서버 연결 오류: ' + e.message);
            } finally {
                document.getElementById('chatLoading').classList.remove('active');
                document.getElementById('sendBtn').disabled = false;
            }
        }

        // UI에 메시지 추가
        function addMessageToUI(role, text) {
            const container = document.getElementById('chatMessages');
            const avatar = role === 'user' ? '👤' : '🤖';

            const messageEl = document.createElement('div');
            messageEl.className = `message ${role}`;
            messageEl.innerHTML = `
                <div class="message-avatar">${avatar}</div>
                <div class="message-content">
                    <div class="message-text">${escapeHtml(text)}</div>
                </div>
            `;

            container.appendChild(messageEl);
            container.scrollTop = container.scrollHeight;

            messages.push({ role, content: text });
        }

        // HTML 이스케이프
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // 입력 키 핸들러
        function handleInputKeydown(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        }

        // 사이드바 토글 (모바일)
        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('open');
            document.querySelector('.sidebar-overlay').classList.toggle('active');
        }

        function closeSidebar() {
            document.getElementById('sidebar').classList.remove('open');
            document.querySelector('.sidebar-overlay').classList.remove('active');
        }
    </script>
</body>
</html>
"""
