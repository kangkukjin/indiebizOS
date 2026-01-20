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
    allowed_tools: [health-record, web-search]
```

| Generic AI | IndieBiz Persona |
|------------|------------------|
| "You may have hypertension. Consult a doctor." | "I can see you're worried. Let me ask a few questions first... Based on your history, here's what I recommend..." |
| Information delivery | Empathetic conversation with context |

**Each agent remembers your context** - your medications, preferences, past conversations. They're not generic assistants; they're **your** specialists.

### 2. One-Click Automation with Switches

Stop repeating the same AI conversations. **Save them as Switches** and execute with one click.

**Before (Manual):**
```
1. Open AI chat
2. Type "Find today's tech news"
3. Wait for results
4. Copy and paste
5. Type "Summarize this"
6. Save to file manually
7. Repeat tomorrow...
```

**After (Switch):**
```
[Toggle] Daily Tech News  →  Click  →  Done!
         ↓
    AI executes predefined prompt
         ↓
    Results saved to outputs/daily_news.md
```

**Switch Features:**
- **Natural language definition** - Write prompts as you normally would
- **Scheduled execution** - Run daily at 8 AM, weekly on Fridays
- **Agent assignment** - Specify which agent handles the switch
- **Output storage** - Results automatically saved to files

**Example Switches:**
| Switch | Prompt | Schedule |
|--------|--------|----------|
| Daily News | "Collect AI/blockchain news and summarize in 5 bullets" | Daily 8 AM |
| Weekly Report | "Analyze this week's work logs and generate productivity report" | Friday 6 PM |
| Market Watch | "Check my watchlist stocks and alert on anomalies" | Daily market close |

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
*Dynamic tool loading - agents only see the tools they need*

![Business Manager](fig4.jpg)
*Business network with auto-response toggle and neighbor management*

![IndieNet](fig5.jpg)
*Decentralized communication via Nostr protocol*

```
IndieBiz OS
├── Medical Project
│   ├── Dr. Kim (empathetic internist)
│   ├── Dr. Park (detail-oriented orthopedist)
│   └── Pharmacist Lee (medication checker)
│
├── Real Estate Project
│   ├── Tax Advisor (conservative, thorough)
│   └── Legal Advisor (fact-focused)
│
└── Startup Project
    ├── Marketing Agent (creative)
    └── Developer Agent (practical)
```

Each project is **completely isolated**. Delete a project, and everything related disappears cleanly.

---

## Core Features

### Project System (Unlimited Workspaces)

- Create as many projects as you need
- Each project has its own conversation history, agents, and context
- Copy projects to create variations
- Delete projects without affecting others

### Agent Teams (Delegation Chain)

- Define multiple agents per project with different personalities
- Agents can delegate tasks to each other
- Parallel delegation: one agent can dispatch to multiple agents simultaneously
- Automatic result reporting back through the chain

### Dynamic Tool Loading

- Tools are loaded **per-agent**, not globally
- Add 1000 tools without overwhelming any single agent
- Each specialist only sees the tools they need

**Installed Tool Packages (19):**

| Package | Description |
|---------|-------------|
| android | Android device management (adb) |
| blog | Blog RAG search and insights |
| culture | Korean cultural data (performances, libraries, exhibitions) |
| health-record | Personal health data management |
| information | API Ninjas, travel info, restaurant search |
| investment | Global financial data (KRX, DART, SEC, Yahoo Finance) |
| kosis | Korean Statistics (KOSIS) data retrieval |
| nodejs | JavaScript/Node.js execution |
| pc-manager | File and storage management, system analysis |
| photo-manager | Photo library management |
| python-exec | Python code execution |
| read-and-see | Document reading and visual analysis |
| real-estate | Korean real estate data |
| startup | Korean startup support |
| study | Study helper and paper summarization |
| system_essentials | File management, search, utilities |
| visualization | Charts (line, bar, candlestick, pie, scatter, heatmap) |
| web | Web search and crawling |
| youtube | YouTube video/audio management |

### Scheduler & Switches

- **Switches**: Save any prompt as a reusable automation
- **Scheduler**: Run switches automatically with cron expressions
- **Examples**:
  - Daily news summary at 9 AM
  - Hourly server health check
  - Weekly report generation

### Business Network

- **Gmail Integration**: Receive and process emails
- **Nostr Integration**: Decentralized messaging
- **Neighbor Management**: Track business partners
- **Auto-Response V2**: Intelligent two-stage AI response system:
  - **Stage 1 - AI Judgment**: Analyzes incoming messages to determine response necessity
    - Message intent classification (business inquiry vs. personal chat vs. spam)
    - Business matching from your registered business list
    - Detects when requested service doesn't exist in your offerings
  - **Stage 2 - Response Generation**: Creates contextual replies using:
    - Chain-of-Thought reasoning + Few-shot learning
    - Work guidelines + business documents + conversation history
    - Graceful handling when no matching business found
  - **Pending Message Queue**: Auto-sends generated responses via background worker
  - **Multi-Channel Support**: Same logic works across Gmail and Nostr

### Multi-Chat Rooms

- **Separate windows**: Each chat room opens in its own window
- **Summon agents**: Bring agents from any project into a conversation
- **@mentions**: Target specific agents with @name syntax
- **Tool assignment**: Assign specific tools to each agent

### System AI (Meta-Controller)

- Sits above all projects
- Manages system-wide settings
- References system documentation as long-term memory
- **Delegation to Project Agents**: Can dispatch tasks to specialized project agents
  - `list_project_agents`: View all projects and their agents
  - `call_project_agent`: Delegate tasks to specific agents
  - Parallel delegation to multiple projects
  - Only delegates when user explicitly requests it

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
│   │   └── not_installed/ # Available packages
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
- API keys for AI providers (Claude, OpenAI, etc.) or Ollama for local LLMs

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
npm run electron:build:mac   # macOS
npm run electron:build:win   # Windows
```

---

## Philosophy

### Human-in-the-Loop Intelligence

We don't believe in a single, all-knowing AGI. Instead:

> **Practical AI = Federation of Specialized AIs + Human Oversight**

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

The human is part of the system:
- Connects insights across domains
- Makes final decisions
- Takes responsibility
- Provides ethical judgment

### Compared to Alternatives

| Feature | Claude Desktop | ChatGPT | IndieBiz OS |
|---------|---------------|---------|-------------|
| Custom personas | Limited | Limited | **Full control** |
| One-click automation | No | No | **Yes (Switches)** |
| Project isolation | No | No | **Yes** |
| Unlimited agents | No | No | **Yes** |
| Scheduler | No | No | **Yes** |
| P2P Network | No | No | **Yes (IndieNet)** |
| Local data | No | No | **Yes** |
| Offline capable | No | No | **Yes (Ollama)** |

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

- 16 active projects in production use
- 19 installed tool packages
- Functional scheduler, switches, and business network
- Advanced Auto-Response V2: AI judgment → business search → response generation → pending queue → auto-send
- System AI delegation to project agents

### Your OS, Your Way

IndieBiz OS is designed to be **customized by each user**.

- **Fork and modify**: This is your personal operating system
- **Add your own tools**: Create packages that fit your workflow
- **Define your own personas**: Build agents that match your needs
- **No prescribed structure**: Organize however makes sense to you

The goal is not a product everyone uses the same way, but a foundation you adapt to your unique needs.

Contributions and feedback welcome.

---

## License

MIT License

---

*IndieBiz OS - Design. Automate. Connect.*
