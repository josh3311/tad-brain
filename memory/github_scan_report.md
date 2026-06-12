# GitHub Auto-Scan Report — 2026-06-12 (Night Build, Task 6)

**REPORT ONLY — nothing cloned, nothing merged. Joshua reviews and approves manually.**

Scanned for free/open tools matching TAD's gaps: real web/Reddit data for the
Market Agent (currently the scan is LLM-only with no live sources), outreach
delivery, LLM cost attribution (THE_MONKEY.md backlog item), agent framework
ideas, and MCP tooling.

---

## 1. agent-search (SearXNG bundle for agents)
- **Repo:** https://github.com/brcrusoe72/agent-search
- **What:** Self-hosted search API + MCP server bundling SearXNG. One-command
  deploy, scores/dedupes/caches results, scrubs prompt injection. Open-source
  alternative to Tavily/Exa/Serper.
- **Why relevant:** Market Agent's biggest weakness is that "scans" are pure
  LLM recall — no live web data. This gives `web_search` a real backend with
  zero API keys.
- **Integration:** Run as a local Docker service; point a `web_search()` tool in
  tools/registry at `http://localhost:<port>`. Market Agent prompt then cites
  real URLs.
- **Paid key:** No (self-hosted, free).

## 2. Perplexica / Vane (AI answering engine)
- **Repo:** https://github.com/ItzCrazyKns/Perplexica
- **What:** Self-hosted Perplexity-style answer engine with bundled SearxNG;
  container runs on localhost:3000.
- **Why relevant:** Heavier alternative to #1 — gives Market Agent synthesized,
  sourced answers rather than raw results. Good for the nightly loophole scan.
- **Integration:** Docker container; Market Agent queries its API for
  "problems people complain about in X" style research.
- **Paid key:** No (can use local Ollama or existing keys).

## 3. Official MCP servers (reference set)
- **Repo:** https://github.com/modelcontextprotocol/servers
- **What:** Anthropic-maintained MCP servers: Fetch (web content), Filesystem,
  Git, Memory (knowledge graph), Sequential Thinking, Time.
- **Why relevant:** TAD runs partly through Claude Code already; Fetch + Memory
  give agents real page retrieval and persistent structured memory without
  custom code.
- **Integration:** Add Fetch + Memory servers to Claude Code MCP config; expose
  to night-mode sessions.
- **Paid key:** No.

## 4. awesome-mcp-servers (directory)
- **Repo:** https://github.com/punkpeye/awesome-mcp-servers
- **What:** Curated index of thousands of MCP servers (also mcp.so registry).
- **Why relevant:** Discovery source for future gap-filling (Reddit, finance,
  CRM connectors) — fits the CSEO Agent's skill-gap scanning loop.
- **Integration:** CSEO Agent could periodically scan this list against
  THE_MONKEY.md backlog and propose candidates via ApprovalGate.
- **Paid key:** No (individual servers vary).

## 5. LiteLLM
- **Repo:** https://github.com/BerriAI/litellm
- **What:** Unified Python SDK/proxy for 100+ LLM providers with built-in cost
  tracking, budgets, rate limits, load balancing, logging.
- **Why relevant:** Directly matches the backlog item "LLM token cost
  attribution dashboard" (p6_build_1). One proxy in front of Claude + Kimi
  gives per-agent cost attribution for free, and budget caps would have
  prevented past credit-burn incidents.
- **Integration:** Point config_providers.py clients at a local LiteLLM proxy
  (both Anthropic and Moonshot are OpenAI-compatible through it); tag each
  call with the agent name for per-agent spend.
- **Paid key:** No (proxy is free; you pay only the underlying APIs you already use).

## 6. Langfuse
- **Repo:** https://github.com/langfuse/langfuse
- **What:** Open-source (MIT) LLM observability: traces, token/cost tracking,
  evals, prompt management. Self-hosted free, no request caps.
- **Why relevant:** Production-grade upgrade path for the new
  tad_observability.py metrics — per-call traces with token costs.
- **Integration:** Heavier (needs Postgres + ClickHouse + Redis); only worth it
  if TAD outgrows metrics.json. Park for later.
- **Paid key:** No (self-hosted).

## 7. listmonk
- **Repo:** https://github.com/knadh/listmonk (site: https://listmonk.app)
- **What:** Self-hosted newsletter/mailing manager (AGPLv3), multi-SMTP queues,
  rate limiting, templating. v6.1.0 (Mar 2026).
- **Why relevant:** tad_client_outreach / pending_emails.json currently depend
  on raw SMTP. listmonk adds queuing, throttling, bounce handling — important
  before real cold outreach volume (deliverability).
- **Integration:** Run via Docker; Marketing Agent posts campaigns/contacts to
  its REST API instead of sending raw SMTP.
- **Paid key:** No (needs an SMTP account, which .env already has).

## 8. Email-automation (PaulleDemon)
- **Repo:** https://github.com/PaulleDemon/Email-automation
- **What:** Lightweight open-source cold-outreach tool: scheduling,
  personalization (Jinja templates), self-hosted.
- **Why relevant:** Much smaller footprint than listmonk if all the Marketing
  Agent needs is personalized sequences for small lead lists.
- **Integration:** Borrow its Jinja-templating + scheduling pattern inside
  tad_client_outreach.py rather than running it as a service.
- **Paid key:** No.

## 9. smolagents (Hugging Face)
- **Repo:** https://github.com/huggingface/smolagents
- **What:** Minimal multi-agent framework built around code-executing agents.
- **Why relevant:** TAD's hand-rolled router/dispatch works, but smolagents'
  tool-calling loop is a clean reference for hardening _run_kimi_with_skill's
  10-iteration tool loop. Reference, not a rewrite.
- **Integration:** Study only — adopt its tool-error-recovery patterns.
- **Paid key:** No.

## 10. Pydantic AI
- **Repo:** https://github.com/pydantic/pydantic-ai
- **What:** Typed agent framework — typed tools, typed structured outputs,
  retries on validation failure.
- **Why relevant:** TAD's #1 recurring bug class is JSON parsing from LLM
  output (claude_json regex-stripping, market agent empty-JSON bug p6_1).
  Pydantic-validated outputs with auto-retry would eliminate it.
- **Integration:** Incremental: define Pydantic models for opportunity/score/
  decision payloads and validate in config_providers.claude_json; full
  framework adoption optional later.
- **Paid key:** No.

---

## Priority recommendation (for Joshua)
1. **LiteLLM** — directly hits the cost-attribution backlog item and adds spend caps.
2. **agent-search** — fixes the Market Agent's "no real data" weakness, zero keys.
3. **Pydantic-style validated JSON** — kills the recurring empty/malformed JSON bug class.
4. **listmonk** — before any real outreach volume goes out.
5. Others: park or reference-only.
