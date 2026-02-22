# 에이전트 웹 퍼블리싱 가이드

IndieBiz OS 에이전트를 Cloudflare Workers 기반 웹앱으로 배포하는 가이드입니다.
AI가 이 가이드를 읽고 직접 퍼블리싱 작업을 수행합니다.

## 개요

```
IndieBiz OS 에이전트 → Cloudflare Worker (백엔드 API + 프론트엔드 HTML)
```

배포된 웹앱은 비밀번호로 보호되며, 어디서든 접속 가능합니다.

---

## 사전 요구사항

### 1. 환경변수 (backend/.env)
```env
CLOUDFLARE_API_TOKEN=xxx    # Cloudflare API 토큰 (필수)
CLOUDFLARE_ACCOUNT_ID=xxx   # Cloudflare Account ID (필수)
GOOGLE_API_KEY=xxx          # Gemini API 키 (기본 프로바이더)
ANTHROPIC_API_KEY=xxx       # Claude API 키 (선택)
OPENAI_API_KEY=xxx          # OpenAI API 키 (선택)
```

### 2. Wrangler CLI 설치
```bash
npm install -g wrangler
wrangler login  # 브라우저에서 로그인
```

---

## 퍼블리싱 절차

### Step 0: 프로젝트/에이전트 정보 찾기

사용자가 "법률 프로젝트의 전문 변호사를 퍼블리싱해줘"라고 하면:

**1. project_id 찾기**
- project_id = 프로젝트 폴더명
- `projects/` 디렉토리 확인: "법률" 폴더 존재 → project_id = `"법률"`

**2. agent_id 찾기**
- `projects/법률/agents.yaml` 파일 읽기
- `name`이 "전문 변호사"인 에이전트의 `id` 필드 확인

```yaml
# projects/법률/agents.yaml 예시
agents:
- id: lawyer_main        # ← 이것이 agent_id
  name: 전문 변호사       # ← 사용자가 부르는 이름
  ai:
    provider: google
    model: gemini-2.0-flash-exp
  role: |
    대한민국 법률 전문가입니다...
```

→ agent_id = `"lawyer_main"`

**필요한 정보 요약:**
| 항목 | 값 | 출처 |
|------|-----|------|
| project_id | "법률" | 폴더명 |
| agent_id | "lawyer_main" | agents.yaml의 id 필드 |
| name | "전문 변호사" | agents.yaml의 name 필드 |
| provider | "google" | agents.yaml의 ai.provider |
| model | "gemini-2.0-flash-exp" | agents.yaml의 ai.model |
| role | 시스템 프롬프트 | agents.yaml의 role 필드 |

---

### Step 1: 배포 디렉토리 생성

```bash
mkdir -p /tmp/agent-deploy-{subdomain}
cd /tmp/agent-deploy-{subdomain}
```

---

### Step 2: worker.js 생성

**중요**: Worker가 "/" 경로에서 프론트엔드 HTML을 직접 서빙합니다.

아래 템플릿에서 `{{AGENT_NAME}}`을 실제 에이전트 이름으로 교체하여 `worker.js`로 저장:

```javascript
/**
 * IndieBiz OS Agent Web App - Cloudflare Worker
 * 백엔드 API + 프론트엔드 HTML을 단일 Worker에서 서빙
 */

// 프론트엔드 HTML ({{AGENT_NAME}}을 실제 이름으로 교체)
const FRONTEND_HTML = `<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{AGENT_NAME}}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .chat-container { height: calc(100vh - 180px); }
    .message-content { white-space: pre-wrap; word-break: break-word; }
  </style>
</head>
<body class="bg-gray-100 min-h-screen">
  <div id="app"></div>
  <script type="module">
    import { h, render } from 'https://esm.sh/preact@10.19.3';
    import { useState, useEffect, useRef } from 'https://esm.sh/preact@10.19.3/hooks';
    import htm from 'https://esm.sh/htm@3.1.1';
    const html = htm.bind(h);

    const AGENT_NAME = '{{AGENT_NAME}}';
    const STORAGE_KEY = 'agent_chat_token';

    function App() {
      const [token, setToken] = useState(localStorage.getItem(STORAGE_KEY));
      const [messages, setMessages] = useState([]);
      const [input, setInput] = useState('');
      const [password, setPassword] = useState('');
      const [loading, setLoading] = useState(false);
      const [error, setError] = useState('');
      const messagesEndRef = useRef(null);

      useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, [messages]);

      const login = async () => {
        setLoading(true);
        setError('');
        try {
          const res = await fetch('/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
          });
          const data = await res.json();
          if (data.success) {
            localStorage.setItem(STORAGE_KEY, data.token);
            setToken(data.token);
          } else {
            setError(data.error || '로그인 실패');
          }
        } catch (e) {
          setError('서버 연결 실패');
        }
        setLoading(false);
      };

      const send = async () => {
        if (!input.trim() || loading) return;
        const userMsg = { role: 'user', content: input.trim() };
        const newMessages = [...messages, userMsg];
        setMessages(newMessages);
        setInput('');
        setLoading(true);

        try {
          const res = await fetch('/chat', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify({ messages: newMessages })
          });
          const data = await res.json();
          if (res.status === 401) {
            localStorage.removeItem(STORAGE_KEY);
            setToken(null);
            return;
          }
          if (data.success) {
            setMessages([...newMessages, { role: 'assistant', content: data.response }]);
          } else {
            setMessages([...newMessages, { role: 'assistant', content: '오류: ' + (data.error || '알 수 없는 오류') }]);
          }
        } catch (e) {
          setMessages([...newMessages, { role: 'assistant', content: '서버 연결 실패' }]);
        }
        setLoading(false);
      };

      const logout = () => {
        localStorage.removeItem(STORAGE_KEY);
        setToken(null);
        setMessages([]);
      };

      if (!token) {
        return html\`
          <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-500 to-purple-600">
            <div class="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md mx-4">
              <div class="text-center mb-8">
                <div class="w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full mx-auto mb-4 flex items-center justify-center">
                  <svg class="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
                  </svg>
                </div>
                <h1 class="text-2xl font-bold text-gray-800">\${AGENT_NAME}</h1>
              </div>
              <div class="mb-6">
                <input type="password" value=\${password} onInput=\${e => setPassword(e.target.value)}
                  onKeyPress=\${e => e.key === 'Enter' && login()}
                  placeholder="비밀번호를 입력하세요"
                  class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              \${error && html\`<div class="mb-4 p-3 bg-red-100 text-red-700 rounded-lg text-sm">\${error}</div>\`}
              <button onClick=\${login} disabled=\${loading}
                class="w-full bg-gradient-to-r from-blue-500 to-purple-600 text-white py-3 rounded-lg font-semibold hover:opacity-90 disabled:opacity-50">
                \${loading ? '로그인 중...' : '로그인'}
              </button>
            </div>
          </div>
        \`;
      }

      return html\`
        <div class="min-h-screen bg-gray-100 flex flex-col">
          <header class="bg-white shadow-sm px-4 py-3 flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
                </svg>
              </div>
              <h1 class="text-lg font-semibold text-gray-800">\${AGENT_NAME}</h1>
            </div>
            <button onClick=\${logout} class="text-gray-500 hover:text-gray-700 text-sm">로그아웃</button>
          </header>
          <div class="flex-1 overflow-y-auto px-4 py-4 chat-container">
            \${messages.length === 0 && html\`
              <div class="text-center text-gray-500 mt-20">
                <p>대화를 시작해보세요!</p>
              </div>
            \`}
            \${messages.map((m, i) => html\`
              <div key=\${i} class="flex \${m.role === 'user' ? 'justify-end' : 'justify-start'} mb-4">
                <div class="max-w-[80%] \${m.role === 'user'
                  ? 'bg-blue-500 text-white rounded-l-2xl rounded-tr-2xl'
                  : 'bg-white text-gray-800 rounded-r-2xl rounded-tl-2xl shadow'} px-4 py-3">
                  <div class="message-content">\${m.content}</div>
                </div>
              </div>
            \`)}
            \${loading && html\`
              <div class="flex justify-start mb-4">
                <div class="bg-white rounded-r-2xl rounded-tl-2xl shadow px-4 py-3">
                  <div class="flex gap-1">
                    <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></span>
                    <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.1s"></span>
                    <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></span>
                  </div>
                </div>
              </div>
            \`}
            <div ref=\${messagesEndRef} />
          </div>
          <div class="bg-white border-t px-4 py-3">
            <div class="flex gap-2">
              <input type="text" value=\${input} onInput=\${e => setInput(e.target.value)}
                onKeyPress=\${e => e.key === 'Enter' && send()}
                placeholder="메시지를 입력하세요..." disabled=\${loading}
                class="flex-1 px-4 py-3 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500" />
              <button onClick=\${send} disabled=\${loading || !input.trim()}
                class="bg-blue-500 text-white px-6 py-3 rounded-full hover:bg-blue-600 disabled:opacity-50">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      \`;
    }

    render(html\`<\${App} />\`, document.getElementById('app'));
  </script>
</body>
</html>`;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

function errorResponse(message, status = 400) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' }
  });
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' }
  });
}

function verifyPassword(request, env) {
  const authHeader = request.headers.get('Authorization');
  if (!authHeader || !authHeader.startsWith('Bearer ')) return false;
  return authHeader.substring(7) === env.APP_PASSWORD;
}

// Google Gemini API
async function callGoogle(messages, systemPrompt, env) {
  const model = env.AI_MODEL || 'gemini-2.0-flash-exp';
  const contents = messages.map(m => ({
    role: m.role === 'assistant' ? 'model' : 'user',
    parts: [{ text: m.content }]
  }));

  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${env.GOOGLE_API_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents,
        systemInstruction: { parts: [{ text: systemPrompt }] },
        generationConfig: { maxOutputTokens: 4096 }
      })
    }
  );

  if (!response.ok) throw new Error(`Google API error: ${await response.text()}`);
  const data = await response.json();
  return data.candidates[0].content.parts[0].text;
}

// Anthropic Claude API
async function callAnthropic(messages, systemPrompt, env) {
  const model = env.AI_MODEL || 'claude-sonnet-4-20250514';
  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': env.ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01'
    },
    body: JSON.stringify({ model, max_tokens: 4096, system: systemPrompt, messages })
  });

  if (!response.ok) throw new Error(`Anthropic API error: ${await response.text()}`);
  const data = await response.json();
  return data.content[0].text;
}

// OpenAI API
async function callOpenAI(messages, systemPrompt, env) {
  const model = env.AI_MODEL || 'gpt-4o';
  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.OPENAI_API_KEY}`
    },
    body: JSON.stringify({
      model,
      messages: [{ role: 'system', content: systemPrompt }, ...messages],
      max_tokens: 4096
    })
  });

  if (!response.ok) throw new Error(`OpenAI API error: ${await response.text()}`);
  const data = await response.json();
  return data.choices[0].message.content;
}

async function callAI(messages, env) {
  const systemPrompt = env.SYSTEM_PROMPT || '당신은 도움이 되는 AI 어시스턴트입니다.';
  const provider = env.AI_PROVIDER || 'google';

  if (provider === 'openai') return await callOpenAI(messages, systemPrompt, env);
  if (provider === 'anthropic') return await callAnthropic(messages, systemPrompt, env);
  return await callGoogle(messages, systemPrompt, env);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // "/" 경로: 프론트엔드 HTML 서빙
    if (path === '/' || path === '/index.html') {
      return new Response(FRONTEND_HTML, {
        headers: { 'Content-Type': 'text/html; charset=utf-8' }
      });
    }

    // 공개 API 엔드포인트
    if (path === '/health') return jsonResponse({ status: 'ok', agent: env.AGENT_NAME });
    if (path === '/info') return jsonResponse({ name: env.AGENT_NAME, description: env.AGENT_DESCRIPTION, requiresAuth: true });

    if (path === '/auth' && request.method === 'POST') {
      try {
        const body = await request.json();
        if (body.password === env.APP_PASSWORD) {
          return jsonResponse({ success: true, token: env.APP_PASSWORD, agent: env.AGENT_NAME });
        }
        return errorResponse('잘못된 비밀번호입니다.', 401);
      } catch (e) {
        return errorResponse('요청 처리 실패', 400);
      }
    }

    // 인증 필요 엔드포인트
    if (!verifyPassword(request, env)) return errorResponse('인증이 필요합니다.', 401);

    if (path === '/chat' && request.method === 'POST') {
      try {
        const { messages } = await request.json();
        if (!messages || !Array.isArray(messages)) return errorResponse('messages 배열이 필요합니다.');

        const response = await callAI(messages, env);
        return jsonResponse({ success: true, response });
      } catch (e) {
        return errorResponse('채팅 처리 실패: ' + e.message, 500);
      }
    }

    return errorResponse('엔드포인트를 찾을 수 없습니다: ' + path, 404);
  }
};
```

**중요: `{{AGENT_NAME}}`을 실제 에이전트 이름으로 모두 교체해야 합니다!**

---

### Step 3: wrangler.toml 생성

```toml
name = "{subdomain}"
main = "worker.js"
compatibility_date = "2024-01-01"

[vars]
AGENT_NAME = "{에이전트 이름}"
AGENT_DESCRIPTION = "{에이전트 설명}"
AI_PROVIDER = "{google|anthropic|openai}"
AI_MODEL = "{모델명}"
SYSTEM_PROMPT = "{시스템 프롬프트 - 줄바꿈은 \\n으로}"
```

**주의**: SYSTEM_PROMPT에서 줄바꿈은 `\n`으로, 따옴표는 `\"`로 이스케이프해야 합니다.

---

### Step 4: Worker 배포

```bash
cd /tmp/agent-deploy-{subdomain}

# 환경변수 설정
export CLOUDFLARE_API_TOKEN=xxx
export CLOUDFLARE_ACCOUNT_ID=xxx

# 배포
wrangler deploy
```

---

### Step 5: 시크릿 설정

```bash
# 비밀번호 설정
echo "{password}" | wrangler secret put APP_PASSWORD --name {subdomain}

# AI API 키 설정 (프로바이더에 따라)
echo "{api_key}" | wrangler secret put GOOGLE_API_KEY --name {subdomain}
# 또는
echo "{api_key}" | wrangler secret put ANTHROPIC_API_KEY --name {subdomain}
# 또는
echo "{api_key}" | wrangler secret put OPENAI_API_KEY --name {subdomain}
```

---

### Step 6: 배포 확인

```bash
# 헬스 체크
curl https://{subdomain}.{account_id}.workers.dev/health

# 브라우저에서 접속
# https://{subdomain}.{account_id}.workers.dev
# → 로그인 화면이 나타나면 성공!
```

---

## 배포 관리

### 배포 목록 확인
```bash
wrangler deployments list --name {subdomain}
```

### 업데이트
```bash
cd /tmp/agent-deploy-{subdomain}
# wrangler.toml 또는 worker.js 수정 후
wrangler deploy
```

### 삭제
```bash
wrangler delete --name {subdomain} -f
```

---

## 퀵 레퍼런스

### 배포 명령 요약

```bash
# 1. 디렉토리 생성
mkdir -p /tmp/agent-deploy-myagent && cd /tmp/agent-deploy-myagent

# 2. worker.js 생성 (위 템플릿에서 {{AGENT_NAME}} 교체)
# 3. wrangler.toml 생성

# 4. 배포
export CLOUDFLARE_API_TOKEN=xxx
export CLOUDFLARE_ACCOUNT_ID=xxx
wrangler deploy

# 5. 시크릿 설정
echo "mypassword" | wrangler secret put APP_PASSWORD --name myagent
echo "sk-xxx" | wrangler secret put GOOGLE_API_KEY --name myagent

# 6. 브라우저에서 확인
# https://myagent.xxx.workers.dev
```

### 배포 URL 형식
```
https://{subdomain}.{account_id}.workers.dev
```

---

## 도구 호환성 참고

웹앱에서 사용 불가능한 로컬 전용 도구:
- `python-exec`, `nodejs` (코드 실행)
- `pc-manager`, `photo-manager` (로컬 파일 접근)
- `browser-action` (브라우저 자동화)
- `visualization` (matplotlib 렌더링)

HTTP API 기반 도구는 Worker에 추가 구현 가능합니다.
