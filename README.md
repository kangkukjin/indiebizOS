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
[sense:search_ddg]{query: "AI news"}
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

### 4. Agent Self-Regulation (Phase 26)

Agents aren't just tools — they **know when to act, when to stop, and when to change strategy**.

- **Goal/Time/Condition System** - Set goals, time limits, and conditional triggers per task. Agents self-terminate when objectives are met or time runs out.
- **Strategy Escalation** - After 3 consecutive failures in the same approach category, agents are forced to switch strategies. When all categories are exhausted, they report to the user instead of looping.
- **Round Memory** - Every attempt is logged with approach category, result, and lessons learned. Agents review past attempts before trying again, eliminating redundant approaches.

### 5. Three-Agent Cognitive Architecture (Reflex, Planning, Reflection)

Most AI systems treat every request the same way. IndieBiz OS models human cognition with **three distinct agents** that process every request in sequence:

```
User Message
    |
    v
[Unconscious Agent] -- Reflex: EXECUTE or THINK?
    |                        |
    | EXECUTE (simple)       | THINK (complex)
    v                        v
[Direct Execution]    [Consciousness Agent] -- Planning: problem definition + achievement criteria
                             |
                             v
                      [AI Agent Execution]
                             |
                             v
                      [Evaluator Agent] -- Reflection: achieved or retry?
                             |
                      (max 3 rounds)
```

**Unconscious Agent** (Phase 28) - A lightweight gatekeeper using gemini-2.5-flash-lite that classifies each request as either EXECUTE (simple tasks that can skip metacognition) or THINK (complex tasks requiring full consciousness processing). This eliminates unnecessary overhead for straightforward requests.

**Consciousness Agent** - Performs meta-judgment before complex requests reach the AI agent: not just "what should be done" but **"how hard is this for me, given what I have?"** Now also outputs **achievement_criteria** -- a measurable definition of success that the evaluator uses.

The core principle: **A problem is born where my limits meet the environment's constraints.** The same command creates different problems depending on what tools you have and how good they are.

- **Task Framing** - Defines the problem including an assessment of tool capabilities and their limits
- **Achievement Criteria** - Measurable success conditions for post-execution evaluation
- **Self-Awareness** - Assesses what the agent can do **and how well**. Each IBL action's `implementation` field enables quality judgment.
- **History Refinement** - Compresses conversation history into a focused summary
- **IBL Focusing** - Highlights relevant nodes/actions with implementation details
- **Guide File Selection** - Picks the most relevant guide documents
- **Context Notes** - World state, situational awareness

**Evaluator Agent** (Phase 28) - After the AI agent responds, evaluates the result against the consciousness agent's achievement_criteria. If NOT_ACHIEVED, re-executes with specific feedback. Maximum 3 evaluation rounds prevent infinite loops.

Applies to both System AI and all Project Agents. Internal delegation messages bypass the consciousness agent.

---

## Unified AI Architecture (Phase 25: 5-Node Integration)

IndieBiz OS features a unified AI core where the **System AI** and **Project Agents** share the same codebase and tool structure.

- **execute_ibl 단일 도구**: All AI entities use a single `execute_ibl` tool to access the system's capabilities.
- **Node Abstraction**: 5 nodes (sense, self, limbs, others, engines) with 308 atomic actions.
- **Action Routing**: Dual-path routing via `api_engine` (automatic API discovery) and `handler` (complex logic).
- **User Interaction as self**: Questions (`[self:ask_user]`), Todos (`[self:todo]`), Approvals (`[self:approve]`), and Notifications (`[self:notify_user]`) are all integrated into the `self` node.

---

## Core Architecture: IBL (IndieBiz Logic)

IndieBiz OS uses a domain-specific language called **IBL** as its unified interface.

### 5 Nodes, 308 Atomic Actions

| Node | Actions | Description |
|------|---------|-------------|
| **sense** | 78 | Data retrieval (web, finance, photos, blog, memory, health, real estate) |
| **self** | 75 | System management, workflows, files, notifications, code execution, health |
| **limbs** | 96 | UI automation (browser, Android, macOS), media playback (YouTube, radio) |
| **others** | 13 | Collaboration, delegation, email, contacts, messaging |
| **engines** | 46 | Content creation (slides, video, charts, images, music, websites, architecture) |

### How It Works

```
User: "Search AI news and save to file"
         |
AI decides: execute_ibl(code='[sense:search_ddg]{query: "AI news"} >> [self:file]{path: "result.md"}')
         |
IBL Engine: parse -> dispatch to handler/api_engine -> return result
```

**Key design principles:**
- **One tool, one language** - AI agents learn one syntax, not 300+ tool schemas
- **Dynamic tool definition** - `execute_ibl` description is generated at runtime
- **Per-agent filtering** - Each agent's `allowed_nodes` restricts access
- **Usage RAG** - Past successful IBL examples are searched and injected as references
- **Atomic actions** - 97% of actions are single API/DB calls
- **Sensory Feedback** - Pipeline results are fully accumulated (no truncation); `>>` halts on error; `_action_count × 16KB` dynamic limit ensures AI sees all intermediate results
- **Sensory Preprocessing** - Information-gathering actions (search, crawl, travel) compress their output via lightweight AI before returning to the agent, preventing context overflow in agentic loops. Configured per-action in `ibl_actions.yaml` with `postprocess` blocks. 65-70% compression in practice.
- **$file:N Parameter** - Pass long code/text via `files` parameter outside IBL parser, referenced as `$file:0`, `$file:1` in IBL code

---

## Core Features

### Project System (Unlimited Workspaces)
- Create as many projects as you need (22 active projects currently)
- Each project has its own conversation history, agents, and context

### Agent Teams (Delegation Chain)
- Define multiple agents per project with different personalities
- Agents can delegate tasks to each other (async or sync) or even across projects

### 3-Layer Delegation System (Phase 27)

| Method | Description | Best For |
|--------|-------------|----------|
| **Sync Delegation** (`call_agent`) | Agent calls another agent directly and waits for result | Simple tasks needing immediate response |
| **Schedule Delegation** (`schedule`) | Register a schedule owned by another agent for time-based delegation | Periodic or delayed tasks |
| **Plan Delegation** (`create_plan` + `execute_plan`) | Write a natural language plan and agents execute steps in order | Complex multi-step workflows |

**Schedule Delegation** - Specify `target_project_id`/`target_agent_id` to make the target agent own and execute the schedule:
```
[self:schedule]{at: "09:00",
  target_project_id: "investing", target_agent_id: "analyst",
  pipeline: "[sense:search_ddg]{query: 'today news'}"}
```

**Plan Delegation** - Structured plans for multi-agent sequential execution:
```
[self:create_plan]{title: "Data Analysis", steps: [...]}
  → [self:execute_plan]{file: "plan.md"}
  → Agent executes its part → Updates plan status → Delegates to next agent
```
- Per-step status tracking (`pending` → `in_progress` → `completed`/`failed`)
- Automatic retry on failure with alternative paths

### IBL Usage RAG (Learning from Experience)
Agents improve over time through a RAG system that learns from successful IBL executions:
- **Usage Dictionary**: ~970 examples (synthetic data + auto-promoted execution logs)
- **Hybrid Search**: Semantic (ko-sroberta) + BM25 (FTS5)
- **Prompt Injection**: Top 3 similar examples injected as XML references

### Advanced Automation
- **Scheduler**: Automate repetitive tasks with cron-like scheduling
- **Auto-response V3**: Intelligent message handling using Tool-use based judgment
- **Remote Finder/Launcher**: Access your files and control your AI remotely via secure tunnels
- **Live CCTV (UTIC + ITS + Windy)**: 16,000+ Korean traffic CCTVs via UTIC real-time API, plus ITS highways and Windy global webcams

---

## Technical Stack

- **Backend**: Python FastAPI (19+ module routers, AI Agent Core, System AI Core)
- **Frontend**: Electron + React (Real-time streaming via WebSocket)
- **AI Providers**: Anthropic (Claude), OpenAI (GPT), Google (Gemini), Ollama (Local)
- **Database**: SQLite (Business, Multi-chat, IBL RAG)
- **Deployment**: Local execution with optional Cloudflare Tunnel for remote access

---
*IndieBiz OS - Your Personal AI Assistant Team*
*Last updated: 2026-03-29*
