# IndieBiz OS

**A Personal AI Operating System for Individuals and Small Businesses**

[Homepage](https://indiebiz-homepage.vercel.app) | English | [한국어](README.ko.md)

IndieBiz OS is not just another AI chatbot. It's a complete operating system where you design your own AI personas, automate tasks with one click, and connect through decentralized networks.

---

## Three Core Values

### 1. Design Your AI Personas

Not just "act as a doctor" - define **who** they are and **how** they communicate.

```yaml
# Example: A compassionate internal medicine doctor
agents:
  dr_kim:
    role: |
      You are Dr. Kim, an internal medicine specialist with 20 years of experience.
      You always start by acknowledging the patient's concerns before asking questions.
      You explain medical terms in everyday language.
      You end every consultation with clear next steps and reassurance.
    model: claude-sonnet
    allowed_nodes: [sense, self, limbs, others, engines]
```

| Generic AI | IndieBiz Persona |
|------------|------------------|
| "You may have hypertension. Consult a doctor." | "I can see you're worried. Let me ask a few questions first... Based on your history, here's what I recommend..." |
| Information delivery | Empathetic conversation with context |

**Each agent remembers your context** - your medications, preferences, past conversations. They're not generic assistants; they're **your** specialists.

### 2. One-Click Automation with Switches & Workflows

Stop repeating the same AI conversations. **Save them as Switches or Workflows** and execute with one click.

**Switches** - Save a prompt + agent pair for one-click execution:
```
[Toggle] Daily Tech News  ->  Click  ->  Done!
         |
    AI executes predefined prompt
         |
    Results saved to outputs/daily_news.md
```

**Workflows** - Chain multiple actions into reusable pipelines using IBL syntax:
```
[sense:web_search]{query: "AI news"}
  >> [others:ask_sync]{agent_id: "content/content", message: "Summarize these articles"}
  >> [self:file]{path: "news_report.html", format: "html"}
```

**Features:**
- **Natural language or IBL code** - Write prompts or program action chains
- **Scheduled execution** - Run daily at 8 AM, weekly on Fridays via the new **Scheduler**
- **Agent assignment** - Specify which agent handles the task
- **Pipeline operators** - Sequential (>>), Parallel (&), Fallback (??)
- **Alias execution** - Run saved workflows by name: `[self:run]{workflow_id: "kinsight"}`

### 3. P2P Network (IndieNet) & Remote Access

Connect with others through decentralized networks and access your system from anywhere.

- **Nostr Protocol** - No central server, no data collection for decentralized DMs and public boards
- **Remote Access (Phase 25)** - Cloudflare Tunnel based Remote Finder (file streaming) and Remote Launcher (AI control/switches)
- **Business Network** - Manage partners, auto-respond to inquiries with **Auto-response V3** (Tool-use based)

---

## Unified AI Architecture (Phase 25: 5-Node Integration)

IndieBiz OS features a unified AI core where the **System AI** and **Project Agents** share the same codebase and tool structure.

- **execute_ibl 단일 도구**: All AI entities use a single `execute_ibl` tool to access the system's capabilities.
- **Node Abstraction**: 5 nodes (sense, self, limbs, others, engines) with 321 atomic actions.
- **Action Routing**: Dual-path routing via `api_engine` (automatic API discovery) and `handler` (complex logic).
- **User Interaction as self**: Questions (`[self:ask_user]`), Todos (`[self:todo]`), Approvals (`[self:approve]`), and Notifications (`[self:notify_user]`) are all integrated into the `self` node.

---

## Core Architecture: IBL (IndieBiz Logic)

IndieBiz OS uses a domain-specific language called **IBL** as its unified interface.

### 5 Nodes, 321 Atomic Actions

| Node | Actions | Description |
|------|---------|-------------|
| **sense** | 105 | Data retrieval (web, finance, photos, blog, memory, health, real estate) |
| **self** | 57 | System management, workflows, files, notifications, code execution, health |
| **limbs** | 97 | UI automation (browser, Android, macOS), media playback (YouTube, radio) |
| **others** | 16 | Collaboration, delegation, email, contacts, messaging |
| **engines** | 46 | Content creation (slides, video, charts, images, music, websites, architecture) |

### How It Works

```
User: "Search AI news and save to file"
         |
AI decides: execute_ibl(code='[sense:web_search]{query: "AI news"} >> [self:file]{path: "result.md"}')
         |
IBL Engine: parse -> dispatch to handler/api_engine -> return result
```

**Key design principles:**
- **One tool, one language** - AI agents learn one syntax, not 300+ tool schemas
- **Dynamic tool definition** - `execute_ibl` description is generated at runtime
- **Per-agent filtering** - Each agent's `allowed_nodes` restricts access
- **Usage RAG** - Past successful IBL examples are searched and injected as references
- **Atomic actions** - 97% of actions are single API/DB calls

---

## Core Features

### Project System (Unlimited Workspaces)
- Create as many projects as you need (24 active projects currently)
- Each project has its own conversation history, agents, and context

### Agent Teams (Delegation Chain)
- Define multiple agents per project with different personalities
- Agents can delegate tasks to each other (async or sync) or even across projects

### IBL Usage RAG (Learning from Experience)
Agents improve over time through a RAG system that learns from successful IBL executions:
- **Usage Dictionary**: ~970 examples (synthetic data + auto-promoted execution logs)
- **Hybrid Search**: Semantic (ko-sroberta) + BM25 (FTS5)
- **Prompt Injection**: Top 3 similar examples injected as XML references

### Advanced Automation
- **Scheduler**: Automate repetitive tasks with cron-like scheduling
- **Auto-response V3**: Intelligent message handling using Tool-use based judgment
- **Remote Finder/Launcher**: Access your files and control your AI remotely via secure tunnels

---

## Technical Stack

- **Backend**: Python FastAPI (19+ module routers, AI Agent Core, System AI Core)
- **Frontend**: Electron + React (Real-time streaming via WebSocket)
- **AI Providers**: Anthropic (Claude), OpenAI (GPT), Google (Gemini), Ollama (Local)
- **Database**: SQLite (Business, Multi-chat, IBL RAG)
- **Deployment**: Local execution with optional Cloudflare Tunnel for remote access

---
*IndieBiz OS - Your Personal AI Assistant Team*
