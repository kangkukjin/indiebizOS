
**{{node_count}} nodes, {{total}} composable actions** — one tool (`execute_ibl`), one vocabulary, not {{total}} schemas:

| Node | Actions | What lives here |
|------|---------|-----------------|
{{node_rows_en}}

IBL's definition lives in a single source of truth (`data/ibl_nodes_src/`, built to `data/ibl_nodes.yaml` via `scripts/build_ibl_nodes.py`), and a commit-time check matches source ↔ tool schema ↔ handler three ways. Tool **packages** ({{tools_n}} installed, plus {{exts_n}} backend core modules) are folders — drop one in and it's recognized, independent of the language; an AI agent can build, install, or modify them for you. Per-agent `allowed_nodes` restricts what each agent can reach.
