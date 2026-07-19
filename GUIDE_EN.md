# IndieBiz OS User Guide

This document is a guide for those who want to actually use IndieBiz OS.

---

## Why It's Designed This Way

### AI is a Medium and a Colleague

Most AI services today are structured around conversations with "one omnipotent AI." Whether it's ChatGPT or Claude, you discuss investments, ask about PC problems, and ask health questions all in one chat window. The result: contexts get mixed, records get tangled, and the AI gets confused too.

Moreover, these "general-purpose AIs" try to give answers that fit everyone, which makes them **lack specificity**. Whether you ask for restaurant recommendations or exhibition suggestions, you only get safe, generic answers.

IndieBiz OS takes a different approach:
- Handle related tasks only within closed spaces called **Projects**
- Give **Agents** specific roles and personas
- Let humans divide and structure their work as they wish

**The Power of Persona**: The same question yields different answers depending on the agent's persona. When asked "Recommend a good restaurant in Seoul":
- "30s female drama writer" persona → atmospheric places, spaces with stories
- "50s scientist" persona → quiet places for conversation, focus on food quality
- "American philosopher" persona → unique Seoul spots seen through unfamiliar eyes

Instead of the average answer from a general AI, you get specific, distinctive answers from a particular perspective.

And because it runs locally, you can directly modify files and control hardware connected to your PC (Android phones, ESP32 boards, etc.).

### Power Comes from Connection

A single AI can't do great things alone. It needs tools to actually take action.

IndieBiz OS provides three types of connections:
- **Connection to tools**: Users can create their own tools for infinite expansion
- **Connection between agents**: Collaboration through delegation chains (single/sequential/parallel)
- **Connection to the outside world**: Communication with other users via IndieNet

Unlike MCP servers, tools are assigned per-agent, so there's no limit on the number of tools. Give 50 tools to an investment agent and 40 to a real estate agent—they won't interfere with each other.

### Agents Collaborate Autonomously

**Delegation Chain** enables agents to work like a team:
- **Single Delegation**: Investment Agent → Information Agent (data collection request)
- **Sequential Delegation**: Planning → Production → Marketing (relay-style step-by-step processing)
- **Parallel Delegation**: Content Agent simultaneously requests from Investment, Real Estate, and Startup Agents

Delegated agents automatically report results after completing tasks. For complex work, you just receive the results.

### It Starts Like an Empty PC

IndieBiz OS is **empty** when first installed. This is intentional.

If general AI services are "pre-made apps," IndieBiz OS is like a "new PC":
- You decide which tool packages to install
- You decide which projects to create
- You decide how to configure which agents

Over time, it becomes "your own AI environment." The examples below show this process.

---

## 1. Getting Started

### Purpose first — the Shared Warehouse, and why an AI agent

Hold one purpose in mind before starting, and everything else gains meaning. One axis of IndieBiz OS is the **Shared Warehouse** — drop a file into a folder and it is published to the world. Put in a video and it does what YouTube did; a post, what a blog did; a product list, what a shopping mall did. Platforms existed per-category because each needed a human-facing storefront; when the reader is an AI, no storefront is needed — one warehouse suffices.

And that warehouse is what demands the other axis, the **AI agent system**. A warehouse lives only if it is filled (agents produce reports, newspapers, and catalogs daily and auto-publish them — production becomes publication), and digging through neighbors' raw file piles to understand them is your AI's job. Just as blogs made writing meaningful and YouTube made video meaningful, a warehouse that can publish anything makes an AI that can produce anything meaningful. There are many AI agent systems in the world; what sets IndieBiz OS apart is that it is one body with its distribution and connection channel.

With that purpose in hand, what you need to get started is clearly defined: **two essential pillars** (AI + a public address), **one near-essential** (your phone), **one automatic** (Nostr), and **a few optional items** (extra communication channels). This chapter walks through them in that order.

### Core Features ↔ Required Setup (the Map)

| What you get | What it is | What it needs |
|---|---|---|
| AI agent system | Three surfaces (autopilot / cockpit / apps) — your own AI running on your PC | Pillar ① AI API key |
| Installation & repair | An external hand that builds the system and fixes it when it breaks | Pillar ① External harness |
| Shared Warehouse | Drop a file in and it's published to the world + a feed of your neighbors' warehouses | Pillar ② Cloudflare + domain |
| Remote launcher, remote NAS, portal, family newspaper, bulletin board | Every public surface you use from a browser, anywhere | Pillar ② Cloudflare + domain |
| Using it from your phone | Any phone via browser (zero install) · on Android, the phone itself becomes a second node | Pillar ③ (Android only) app install |
| Messaging other users | Nostr communication | Automatic (key = account) |
| Email, Telegram, etc. | Additional channels | Optional (when you want them) |

With pillar ① alone the agent system runs. But without pillar ② every public surface — remote access and the Shared Warehouse — stays locked, and **the system is half of itself**: it can produce, but it cannot publish or connect.

**The cost structure is simple**: the only variable cost is AI API usage. The only fixed cost is a domain, once a year (~$10). Everything else (Cloudflare, Nostr, the software itself) is free.

### Installation

1. Download the latest version from [GitHub Releases](https://github.com/kangkukjin/indiebizOS/releases)
   - macOS: `.dmg` file
   - Windows: `.exe` installer
2. Install using the downloaded file
3. Double-click the IndieBiz app icon

When the app starts, the backend server automatically starts with it.

An even better way is to **hand the whole installation to an AI harness like Claude Desktop (or Claude Code)** — one line, "Install https://github.com/kangkukjin/indiebizOS on my PC", and it clones, installs dependencies, and walks the initial setup with you in conversation. Why we recommend this is explained in pillar ① below.

**For Developers (Running from Source)**

```bash
cd backend && python api.py        # Terminal 1
cd frontend && npm run electron:dev # Terminal 2
```

### Pillar ① — AI API Key + External Harness (Essential)

**You need at least one AI API key.** This is the only variable cost and the first gate. Once past it, you can ask or instruct the System AI for everything else.

**Recommended as of 2026: Google Gemini API (free to start)**

1. Get an API key at https://aistudio.google.com
2. Enter it in Settings → API Keys tab
3. Select a model:
   - `gemini-3-flash-preview`: fast and lightweight (recommended for general use)
   - `gemini-3-pro-preview`: more powerful (for complex tasks)

If you don't know how to get an API key, ask any AI: "How do I get a Gemini API key?" Once the key is in, the System AI wakes up, and from then on you install tools, create projects, and change settings by conversation.

**An external harness (Claude Desktop, Claude Code, etc.) is effectively essential too.** Not an alternative — the other half of this pillar. Two reasons:

- **The installing blacksmith**: IndieBiz OS is not a static app finished by `npm install`; it is a system continuously forged to fit you. The harness that installs it becomes that blacksmith.
- **The recovery path**: the System AI can repair its own system, but **not when the backend itself is broken** — a patient who has lost consciousness cannot operate on themselves. That is when the external harness opens the system folder and fixes it. You can only drive a car with confidence if there is a garage to tow it to when it won't start.

**Tool API keys (weather, real estate, statistics, …) are optional and for later.** The moment you need one, the System AI tells you which key and where to get it (Settings → API Keys has per-key signup guidance and live tests).

### Pillar ② — Cloudflare Account + Your Own Domain (the Public Face)

Without this the agent system still runs, but all of the following stay locked: **remote launcher** (drive your home system from a phone browser anywhere), **remote NAS**, **Shared Warehouse** (file publishing + neighbor feed), **personal portal**, **family newspaper**, **bulletin board**. In short: the system's entire public face.

**Why Cloudflare**: the four parts you need — a tunnel (connects your home PC to the public internet without port forwarding), Workers (edge logic), R2 (cache storage), and DNS — are bundled free in one account only at Cloudflare today. The architecture costs nothing to keep running: no server fees, no bandwidth fees.

**A domain is required**: to attach a stable public address to the tunnel, your own domain must be registered on Cloudflare. About $10/year — the single fixed cost of the whole system. And it is more than a cost: your YouTube channel name belongs to YouTube, but **a domain is an address you own** — you take it with you if you ever switch providers. In the Shared Warehouse, your address *is* your identity.

**Outline** (hand the details to your harness or System AI):

1. Sign up for Cloudflare (free)
2. Buy a domain (Cloudflare Registrar, sold at cost) or move an existing domain's nameservers to Cloudflare
3. Create a tunnel (cloudflared) — connects your home PC to Cloudflare
4. Deploy the Worker — serves the public surfaces
5. Designate the Shared Warehouse folder — from now on, drop a file in and it's published

The easiest path: tell your harness "set up the Cloudflare tunnel and the Shared Warehouse", and do only the account signup and domain payment yourself.

### Pillar ③ — Your Smartphone (Near-Essential)

The phone is a two-rung ladder:

- **Rung 1 — any phone, browser (zero install)**: opens automatically once pillar ② is up. iPhone or Android, one browser address gets you the remote launcher (a remote control for your home system), remote NAS, and Shared Warehouse. Nothing to install.
- **Rung 2 — the Android app (your phone becomes a second node)**: IndieBiz OS runs on the phone itself — not a remote control but an independent body: location/microphone/camera senses, phone hardware control, clipboard straight into KakaoTalk, working even when the home PC is off. Installation currently needs a USB cable and a script, so we recommend telling your harness "install IndieBiz on my phone".

Rung 1 is enough for daily use. Climb to rung 2 when the phone becomes a place you actively work.

### Automatic — Your Nostr Identity

Nostr is a communication protocol with no signup: generating a key *is* opening an account. IndieBiz OS generates the key automatically, and its public key (npub) becomes your contact address, automatically attached to what you publish in the Shared Warehouse. There is nothing for you to do.

### Optional — More Communication Channels

Set these up only when you want them. Let the System AI drive, but know the difficulty going in:

- **Telegram (bot)**: easy — one chat with BotFather issues a token
- **Matrix**: easy — sign up on a homeserver
- **Email (Gmail)**: hard — creating a Google Cloud project, configuring the OAuth consent screen, issuing a client ID, and publishing the app takes several steps. Walk through it with your harness if you want it.
- **KakaoTalk**: no personal messaging API exists, so it can't be a channel — instead the Android app (pillar ③, rung 2) reaches it via the clipboard.

### Getting-Started Checklist

1. **Install** — tell Claude Desktop "install it" (or download from Releases)
2. **Enter an AI API key** — the System AI wakes up (minimum working system ends here)
3. **Cloudflare + domain** — the public face turns on (strongly recommended — without it the system is half of itself)
4. **Phone** — open the remote launcher in a browser; on Android, install the app
5. **Everything else** — by conversation with the System AI: create projects, install tools, add channels

---

## 2. Core Concepts

### Structure

```
IndieBiz OS
├── Projects (Investment, Real Estate, Medical, ...)
│   └── Agents (each with roles and tools)
└── Tool Packages (installable/removable feature sets)
```

### Projects

Independent workspaces. Conversation history and context don't mix between projects.

Examples:
- **Investment**: Stock analysis, financial statements, market news
- **Real Estate**: Transaction price lookup, area analysis
- **Medical**: Health consultation, medication management

### Agents

The AI you actually talk to within a project. Each agent has:
- **Role**: What kind of expert, how they communicate
- **Tools**: What functions they can use
- **AI Model**: Which provider/model to use

You can have multiple agents in one project. Like having internal medicine, dermatology, and family medicine agents in a medical project.

### Tool Packages

Collections of features that agents can use. You can install/remove them within the app.

Examples:
- **investment**: Korea/US stock prices, financial statements, disclosure lookup
- **real-estate**: Apartment/house transaction prices
- **web**: Web search, crawling
- **media_producer**: HTML-based slides (12 themes), video production, AI image generation

---

## 3. Basic Usage

### Creating a Project

1. Right-click on empty space in the main screen (launcher)
2. Select "New Project"
3. Enter a name (e.g., "Investment", "Real Estate")

Double-click a project icon to enter the project screen.

### Setting Up Agents

The agent list is on the left side of the project screen.

**Adding a new agent:**
1. Click the "+" button at the bottom of the agent list
2. Enter name and role description

**Role description example:**
```
You are an internal medicine specialist with 20 years of experience.
You acknowledge the patient's concerns first before asking questions.
You explain medical terminology in everyday language.
```

**Selecting AI Model:**
Each agent can use a different AI. In settings, select the provider (Anthropic, OpenAI, Google, Ollama) and model.

### AI's Long-term Memory: Using Memos

Each AI in IndieBiz OS has a "memo" feature. This serves as the AI's long-term memory. No matter how long the conversation gets, the content in the memo is always passed to the AI.

**Types of Memos:**
- **System Memo**: Content for the System AI to remember (edit in Settings)
- **Notes**: Content for project agents to remember (edit in Agent Settings)
- **Work Guidelines**: Content for auto-response AI to remember (edit in Business Settings)

**Good things to write in memos:**
- User preferences or circumstances (e.g., "I have diabetes", "I live in Seoul Gangnam")
- Context you don't want to repeat (e.g., "This is a React project", "Target customers are women in their 20s")
- Rules the AI should follow (e.g., "Always respond in Korean", "Confirm price info before answering")

**Caution: Shorter is Better**

Memos are passed to the AI with every conversation. Long memos cause:
- Token waste → increased cost, slower responses
- AI confusion → too many instructions actually reduce quality
- Diluted focus → important content gets buried

**Recommendation:** Keep memos to 5-10 lines, only the truly important stuff. Content that's "nice to have" is better communicated through conversation when needed.

### Assigning Tools

Configure which tools an agent can use.

1. Go to the "Tools" tab in agent settings
2. Check the tools to use

**Principle:** Agents only see their assigned tools. Give only investment tools to an investment agent, and it won't be confused by unnecessary tools.

### Installing/Removing Tool Packages

Click "Toolbox" in the top menu to open the package management screen.

- **Installed**: Currently available packages
- **Not Installed**: Available for installation

Once installed, you can assign those tools to agents.

### Sharing Tool Packages (Nostr)

You can share your custom tool packages with other IndieBiz users.

**Publishing a Package:**
1. Click "Publish to Nostr" button on an installed package in Toolbox
2. Installation instructions are auto-generated by AI (editable)
3. Optionally add your signature
4. Click Publish

Published packages are posted to the Nostr network with the `#indiebizOS-package` hashtag.

**Searching/Installing Others' Packages:**
1. Click "Search Tools" button in Toolbox
2. Search for published packages on the Nostr network
3. Select a package to view details
4. Click "Install" and System AI will review before installing

System AI reviews security, quality, and compatibility before installation.

---

## 4. Switches

A feature to save repetitive tasks and execute them with one click.

### Creating a Switch

1. Click the "Switch" button at the top of the project screen
2. Click "New Switch"
3. Enter name and prompt

**Example:**
- Name: "Daily News"
- Prompt: "Search for AI, blockchain, and startup news and summarize in 5 lines"

### Running a Switch

Press the run button in the switch list to send that prompt to the designated agent. Results can also be saved to the outputs folder.

---

## 5. IndieNet (P2P Network)

A decentralized network based on the Nostr protocol.

### Setup

1. Click "My Info" in the top menu
2. Generate Nostr keys or enter existing keys

### Features

- **Board**: Share public posts with other IndieBiz users
- **Encrypted DM**: Private 1:1 messages

### Business Network

- **Neighbor Management**: Register business partners
- **Auto-Response V3**: Single AI call using Tool Use for judgment/search/send integration
  - Message received → AI judges intent → Search business DB → Send response immediately
  - Spam/ads are automatically filtered (no response sent)
  - Same logic processes both Gmail and Nostr

### Multi-Chat Rooms

Invite multiple agents to one chat room to discuss complex topics together.

- **Separate Windows**: Each chat room opens in its own window
- **Summon Agents**: Invite agents from any project into the conversation
- **@Mentions**: Call specific agents with @name syntax
- **Tool Assignment**: Assign specific tools to each agent

**Example**: "Gap investment in real estate vs stock investment—which is better considering taxes?"
→ Investment, Real Estate, and Tax agents each provide opinions from their perspectives.

---

## 6. Design Philosophy

IndieBiz OS aims for "expert team + human orchestration" rather than "one all-powerful AI."

- Humans design the project structure
- Each agent has only tools for their field
- Humans connect between projects and make judgments
- When patterns emerge, automate with switches

All data is stored locally. No cloud dependency.

---

## 7. Folder Structure

```
indiebizOS/
├── backend/           # Python FastAPI server
├── frontend/          # Electron + React app
├── data/
│   ├── packages/      # Tool packages
│   │   ├── installed/ # Installed packages
│   │   └── not_installed/
│   └── system_docs/   # System documentation
├── projects/          # User projects
│   └── {project_name}/
│       ├── agents.yaml      # Agent configuration
│       └── conversations.db # Conversation history
└── outputs/           # Switch execution results
```

---

## 8. Troubleshooting

### Backend Connection Failed
- Check if port 8765 is in use
- Check `python api.py` execution logs

### No AI Response
- Verify API key is correct
- Check the key for that provider in settings

### Tool Execution Error
- Check if the `.env` file has the API key for that tool
- Check backend logs for detailed errors

---

## 9. Examples: Building Your Own Environment

Here are some examples of how to turn an empty IndieBiz OS into your own system.

### Example 1: Building an Investment Environment

**Goal**: An environment to analyze Korea/US stocks and track market news

**Step 1 - Install Tools**
- Install the `investment` package in package management
- Optionally install the `web` package (for news search)

**Step 2 - Create Project**
- Create a project named "Investment"

**Step 3 - Configure Agent**
- Agent name: "Investment Analyst"
- Role: "You are an analyst with 10 years of experience. You analyze based on data and mention risks first."
- Assign tools: Stock price lookup, financial statements, disclosure lookup, web search

**Step 4 - Set Up Switches (Optional)**
- "Daily Market": "Summarize today's KOSPI/NASDAQ trends and major news"
- "Watch List Check": "Tell me current prices and recent disclosures for Samsung Electronics, Apple, Tesla"

Now when you enter the investment project, an investment-specialized AI responds using only investment tools.

### Example 2: Building a Medical Consultation Environment

**Goal**: An environment to answer health questions and manage medications

**Step 1 - Install Tools**
- Install the `medical` package (drug information, interaction lookup)

**Step 2 - Create Project**
- Create a project named "Medical"

**Step 3 - Configure Multiple Agents**
- **Internal Medicine**: "You are an internal medicine specialist. You acknowledge the patient's concerns first and explain medical terms simply."
- **Family Medicine**: "You are a family medicine specialist. You focus on preventive medicine and lifestyle improvement."
- **Medication Manager**: "You are a pharmacist. You check interactions between medications and manage dosing schedules."

Assign only necessary tools to each agent. Give the drug interaction tool to the medication manager, the symptom search tool to the internal medicine agent.

### Example 3: Building a Development Assistant Environment

**Goal**: An environment to help with code review, documentation, and bug tracking

**Step 1 - Install Tools**
- `file` package (file read/write)
- `web` package (documentation search)
- Optionally create and add your own GitHub API tools

**Step 2 - Create Project**
- Create a project named "Development"

**Step 3 - Configure Agents**
- **Code Reviewer**: "You are a senior developer. You check for bugs, performance issues, and readability in code."
- **Documentation Writer**: "You are a technical writer. You organize complex code into clear documentation."

### Example 4: Building a Content Creation Environment

**Goal**: An environment to auto-generate slides and promotional videos

**Step 1 - Install Tools**
- Install the `media_producer` package
- Optionally install the `web` package (for image search)

**Step 2 - Create Project**
- Create a project named "Content"

**Step 3 - Configure Agent**
- **Designer**: "You are a presentation designer. You create slides reflecting 2025-2026 design trends."
- Assign tools: create_slides, render_html_to_image, generate_ai_image, create_video

**Step 4 - Usage Examples**
- "Create 5 company intro slides. Use dark theme."
- "Make a promotional video with narration from these slides."
- "Generate a futuristic city background with AI image."

**media_producer Theme Types**:
- Basic: `modern`, `tech`, `business`
- Trend: `title_bold`(large title), `dark_tech`(neon), `glassmorphism`(glass effect), `gradient_modern`(gradient), `split_asymmetric`(asymmetric), `minimal_white`(minimal), `image_fullscreen`(full background), `data_card`(data emphasis)

### Core Principles

Patterns seen in these examples:

1. **Install only needed tools** - No need to install all packages
2. **Group related work together** - Separate contexts with projects
3. **Give agents clear roles** - Personas improve response quality
4. **Assign tools selectively** - Agents see only what they need

Over time, your own projects, agents, and switches accumulate, and that becomes "your own AI operating system."

---

## 10. Remote Access (Finder & Launcher)

Turn your home PC into a personal cloud accessible from anywhere. Use Cloudflare Tunnel for file access and AI control.

### Two Remote Features

| Feature | Path | Purpose |
|---------|------|---------|
| **Remote Finder** | `/nas/app` | File browsing, video streaming, downloads |
| **Remote Launcher** | `/launcher/app` | System AI/agent chat, switch execution |

Each feature can be independently enabled with **separate passwords**.

### What Can You Do?

**Remote Finder:**
- **Browse Files**: Access your home PC's files from any smartphone or computer via browser
- **Stream Videos**: Watch movies/shows stored at home while traveling
- **Preview Documents**: Quickly view text file contents
- **Download Files**: Get any file you need from anywhere

**Remote Launcher:**
- **System AI Chat**: Give instructions to System AI from anywhere
- **Agent Chat**: Converse with project-specific AI agents
- **One-Tap Switch Execution**: Run automated tasks with a single touch
- **Mobile Optimized**: Dark theme, responsive UI

### Why Cloudflare Tunnel?

Typically, accessing your home PC from outside requires complex network setup: port forwarding, DDNS, SSL certificates. Cloudflare Tunnel handles all of this:

- **No Port Opening**: Connect securely without router configuration
- **Auto HTTPS**: Cloudflare manages SSL certificates automatically
- **DDoS Protection**: Cloudflare network blocks attacks
- **Global Edge**: Fast response from anywhere in the world

### What You Need Before Starting

To use Remote Access, you need a **Cloudflare account**.

**1. Sign Up for Cloudflare**
- Create a free account at https://dash.cloudflare.com
- Connect a domain you own to Cloudflare (free)
  - If you don't have a domain, consider purchasing an inexpensive one

**2. Get API Token**
- Cloudflare Dashboard → My Profile → API Tokens
- Click "Create Token"
- Select "Edit Cloudflare Workers" template or set custom permissions
- Copy the generated token

**3. Find Account ID**
- Visible in the right sidebar of Cloudflare Dashboard
- Or on the Overview page after selecting a domain

**4. Configure IndieBiz OS**
- Go to Settings → Environment Variables and enter:
  - `CLOUDFLARE_API_TOKEN`: Your API token
  - `CLOUDFLARE_ACCOUNT_ID`: Your account ID

### Setup Summary

**Remote Finder Setup:**
1. **Launcher Settings** → **Remote Finder** tab
2. Turn on "Enable NAS" toggle
3. Set a password
4. Add folders to allow access (e.g., `/Users/me/Videos`)

**Remote Launcher Setup:**
1. **Launcher Settings** → **Remote Launcher** tab
2. Turn on "Enable Remote Launcher" toggle
3. Set a password (can be different from Remote Finder)

**Tunnel Setup:**
Ask System AI: **"Set up a Cloudflare tunnel for remote access"**

System AI will automatically handle tunnel creation, DNS setup, and config file generation.

### Running the Tunnel

Once setup is complete, you need to run the tunnel:

```bash
cloudflared tunnel run indiebiz
```

If using your PC as a 24/7 server, configure this command to run automatically at system startup.

### Accessing

Open your configured addresses in a browser:
```
https://home.yourdomain.com/nas/app      # File access
https://home.yourdomain.com/launcher/app # AI control
```

### Detailed Documentation

For detailed technical information about Remote Access, see:
- **System Docs**: `data/system_docs/remote_finder.md`

For detailed usage of the Cloudflare Tunnel tool (`cf_tunnel`), see the cloudflare package documentation.

---

*For detailed technical documentation, see the `data/system_docs/` folder.*
