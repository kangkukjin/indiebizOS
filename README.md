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
    allowed_nodes: [source, system, forge, interface, stream, messenger]
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
[source:search]("AI news") {type: "news"}
  >> [system:agent_ask_sync]("컨텐츠/컨텐츠") {message: "Summarize these articles"}
  >> [system:file]("news_report.html") {format: "html"}
```

**Features:**
- **Natural language or IBL code** - Write prompts or program action chains
- **Scheduled execution** - Run daily at 8 AM, weekly on Fridays
- **Agent assignment** - Specify which agent handles the task
- **Pipeline operators** - Sequential (>>), Parallel (&), Fallback (??)
- **Alias execution** - Run saved workflows by name: `[system:run]("kinsight")`

### 3. P2P Network (IndieNet)

Connect with others through decentralized, censorship-resistant networks.

- **Nostr Protocol** - No central server, no data collection
- **Public Board** - Share and discover with other IndieBiz users
- **Encrypted DMs** - Private messages only you and the recipient can read
- **Business Network** - Manage partners, auto-respond to inquiries

---

## Why IndieBiz OS?

### The Problem with "Universal AI"

Most AI systems try to be one all-knowing assistant. This approach fails because:

- **Context pollution**: Your medical consultation gets mixed with your hardware projects
- **No personalization**: Every AI sounds the same, generic responses
- **No automation**: You must manually trigger every action
- **Platform lock-in**: Your data lives on their servers

### The IndieBiz Approach

> "Many purpose-built AIs beat one universal AI"

![IndieBiz OS Launcher](fig1.jpg)
*Project folders as an OS desktop - each folder is an isolated AI workspace*

![Agent Team](fig2.jpg)
*Medical project with specialized agents (Internal Medicine, Urology, Cardiology, Family Medicine)*

![Tool Packages](fig3.jpg)
*Dynamic action loading - agents only see the actions they need*

![Business Manager](fig4.jpg)
*Business network with auto-response toggle and neighbor management*

![IndieNet](fig5.jpg)
*Decentralized communication via Nostr protocol*

```
IndieBiz OS
|-- Medical Project
|   |-- Dr. Kim (empathetic internist)
|   |-- Dr. Park (detail-oriented urologist)
|   +-- Dr. Lee (family medicine)
|
|-- Real Estate Project
|   |-- Tax Advisor (conservative, thorough)
|   +-- Legal Advisor (fact-focused)
|
+-- Startup Project
    |-- Marketing Agent (creative)
    +-- Developer Agent (practical)
```

Each project is **completely isolated**. Delete a project, and everything related disappears cleanly.

---

## Core Architecture: IBL (IndieBiz Logic)

IndieBiz OS uses a domain-specific language called **IBL** as its unified interface between AI agents and the system. Instead of giving each agent hundreds of individual tools, every agent receives a **single tool** (`execute_ibl`) and an XML-structured environment prompt describing available nodes and actions.

### 6 Nodes, ~330 Atomic Actions

```
system    (~65 actions)  - System management, workflows, files, notifications, code execution
interface (~79 actions)  - UI automation (browser / Android / macOS desktop)
source    (~100 actions) - Data retrieval (web, finance, photos, blog, memory, health)
stream    (~22 actions)  - Media playback (YouTube / internet radio)
forge     (~58 actions)  - Content creation (slides, video, charts, images, music, websites)
messenger (~9 actions)   - Contacts and messaging
```

### How It Works

```
User: "Search AI news and save to file"
         |
AI decides: execute_ibl(code='[source:web_search]("AI news") >> [system:file]("result.md")')
         |
IBL Engine: parse -> dispatch to handler -> return result
```

**Key design principles:**
- **One tool, one language** - AI agents learn one syntax, not 300+ tool schemas
- **Dynamic tool definition** - `execute_ibl` description is generated at runtime from `ibl_nodes.yaml`, so it always reflects installed packages
- **Per-agent filtering** - Each agent's `allowed_nodes` restricts which nodes appear in the tool definition, system prompt, and runtime — three consistent layers
- **Atomic actions** - 97% of actions are single API/DB calls (true atoms)
- **Verb abstraction** - Common verbs like `search`, `get`, `create` route to specific actions by type
- **Two ways to extend** - Save IBL pipelines as workflows (no code) or write Python packages (new atoms)

### Workflows as Reusable Actions

```yaml
# data/workflows/kinsight.yaml
name: "kinsight"
pipeline: >
  [source:search]("recent posts") {type: "blog", count: 10}
  >> [system:agent_ask_sync]("content/content") {message: "Analyze and write insight report"}
  >> [system:file]("kinsight_report.html") {format: "html"}
```

Execute by name: `[system:run]("kinsight")`

---

## Core Features

### Project System (Unlimited Workspaces)

- Create as many projects as you need
- Each project has its own conversation history, agents, and context
- Copy projects to create variations
- Delete projects without affecting others

### Agent Teams (Delegation Chain)

- Define multiple agents per project with different personalities
- Agents can delegate tasks to each other (async or sync)
- Parallel delegation: one agent can dispatch to multiple agents simultaneously
- Automatic result reporting back through the chain

### Dynamic Action Loading

- Actions are filtered **per-agent** via `allowed_nodes` in agents.yaml
- The `execute_ibl` tool definition itself is dynamically generated — each agent's tool description only shows their permitted nodes
- Add hundreds of actions without overwhelming any single agent
- Each specialist only sees the nodes they need
- XML-structured environment prompt with verb tables and action catalogs

### Self-Contained Action Packages (30 installed)

Each package is **self-contained**: it includes its own `ibl_actions.yaml` declaring which IBL actions it provides. When a package is installed, its actions are **automatically registered** into `ibl_nodes.yaml`. When uninstalled, they are **automatically removed**. This means:

- **No manual YAML editing** — install a package and its actions are immediately available
- **Clean uninstall** — removing a package cleanly removes only its actions
- **Shareable via Nostr** — packages can be shared over the P2P network; recipients just install and actions work
- **Provenance tracking** — `_ibl_provenance.yaml` tracks which package owns each action

| Package | Description |
|---------|-------------|
| android | Android device management (adb) |
| blog | Blog RAG search and insights |
| browser-action | Playwright-based browser automation (click/input/scroll/extract) |
| business | Business relationships and contact (neighbor) management |
| cctv | CCTV monitoring and management |
| cloudflare | Cloudflare services (Pages, Workers, R2, D1, Tunnel) |
| computer-use | Computer use automation (screen capture, mouse/keyboard control) |
| culture | Korean cultural data (performances, libraries, exhibitions) |
| health-record | Personal health data management |
| investment | Global financial data (KRX, DART, SEC, Yahoo Finance) |
| kosis | Korean Statistics (KOSIS) data retrieval |
| legal | Korean legal information search (laws, precedents, regulations) |
| location-services | Location-based services (weather, restaurants, directions, travel) |
| media_producer | HTML-based slides (12 themes), video production, AI image generation |
| music-composer | ABC notation composing, MIDI generation, audio conversion |
| nodejs | JavaScript/Node.js execution |
| pc-manager | File and storage management, system analysis |
| photo-manager | Photo library management |
| python-exec | Python code execution |
| radio | Internet radio search and playback (Radio Browser API + Korean broadcasters) |
| real-estate | Korean real estate data |
| remotion-video | React/Remotion-based programmatic video generation |
| shopping-assistant | Shopping search (Naver, Danawa price comparison) |
| startup | Korean startup support |
| study | Study helper and paper summarization |
| system_essentials | File management, todo, plan mode, neighbor lookup |
| visualization | Charts (line, bar, candlestick, pie, scatter, heatmap) |
| web | Web search, crawling, news, newspaper generation, bookmarks |
| web-builder | Website builder and generator |
| youtube | YouTube video/audio management |

### Scheduler, Switches & Workflows

- **Switches**: Save any prompt + agent as a reusable one-click automation
- **Workflows**: Chain IBL actions into reusable pipelines (with AI thinking steps via `agent_ask_sync`)
- **Scheduler**: Run switches/workflows automatically with cron expressions
- **Examples**:
  - Daily news summary at 9 AM
  - Blog insight report generation
  - Weekly investment analysis

### Remote Access (Finder & Launcher)

Control your home server from anywhere via Cloudflare Tunnel:

**Remote Finder** (`/nas/app`) - Personal NAS + Music:
- Browse files with Finder-style web interface
- Stream videos with seek support
- Download files securely
- Protect specific directories only
- **Music Streaming**: Search YouTube and stream audio directly

**Remote Launcher** (`/launcher/app`) - AI Control:
- Chat with System AI remotely
- Control project agents from your phone
- Execute switches with one tap
- Mobile-friendly dark theme UI

```
Your Phone -> Cloudflare Edge -> Tunnel -> IndieBiz OS
                 (HTTPS)        (Secure)    (localhost:8765)
                                              |-- /nas/app (Files + Music)
                                              +-- /launcher/app (AI Control)
```

### Custom Web Apps

Build and serve web apps directly from IndieBiz OS:

- **Inline Web Apps**: API endpoints can serve complete HTML/CSS/JS applications
- **No Separate Deployment**: Web apps run alongside IndieBiz backend
- **Cloudflare Integration**: Expose apps globally via Tunnel, or deploy to Pages/Workers
- **AI-Generated**: Agents can create web apps (dashboards, tools, games) on request

### Business Network

- **Gmail Integration**: Receive and process emails
- **Nostr Integration**: Decentralized messaging
- **Neighbor Management**: Track business partners
- **Auto-Response V3**: Single AI call with Tool Use for judgment/search/send

### Multi-Chat Rooms

- **Separate windows**: Each chat room opens in its own window
- **Summon agents**: Bring agents from any project into a conversation
- **@mentions**: Target specific agents with @name syntax

### System AI (Meta-Controller)

- Sits above all projects with access to all 6 IBL nodes
- Manages system-wide settings
- References system documentation as long-term memory
- Can delegate tasks to any project agent

---

## Data Sovereignty

**Your data stays on your computer.**

| Cloud AI | IndieBiz OS |
|----------|-------------|
| Data on their servers | Data on your PC |
| Internet required | Offline capable (Ollama) |
| Platform lock-in | Freedom of choice |
| Subscription fees | Pay per API call (or free with local LLMs) |

---

## Architecture

```
indiebizOS/
|-- backend/              # Python FastAPI (port 8765)
|   |-- api.py           # Main server (21 API routers)
|   |-- ibl_engine.py    # IBL dispatcher (node/action routing)
|   |-- ibl_parser.py    # IBL syntax parser (pipelines, parallel, fallback)
|   |-- ibl_access.py    # Node access control + XML environment builder
|   |-- ai_agent.py      # Agent core (single execute_ibl tool)
|   |-- agent_runner.py  # Delegation chain executor
|   |-- tool_loader.py   # Dynamic execute_ibl tool builder + package loader
|   |-- ibl_action_manager.py # Auto-register/unregister actions on package install/uninstall
|   |-- package_manager.py # Package install/uninstall (triggers action registration)
|   |-- workflow_engine.py # Workflow CRUD + pipeline executor
|   |-- system_ai.py     # System AI core
|   |-- scheduler.py     # Task scheduler
|   |-- auto_response.py # Auto-response service
|   +-- prompt_builder.py # Agent prompt + IBL environment injection
|
|-- frontend/            # Electron + React (TypeScript)
|   |-- electron/        # Main/preload
|   +-- src/             # React components
|
|-- data/
|   |-- ibl_nodes.yaml   # IBL language definition (6 nodes, ~330 actions, verbs)
|   |-- _ibl_provenance.yaml # Action ownership tracking (action -> package mapping)
|   |-- packages/        # Action packages (Python handlers)
|   |   |-- installed/   # Active packages (30 tools + 9 extensions)
|   |   |   +-- tools/*/ibl_actions.yaml  # Per-package action declarations
|   |   +-- not_installed/ # Available packages
|   |-- workflows/       # Saved IBL workflows (YAML)
|   +-- system_docs/     # System AI memory
|
+-- projects/            # User projects (20 active)
    +-- {project_id}/
        |-- agents.yaml  # Agent definitions (AI config, allowed_nodes)
        +-- conversations.db # Conversation history
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- API keys for AI providers (Claude, Gemini, etc.) or Ollama for local LLMs

### Installation

```bash
# Clone the repository
git clone https://github.com/kangkukjin/indiebizOS.git
cd indiebizOS

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install
```

### Running

```bash
# Option 1: Use start script
./start.sh

# Option 2: Run separately
# Terminal 1 - Backend
cd backend && python api.py

# Terminal 2 - Frontend
cd frontend && npm run electron:dev
```

### Building

```bash
cd frontend

# macOS
npm run prepare:python:mac   # Bundle Python runtime
npm run electron:build:mac

# Windows
npm run prepare:python:win   # Bundle Python runtime
npm run electron:build:win
```

**Data Storage (Production):**
- macOS: `~/Library/Application Support/IndieBiz/`
- Windows: `%APPDATA%/IndieBiz/`
- Data persists across app updates

---

## Philosophy

### Human-in-the-Loop Intelligence

We don't believe in a single, all-knowing AGI. Instead:

> **Practical AI = Federation of Specialized AIs + Human Oversight**

```
        +----------------------------------+
        |            HUMAN                 |
        |   (Connector, Judge, Owner)      |
        +--------------+------------------+
                       |
        +--------------+--------------+
        |              |              |
   +---------+   +---------+   +---------+
   | Medical |   | Finance |   | Startup |
   |  Team   |   |  Team   |   |  Team   |
   +---------+   +---------+   +---------+
```

The human is part of the system:
- Connects insights across domains
- Makes final decisions
- Takes responsibility
- Provides ethical judgment

### Compared to Alternatives

| Feature | Claude Desktop | ChatGPT | IndieBiz OS |
|---------|---------------|---------|-------------|
| Custom personas | Limited | Limited | **Full control** |
| One-click automation | No | No | **Yes (Switches + Workflows)** |
| Project isolation | No | No | **Yes** |
| Unified action language | No | No | **Yes (IBL)** |
| Scheduler | No | No | **Yes** |
| P2P Network | No | No | **Yes (IndieNet)** |
| Local data | No | No | **Yes** |
| Offline capable | No | No | **Yes (Ollama)** |

---

## Status

**This project is under active development.**

- 20 active projects in production use
- 6 IBL nodes with ~330 atomic actions
- 30 installed action packages + 9 extension packages
- Self-contained packages with `ibl_actions.yaml` — automatic action registration on install/uninstall
- Dynamic `execute_ibl` tool definition generated from `ibl_nodes.yaml` at runtime
- Per-agent node filtering across tool definition, system prompt, and runtime (3-layer consistency)
- IBL workflow engine with pipeline operators (>>, &, ??)
- Synchronous agent delegation for AI-powered workflow steps
- XML-structured environment prompts for optimal AI recognition
- Remote Finder + Launcher via Cloudflare Tunnel

### Your OS, Your Way

IndieBiz OS is designed to be **customized by each user**.

- **Fork and modify**: This is your personal operating system
- **Add your own actions**: Create IBL workflows (no code) or Python packages with `ibl_actions.yaml` (auto-registered on install)
- **Share packages via Nostr**: Publish packages to the P2P network; recipients install and actions work immediately
- **Define your own personas**: Build agents that match your needs
- **No prescribed structure**: Organize however makes sense to you

The goal is not a product everyone uses the same way, but a foundation you adapt to your unique needs.

Contributions and feedback welcome.

---

## License

MIT License

---

*IndieBiz OS - Design. Automate. Connect.*
