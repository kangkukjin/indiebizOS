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

### Toolbox & Package Sharing (Nostr)

- **Publish packages**: Share your custom tool packages to the Nostr network
- **AI-generated docs**: Installation instructions auto-generated by AI analyzing your code
- **Search & install**: Find and install packages published by other IndieBiz users
- **AI review**: System AI reviews security, quality, and compatibility before installation
- **Agent Publishing**: Share agent personas (role definitions, tool configurations) with the community
- **Knowledge Sharing**: Published packages include usage guides that help other AI systems replicate functionality

**Installed Tool Packages (27):**

| Package | Description |
|---------|-------------|
| android | Android device management (adb) |
| blog | Blog RAG search and insights |
| browser-action | Playwright-based browser automation (click/input/scroll/extract) |
| business | Business relationships and contact (neighbor) management |
| cloudflare | Cloudflare services (Pages, Workers, R2, D1, Tunnel) |
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

### Scheduler & Switches

- **Switches**: Save any prompt as a reusable automation
- **Scheduler**: Run switches automatically with cron expressions
- **Examples**:
  - Daily news summary at 9 AM
  - Hourly server health check
  - Weekly report generation

### Remote Access (Finder & Launcher)

Control your home server from anywhere via Cloudflare Tunnel:

**Remote Finder** (`/nas/app`) - Personal NAS + Music:
- Browse files with Finder-style web interface
- Stream videos with seek support
- Download files securely
- Protect specific directories only
- **Music Streaming**: YouTube audio-only playback via yt-dlp — search, queue, shuffle/repeat, lock screen controls (Media Session API), minimal data usage on mobile

**Remote Launcher** (`/launcher/app`) - AI Control:
- Chat with System AI remotely
- Control project agents from your phone
- Execute switches with one tap
- Mobile-friendly dark theme UI

**Multi-PC Support**: Same Cloudflare account can manage tunnels for multiple PCs with unique hostnames per device.

```
Your Phone → Cloudflare Edge → Tunnel → IndieBiz OS
                 (HTTPS)        (Secure)    (localhost:8765)
                                              ├─ /nas/app (Files + Music)
                                              └─ /launcher/app (AI Control)
```

Each feature uses **separate passwords** for independent access control. External access URLs are automatically displayed in Settings when tunnel is configured.

### Custom Web Apps

Build and serve web apps directly from IndieBiz OS:

- **Inline Web Apps**: API endpoints can serve complete HTML/CSS/JS applications
- **No Separate Deployment**: Web apps run alongside IndieBiz backend
- **Cloudflare Integration**: Expose apps globally via Tunnel, or deploy to Pages/Workers
- **AI-Generated**: Agents can create web apps (dashboards, tools, games) on request

Examples:
- Photo gallery with map view
- Personal newspaper viewer
- IoT device control panel
- Custom data dashboards

### Business Network

- **Gmail Integration**: Receive and process emails
- **Nostr Integration**: Decentralized messaging
- **Neighbor Management**: Track business partners
- **Auto-Response V3**: Intelligent single-call AI response system using Tool Use:
  - **Unified Processing**: AI judgment, business search, and response sending in a single API call
  - **Built-in Tools**:
    - `search_business_items`: Search business database for relevant matches
    - `no_response_needed`: Mark as spam/ad/irrelevant (no response sent)
    - `send_response`: Generate and send response immediately
  - **Simpler Architecture**: Eliminates the need for pending queue and two-stage processing
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
│   ├── api_nas.py       # Remote Finder API (file access/streaming)
│   ├── api_launcher_web.py # Remote Launcher API (AI control)
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

## Real-World Use Cases

### 🔧 Hardware Management
- **PC File Management**: Organize files through conversation with an agent — AI assesses deletion necessity and risks
- **Android Phone Control**: Device management through an agent
- **ESP32 IoT**: Agent uploads code to ESP32 board + creates a web app → control LED switches from your phone

### ⚖️ Legal Research
- **Law Verification**: Check whether a specific tax exemption law was actually enacted by querying official government legislation databases
- **Inheritance Tax**: Search inheritance tax regulations and get consultation
- Reliable answers based on official government publications, not just news articles

### 🎬 Video / Slides / Homepage Production
- **Quick Videos**: Family photos + YouTube BGM → photo slideshow videos
- **Professional Videos**: Book review-based introduction videos (React/Remotion)
- **Presentations**: Rapidly generate slide decks
- **Homepage Management**: Remembers file locations of multiple websites, updates with modern Tailwind CSS

### 🛒 Smart Shopping
- Naver Shopping + Danawa price comparison combined with AI judgment
- Vague questions like "What should I get for my wife's birthday?" → AI selects items → searches and compares actual products

### 📚 Deep Learning & Research
- Multiple sources connected (academic papers, The Guardian, etc.) for in-depth study conversations
- "Why is fine dust bad in Korea?" → answers based on latest paper searches
- "US policy changes toward Korea after Trump's election" → report writing based on primary sources

### 🎯 Personalized Recommendations
- Assign personas to recommendation agents for restaurants, exhibitions, movies
- "50-year-old scientist" or "30-something female drama writer" perspectives → diverse viewpoints on the same question

### 🎵 Music
- **ABC Notation Composing**: "Play a lively 2-minute waltz as a quartet" → LLM generates sheet music and plays it
- **YouTube Music Playback**: "Play 3 IU songs" → AI curates selection → playback. Like having an infinite playlist

### 📷 Photo Management
- Scan photo folders → chronological view, map view
- "Where did I go in October 2024?" → answers with GPS data from photos
- "Show me photos from when I visited Suwon" → displays matching photos in browser

### 📰 Personal Newspaper
- One switch click → searches Google News with preset keywords → auto-edits into newspaper format → displays in browser
- Custom news briefing every day with a single click

### 🎥 Content
- YouTube video subtitle extraction and summary generation
- YouTube music video MP3 extraction and saving

### 💬 Multi-Chat Rooms
- Freely gather agents from any project into one chat room
- Creative uses like a three-way conversation between Admiral Yi Sun-sin, General Won Gyun, and yourself

### 🏥 Health Management
- Multiple specialist agents (internal medicine, surgery, etc.)
- Automatically records health information from conversations → personalized health consultations based on accumulated records

### 🏠 Real Estate Analysis
- Apartment and multi-family actual transaction prices, monthly/yearly rent lookup + map visualization
- Regional analysis like "How's the commercial district in Oseong, Cheongju?"

### 📈 Investment Consulting
- Investment consultation based on your stock portfolio
- Stock, gold, and cryptocurrency price graph visualization

### 📱 Remote Commands & Auto-Response
- Send commands to IndieBiz OS on your PC while on the go, via Gmail or smartphone apps like Norst
- Example: Send a Norst message "Publish a newspaper and email it to me as an attachment" → System AI executes the task
- Built-in auto-response system: When someone other than the owner sends a message, AI responds appropriately (but does not execute commands from them)
- This auto-response system serves as the foundation for automated business operations such as customer inquiry handling and reservation guidance

### 🌐 Remote Access (Personal NAS + Music + AI Control)
- **Remote Finder**: Access your PC's files from anywhere via Cloudflare Tunnel — stream videos, browse files, download securely
- **Music Streaming**: YouTube audio-only playback from your phone — yt-dlp extracts audio on your home PC, streams to your phone with minimal data. Queue management, shuffle/repeat, lock screen controls
- **Remote Launcher**: Chat with System AI and all project agents from your phone — execute switches, run automations remotely
- Turn your home PC or mini PC into a **personal NAS + music server + AI server** — no port forwarding or complex network setup
- Use it like a personal cloud: store files at home, access and stream from anywhere
- Run all your AI agents remotely — get investment analysis, legal research, or news summaries while on the go
- Finder-style web interface + mobile-friendly dark theme UI
- Secure with separate passwords for file access and AI control

### 🔄 Tool Package Sharing
- Share tool package installation info via Norst public messages
- Other users receive the info and ask their System AI to install the package adapted to their own PC
- Instead of downloading the program itself, the shared information (description, structure, dependencies, etc.) is sufficient for the System AI to build and install it

### #️⃣ Hashtag Bulletin Boards
- IndieNet hashtag-based boards: create a board with any hashtag among people who want to participate
- Semi-open structure — public for those who know the hashtag, but inaccessible without it
- Use cases include interest-based communities, small group communication, and tool package sharing channels

### ⚡ Quick Contacts
- Send messages instantly to registered contacts with a quick contact button

---

## Status

**This project is under active development.**

- 16 active projects in production use
- 27 installed tool packages (+ 9 extension packages)
- Functional scheduler, switches, and business network
- Advanced Auto-Response V3: Single AI call with Tool Use for judgment/search/send
- System AI delegation to project agents
- Remote Access: Personal NAS + Music Streaming (Remote Finder) + AI Control (Remote Launcher) via Cloudflare Tunnel

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
