# IndieBiz OS

**A Personal AI Operating System for Individuals and Small Businesses**

[Homepage](https://indiebiz-homepage.vercel.app) | English | [한국어](README.ko.md)

IndieBiz OS is not just another AI chatbot. It's a complete operating system where you can create unlimited AI agent teams, each working in isolated project workspaces with their own specialized tools.

---

## Why IndieBiz OS?

### The Problem with "Universal AI"

Most AI systems try to be one all-knowing assistant. This approach fails because:

- **Context pollution**: Your medical consultation gets mixed with your hardware projects
- **Tool overload**: 100 tools confuse a single agent
- **No automation**: You must manually trigger every action
- **No separation**: Can't easily delete or isolate work domains

### The IndieBiz Approach

> "Many purpose-built AIs beat one universal AI"

![IndieBiz OS Launcher](fig1.jpg)
*Project folders as an OS desktop - each folder is an isolated AI workspace*

![Agent Team](fig2.jpg)
*Medical project with specialized agents (Internal Medicine, Urology, Cardiology, Family Medicine)*

![Tool Packages](fig3.jpg)
*Dynamic tool loading - agents only see the tools they need*

![Business Manager](fig4.jpg)
*Business network with auto-response toggle and neighbor management*

![IndieNet](fig5.jpg)
*Decentralized communication via Nostr protocol*

```
IndieBiz OS
├── Medical Project
│   ├── Internal Medicine Agent (GPT-4o-mini, cheap)
│   ├── Orthopedic Agent (Claude Sonnet)
│   └── Pharmacist Agent (local LLM, free)
│
├── Real Estate Project
│   ├── Tax Advisor Agent (Claude Opus, accurate)
│   └── Legal Agent (Claude Sonnet)
│
└── Startup Project
    ├── Marketing Agent
    └── Developer Agent
```

Each project is **completely isolated**. Delete a project, and everything related disappears cleanly.

---

## Core Features

### 1. Project System (Unlimited Workspaces)

- Create as many projects as you need
- Each project has its own conversation history, agents, and context
- Copy projects to create variations
- Delete projects without affecting others

### 2. Agent Teams (Delegation Chain)

- Define multiple agents per project with different roles
- Agents can delegate tasks to each other
- Parallel delegation: one agent can dispatch to multiple agents simultaneously
- Automatic result reporting back through the chain

```yaml
# Example: agents.yaml
agents:
  coordinator:
    role: "Route requests to specialists"
    model: claude-sonnet

  researcher:
    role: "Deep research and analysis"
    model: claude-opus
    allowed_tools: [web-search, web-crawl]

  coder:
    role: "Write and execute code"
    model: gpt-4o
    allowed_tools: [python-exec, nodejs]
```

### 3. Dynamic Tool Loading

- Tools are loaded **per-agent**, not globally
- Add 1000 tools without overwhelming any single agent
- Each specialist only sees the tools they need

**Installed Tool Packages:**

| Package | Description |
|---------|-------------|
| android | Android device management (adb) |
| blog | Blog RAG search and insights |
| browser-automation | Web automation (Playwright) |
| information | API Ninjas, travel info, publishing |
| nodejs | JavaScript/Node.js execution |
| pc-manager | File and storage management |
| python-exec | Python code execution |
| system_essentials | File management, search, utilities |
| web-crawl | Web page crawling |
| web-search | Web search (DuckDuckGo, Google News) |
| youtube | YouTube video/audio management |

### 4. Scheduler (Automated Execution)

- Schedule tasks with cron expressions
- Agents work automatically without manual triggers
- Examples:
  - Daily news summary at 9 AM
  - Hourly server health check
  - Weekly report generation

### 5. Switches (Event Triggers)

- Define conditions that trigger agent actions
- React to external events automatically

### 6. Business Network (Communication Channels)

- **Gmail Integration**: Receive and process emails
- **Nostr Integration**: Real-time decentralized messaging
- **Neighbor Management**: Track business partners and contacts
- **Auto-Response**: AI generates contextual replies based on:
  - Work guidelines
  - Business documents
  - Conversation history

### 7. System AI (Meta-Controller)

- Sits above all projects
- Manages system-wide settings
- References system documentation as long-term memory
- Provides guidance and coordination

---

## Architecture

```
indiebizOS/
├── backend/              # Python FastAPI (port 8765)
│   ├── api.py           # Main server
│   ├── ai_agent.py      # Agent core
│   ├── agent_runner.py  # Delegation chain executor
│   ├── system_ai.py     # System AI core
│   ├── scheduler.py     # Task scheduler
│   ├── auto_response.py # Auto-response service
│   └── channel_poller.py # Gmail/Nostr message receiver
│
├── frontend/            # Electron + React (TypeScript)
│   ├── electron/        # Main/preload
│   └── src/             # React components
│
├── data/
│   ├── packages/        # Tool packages
│   │   ├── installed/   # Active packages
│   │   ├── not_installed/ # Available packages
│   │   └── dev/         # Development packages
│   └── system_docs/     # System AI memory
│
└── projects/            # User projects
    └── {project_id}/
        ├── agents.yaml  # Agent definitions
        └── conversations.db # Conversation history
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- API keys for AI providers (Claude, OpenAI, etc.)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/indiebizOS.git
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
npm run electron:build:mac   # macOS
npm run electron:build:win   # Windows
```

---

## Philosophy

### Human-in-the-Loop AGI

We don't believe in a single, all-knowing AGI. Instead, we believe:

> **AGI = Federation of Specialized AIs + Human**

```
        ┌─────────────────────────────────┐
        │            HUMAN                │
        │   (Connector, Judge, Owner)     │
        └─────────────┬───────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │ Medical │   │ Finance │   │ Startup │
   │  Team   │   │  Team   │   │  Team   │
   └─────────┘   └─────────┘   └─────────┘
```

**The human is part of the system**, not just a user:
- Connects insights across different domains
- Makes final decisions
- Takes responsibility
- Provides ethical judgment

**Why this is better than a single AGI:**

| Single AGI | IndieBiz Approach |
|------------|-------------------|
| One system decides everything | Human makes final calls |
| One failure breaks all | Failures are isolated |
| Unclear accountability | Human is accountable |
| Hallucinations spread | Domain experts can verify |
| Black box | Transparent, modular |

This isn't a limitation—it's a feature. The safest, most practical path to general intelligence is **distributed intelligence with human oversight**.

---

### Why Project Isolation Matters

1. **Clean deletion**: Remove a project, remove all its data
2. **Context accuracy**: Medical agents don't see hardware code
3. **Cost optimization**: Use expensive models only where needed
4. **Experimentation**: Create throwaway agents, test prompts freely

### Why Many Agents Beat One

- Simple tasks → cheap/local models ($0)
- Medium tasks → mid-tier models ($0.01)
- Complex tasks → premium models ($0.10)

A single "universal agent" can't optimize this. IndieBiz can.

### Compared to Alternatives

| Feature | Claude Desktop | OpenDAN | IndieBiz OS |
|---------|---------------|---------|-------------|
| GUI | Native app | CLI/Telegram | Electron app |
| Project isolation | No | No | Yes |
| Unlimited agents | No | Limited | Yes |
| Tool scaling | MCP (limited) | Limited | Unlimited |
| Scheduler | No | No | Yes |
| Business network | No | No | Yes |
| Auto-response | No | No | Yes |

---

## Use Cases

- **Solopreneur**: Automate customer communication, research, content creation
- **Consultant**: Separate projects per client, specialized agent teams
- **Developer**: Code execution, documentation, testing agents
- **Investor**: Market research, portfolio analysis, news monitoring
- **Healthcare**: Separate medical domains, privacy-respecting isolation

---

## Status

**This project is under active development.**

This is a working personal project with:
- 11 active projects in production use
- 13 installed tool packages
- Functional scheduler, switches, and business network

### Design Philosophy: Your OS, Your Way

IndieBiz OS is designed to be **customized by each user**. There is no "correct" way to use it.

- **Fork and modify**: This is your personal operating system—change anything
- **Add your own tools**: Create packages that fit your workflow
- **Define your own agents**: Build teams that match your thinking style
- **No prescribed structure**: Organize projects however makes sense to you

The goal is not to build a product everyone uses the same way, but to provide a foundation that each person can adapt to their unique needs. Think of it as a starting point, not a finished product.

Contributions and feedback welcome.

---

## License

MIT License

---

*IndieBiz OS - Your Personal AI Team, Not Just Another Chatbot*
