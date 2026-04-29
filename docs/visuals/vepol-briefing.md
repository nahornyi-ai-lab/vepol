# Vepol: Personal AI Operating Environment

## Executive Summary
Vepol is a personal operating environment designed to transform local markdown files into a persistent, actionable knowledge base for AI agents. Based on the Russian TRIZ "substance-field" model (*Веполь*), it coordinates multiple agents—specifically Claude Code and Codex CLI—to operate against a single source of truth rather than fragmented, session-specific memory. By combining a structured knowledge schema (~/knowledge/) with an active orchestration layer, Vepol provides developers with a durable environment for long-term project management, cross-agent review, and automated session capture. It is currently in alpha (v0.1.x) and is tailored for macOS power users who require their AI agents to maintain state and context across complex, multi-project workflows.

## Core Concepts and Architecture

### The Substance-Field Model
The name "Vepol" is derived from the TRIZ concept of a smallest functional unit. In this framework:
*   **Two Substances:** The user and the AI agents (Claude, Codex).
*   **The Field:** The markdown knowledge base that binds the agents and the user together.
*   **The Result:** A system where knowledge is not just stored but actively transformed into action.

### Core vs. Overlay Separation
Vepol maintains a strict mechanical boundary to ensure stability and privacy:
*   **Core Repo:** Contains universal schemas, scripts, and methodology. This is managed via a `.managed.yaml` file, which tracks files belonging to the Vepol repository for seamless upgrades.
*   **User Overlay:** Resides in `~/knowledge/`. This contains the user's private registry, logs, concepts, and project-specific data. Vepol is designed so that the overlay is never published or overwritten during core updates.

### The Four-Layer Privacy Model
The system incorporates four layers of privacy (currently tested in alpha). This includes a privacy-aware sync mechanism that allows developers to curate and publish specific portions of their knowledge base without leaking sensitive local data or session transcripts.

### Parallel Orchestration
Vepol treats Claude Code and Codex as equal interfaces to the same "brain." This "zero split-brain" policy ensures:
*   **Single Source of Truth:** All agents read from the same `README.md`, `state.md`, and `log.md`.
*   **Shared Memory:** If one agent finds an answer, it must be recorded in the knowledge base so the second agent does not have to repeat the search.
*   **Cross-Agent Review:** Non-trivial changes (e.g., architectural shifts) must be reviewed by the "other" agent before implementation.

## The Knowledge-Base (KB) Schema
Vepol mandates a standardized structure for every project to ensure agents can immediately orient themselves.

| File | Purpose |
| :--- | :--- |
| `README.md` | High-level project status (1–2 sentences). |
| `state.md` | Current project snapshot. |
| `log.md` | Chronological event log (auto-updated by session captures). |
| `backlog.md` | Tasks to be executed. |
| `escalations.md` | Blockers or decisions requiring user/hub intervention. |
| `incidents.md` | Root cause analysis and prevention rules for errors. |
| `strategies.md` | Weekly-reviewed hypotheses and long-term project direction. |

## License Model: FSL-1.1-MIT
Vepol uses the Functional Source License (FSL) with an automatic MIT conversion, ensuring the software is source-available now and fully open-source eventually.

*   **Phase 1 (First 2 Years):** The FSL allows almost all uses except for competing managed services. Users can freely use Vepol for personal projects, internal company tooling, and professional consulting.
*   **Phase 2 (Automatic Conversion):** Two years after any specific release, that version's license automatically and irrevocably converts to MIT.
*   **Competitive Restriction:** Users may not host Vepol as a SaaS that competes with the original product without a commercial license.

### Commercial Licensing Tiers
For enterprises requiring pre-conversion freedom or competing use, pricing is tiered by company size:
*   **Startups:** $500–$2,000/year.
*   **Mid-size:** $2,000–$10,000/year.
*   **Large Enterprise:** Case-by-case.

## Comparison to Alternatives

| Feature | Vepol (FSL-1.1-MIT) | Standard Open Source (MIT/Apache) | Restrictive (AGPL/BUSL) |
| :--- | :--- | :--- | :--- |
| **Personal/Internal Use** | Free | Free | Often Free (but AGPL has viral risks) |
| **Consulting Services** | Explicitly Permitted | Permitted | Varies |
| **SaaS Protection** | 2-year protection for creators | None | Permanent protection/restriction |
| **Eventual Open Source** | Guaranteed (2-year lag) | Immediate | Often Never |

Vepol positions itself as more developer-friendly than AGPL because it lacks the "viral" requirement to release source code for network services, focusing only on preventing direct SaaS competition.

## Actionable Insights for Developers

### Quickstart in 5 Commands
To get Vepol running in a local environment:

1.  **Install:** `curl -fsSL https://get.vepol.ai | bash` (Installer checks for Claude CLI, Node, Bun, and Git).
2.  **Initialize KB:** `claude -p "run skill init-kb"` (Sets up the standard folder structure).
3.  **Add Task:** `kb-task "Design new API endpoint" --project my-app` (Adds to the project backlog).
4.  **Execute:** `claude` (The agent reads the backlog and starts working with full context).
5.  **Review Status:** `kb-backlog --open` (View the unified "Jira-style" list of tasks across all projects).

### Technical Requirements
*   **OS:** macOS 13+ (Required for v0.1 due to `launchd` and path dependencies).
*   **Primary Interface:** Claude Code CLI.
*   **Runtime:** Node 18+ and Bun 1.0+.
*   **Optional:** Codex CLI (for cross-agent review) and Telegram (for daily/evening briefings).

## Important Quotes

### On Persistence
> "Vepol is a personal operating environment that turns your local markdown files into a living knowledge base... Both Claude Code and Codex CLI work against the same files — there is no separate 'Claude memory' and 'Codex memory.'"

### On Methodology
> "Any non-trivial change (≥ ~30 min implementation, any design decision, new infrastructure) passes a cycle: Specification → Tests-before-code → Code → Test run → Revisions."

### On Problem Solving (TRIZ)
> "Formulate the contradiction first. What prevents progress? Often it is 'need X and simultaneously not-X'... Seek resolution through separation, not through compromise."

### On License Philosophy
> "Most commercial-friendly licenses (BUSL, Elastic v2, SSPL) have no expiration — they stay restrictive forever. We picked FSL because... two years out, the community owns the code under MIT."