# Auto-Leverage: Intent Resolution Architecture
**Author:** Joshua Nkeng Abraham Fowah
**Project:** TAD (Total Autonomous Director) — josh3311/tad-brain
**Phase:** 6 | **Date:** June 27, 2026

---

## What Is Auto-Leverage?

Auto-Leverage is a third stage in AI agent architecture — sitting after
pre-training and fine-tuning — whose sole purpose is to resolve the precise
meaning and intent behind a user's words before any execution begins.

The 3-stage model:

| Stage | Purpose | Outcome |
|---|---|---|
| Pre-Training | Pattern recognition at scale | Language understanding |
| Fine-Tuning | Safety, alignment, helpfulness | Responsible behaviour |
| Auto-Leverage | Intent + thought mapping per prompt | Precise execution |

---

## The 6-Step Resolution Loop
STEP 1 — PARSE     → Read every word. Identify multi-meaning terms.

STEP 2 — FLAG      → Mark ambiguous words. Do not guess. Do not proceed.

STEP 3 — ASK       → Ask only questions that genuinely need human input.

STEP 4 — LOCK      → Commit to resolved meaning for the full session.

STEP 5 — CONVERGE  → Apply Threshold or Deep Clarity mode (see below).

STEP 6 — EXECUTE   → Proceed with full specificity. Not just what to build
but WHY it needs to be built exactly this way.

---

## Dual-Mode Convergence

When two interpretations are equally valid:

| Mode | Trigger | Behaviour |
|---|---|---|
| Threshold | autonomous tasks (night builds, scheduler, CSEO) | Scores interpretations, picks highest confidence, logs choice, proceeds |
| Deep Clarity | interactive tasks (GUI chat, voice input) | Surfaces ambiguity, asks one precise question, waits for confirmation |

**Mode preference lives at the task-type level.**
Set once in scheduler.py at task creation. No agent figures it out itself.

---

## Agent Self-Resolution Loop

When an agent cannot ask the user, it resolves internally:

[1] WHY am I solving this?         → situational context

[2] WHY is this word here?         → positional/functional role

[3] WHAT does this word mean       → generate multiple interpretations
across similar contexts?

[4] WHAT are the similarities      → find the common thread
between those contexts?

[5] CONVERGE                       → lock most precise meaning

[6] EXECUTE                        → full specificity, not assumption

---

## TAD Integration Points

| File | Change |
|---|---|
| skills/auto_leverage.py | Core engine — resolve_intent() entry point |
| scheduler.py | Tags every task with task_type at creation |
| agent.py | Calls resolve_intent() before any routing |
| night_mode.py | Forces task_type='autonomous' on all generated tasks |

---

## TAD Agent Map

| Agent | Default Mode |
|---|---|
| Market, Decision, CEO, CSEO, Ops, Finance, Marketing | Threshold |
| Build Agent (night) | Threshold |
| Build Agent (interactive) | Deep Clarity |

---

*Full concept documentation: Auto_Leverage_Framework_TAD.docx (same folder)*
