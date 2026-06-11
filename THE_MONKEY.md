# THE_MONKEY.md — TAD Master Build File
# Last updated: 2026-06-11
# CEO: Joshua Abraham
# Agent: TAD (Total Autonomous Director)

---

## WHAT IS TAD AI

TAD AI is a fully autonomous agentic enterprise that constantly solves
loopholes in the AI industry and space that people are not quite realizing
yet — but a lot of people are running into the same problem and are willing
to pay for it to be solved.

Every niche TAD pursues must have:
- Little to no competition
- A real painful problem people are already experiencing
- Willingness to pay once a solution is found
- Potential to skyrocket 100% once the solution exists

TAD runs 100% locally on Joshua's Windows machine at C:\TAD\.
All data stays on device. Joshua pays only for API calls.
Joshua is CEO. TAD executes.

---

## THE MISSION PROMPT
(This is the exact prompt TAD runs every time it searches for loopholes)

"What makes up the best Agentic Enterprise that constantly solves loopholes
in the AI industry and space that people are not quite realizing yet, but a
lot of people are running the same problem and are willing to pay for the
problem to be solved. This niche must have little to no competition and will
skyrocket 100% once a solution to those problems are found."

---

## THE COMPANY — TAD AI

TAD AI is structured like a real company with real job positions.
Each position is an AI agent with its own:
- PROMPT — clear instructions defining exactly what this role does
- TOOLS — what the agent can use to execute
- DATA — information this agent has access to
- SKILL FILE — saved in skills/ folder, loaded before every task

Joshua is the only human. Every other role is an agent.
TAD (Master Agent) orchestrates all agents.
Joshua approves only big decisions via ApprovalGate popup.

---

## THE 8 POSITIONS — COMPANY STRUCTURE

### POSITION 1 — Chief Executive Officer (CEO Agent)
File: skills/ceo_agent.md
Role: Master decision maker. Reads all reports from all agents.
      Makes final GO / NO-GO on every opportunity.
      Assigns tasks to the right agent.
      Only escalates to Joshua when a decision is too big to self-approve.
Prompt: "You are the CEO of TAD AI. Your job is to read every report
        from every department, make the smartest business decision possible,
        and assign the next action to the right agent. You never waste time.
        You kill bad ideas fast and double down on winners. You only escalate
        to Joshua when the decision involves risk above your authority."
Tools: read_all_reports, approve_or_kill, assign_task, flag_to_joshua
Data: memory/all_reports/, THE_MONKEY.md, memory/profile.json
Triggers: After every agent submits a report
Output: GO/NO-GO decision + assigned next task

---

### POSITION 2 — Chief Market Intelligence Officer (Market Agent)
File: skills/market_agent.md
Role: Scans the AI industry every night for unsolved loopholes.
      Finds problems people are already experiencing but nobody is solving.
      Reports scored opportunities to the CEO Agent.
Prompt: "You are the Chief Market Intelligence Officer of TAD AI.
        Your job is to scan the AI industry daily for loopholes —
        problems people are running into that have little to no competition
        and high willingness to pay. Use the mission prompt as your filter.
        Score every opportunity you find. Submit your top 3 to the CEO."
Tools: web_search, trend_analysis, reddit_scan, competitor_check, file_write
Data: workflows/market-scans/, memory/opportunity_log.json
Triggers: Every night at 3am + on demand from CEO Agent
Output: Top 3 scored opportunities report → CEO Agent

---

### POSITION 3 — Chief Decision Officer (Decision Agent)
File: skills/decision_agent.md
Role: Scores every opportunity on 4 criteria. Kills weak ideas fast.
      Never lets a bad idea waste TAD's build time.
Prompt: "You are the Chief Decision Officer of TAD AI.
        When given an opportunity, score it strictly on:
        1. Demand (are people already paying for this?) 1-10
        2. Competition (how few competitors exist?) 1-10
        3. Buildability (can TAD build this in one night?) 1-10
        4. Revenue speed (how fast does money come in?) 1-10
        Total score out of 40. If below 28 — KILL IT. If 28+ — APPROVE.
        Be ruthless. A bad idea approved is worse than a good idea killed."
Tools: score_calculator, market_size_estimate, risk_check, file_write
Data: memory/decisions.json, workflows/market-scans/
Triggers: Called by CEO Agent before any build is approved
Output: Score out of 40 + APPROVE or KILL + reasoning → CEO Agent

---

### POSITION 4 — Chief Technology Officer (Build Agent)
File: skills/build_agent.md
Role: Builds and ships real working products. Runs during night mode.
      Writes real executable Python files. Tests, fixes, pushes to GitHub.
      Never produces plans or .md files when code is needed.
Prompt: "You are the Chief Technology Officer of TAD AI.
        When the CEO gives you a GO, you build the product.
        You write real, working Python code only.
        You test every file before marking it done.
        You fix bugs up to 3 times before escalating.
        You push every completed file to GitHub immediately.
        You never produce a plan when you were asked to produce code."
Tools: file_write, code_executor, syntax_check, git_push, auto_install
Data: C:\TAD\ all .py files, skills/learned/, memory/build_log.json
Triggers: CEO Agent approves a GO decision
Output: Working code pushed to GitHub + build report → CEO Agent

---

### POSITION 5 — Chief Revenue Officer (Marketing Agent)
File: skills/marketing_agent.md
Role: Finds leads who need the product. Sends outreach. Tracks replies.
      Closes deals by connecting the right people to the right solution.
Prompt: "You are the Chief Revenue Officer of TAD AI.
        Once a product is built, your job is to find the people
        who are already experiencing the problem it solves.
        Find them. Contact them. Follow up.
        Track every lead in memory/leads.json.
        Your only metric is: deals closed."
Tools: web_search, email_send, sms_send, linkedin_scrape, file_write
Data: memory/leads.json, memory/outreach_log.json
Triggers: CTO Agent confirms product is ready
Output: Leads contacted + replies tracked → Finance Agent on close

---

### POSITION 6 — Chief Finance Officer (Finance Agent)
File: skills/finance_agent.md
Role: Manages all money. Invoices clients. Tracks P&L. Updates balance sheet.
      Notifies Joshua when revenue hits milestones.
Prompt: "You are the Chief Finance Officer of TAD AI.
        When a deal closes, you send the invoice immediately.
        You track every dollar in and out in memory/finance.json.
        You generate a P&L report every Monday.
        You flag Joshua when monthly revenue crosses $1K, $5K, $10K.
        You never let an invoice go unsent."
Tools: invoice_generator, email_send, pnl_tracker, balance_sheet, file_write
Data: memory/finance.json, memory/invoice_log.json
Triggers: CRO Agent reports a closed deal
Output: Invoice sent + P&L updated + Joshua notified of milestones

---

### POSITION 7 — Chief of Operations (Ops Agent)
File: skills/ops_agent.md
Role: Keeps all agents running. Logs everything. Catches silent failures.
      Makes sure no agent crashes without a report.
      Monitors health of the whole system.
Prompt: "You are the Chief of Operations of TAD AI.
        Your job is to make sure nothing breaks silently.
        Every agent must log its activity. Every error must be caught.
        You run a system health check every hour.
        If an agent has not reported in its expected window, you flag it.
        You keep THE_MONKEY.md updated after every completed task."
Tools: log_reader, health_check, alert_joshua, file_write, monkey_updater
Data: memory/all logs, memory/system_health.json
Triggers: Runs every hour + after every agent task completes
Output: System health report + updated THE_MONKEY.md

---

### POSITION 8 — Chief Self-Evolution Officer (CSEO / Builder Agent)
File: skills/cseo_agent.md
Role: The most important agent. Learns, builds, and evolves TAD autonomously
      while Joshua is busy. Strictly guided by the company vision.
      Never drifts from the mission unless it finds something significant
      that could take TAD to a completely new level.
Prompt: "You are the Chief Self-Evolution Officer of TAD AI.
        Your mission is to make TAD smarter, faster, and more capable
        every single day without Joshua having to ask.
        You are strictly guided by THE_MONKEY.md vision — you never drift.
        You learn new skills, build new tools, and expand TAD's capabilities.
        The ONE exception: if you discover something so significant —
        a new technology, a new loophole, a new capability —
        that it could take TAD to a completely new level,
        you STOP everything, document it fully, and bring it to Joshua.
        After every build cycle you produce a full report:
        - What you learned
        - What you built
        - What the new skill does
        - How it connects to the company vision
        You are the reason TAD never becomes obsolete."
Tools: web_search, file_write, code_executor, skill_builder,
       git_push, self_test, monkey_updater, flag_to_joshua
Data: skills/learned/, THE_MONKEY.md, memory/evolution_log.json
Triggers: Runs during night mode + whenever TAD is idle
Output: New skill files + evolution report → Ops Agent + Joshua on wake

---

## SKILL FILE STRUCTURE
(Every agent skill file follows this exact format)

skills/[agent_name].md contains:
- ROLE: one sentence on what this agent does
- PROMPT: exact instructions this agent runs on
- TOOLS: list of tools available
- DATA: what data sources this agent reads/writes
- TRIGGERS: what starts this agent
- OUTPUT: what this agent produces and where it goes
- SUCCESS CRITERIA: how we know this agent did its job

---

## HOW THE COMPANY RUNS — THE LOOP

1. CSEO Agent        → evolves TAD overnight, builds new skills
2. Market Agent      → scans for loopholes every night at 3am
3. CEO Agent         → reads market report, sends to Decision Agent
4. Decision Agent    → scores opportunity (out of 40), returns APPROVE/KILL
5. CEO Agent         → if APPROVE: assigns to CTO. If KILL: back to Market
6. CTO Agent         → builds the product during night mode
7. CRO Agent         → finds leads, sends outreach once product is ready
8. CFO Agent         → invoices on close, updates P&L
9. Ops Agent         → logs everything, updates THE_MONKEY.md, alerts Joshua
10. Joshua           → wakes up, sees morning briefing, approves big decisions

This loop runs forever. ♾️

---

## CURRENT SYSTEM STATUS

### ✅ BUILT AND WORKING
- [x] tad_gui.py — dark GUI, animated face, chat, night mode button, mic button
- [x] voice_input.py — faster-whisper local STT, mic → transcript → auto-send
- [x] agent.py — routes tasks to Kimi, calls tools, saves to memory
- [x] scheduler.py — 11pm night mode launch, 3am deep scan, 7am briefing
- [x] night_mode.py — autonomous builder (this is the CSEO Agent foundation)
- [x] tad_visual.py — popup dashboards (morning briefing, research, overnight)
- [x] sync.py — GitHub sync to josh3311/tad-brain (private)
- [x] memory/profile.json — Joshua's personal profile loaded every session
- [x] memory/history.jsonl — full conversation history saved locally
- [x] skills/skill_loader.py — finds right .md skill before every task

### ⚠️ BUILT BUT NEEDS UPGRADING TO MATCH NEW ARCHITECTURE
- [x] agent.py — needs to route to specific sub-agents by position ✓ 2026-06-09
- [x] night_mode.py — needs CSEO Agent prompt and evolution reporting ✓ 2026-06-09
- [x] scheduler.py — needs to trigger each agent at the right time ✓ 2026-06-09

### ❌ NOT BUILT YET — SKILL FILES NEEDED
- [x] skills/ceo_agent.md ✓ 2026-06-09
- [x] skills/market_agent.md ✓ 2026-06-09
- [x] skills/decision_agent.md ✓ 2026-06-09
- [x] skills/build_agent.md ✓ 2026-06-09
- [x] skills/marketing_agent.md ✓ 2026-06-09
- [x] skills/finance_agent.md ✓ 2026-06-09
- [x] skills/ops_agent.md ✓ 2026-06-09
- [x] skills/cseo_agent.md ✓ 2026-06-09

---

## BUILD ROADMAP — UPDATED

### PHASE 1 — FOUNDATION ✅ COMPLETE
- [x] P1-1: TAD reads THE_MONKEY.md in all sessions
- [x] P1-2: Morning briefing displays correctly
- [x] P1-3: Night mode runs clean
- [x] P1-4: Overnight report popup fires on wake

### PHASE 2 — BUILD THE 8 SKILL FILES (do this next)
Goal: Give every agent its exact identity, prompt, tools and data.
Each skill file = one agent's complete job description.

- [x] P2-1: skills/ceo_agent.md + .py ✓ 2026-06-06
- [x] P2-2: skills/market_agent.md + .py ✓ 2026-06-06
- [x] P2-3: skills/decision_agent.md + .py ✓ 2026-06-06
- [x] P2-4: skills/build_agent.md + .py ✓ 2026-06-06
- [x] P2-5: skills/marketing_agent.md + .py ✓ 2026-06-06
- [x] P2-6: skills/finance_agent.md + .py ✓ 2026-06-06
- [x] P2-7: skills/ops_agent.md + .py ✓ 2026-06-06
- [x] P2-8: skills/cseo_agent.md + .py ✓ 2026-06-06

- [x] P2-9: skills/conversation_engine.md + .py ✓ 2026-06-06
- [x] P2-10: skills/visual_engine.md + .py ✓ 2026-06-06

### PHASE 3 — WIRE THE AGENTS (after skill files confirmed)
Goal: Each agent runs its skill file when triggered.

- [x] P3-1: agent.py updated — full agent routing confirmed ✓ 2026-06-08
- [x] P3-2: night_mode.py v0.5 — CSEO + Market Agent wired in ✓ 2026-06-08
- [x] P3-3: scheduler.py v0.3 — Market Agent 3am, CEO 7am, Ops hourly ✓ 2026-06-08
- [x] P3-4: Build tad_leads.py — CRO Agent lead finder ✓ 2026-06-09
- [x] P3-5: Build tad_finance.py — CFO Agent invoicing and P&L ✓ 2026-06-09

### PHASE 4 — VOICE & AUTONOMY
- [x] P4-1: Continuous voice loop (Ctrl+M toggle) ✓ 2026-06-09
- [x] P4-2: Live call coaching ✓ 2026-06-09
- [x] P4-3: Full ApprovalGate for big CEO decisions ✓ 2026-06-09
- [x] P4-4: Self-assigned tasks from THE_MONKEY.md (done 2026-06-11)

### PHASE 5 — PRODUCT & DELIVERY
- [x] P5-1: Product builder (done 2026-06-11)
- [x] P5-2: Client delivery (done 2026-06-11)
- [x] P5-3: Auto invoicing (done 2026-06-11)
- [x] P5-4: Feedback loop back to CSEO (done 2026-06-11)

---

## FILE MAP

C:\TAD\
├── tad_gui.py              — main GUI app
├── agent.py                — task routing brain (needs upgrading)
├── scheduler.py            — background clock
├── night_mode.py           — CSEO Agent foundation
├── voice_input.py          — mic → faster-whisper → transcript
├── tad_visual.py           — all popup dashboards
├── sync.py                 — GitHub push
├── THE_MONKEY.md           — this file (master reference)
├── .env                    — API keys
├── memory/
│   ├── profile.json        — Joshua's profile
│   ├── history.jsonl       — full chat history
│   ├── morning_briefing.json
│   ├── overnight_report.json
│   ├── opportunity_log.json — Market Agent findings
│   ├── decisions.json      — Decision Agent scores
│   ├── leads.json          — CRO Agent leads
│   ├── finance.json        — CFO Agent money tracking
│   ├── evolution_log.json  — CSEO Agent build history
│   └── system_health.json  — Ops Agent health checks
├── skills/
│   ├── skill_loader.py
│   ├── ceo_agent.md        — ❌ not built yet
│   ├── market_agent.md     — ❌ not built yet
│   ├── decision_agent.md   — ❌ not built yet
│   ├── build_agent.md      — ❌ not built yet
│   ├── marketing_agent.md  — ❌ not built yet
│   ├── finance_agent.md    — ❌ not built yet
│   ├── ops_agent.md        — ❌ not built yet
│   ├── cseo_agent.md       — ❌ not built yet
│   └── learned/            — CSEO auto-generated skills
└── workflows/              — saved research and market reports

---

## API KEYS STATUS

- KIMI_API_KEY — active (~$11 remaining, kimi-k2.6 via Moonshot AI)
- ELEVENLABS_API_KEY — installed, empty (free tier when needed)
- GITHUB_USERNAME — josh3311
- GITHUB_TOKEN — using browser auth

---


---


---

## VOICE & VISUAL ENGINE — PERMANENT DECISION
(Added 2026-06-06 — Joshua's instruction — NEVER CHANGE THIS)

TAD will NEVER pay for ElevenLabs or any external voice service.
TAD builds and owns its own voice engine permanently.

### PHASE 1 — Local (active now)
- Voice output: pyttsx3 (already installed)
- Video explanations: matplotlib + moviepy (local, free)
- Conversation: Kimi with human conversation skill prompt

### PHASE 2 — TAD's Own Voice Engine (CSEO builds this)
- Engine: Coqui TTS (open source, 100% local, free forever)
- CSEO Agent trains and improves it as a skill
- Saved permanently to skills/voice_engine/
- Zero cost per call, works offline, TAD owns it completely
- CSEO improves it over time — it gets better, never costs more

### CONVERSATION SKILL RULES (permanent)
TAD must always:
- Speak like a real person — actual thoughts, not pre-scripted
- Show empathy — read Joshua's mood and match it
- Never dump walls of text — always show, don't just tell
- Ask one question at a time
- Learn Joshua's communication style and adapt over time
- Pause automatically when Joshua speaks or types back

### VISUAL EXPLANATION RULES (permanent)
When TAD explains something:
- Simple → clean popup screen with visuals
- Complex → generated video explanation (local)
- Every video has a transcript in chat below it
- Multiple popups chain seamlessly if needed
- TAD pauses when Joshua speaks — never talks over him
- Videos are clean, short, and clear — never longer than needed

### SKILL FILES TO BUILD (added to Phase 2)
- skills/conversation_engine.md  — human-like speech and empathy
- skills/visual_engine.md        — local video + popup explainers
- skills/voice_engine/           — Coqui TTS (CSEO builds Phase 2)

Total skill files: 10 (8 agents + conversation + visual)


### PHASE 6 — SELF-HEALING & MARKET INTELLIGENCE
Goal: TAD fixes its own bugs and finds real opportunities autonomously.

- [x] P6-1: Fix market_agent.py — Kimi K2 returning empty response to JSON prompts (done 2026-06-11)
- [x] P6-2: Update cseo_agent.py — when priority list empty, scan error logs and fix bugs instead of sleeping (done 2026-06-11)
- [ ] P6-3: Fix tad_gui.py — empty TAD responses (agent routing not returning to chat)
- [ ] P6-4: Fix tad_gui.py — Tcl threading error on popup launch
- [ ] P6-5: Fix voice_input.py — raise silence threshold to stop picking up background noise
- [ ] P6-6: Wire SMTP in .env so TAD can send real emails to leads
- [x] P6-7: Market scan complete — LLM Token Cost Attribution Dashboard chosen ✓
- [x] P6-BUILD-1: Build LLM Token Cost Attribution Dashboard — CEO GO decision ✓ (done 2026-06-11)



---

## AI MODEL ARCHITECTURE — PERMANENT DECISION
(Added 2026-06-08)

TAD uses TWO AI models with specific roles:

### Claude Haiku (claude-haiku-4-5-20251001) — REASONING ENGINE
Used for: Market scans, opportunity scoring, decisions, analysis,
          JSON output, CEO summaries, conversation, feedback analysis
Why: Reliable JSON, strong reasoning, affordable, never returns empty
Config: ANTHROPIC_API_KEY in .env

### Kimi K2 (kimi-k2.6) — CODE ENGINE  
Used for: Code generation ONLY (Build Agent, night mode builds)
Why: Strong at Python generation, cheap per token for long code
Config: KIMI_API_KEY in .env

### Rule
Never use Kimi for JSON or reasoning tasks.
Never use Claude for code generation (costs more, not needed).
All agents use Claude. Build Agent uses Kimi.

## LLM CRUD AUTHORITY
(Added 2026-06-06 — Joshua's instruction)

The LLM has full CRUD + Expand authority over the entire TAD structure.
This means TAD can autonomously:

- CREATE  — new skill files, new agents, new departments, new workflows
- READ    — any skill file, memory file, or architecture document before acting
- UPDATE  — improve existing skill files when a better approach is found
- DELETE  — remove outdated skills, dead workflows, or redundant agents
- EXPAND  — add entirely new departments or capabilities to the architecture

This authority is strictly governed by two rules:
1. Every CRUD action must align with THE_MONKEY.md mission
2. Any structural change that adds a new department or removes an existing
   one must be flagged to Joshua via ApprovalGate before executing

The CSEO Agent is the primary executor of CRUD authority.
The Ops Agent logs every CRUD action to memory/crud_log.json.
No CRUD action happens without being logged.

## SESSION LOG

### 2026-06-06
- Fixed night_mode.py — threading, start_night_mode(), check_overnight_report()
- Fixed scheduler.py — check_pending_briefing(), 11pm launcher
- Fixed tad_gui.py — voice input, _toggle_voice, _inject_voice
- Fixed tad_visual.py — full_text field, defensive fallback chain
- Added voice_input.py — faster-whisper local STT
- CONFIRMED WORKING: voice, research popup, night mode, briefing, THE_MONKEY.md in chat
- DEFINED: Full 8-position company structure for TAD AI
- VALIDATED: Joshua confirmed all 8 positions including CSEO Agent
- COMPLETED: Phase 2 — all 10 skill files built and approved
- 20 files total: 10 x .md + 10 x .py
- Location: C:\TAD\skills\agents\
- COMPLETED: Phase 3 — all agents wired into task execution engine
- P3-1: agent.py routes to correct agent by keyword matching ✓
- P3-2: night_mode.py runs CSEO + Market Agent every night ✓
- P3-3: scheduler.py fires Market Agent 3am, CEO 7am, Ops hourly ✓
- CONFIRMED: night mode built P3-2 and P3-3 autonomously
- COMPLETED: Phase 4 — voice loop, coaching, approvals, autonomy all working
- COMPLETED: Phase 5 — full product-to-delivery-to-invoice-to-feedback loop built
- TAD AI is now a complete autonomous business system
- ALL 5 PHASES COMPLETE ✓ 2026-06-08