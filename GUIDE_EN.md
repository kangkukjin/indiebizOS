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

### Installation and Launch

1. Download the latest version from [GitHub Releases](https://github.com/kangkukjin/indiebizOS/releases)
   - macOS: `.dmg` file
   - Windows: `.exe` installer
2. Install using the downloaded file
3. Double-click the IndieBiz app icon

When the app starts, the backend server automatically starts with it.

### For Developers (Running from Source)

```bash
cd backend && python api.py        # Terminal 1
cd frontend && npm run electron:dev # Terminal 2
```

### API Key Setup - The Most Important First Step

To use IndieBiz OS, you need **at least one AI API key**. This is the biggest first hurdle. But once you get past this, you can ask or instruct the System AI for everything else.

**Recommended as of Jan 2026: Google Gemini API (Free)**

Currently, Gemini API can be used for free for a while, making it a good starting point.

1. Get an API key at https://aistudio.google.com
2. Enter the Gemini API key in the app's settings screen
3. Select a model:
   - `gemini-3-flash-preview`: Fast and lightweight (recommended for general use)
   - `gemini-3-pro-preview`: More powerful (for complex tasks)

If you don't know how to get an API key, just ask any AI like ChatGPT or Claude: "How do I get a Gemini API key?"

**After entering the API key?**

The System AI becomes active. From then on, you can chat with the System AI to install tools, create projects, change settings, and more.

**Alternative: Use Claude Desktop**

If getting an API key is difficult, you can install [Claude Desktop](https://claude.ai/download) instead. You can have Claude Desktop open the indiebizOS folder, explore the system, install tools, or make system modifications.

**Tool APIs (Optional, for later)**

Some tool packages require external APIs. You can set these up later by asking the System AI when you need them.

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

*For detailed technical documentation, see the `data/system_docs/` folder.*
