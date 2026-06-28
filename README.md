# TAD — Total Autonomous Director

**GitHub:** josh3311/tad-brain

TAD is an autonomous business agent that finds AI loopholes, scores opportunities, builds products, and ships code — unattended.

---

## Architecture Concepts

### Auto-Leverage — Intent Resolution Layer
TAD includes a custom intent resolution layer that runs before any agent
executes a task. It detects ambiguous words in a prompt, then resolves
meaning via one of two modes:

- **Threshold Mode** — autonomous tasks (night builds, CSEO, scheduler):
  TAD scores interpretations, picks the most probable meaning, logs its
  choice, and proceeds without interrupting the user.

- **Deep Clarity Mode** — interactive tasks (GUI chat, voice input):
  TAD surfaces the ambiguity and asks one precise clarifying question
  before proceeding.

This eliminates silent guesswork, reduces wrong builds, and makes agents
behave as senior problem solvers rather than fast prompt executors.

Full documentation: [`docs/auto_leverage_framework.md`](docs/auto_leverage_framework.md)
