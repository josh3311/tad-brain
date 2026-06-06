# THE MONKEY — TAD Master Project File
# Auto-updated by TAD after every build session
# Last updated: 2026-06-06

---

## What TAD Is
TAD is Joshua Abraham's personal sovereign AI agent and fully autonomous business operating system.
It runs 100% locally on his machine. All data stays on device. Nothing leaves except API calls.
API credits are pay-per-use across Kimi, Claude, OpenAI, Perplexity — swappable in one config line.
Joshua is the final decision authority. TAD executes. Joshua approves big moves only.

---

## Joshua's Vision — The Full Picture
TAD is not a chatbot. TAD is an autonomous enterprise AI company where Joshua is the CEO.

### Division 1 — Business Engine
Continuously scans markets, identifies profitable gaps and loopholes with low competition,
develops business ideas, runs marketing campaigns, finds leads, communicates with clients via text,
coaches Joshua in real time during video calls (tells him exactly what to say to win deals),
builds products autonomously (architecture → code → bug fixes → security → shipping),
chooses the right LLM for each task, only comes back to Joshua when finished or genuinely stuck,
finalizes products and ships to clients, learns every skill it used to build.

### Division 2 — Growth Engine
Teaches Joshua new concepts visually (not text walls), tracks business performance,
sharpens decision-making, forecasts trends, helps Joshua understand current situation
and foresee the future. TAD is Joshua's smartest advisor.

### Division 3 — Finance Engine
Expert accountant for the business: invoicing, balance sheets, P&L statements,
expense tracking, tax preparation, everything a small business accountant does.
All financial data stays local and clean.

### The Moat — Why This Cannot Be Replaced
When any AI company ships a new feature, TAD doesn't migrate.
The feature gets wrapped as a tool, dropped into tools/registry.py,
and TAD gets more powerful. Competitive advantage compounds every day.

### Target Outcomes
- Stage 1 (now): TAD researches, advises, saves intelligence locally
- Stage 2 (2-4 weeks): $500-$3,000/month from one executed idea TAD surfaces
- Stage 3 (2-6 months): $5,000-$20,000/month from multiple streams
- Stage 4 (6-18 months): Sellable platform or portfolio of AI businesses

---

## Current State — What Is Built

### Core files
- tad_gui.py         — dark GUI, animated face, voice output (pyttsx3), Ctrl+Space hotkey
- agent.py           — sovereign agent v0.3, skill loader, monkey reader, LLM router, visual popup trigger
- scheduler.py       — 3am deep scan (5 queries), 7am briefing with visual dashboard launch
- tad_visual.py      — visual popup system: MorningBriefingDashboard, ResearchDashboard, ApprovalGate
- config/providers.py — LLM provider config, ACTIVE_PROVIDER = kimi
- tools/registry.py  — tool registry: web_search (DuckDuckGo), file_write, file_read
- tools/__init__.py
- memory/profile.json — Joshua Abraham's personal profile, goals, vision, role
- memory/history.jsonl — all conversations + agent runs saved locally
- .env               — API keys (Kimi active, ElevenLabs ready, others ready to add)
- .gitignore         — protects API keys from GitHub
- .vscode/mcp.json   — filesystem MCP server pointing at C:\TAD

### Skills library
- skills/universal/sovereign_system.md   — TAD's core identity and system prompt
- skills/agents/research/market_analysis.md — market research execution instructions
- skills/agents/business/opportunity_score.md — opportunity scoring framework
- skills/agents/coding/debug.md — code debugging and explanation
- skills/skill_loader.py — finds right skill, auto-builds new ones if missing, saves to learned/
- skills/__init__.py

### Workflows produced so far
- workflows/market-analysis-may-2026.md
- workflows/market-analysis-vertical-ai-agents-2026-06-06.md
- workflows/deep-scan-2026-06-06.md
- workflows/briefing-2026-06-06.md

- plans\fix-3am-popup-scheduler-should-save-sile-plan.md
### Working capabilities
- Chat with memory across sessions (last 5 conversations injected on startup)
- Personal profile loaded on every startup (Joshua Abraham, goals, vision, role)
- Web search via DuckDuckGo (free, no API key, real-time)
- Market research reports saved to workflows/ automatically
- Skill loader — reads right .md before every task, builds new skills if missing
- THE_MONKEY.md auto-update after every task (timestamp + new files logged)
- LLM router — routes task types to best provider (all on Kimi now, Claude/OpenAI ready)
- Voice output via pyttsx3 (free, local, works on Windows)
- Scheduler — 3am deep scan + 7am briefing (runs as background thread in tad_gui.py)
- Visual popup system — morning briefing dashboard with score cards, bar charts, voice narration
- Research report popup — launches after every research task with full report
- Approval gate popup — pauses TAD and asks Joshua to approve big decisions
- MCP filesystem server — VS Code can read/write C:\TAD files directly

---

## What Is NOT Built Yet — Priority Order

### Priority 1 — Build this session
- [x] Fix 3am popup — scheduler should save silently, briefing shows when Joshua wakes up and says "hey TAD" ✓ 2026-06-06 (built+tested)
- [ ] GitHub sync — push skills/ and memory/profile.json to private repo (TAD travels anywhere)

### Priority 2 — Next session
- [ ] Voice input — mic → faster-whisper (local STT) → full voice loop (speak to TAD, not just listen)
- [ ] Opportunity pipeline — tracks ideas TAD surfaces, scores them over time, flags best ones
- [ ] Competitor monitor — daily scan of specific competitors in chosen niche

### Priority 3 — Enterprise features
- [ ] Sales arm — TAD runs marketing campaigns, finds leads, sends outreach texts
- [ ] Client text communication — TAD handles client messaging autonomously
- [ ] Video call coaching — TAD listens to call context and tells Joshua exactly what to say in real time
- [ ] Build arm — TAD architects, codes, fixes bugs, handles security, ships products to clients
- [ ] Smart LLM routing — Claude for reasoning/writing, Codex for code, Perplexity for live search
- [ ] Sub-agent spawner — TAD creates fresh agents for heavy parallel tasks
- [ ] Skill learner — every skill used in a build project gets saved permanently to skills/learned/

### Priority 4 — Finance engine
- [ ] Invoice generator — TAD creates and sends professional invoices
- [ ] Balance sheet tracker — income, expenses, profit tracked automatically
- [ ] P&L statement — monthly reports generated automatically
- [ ] Tax preparation assistant — organizes deductibles, flags tax obligations
- [ ] Business health dashboard — visual popup showing financial state at a glance

### Priority 5 — Learning module
- [ ] Visual explainer — TAD teaches new concepts via diagrams and charts, not text walls
- [ ] Tutor agent — when Joshua is stuck, TAD explains visually why and how to fix it
- [ ] Progress tracker — tracks what Joshua has learned and what gaps exist

---

## Architecture

### Request flow
User (voice or text) → TAD GUI → intent classification
→ skill_loader loads right .md skill file
→ agent reads THE_MONKEY.md for project state
→ LLM router picks best provider
→ specialist agent executes with tools
→ result saved to workflows/
→ visual popup launched (ResearchDashboard or MorningBriefingDashboard)
→ voice narration speaks summary
→ THE_MONKEY.md updated
→ memory/history.jsonl updated

### LLM routing (current → target)
- Research tasks → Kimi (long context, good at synthesis)
- Reasoning + writing → Kimi now → Claude claude-sonnet-4-6 when key added
- Code generation → Kimi now → Codex/GPT-4o when key added
- Live web data → DuckDuckGo now → Perplexity when key added
- General → Kimi

### Skill system
Task arrives → skill_loader.find_skill(input) → loads .md file
→ if missing → Kimi builds it → saved to skills/learned/ permanently
Skill file format: Purpose / Instructions / Tools needed / Output format / Success criteria

### Visual popup system
tad_visual.py contains:
- MorningBriefingDashboard — score cards + bar chart + hidden gem + action + voice
- ResearchDashboard — full report + save button + voice narration
- ApprovalGate — proposed action + reasoning + approve/reject buttons + voice

### File tree ownership
/tad
  /config          — provider settings
  /memory          — profile.json + history.jsonl + morning_briefing.json (pending)
  /skills
    /universal     — identity and core prompts
    /agents        — research, business, coding skill files
    /learned       — auto-built skills TAD generates itself
  /tools           — registry.py with all tool implementations
  /workflows       — all reports, scans, briefings saved here
  /.vscode         — mcp.json for VS Code filesystem access
  THE_MONKEY.md    — this file (auto-updated by TAD)
  tad_gui.py       — main application entry point
  agent.py         — sovereign agent core
  scheduler.py     — autonomous daily intelligence engine
  tad_visual.py    — visual popup dashboard system

New AI features get absorbed as tools in tools/registry.py — TAD never migrates.
File tree owns everything. MCP connects to external world. GitHub syncs everything portable.

---

## API Keys Status
- KIMI_API_KEY — active, $11.64 balance (Moonshot AI / kimi-k2.6)
- ELEVENLABS_API_KEY — installed, free tier (upgrade for better voice quality)
- ANTHROPIC_API_KEY — not yet added (add for Claude reasoning tasks)
- OPENAI_API_KEY — not yet added (add for Codex tasks)
- PERPLEXITY_API_KEY — not yet added (add for live web search upgrade)

---

## How TAD Updates This File
After every completed task TAD must:
1. Read this file
2. Check off completed items in "What Is NOT Built Yet"
3. Add any new files created to "Current State — Workflows produced" or "Core files"
4. Update "Last updated" timestamp to today
5. Save the file back using file_write tool