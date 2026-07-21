# IndieBiz OS

**The shared warehouse — a media network for the age when AI does the reading. And the personal AI OS that fills and reads it.**

[Homepage](https://indiebiz-homepage.vercel.app) | English | [한국어](README.ko.md)

IndieBiz OS has two axes. One is an **AI agent system** — a personal OS that compiles plain language into an action language (IBL) and hardens frequent work into apps you own. The other is the **shared warehouse** — something that doesn't exist anywhere else, and simple enough to explain in a paragraph. So this README starts with the warehouse.

---

## The shared warehouse — a media network without platforms

**You put a file in a folder. That is the entire act of publishing.** The `공유창고/0..4/` folders on your disk are served live at your node's public address — no index, no conversion; the filesystem *is* the truth. Humans open it in a browser; **other people's AI agents read it through `/manifest` (JSON).**

### Platforms were shelving for humans

YouTube, blogs, Twitter, and shopping malls exist as *separate* services not because the data differs in nature, but because **humans can't handle raw data, so someone had to pre-build — and monopolize — a different shelf (UI) for each kind.** The moment an AI stands on the reading side, that premise dissolves: rendering happens at visit time, on the reader's side. So one warehouse becomes whatever you put in it:

| What you put in | What the warehouse becomes |
|---|---|
| videos | YouTube |
| writing | a blog · Twitter |
| a product catalog | a shopping mall |
| a list of services | a freelance network |

A broadcast station and a shop at once — and **format-free (schema-on-read)**: the warehouse serves bytes (a PDF as a PDF, a spreadsheet as a spreadsheet), and interpretation is the reading AI's job.

### The asker pays

The old web made the host pay for querying, rendering, and delivery — which is why a crowd of visitors melts the owner's server. The warehouse inverts it: **the owner only places files; the searching, filtering, and rendering are computed by the asker's AI, on the asker's hardware.** Serving costs the owner ~nothing. That's also why there is no CAPTCHA: the web blocks bots as a symptom of server-pays economics, but here a reading AI brings its own compute, so the door never asks "human or bot?" — only **"who are you?" (identity and level).**

### The number on the folder is the gate

A visitor's level (0 → 4) is the *same scale* as their grade in your neighbor CRM — promote someone once and it applies to messaging, portal membership, and the warehouse alike. A viewer sees levels `0..their level` **merged into one flat list** (same name: higher level wins), and a file above their level returns **404, not 403** — existence itself is information. The one deliberate leak is a single `has_restricted` flag, a *smell*: "there is more here," with no names or counts. Since the security is the level, the address needs no hiding — the front door stays confidently open.

### `/manifest` — the machine face, and a very small protocol

Beside the human page, the same listing is served as JSON — a title, files with sizes, mtimes and direct URLs, `has_restricted`, a self-describing `about`, and a **`login` block stating exactly how to authenticate**. A foreign AI agent reads your node without scraping HTML or reverse-engineering anything.

And that is the *entire* contract of the face: `GET /manifest` + `GET /f?path=` + a cookie login. **Just HTTP and files** — no IBL, no cognitive pipeline, not even IndieBiz OS itself is part of the contract. Any AI system can implement the same face in an afternoon, and that's the point: like RSS and TCP/IP, the interfaces that win are boringly small.

### The reading half — a neighbor feed, and reposts as files

Register a neighbor's warehouse and a poller fetches their `/manifest` every 30 minutes, diffing paths and mtimes into a timeline — `seed` on the first poll (their back catalogue, like seeing past posts right after a follow), then `new` and `changed`. The retained snapshots double as a **filename index of your whole neighborhood**, so one search sweeps every neighbor's warehouse at once. This layer is **pure machine — zero model calls, zero tokens**: collecting the scent is mechanical; interpreting it is the AI's job.

**A neighbor doesn't have to run IndieBiz OS.** Under the poller sits a dialect-adapter layer that normalizes nginx/Apache directory indexes, RSS/Atom feeds (auto-discovered from HTML), Nextcloud public shares, and even the file links on an ordinary web page into the same manifest currency — someone becomes a neighbor without installing anything. A blog's RSS or a file server's index subscribes as-is, so **the entire existing web is a potential first neighbor** — the network doesn't start in an empty room.

A warehouse address isn't a separate address book — it's stored as one more **contact type** on a neighbor, right beside their email and Nostr key (someone you only know by address is still a proper neighbor). A repost is a standard `.url` shortcut file dropped into your own warehouse; when your manifest is served it resolves to the original, so **a subscriber's click goes straight to the origin warehouse, never through you.** Friend-of-a-friend discovery, implemented not as a protocol but as *a file*.

Subscription doesn't stay anonymous (level 0), either. Warehouses serve a join page; sign up or log in through the in-app browser and the credential is **captured on the spot** — no copying it anywhere by hand. From then on the poller logs in through the manifest's `login` contract, so **files at your granted level flow into your feed and search.** Expired or revoked cookies re-login automatically, and if login fails the poll continues anonymously (the feed never stops). There is no separate key exchange: the credentials you made at signup *are* the key.

### The AI fills it — production is publication

What this system's agents produce is **published the moment it is made**. Daily schedules drop the morning newspaper, an AI trend report, and the latest blog post into the warehouse through a one-line IBL pipeline (`[self:read] >> [table:document] >> [self:copy]`), and business items (Sharing · For sale · Can do …) are **auto-materialized from the DB into garage-sale shelves** — each item becomes a document plus photos in a warehouse folder, so an outsider browses your whole catalog without ever asking. The intro document ends with an automatically attached way to reach you (your Nostr address). To subscribing neighbors, all of it flows past like tweets.

### The easiest live example — a sharing economy

Put something you're giving away under `Sharing`: it appears in your neighbors' feeds → a neighbor's AI recognizes the match → one DM → hand it over. **The whole loop closes with no payment layer** — the first practical case. Selling and commissioning are the next chapter, to be built on top.

---

Filling this warehouse — and reading and interpreting your neighbors' — is ultimately an AI's work. From here on, this README is about that AI: the second axis, the agent system.

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

Six nodes (`sense`, `self`, `limbs`, `others`, `engines`, `table`), one composable vocabulary. The point is *not* that there are 157 actions — it's that there are *only* 157, down from 332, because related tools were folded into single actions with parameter/`op` branching (45 bespoke Android actions became one `[limbs:android]{op}`). **The language got smaller as it got stronger:** fewer, more composable verbs that a human *or a small model* can write one line of and have work. Because everything speaks one vocabulary, your accumulated experience forms a single coherent corpus instead of a pile of incompatible tool calls.

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

The `table` node carries domain-agnostic transformers — filter / sort / take / select / dedup / groupby / join / union / merge — that take a shared *currency* (record lists or tables) and return the *same* currency, plus emitters (chart / spreadsheet / document / structure) that turn it into an artifact. So any search result composes into a report of any format via `>>` (or the `|` pipe shorthand), with no glue code in between:

```
[sense:realty]{region: "Gangnam"} | where: "lease" | sort: price | take: 5 >> [table:document]{}
```

Coverage is the nouns; depth is the currency verbs. A language *with an algebra* is what turns one line of search into one report.

### → Publishing to the open web, at personal scale

The same language that runs a private action can also *expose* one to the public internet. A small family of `others` actions turns an IBL flow into a real web address anyone can open — no server to rent, no framework to deploy:

- `[others:portal]` — **personal portals** at `/h/<slug>/`: give family, friends, or neighbors a login and a level (0 guest → 4 family), and they borrow your instruments and content *through the browser, without installing anything*. Members are your neighbor CRM, unified — no separate account system.
- `[others:family_news]` — a **family newspaper** at `/n/<slug>/`, typeset from your phone's photos, with a guestbook and photo uploads.
- `[others:bulletin]` — **login-free bulletin boards** at `/b/<slug>/`; anyone with the address posts text and photos.
- `[others:showcase]` — **public file shares** at `/s/<slug>/`, served straight off your disk.
- **report faces** at `/r/<slug>/` — a recurring-report folder rendered to HTML *on view*, so a fresh report every morning never needs a fresh link. (Configuration only, no verb of its own.) Separately, `[others:publish]` pushes a piece you wrote out as a Nostr long-form article (NIP-23) and hands back a shareable link.

This is the first step of the larger vision — individually raised systems finding each other. The principle is **"one node per community"**: your system is the node, and the people around you are browsers reaching it, speaking the same language from the outside.

### → The shared warehouse — the node's front door

If the surfaces above are *destinations you make*, the front door — the node itself having an address, with its publishing folders, level gate, machine face, neighbor feed, and reposts — is covered at the [top of this README](#the-shared-warehouse--a-media-network-without-platforms). One thing belongs here, from the language's point of view: **all of it cost IBL zero new verbs.** Publishing composes out of vocabulary that already existed (`self:copy`, `table:document`, `self:delete`); the outermost discovery ring — a Nostr profile whose `website` is your warehouse, plus an `#IndieNet` note carrying only a greeting and the address — is `[self:business_document]{op: "publish"}`. A stranger finds you on an open relay, then reads *you* out of your own warehouse.

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

- **Hippocampus (procedural)** — a fine-tuned 768-dim embedding model maps your natural language to past IBL code (~88.9% code / 91.2% description Top-5; retrained locally on Apple Silicon, ~2,750-example corpus). Successful runs distill into reusable examples, so the system gets faster at *your* recurring tasks. A closed loop records whether a recalled example actually worked, so proven patterns rise and bad ones sink.
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

**6 nodes, 157 composable actions** — one tool (`execute_ibl`), one vocabulary, not 157 schemas:

| Node | Actions | What lives here |
|------|---------|-----------------|
| **sense** | 48 | Retrieval — web, Naver, finance, travel, photos, blog, health, real estate (official prices + live listings), accommodation, second-hand markets, legal, statistics, classic literature, performances, academic papers/dissertations/researchers, entity resolution (Wikidata), AI grants & contests — plus the phone's on-demand senses (notifications, location, mic, camera) |
| **self** | 49 | System management, workflows, triggers, files, deep + forager memory, business (catalog/items/docs/guidelines), phone sync, calendar, health records, library install (approval-gated) |
| **limbs** | 17 | UI automation (browser, Android, macOS screen), phone-native actions, media playback (YouTube, radio), maps |
| **others** | 17 | Collaboration, delegation, messaging (DM/feed/board/Nostr NIP-17), neighbor CRM, contacts (a neighbor's warehouse address is just another contact type), auto-response — and the public-web surfaces others can reach: personal portals, family newspaper, login-free bulletin boards, public file shares |
| **engines** | 13 | Content creation — document IR, slides, video, charts, images (+ vision read/critique), icons, websites, web components, TTS |
| **table** | 13 | Currency algebra — transformers (filter/sort/take/select/dedup/groupby/join/union/merge) + emitters (chart/spreadsheet/document/structure), split out of `engines` so the grammar survives even when heavy media generation is off |

IBL's definition lives in a single source of truth (`data/ibl_nodes_src/`, built to `data/ibl_nodes.yaml` via `scripts/build_ibl_nodes.py`). Tool **packages** (40 installed, growing) are folders — drop one in and it's recognized, independent of the language; an AI agent can build, install, or modify them for you. Per-agent `allowed_nodes` restricts what each agent can reach.

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

**You'll provide:** an LLM API key (Anthropic, Google, or OpenAI); answers to a few questions about what you want; external API keys only as you actually use those features. To also turn on the public surfaces — Shared Warehouse, remote access — you'll additionally need a **Cloudflare account + your own domain**; the full setup map is in the [Getting Started guide](GUIDE_EN.md#1-getting-started).

<details>
<summary><strong>Alternative: download the desktop app (no Claude Desktop)</strong></summary>

Don't have Claude Desktop? Download a prebuilt desktop app. It bundles everything (Python, Node, all runtimes) inside the app, so nothing has to be installed on your machine and installing costs nothing — you just enter your own AI API key (Anthropic / Google / OpenAI) on first launch.

Get it from the [**app-latest** release](https://github.com/kangkukjin/indiebizOS/releases/tag/app-latest):
- **macOS (Apple Silicon)**: `IndieBiz-*-arm64.dmg`
- **macOS (Intel)**: `IndieBiz-*-x64.dmg`
- **Windows**: `IndieBiz-Setup-*.exe`

Open the `.dmg` and drag IndieBiz into Applications (macOS), or run the installer (Windows). The apps aren't code-signed yet, so the first launch may need **right-click → Open** on macOS, or **More info → Run anyway** on Windows SmartScreen.

**Language:** the AI replies in whatever language you write to it, so no setting is needed. (The bundled guides and desktop UI labels are currently Korean.)

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

## What's core vs what's yours

IndieBiz OS ships a **standard core** — the IBL grammar, the function-word nodes, the backend/frontend engine, and a catalog of tool packages and apps — but the moment you install it, it becomes *your* instance. You add vocabulary, install or author apps, accumulate conversations and settings. The line between the two is a single source of truth: `data/core_manifest.json`, derived from what's committed to the repo (`scripts/build_core_manifest.py`), so nothing has to be hand-tagged.

Two guarantees follow:

- **Install doesn't dump everything on you.** Many packages need their own API keys; installing them all would bury you in things you can't use. The whole catalog ships, but only a curated set is *active* by default — the rest sit available, ready to switch on when you want them. Every package carries an `origin` (core / user), and the desktop-app packaging is built from the manifest, so your own committed apps and personal files never leak into a distribution. (Committing a personal package for backup? Mark it `origin: user` and it stays out of the core.)
- **Updates never overwrite what's yours.** A reinstall or update refreshes only core-owned files. Which packages you've turned on or off, the vocabulary and apps you authored, your settings, and your conversation history all survive untouched — the updater respects the folder placement *you* chose rather than re-imposing the bundle's defaults.

This is the same substrate/superstructure seam that separates the standard grammar from your personal dictionary — pushed all the way out to packages, apps, install, and update.

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

*Last updated: 2026-07-21 — **The body's address becomes derived, and the author's Mac moves onto its own product**: a body's public identity is no longer configuration scattered through files. The remote launcher and finder now *derive* their URLs from whichever face the warehouse actually serves (one `origin_host` resolver that follows Cloudflare ↔ Tailscale switches), the auth gate went **fail-closed** (an unregistered host is treated as external, and proxy signals are read before `Host` — which cloudflared rewrites), and every open remote address is listed in one place. The installer no longer ships body-exclusive identity or personal data (Worker name, tunnel credentials, `wrangler.toml` separated out), and Cloudflare provisioning now creates the R2-cache Worker as part of issuance — after which the Mac's own hand-crafted Worker and tunnel were migrated onto that same provisioner (token tunnel; extra hostnames keep the phone delegation intact). **The machine this system was built on now runs on exactly the mechanism a fresh install gets.** On the reading side, the warehouse window became a finder, the neighbor tab became feed cards with an in-app finder into a neighbor's warehouse (discovery pinned to `#indienet`), and a neighbor's warehouse takes a **favorite score (0–3)** — your own rating axis, independent of the access level they granted you — filtering feed and search. Public warehouses serve a join page, and signing up or logging in through the in-app browser **captures the credential on the spot** — from then on both your browsing and the poller run at your granted level, with `[others:neighbor]{op: merge}` closing the duplicate-neighbor loose end. And the clipboard now crosses **both ways**: a thin button in the phone launcher's header ships the phone's clipboard to the Mac through the existing `[self:output]{op: clipboard}` — the mirror of the Mac's "to phone" button (a pbcopy locale trap that garbled non-ASCII was sealed on the way). Installer channel at v1.4.0. Zero new IBL verbs, action count unchanged (**157**). Earlier (2026-07-20) — **Dialect adapters + member subscription + a fresh-environment triple fix**: the warehouse poller gained a **dialect-adapter layer** — nginx/Apache directory indexes, RSS/Atom feeds (auto-discovered from HTML), Nextcloud public shares, and the file links on ordinary web pages all normalize into the same manifest currency, so someone becomes a neighbor without installing anything (a cold-start bypass: the existing web is the warehouse network's first neighbors). Subscription now runs **at your granted level**: register the id/password you created at a neighbor's warehouse and the poller logs in through the manifest's `login` contract — auto re-login on expired/revoked cookies, anonymous fallback on failure (the feed never stops). Reposts deliberately gained no guard — the level gate lives at the origin warehouse's serving, so a repost can't open any door; what to introduce is a human trust judgment, not a tool's. And three fresh-environment bug classes exposed by the first Windows install were sealed at the source: cloudflared freezing on a pipe nobody read (log-file redirect + precise tunnel process markers), a fresh-DB boot crash (migration order), and cold-start screens hardening on a failed first fetch (`useRetryingLoad` converged across 24 files) — plus a new Windows-portability CI gate on every push (static AST scan + a real Windows boot smoke), and the installer channel (app-latest) is at v1.3.3. Zero new IBL verbs, action count unchanged (**157**). Earlier (2026-07-19) — **Garage-sale shelves + the warehouse becomes the face**: every business item is now auto-materialized as a document (plus its photo files) under `공유창고/<level>/<business>/` — an outsider browses the whole catalog without ever asking ("asking" replaced by "placing"). A hidden sidecar guards the derived zone's boundary, so hand-placed files and folders are never touched, and photos ship as individual files so they pass the public face's EXIF-strip gate unchanged. The intro document (비즈니스문서.md) now ends with an automatically attached way to reach you — Nostr address automatic, email optional. And daily scheduled pipelines publish the morning newspaper, an AI trend report, and the latest blog post into the warehouse — production is publication. Zero new IBL verbs, action count unchanged (**157**). The README was restructured to put the shared warehouse up front. Earlier (2026-07-18) — **The shared warehouse — the node gets an address, and a reading half**: the public surfaces so far were destinations you *make*; the warehouse is the node itself being reachable. Level folders (`공유창고/0..4/`) on your disk are served live at the node's bare root with no index and no conversion — schema-on-read, the reader interprets, so serving costs the owner ~nothing. A viewer sees levels `0..their level` merged into one flat list (higher wins, 404 rather than 403 above their level, with a single deliberate `has_restricted` "there is more" smell), and the level is the *same* scale as their grade in your neighbor CRM. Beside the human page, `/manifest` serves the same walk as JSON with a self-describing `about` and a `login` block, so a foreign AI agent can read the node without scraping HTML. The genuinely new half is **subscription**: a background poller fetches registered neighbors' manifests every 30 minutes, diffs paths/mtimes into a timeline (`seed` / `new` / `changed`), and retains a snapshot that doubles as a **filename index of the whole neighborhood** — a pure machine layer, zero model calls. A warehouse address is stored as a *contact type* on a neighbor (so it sits beside their email and Nostr key, and an address-only stranger is still a proper neighbor, self-named from their manifest), and a repost is a plain `.url` pointer file that resolves to the origin when your manifest is served — **friend-of-a-friend discovery reduced to a file**. All of it composes from existing vocabulary: **zero new IBL verbs**, action count unchanged (**157**). Earlier (2026-07-17) — **The community surface — publishing to the open web at personal scale**: a family of `others` actions turns an IBL flow into a real public web address, no server or deploy — `[others:portal]` personal portals at `/h/<slug>/` (multiple portals, each owning its own member roster + display dial; login by id/pw or an operator-issued key; members *are* your neighbor CRM, levels 0 guest → 4 family; a per-portal audio proxy so borrowed instruments stream through your home IP), `[others:family_news]` a family newspaper at `/n/<slug>/` typeset from phone photos with guestbook + uploads, `[others:bulletin]` login-free bulletin boards at `/b/<slug>/`, and `[others:showcase]` public file shares at `/s/<slug>/` served straight off disk (on-the-fly directory walk, EXIF strip, video transcode). All ride one Cloudflare Worker over a tunnel to the Mac; a guest reaches only `min_level: 0` content. This is the first step of the "one node per community" strategy — your system is the node, the people around you are browsers reaching it. Also new: `[sense:stay]` (accommodation / short-let across three sources), `[sense:entity]` (Wikidata entity resolution — a QID pins down "common name" ambiguity), `[sense:used]` (second-hand markets), `[self:install_lib]` (a supply-chain approval gate for adding Python libraries), `[engines:icon]` (an app-only comic-icon generator that runs phone-local), and a crawl escalation ladder (curl_cffi → login-session → headless). Earlier (2026-06-30) — **The `table` node split (5 → 6 nodes)**: the currency transformers and emitters that used to live under `engines` moved to a new `table` node, so `engines` is now pure media generation and the currency grammar survives even when heavy generation is toggled off. Tool mapping and handlers unchanged — a semantic reorganization. Action count reflects both the split and steady vocabulary growth: **157 actions** (sense 48, self 49, limbs 17, others 17, engines 13, table 13), 40 tool packages. Earlier (2026-07-10) — **A clean core/user install seam**: the boundary between the standard core and your own additions is now one source of truth — `data/core_manifest.json`, derived from what's committed to the repo (`scripts/build_core_manifest.py`), replacing three divergent encodings (`.gitignore` + electron-builder filter + an extension-based update heuristic) that used to disagree. Every package resolves an `origin` (core / user); a committed-but-personal package can opt out with an `origin: user` marker. The desktop-app packaging is built from the manifest (`scripts/build_dist_filter.py`), so your apps and personal files — and unbounded runtime cruft the old filter never caught — no longer leak into a distribution. And an update now refreshes only core-owned files: `frontend/electron/main.js` preserves your install/uninstall choices (package folder placement), your authored vocabulary and apps, settings, and conversation history, force-refreshing only core vocabulary artifacts. This lays the groundwork for shipping the full catalog while activating only a curated key-free default set. Guarded by pre-commit + `build_ibl_nodes.py --check`. Earlier (2026-06-30) — **Model gear (dashboard shifting) + per-agent model retired**: the ~15 scattered places that picked a model are unified behind one resolver (`backend/model_resolver.py`) keyed by *cognitive role → axis → gear → tier*. A dashboard lever (`Save / Balance / Max`) shifts the whole system's model grade in one move, with a preset editor (gear × axis → tier) and per-agent pins for exceptions — all hot-reloaded with no restart, exposed over a `/model-gear` REST surface and rendered on the desktop, remote launcher, and phone. **Per-agent model config is retired**: an agent's yaml no longer carries `provider/model/apiKey` — the model *and its key* are inherited from the execution tier (this also closed a hidden bug where a keyless agent yaml died in THINK mode but survived EXECUTE via the midtier swap). Also: the phone's engine bundle is no longer a hand-maintained module list — it is **derived** from `data/bodies/*.json` body profiles (`scripts/build_body_bundle.py`, guarded three ways: build-time regeneration + pre-commit `--check` + on-device self-check), so a new backend module flows to the phone automatically. Action count unchanged (**142**), 38 tool packages. Earlier (2026-06-29) — **App-mode interactive render primitives**: the app-surface vocabulary (which the desktop, remote launcher, and phone all read from one `app:` block) gained an interactive `map` (leaflet) plus an `on:` view-event grammar — interaction-as-data: panning the map re-queries (`moveend` → `$lat/$lng/$radius`), and a marker click either runs an IBL action or, with `{stream: true}`, plays the marker's HLS video. A result-field dynamic filter (`filter: {from_field}`) builds chips from a result's distinct values and filters client-side (no re-query). The bespoke commercial-district instrument retired into this declarative vocabulary; the directions instrument's retirement was deferred (its route + separately-queried CCTV overlay needs more than one consumer to justify) and a lightbox primitive proved unnecessary (image grids already go fullscreen). The single-currency (`items`) migration was confirmed complete — zero `records` producers across backend and tools. Action count unchanged (**142** — a rendering-layer change), 38 tool packages. Earlier (2026-06-27) — **Live real-estate listings, AI opportunities & app-surface polish**: `sense:realty` now serves live asking-price listings (`source: zigbang`) beside official transaction prices (`source: molit`); new `sense:contest` (Kaggle) and `sense:startup` join the nanet academic search. App instruments got a quality sweep — radio favorites, CCTV in-app HLS playback (a reusable client-side `stream` button), flight-search date input + Korean regional airports (e.g. Cheongju/CJJ), an ETF quick-pick, weather & culture quick options, and route distance/ETA — and the phone-native app was rebuilt to match. **142 actions** (sense 44, self 44, limbs 17, others 11, engines 26), 38 tool packages. Earlier (2026-06-22) — **National-academic person & dissertation finding**: new `sense:researcher` (find/coauthor) and `sense:paper{source: nanet}` actions tap the National Assembly Library's academic-info API — a researcher search that splits same-name people by affiliation and birth year (the "common name" wall generic web search can't climb), plus Korean dissertation/journal search. Also: the **forager memory** (7th memory, spatial) is now live — when the AI searches the disk, web, or code, it accumulates a reusable map of that space (folder identities, conventions, dead ends, an owner-model) across sessions. 136→**141 actions** (sense 43, self 44, limbs 17, others 11, engines 26). Earlier (2026-06-17) — **Mac↔phone federation is live and authenticated**: the phone backend now runs without opening the app (always-on foreground service), the Mac↔phone borrow is bidirectional over the LAN behind a shared token (the phone binds to the LAN only when that token is present, and each side sends its credential automatically), and the self-check no longer flags a peer being temporarily offline as a failure. Also: `table:join` now composes record lists too (not just tables); fixes to `run_pipeline` (string steps), `self:grep` (single-file paths, `~` expansion across file actions), and the KOSIS statistics endpoint. Earlier (2026-06-15) — **Currency algebra**: `engines` gained domain-agnostic currency→currency transformers (unary filter/sort/take/select/dedup/groupby + binary join/union/merge), a `|` pipe shorthand, and a document-IR emitter — so any search result composes into a report of any format (html/pdf/docx/pptx). 124→136 actions (sense 42, self 41, limbs 17, others 11, engines 25).*
