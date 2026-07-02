# IndieBiz OS

**Raise your own digital humanoid. Grow together. Connect with others.**

[Homepage](https://indiebiz-homepage.vercel.app) | English | [한국어](README.ko.md)

<p align="center">
  <img src="docs/xray-bodymap.png" alt="IndieBiz OS X-Ray Body Map" width="800"/>
  <br/>
  <em>X-Ray: Your system's vital signs — cognitive nodes, action health, and self-check status, all alive.</em>
</p>

---

## In one minute

**IndieBiz OS turns plain language into a real action language — *IBL* — that runs on your own desktop and phone, and lets the things you do often harden into one-tap apps you own.** No app store, no cloud account, no code.

You say what you want. *How* you say it depends only on how often you do it:

| You want to… | You get… | Surface |
|---|---|---|
| *"Find lease listings near Gangnam under 500M and put the top 5 in a report"* — a one-off | the AI discovers the steps and just does it | **Autopilot** |
| the same kind of task, repeatedly | a lightweight model translates it into **one reusable line you review and keep** | **Manual** |
| a task you do every day | it crystallizes into an **icon you tap — 0 tokens, instant — even on your phone** | **App** |

One system, one person, from a one-off question to a superapp you authored just by using it. It starts minimal and grows only what you ask for; an AI agent is the blacksmith who keeps forging it to fit you.

**New here?** → [What it actually is](#the-one-idea) · [See it on a phone](#the-phone-is-where-you-see-it) · [Install in 3 lines](#getting-started-recommended)

---

## The one idea

Most AI harnesses get more capable by reaching for *more intelligence* — a bigger model, a longer prompt, more tools. IndieBiz OS makes a different bet:

> **Handle complexity with *structure*, not more intelligence — because structure is the one layer no foundation model absorbs.**

A better model keeps absorbing *how to produce an action*. It never absorbs *where the action lives, who owns it, how often it repeats, or whose body it runs on* — that's the life *around* the generation, and it's where IndieBiz OS works.

That bet rests on two generative cores. Almost everything distinctive about the system *falls out* of them — so instead of listing fifty features, this README shows the two roots and lets the features hang off them as consequences:

1. **There is a real language underneath — IBL.** A small, regular vocabulary that every part of the system compiles to.
2. **A clean seam between the vocabulary and the body.** What a capability *is* stays separate from *which machine runs it*.

If you grasp those two, you can re-derive the feature list yourself. That's the point.

---

## What it aims to be — a wearable robot, not an autopilot

Most harnesses aim at **autonomy**: give a destination and the AI drives there on its own — you specify, you receive. IndieBiz OS aims to be a **cognitive exoskeleton you wear.** It absorbs your *settled* judgment so repeated work happens almost unconsciously, freeing your conscious attention for what doesn't repeat. And it doesn't need a clear destination up front: for the deepest work — research, writing, building, deciding what you even want — the goal isn't *given then pursued*, it's *discovered in the pursuit*. **Autonomy treats the destination as a precondition; an exoskeleton treats it as a product** — co-authored step by step, with you still holding the judgment.

So the development north star is **fit** (착용감): the exoskeleton disappearing into intention; trials made cheap enough that *your taste* drives a tight loop; your judgment reaching *further* — not you doing *less*. Success is the fruit you couldn't have made bare, never how little of you was needed. A self-driving car's endpoint is to delete the driver's seat; ours is to make the seat worth sitting in even when the system can drive itself. (Full vision: `data/system_docs/vision.md`.)

---

## Philosophy — a system you raise, not one you're given

IndieBiz OS is not software you install and use as-is. It's a **living system** — like armor forged to fit your body, or a horse you raise and ride yourself. An AI agent sets up the skeleton, asks about your life, and starts building — but the system only becomes *yours* through use. Your habits shape it; your needs grow it.

**No two installations are the same.** A freelancer's system looks nothing like a small-business owner's; hand yours to someone else and it wouldn't fit. It starts minimal — only the core (IBL engine, cognitive pipeline, hippocampus) — and grows on demand: say "track my investments" and the investment package appears. No app store, no mandatory update, no one-size-fits-all. Your AI agent is the blacksmith who keeps forging it as you grow.

And one day these individually raised systems find each other — connecting over decentralized networks, each unique but speaking the same language. That is the vision.

---

## Why this shape — the whole spectrum, not one end of it

People want two different things from AI, and the market sells them as separate products. One crowd wants **autopilot**: say it, the AI does it — fast, but you own nothing afterward and pay full price every time. Another wants the **artifact**: code-generation agents hand you something durable — but it's *code*, and code needs a production environment (terminal, server, hosting) to run.

A single person doing real work needs both — and a third thing between them — as **one continuum**, not three purchases:

- one-off, exploratory work → **autopilot** (let the model discover the steps)
- recurring work → **vocabulary** (natural language compiles to a line of IBL you keep)
- daily work → **an app** (an icon that runs deterministically, 0 tokens)

No single *task* needs all three; a single *life* does. The market doesn't sell the continuum not because it's unwanted, but because it only collapses into one product **at personal scale**. In a company the three stages split across three roles — developers generate, ops run automation, users tap apps — three people, so three products. Put all of it in *one* pair of hands and it has to be one system. **Single-user isn't a limitation here; it's the condition that makes the spectrum coherent.** That is what "IndieBiz" means.

### The phone is where you see it

The clearest demonstration is IndieBiz OS on a phone, where it behaves like a **superapp you authored by using it** — and where the alternatives can't follow. A phone is a sealed *consumption* device: no build toolchain, no server, no way to author-and-run your own app. A code-generation agent's output **strands** there — an app you can't run. IndieBiz OS's "app" is not a compiled binary but a *manifest over the IBL the runtime already speaks*, so **authoring and running collapse into one device and one moment — no store, no build, no deploy.** (How a phone runs the engine at all is Core #2.)

The closest existing thing — Apple Shortcuts, Tasker — proves the demand is real, but it's only the bottom of the spectrum: you still hand-author each shortcut in a fixed visual language, nothing crystallizes from *use*, and it's bound to the OS's actions, not your context. IndieBiz OS is that on-device execution **plus** an autopilot on-ramp **plus** a vocabulary that's yours. Not "like a superapp" — **the first superapp a person builds for themselves, without being a developer.**

---

## Core #1 — There's a real language underneath (IBL)

Every capability — a web search, a file write, a phone notification, a chart — is one line in a single language, **IBL (IndieBiz Logic)**:

```
[sense:search_ddg]{query: "AI news"} >> [self:file]{path: "result.md"}
```

Five nodes (`sense`, `self`, `limbs`, `others`, `engines`), one composable vocabulary. The point is *not* that there are 142 actions — it's that there are *only* 142, down from 332, because related tools were folded into single actions with parameter/`op` branching (45 bespoke Android actions became one `[limbs:android]{op}`). **The language got smaller as it got stronger:** fewer, more composable verbs that a human *or a small model* can write one line of and have work. Because everything speaks one vocabulary, your accumulated experience forms a single coherent corpus instead of a pile of incompatible tool calls.

Here is what *falls out* of having a real language:

### → Three surfaces for every task (the trilemma)

Because there's a compile target, the *same* IBL expression can be reached three different ways. Each surface takes two of **{speed, expressiveness, sovereignty}** and gives up the third:

| Surface | How you reach the IBL | Trade-off |
|---------|----------------------|-----------|
| **Autopilot** | A flagship model takes your intent and *discovers* the steps, emitting IBL as it goes. Best for new, exploratory work. | speed + expressiveness − sovereignty |
| **Manual** | A *lightweight* model **translates** your natural language into IBL — a compiler front-end. You review the *effect* (dry-run) and run it. Near-zero cost; intelligence accrues in the language, not the model. | expressiveness + sovereignty − speed |
| **App** | An icon **invokes** a fixed IBL expression directly — 0 tokens, deterministic. Fastest, most discoverable. | speed + sovereignty − expressiveness |

No other harness can offer this, because no other harness has a compile target: there is nothing for a "manual mode" to translate *into*, no stable expression to dry-run, and nothing for an icon to *invoke*. **The three surfaces are not a UI menu — they are a property of having a language.**

### → Crystallization

Frequency moves a task between surfaces. Autopilot explores it once → its IBL trace seeds Manual → a proven, high-frequency flow crystallizes into an **App icon (0 tokens)** on a 2D desktop you own and return to. A saved shortcut is *not* the same as an icon you keep — the difference is **placement**, and most harnesses have no launcher surface at all, so a proven flow has nowhere to live. This *survives cheaper models*: what you want from a daily task isn't a lower token bill — it's determinism, instant response, and control. **Crystallize only what's proven.**

(Manual mode obeys two rules: side-effecting steps are gated behind explicit confirmation while read-only steps run friction-free, and the hippocampus learns *only the results you approve*. App instruments are declaration-driven — each is an `app:` block on an IBL action, and one declaration renders identically on the desktop, the remote launcher, and the phone.)

### → A currency algebra

`engines` carries domain-agnostic transformers — filter / sort / take / select / dedup / groupby / join / union / merge — that take a shared *currency* (record lists or tables) and return the *same* currency. So any search result composes into a report of any format via `>>` (or the `|` pipe shorthand), with no glue code in between:

```
[sense:realty]{region: "Gangnam"} | where: "lease" | sort: price | take: 5 >> [table:document]{}
```

Coverage is the nouns; depth is the currency verbs. A language *with an algebra* is what turns one line of search into one report.

---

## Core #2 — A clean seam between the vocabulary and the body

A capability's *meaning* (`[sense:here]` = "where am I?") is body-independent; *how* it runs depends on the machine. Keep those two apart with a clean seam, and a second consequence falls out.

### → The phone is a second self, not a remote control

A native Android app runs IndieBiz OS *on the phone itself*, with its own on-device LLM brain (in-process Gemini — a lightweight tier for classification, a fuller tier for execution) and the real IBL engine executing phone-safe packages locally. The model **detects its own hardware** (`detect_body`) and knows it is "the phone," not the Mac — a different body, therefore a different identity.

`runs_on` capability tags mark each action honestly — `anywhere`, `mac_only` (phone forwards to the Mac), `phone_only` (Mac forwards to the phone) — and borrowed actions are forwarded transparently. The federation is **bidirectional and authenticated with no manual login**: the phone runs an always-on foreground service, binds to the LAN only behind a shared token, and each side carries its credential automatically. The Mac borrows the phone's senses (`[sense:here]` location, `[sense:listen]` mic, `[sense:see]` camera); the phone borrows the Mac's heavy compute (`[sense:host]`, video/slide rendering). **No other harness runs *on the phone as a second self*** — "phone access" elsewhere means remote-controlling a PC.

The seam also splits memory cleanly: your world-data (contacts, business, calendar, health) is shared and synced (CRDT union merge), while each self's subjective memory (conversations, hippocampus, self-state) stays private.

---

## The split mind — define the problem, then execute it

Most systems plan-and-act as a single agent. IndieBiz OS splits the mind into **separate subjects**:

```
User Message
   │
[Unconscious] — reflex: EXECUTE or THINK?
   │ EXECUTE                 │ THINK
   ▼                         ▼
[Direct execution]    [Consciousness] — frames the problem:
                       task framing, achievement criteria,
                       self-awareness, guide selection
                             │
                      [Executor] — solves the already-framed problem
                             │
                      [Evaluator] — achieved, or retry? (max 3 rounds)
```

The consciousness agent reframes the raw request into a well-defined problem *before* the executor ever sees it. Because the two are different subjects, the executor solves an *already-framed* problem: the off-target or unsafe paths a single plan-then-act agent would have to *consider and reject* are largely kept out of its frame from the start. This is **containment, not alignment** — safety dissolved into the goal rather than bolted on as a rule. And it's a property a single agent *cannot* have, because it cannot un-ask its own question — which is exactly why a more capable reasoning model doesn't absorb it.

Three model tiers serve this cheaply — **lightweight**, **midtier**, **full** — but which tier each cognitive role uses isn't hardwired. An **automatic transmission** (the unconscious classifier) already picks a tier per task; on top of it sits a **manual gear lever** (`Save / Balance / Max`) that shifts the whole system at once, the way a car's gearbox does. The four cognitive axes — *classify, evaluate, execute, consciousness* — each map to a tier through the chosen gear, so one lever rebalances cost vs. quality across the entire mind without restarting. (Models — and their API keys — flow from the gear, not from any per-agent setting.)

---

## Memories that learn you — and your spaces

Several memories learn from you automatically and keep themselves clean:

- **Hippocampus (procedural)** — a fine-tuned 768-dim embedding model maps your natural language to past IBL code (~88.9% code / 91.2% description Top-5; retrained locally on Apple Silicon, ~2,600-example corpus). Successful runs distill into reusable examples, so the system gets faster at *your* recurring tasks. A closed loop records whether a recalled example actually worked, so proven patterns rise and bad ones sink.
- **Deep memory (relational)** — after each conversation a lightweight pass extracts durable facts about you (preferences, decisions, key dates) and recalls them, with their last-seen date, when relevant.
- **Forager memory (spatial)** — every time the AI *forages* the disk, web, or codebase, it accumulates what it learned about that space across sessions: folder identities, search conventions, dead ends, and an owner-model of whose files live where. A model built foraging the disk disambiguates a web search, and vice versa — a compounding loop. It borrows the vocabulary of Information Foraging Theory; what's new is treating it as the *persistent* faculty a stateless model lacks, and adding only that memory — no controller, no stopping-formula. (`[self:forage]`, the Mac self.)

A periodic consolidation pass (part of the immune patrol below) merges near-duplicates, prunes stale or proven-bad entries, and resolves contradictions, so memory stays sharp instead of bloating.

---

## The system watches itself

- **World Pulse** — hourly: economy, weather, news (every 6h), user activity, system health.
- **Self-Check** — every 12 hours, a full sweep of side-effect-free IBL actions across all six nodes (an immune patrol). On `/self-inspect`, the system AI retries failures to classify them transient vs reproducible and rate fix difficulty (easy / medium / hard).

---

## Agents you design, teams that delegate

You don't just say "act as a doctor" — you define **who** an agent is and **how** it communicates, and it remembers *your* context (medications, preferences, past conversations):

```yaml
agents:
  dr_kim:
    role: |
      You are Dr. Kim, an internal-medicine specialist of 20 years.
      You acknowledge the patient's concern before asking questions,
      explain terms in everyday language, and always end with clear next steps.
    allowed_nodes: [sense, self, limbs, others, engines]
```

You define *who* an agent is, not *which model* runs it — model and API key are decided centrally by the gear lever above (with an optional per-agent **pin** to override one agent's tier). Agents form teams and delegate — synchronously (`call_agent`, wait for the result), on a schedule (hand a task to another agent's clock), or via a written plan (`create_plan` → `execute_plan`, each agent runs its part and hands off). Agents with a communication channel (Nostr, Gmail) can take orders remotely and reach other people's agents over **IndieNet** (Nostr; DMs use modern NIP-17 gift-wrap encryption).

---

## Under the hood (reference)

**6 nodes, 142 composable actions** — one tool (`execute_ibl`), one vocabulary, not 142 schemas:

| Node | Actions | What lives here |
|------|---------|-----------------|
| **sense** | 44 | Retrieval — web, Naver, finance, travel, photos, blog, health, real estate (official prices + live listings), legal, statistics, classic literature, performances, academic papers/dissertations/researchers, AI grants & contests — plus the phone's on-demand senses (notifications, location, mic, camera) |
| **self** | 44 | System management, workflows, triggers, files, deep + forager memory, business (catalog/items/docs/guidelines), phone sync, calendar, health records |
| **limbs** | 17 | UI automation (browser, Android, macOS screen), phone-native actions, media playback (YouTube, radio), maps |
| **others** | 11 | Collaboration, delegation, messaging (DM/feed/board/Nostr NIP-17), neighbor CRM, contacts, auto-response |
| **engines** | 26 | Currency transformers + content creation (document IR, slides, video, charts, images, websites, spreadsheets, TTS) + image vision read/critique |

IBL's definition lives in a single source of truth (`data/ibl_nodes_src/`, built to `data/ibl_nodes.yaml` via `scripts/build_ibl_nodes.py`). Tool **packages** (38 installed, growing) are folders — drop one in and it's recognized, independent of the language; an AI agent can build, install, or modify them for you. Per-agent `allowed_nodes` restricts what each agent can reach.

---

## Getting started (recommended)

The easiest way to install IndieBiz OS is through **Claude Desktop**.

1. Open **Claude Desktop** and switch to the **Claude Code** tab.
2. Tell Claude:

```
"Install IndieBiz OS from https://github.com/kangkukjin/indiebizOS on my PC"
```

3. Claude clones the repo, installs dependencies (Python, Node.js), asks about your needs, and sets up a system tailored to you.

> **Why Claude Desktop?** IndieBiz OS is a living system, not a static `npm install`. The agent that installs it becomes the blacksmith who keeps forging it to fit you.

**You'll provide:** an LLM API key (Anthropic, Google, or OpenAI); answers to a few questions about what you want; external API keys only as you actually use those features.

<details>
<summary><strong>Alternative: standalone installer (no Claude Desktop)</strong></summary>

Don't have Claude Desktop? A tiny, hardware-agnostic **seed** installs the system itself — it detects your machine, clones the repo, installs dependencies, wires your key, picks a profile that fits your hardware, and verifies the backend boots. It's a stdlib-only Python agent (no dependencies to run the installer itself); the only thing embedded is this repo's URL. Bring your own LLM key (Anthropic / OpenAI / Google — the provider is inferred from the key).

**macOS / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.sh | INDIEBIZ_API_KEY=sk-ant-... bash
```

**Windows (PowerShell):**
```powershell
$env:INDIEBIZ_API_KEY="sk-ant-..."; irm https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.ps1 | iex
```

The key is used only to run the installer and is written into your local config; it never leaves your machine except as the auth header to your chosen provider. See `installer/` for the seed and its install guide.

**Language:** the installer and the running system both work in English — the AI replies in whatever language you write to it, so no setting is needed. (The bundled guides and desktop UI labels are currently Korean; the AI reads them and still answers you in your language.)

**Re-installing / updating** an existing install overwrites it with the latest GitHub code while your `.env`, keys, and personal data are always kept (`.gitignore` is the preservation boundary). Two modes:
```bash
# keep your learning & settings, refresh code + shipped vocabulary:
curl -fsSL https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.sh | INDIEBIZ_UPDATE=standard bash
# factory-reset learned data & tuning too (still keeps .env + personal data):
curl -fsSL https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.sh | INDIEBIZ_UPDATE=full bash
```
(Windows: set `$env:INDIEBIZ_UPDATE="standard"` before the `irm … | iex` line. Omit the variable and you'll be asked which mode.)

</details>

<details>
<summary><strong>Alternative: manual setup</strong></summary>

```bash
git clone https://github.com/kangkukjin/indiebizOS.git
cd indiebizOS
./start.sh
```

This runs the system, but you configure agents, packages, and preferences yourself. The Claude Desktop path is recommended because the AI handles all of it for you.
</details>

---

## Technical Stack

- **Backend**: Python FastAPI (port 8765)
- **Frontend**: Electron + React (TypeScript)
- **AI Providers**: Anthropic (Claude), Google (Gemini), OpenAI (GPT), Ollama (Local)
- **Database**: SQLite
- **Deployment**: Local-first, optional Cloudflare Tunnel for remote access

---

## Running

```bash
# Development mode
./start.sh

# Or separately
cd backend && python3 api.py        # Backend (port 8765)
cd frontend && npm run electron:dev  # Frontend (Electron)
```

---

*IndieBiz OS — An AI system that grows with you, not one that's given to you.*

*Last updated: 2026-06-30 — **Model gear (dashboard shifting) + per-agent model retired**: the ~15 scattered places that picked a model are unified behind one resolver (`backend/model_resolver.py`) keyed by *cognitive role → axis → gear → tier*. A dashboard lever (`Save / Balance / Max`) shifts the whole system's model grade in one move, with a preset editor (gear × axis → tier) and per-agent pins for exceptions — all hot-reloaded with no restart, exposed over a `/model-gear` REST surface and rendered on the desktop, remote launcher, and phone. **Per-agent model config is retired**: an agent's yaml no longer carries `provider/model/apiKey` — the model *and its key* are inherited from the execution tier (this also closed a hidden bug where a keyless agent yaml died in THINK mode but survived EXECUTE via the midtier swap). Also: the phone's engine bundle is no longer a hand-maintained module list — it is **derived** from `data/bodies/*.json` body profiles (`scripts/build_body_bundle.py`, guarded three ways: build-time regeneration + pre-commit `--check` + on-device self-check), so a new backend module flows to the phone automatically. Action count unchanged (**142**), 38 tool packages. Earlier (2026-06-29) — **App-mode interactive render primitives**: the app-surface vocabulary (which the desktop, remote launcher, and phone all read from one `app:` block) gained an interactive `map` (leaflet) plus an `on:` view-event grammar — interaction-as-data: panning the map re-queries (`moveend` → `$lat/$lng/$radius`), and a marker click either runs an IBL action or, with `{stream: true}`, plays the marker's HLS video. A result-field dynamic filter (`filter: {from_field}`) builds chips from a result's distinct values and filters client-side (no re-query). The bespoke commercial-district instrument retired into this declarative vocabulary; the directions instrument's retirement was deferred (its route + separately-queried CCTV overlay needs more than one consumer to justify) and a lightbox primitive proved unnecessary (image grids already go fullscreen). The single-currency (`items`) migration was confirmed complete — zero `records` producers across backend and tools. Action count unchanged (**142** — a rendering-layer change), 38 tool packages. Earlier (2026-06-27) — **Live real-estate listings, AI opportunities & app-surface polish**: `sense:realty` now serves live asking-price listings (`source: zigbang`) beside official transaction prices (`source: molit`); new `sense:contest` (Kaggle) and `sense:startup` join the nanet academic search. App instruments got a quality sweep — radio favorites, CCTV in-app HLS playback (a reusable client-side `stream` button), flight-search date input + Korean regional airports (e.g. Cheongju/CJJ), an ETF quick-pick, weather & culture quick options, and route distance/ETA — and the phone-native app was rebuilt to match. **142 actions** (sense 44, self 44, limbs 17, others 11, engines 26), 38 tool packages. Earlier (2026-06-22) — **National-academic person & dissertation finding**: new `sense:researcher` (find/coauthor) and `sense:paper{source: nanet}` actions tap the National Assembly Library's academic-info API — a researcher search that splits same-name people by affiliation and birth year (the "common name" wall generic web search can't climb), plus Korean dissertation/journal search. Also: the **forager memory** (7th memory, spatial) is now live — when the AI searches the disk, web, or code, it accumulates a reusable map of that space (folder identities, conventions, dead ends, an owner-model) across sessions. 136→**141 actions** (sense 43, self 44, limbs 17, others 11, engines 26). Earlier (2026-06-17) — **Mac↔phone federation is live and authenticated**: the phone backend now runs without opening the app (always-on foreground service), the Mac↔phone borrow is bidirectional over the LAN behind a shared token (the phone binds to the LAN only when that token is present, and each side sends its credential automatically), and the self-check no longer flags a peer being temporarily offline as a failure. Also: `table:join` now composes record lists too (not just tables); fixes to `run_pipeline` (string steps), `self:grep` (single-file paths, `~` expansion across file actions), and the KOSIS statistics endpoint. Earlier (2026-06-15) — **Currency algebra**: `engines` gained domain-agnostic currency→currency transformers (unary filter/sort/take/select/dedup/groupby + binary join/union/merge), a `|` pipe shorthand, and a document-IR emitter — so any search result composes into a report of any format (html/pdf/docx/pptx). 124→136 actions (sense 42, self 41, limbs 17, others 11, engines 25).*
