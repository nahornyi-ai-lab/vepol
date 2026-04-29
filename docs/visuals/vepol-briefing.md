# Vepol: The Autonomous AI Operating Environment

## Executive Summary

Vepol is an opinionated, local-first personal operating environment designed to transform passive AI interactions into a proactive partnership. It is explicitly not a "memory tool"; rather, it utilizes a structured markdown knowledge base as infrastructure to support an autonomous agent that grows in agency over time. By layering active orchestrators—primarily Claude Code and Codex—over a unified source of truth, Vepol automates routine tasks, monitors user health and goals, and self-reflects on its own operational strategies.

The system is built on the TRIZ "substance-field" model (*Ve-pol*), where the user and the AI agents are interacting elements bound by a "field" of structured markdown. For developers, Vepol offers a "visible discipline" where every AI action leaves a textual trace, ensuring transparency, auditability, and a compounding level of autonomy that reduces operational overhead the longer the system is utilized.

## The Core Paradigm: Partnership and Agency

Vepol shifts the AI assistant model from a reactive chatbot to a proactive partner. While standard tools focus on session persistence, Vepol focuses on **initiative** and **autonomy progression**.

### The Growth of Autonomy
Vepol is designed to take on an increasing share of the user's routine based on observed interactions and feedback. The progression of this autonomy is modeled over a six-month horizon:

| Timeline | Autonomy Level | Action |
| :--- | :--- | :--- |
| **Day 1** | Assisted Drafting | Vepol drafts routine outputs (e.g., emails); user proofreads and sends. |
| **Week 2** | Classification | Vepol classifies routine inputs; the user only reviews exceptions. |
| **Month 2** | Controlled Execution | Vepol answers typical inquiries in draft folders; user performs spot-checks. |
| **Month 6** | Operational Routine | Half of the user’s operational routine runs autonomously; user focuses on high-level creative work. |

### Proactive Operations
Unlike reactive bots that wait for prompts, Vepol initiates interaction through:
*   **Daily Briefings:** Morning summaries of open tasks, deadlines, and prioritized goals based on the current knowledge state.
*   **Evening Retros:** Summaries of the day's achievements and lessons learned.
*   **Routine Execution:** Background execution of low-judgment tasks marked as `auto: true`.
*   **Health Alignment:** Integration with health data (Garmin, Apple Health) to adjust workload intensity based on sleep quality or stress levels.

---

## Visible Discipline: The Structured Knowledge Field

Vepol’s "Visible Discipline" ensures that AI operations are not black-box events. Every decision, lesson, and task is recorded in a human-readable, auditable markdown format.

### The Knowledge Base Schema
The system utilizes a mandatory triad of coordination files in every project’s `knowledge/` directory:

| File | Primary Author | Purpose |
| :--- | :--- | :--- |
| `backlog.md` | Hub or User | Tasks to be executed; includes status (`open`, `in-progress`, `done`) and metadata. |
| `escalations.md` | Project Agent | Items where the AI requires human judgment, resources, or cross-project coordination. |
| `incidents.md` | Project Agent | Chronological log of errors, root causes, fixes, and newly implemented "Automated Guards." |
| `strategies.md` | Project Agent | Active hypotheses about how the agent can improve; re-evaluated weekly or upon project pivots. |
| `log.md` | Auto-compiler | A grep-friendly chronological log of every session and significant event. |
| `state.md` | Project Agent | A current snapshot of the project’s status. |

### Self-Reflection and Strategy
The `strategies.md` file is a critical differentiator. Vepol does not just store data; it interprets it. Once a week, the system re-reads its own logs, checks which assumptions held true, and rewrites its strategy file. This allows the AI to adjust its help based on identified patterns, such as recognizing when a user is more productive or when specific tasks tend to stall.

---

## Operational Frameworks and Quality Control

Vepol embeds rigorous engineering methodologies into the AI’s workflow to ensure high-quality output and architectural integrity.

### Parallel Orchestration and Cross-Agent Review
Vepol treats Claude Code and Codex as interchangeable interfaces to the same knowledge base. To prevent "split-brain" scenarios, a strict protocol is enforced:
*   **Single Source of Truth:** Both agents read and write to the same `~/knowledge/` hub and project-specific folders.
*   **Cross-Agent Review:** Any non-trivial implementation (≥30 minutes or architectural changes) requires a plan review by the *other* agent. A plan written by Claude Code must be approved or critiqued by Codex before implementation begins.
*   **Knowledge-Gap Delegation:** If one agent lacks specific knowledge (e.g., an external API), it must delegate the search to the other agent and require the result be written to the permanent knowledge base (`sources/` or `concepts/`) rather than just the chat history.

### Spec-Driven and TRIZ-Grounded Design
*   **Spec-Driven Workflow:** For non-trivial work, the agent must follow a cycle: Specification -> Tests-before-code (Red) -> Code implementation -> Test execution (Green) -> Revision.
*   **TRIZ Optics:** Design solutions are filtered through the Theory of Inventive Problem Solving. Agents are instructed to formulate contradictions (e.g., "fast and reliable") and seek "Ideal Final Results" through separation in space, time, condition, or structure, rather than settling for compromises.

---

## Technical Architecture and Implementation

### Environment and Dependencies
Vepol is a local operating environment, currently optimized for macOS 13+.
*   **Primary Orchestrator:** Claude Code CLI.
*   **Secondary Orchestrator:** Codex CLI (recommended for cross-review).
*   **Runtime:** Node 18+ and Bun 1.0+ for performance scripts.
*   **Storage:** Plain markdown files, searchable via CLI (`kb-search`) or visualizable via Obsidian.

### Session Auto-Capture
Every Claude Code session is captured via the `claude-memory-compiler`. Upon session end:
1.  **Transcript Parsing:** Decisions, lessons, action items, and context shifts are extracted.
2.  **Daily Log:** The extraction is appended to `<project>/knowledge/daily/YYYY-MM-DD.md`.
3.  **Project Log:** A one-line summary with a cross-reference link is added to `log.md`.
4.  **Lifting:** Periodically, Vepol "lifts" raw data from daily logs into permanent categories like `concepts/`, `people/`, or `solutions/`.

---

## Important Quotes and Context

> **"Memory is just infrastructure."**
*Context: Defining the core philosophy that Vepol is an agentic partner, not a storage tool.*

> **"If after your session the second orchestrator cannot understand what you did and what changed from the files, then the memory is updated insufficiently."**
*Context: The practical rule for maintaining the "Zero Split-Brain" policy between Claude and Codex.*

> **"Vepol's autonomy compounds over time... the progression is real because Vepol watches what you actually edited vs accepted."**
*Context: Explaining how the AI monitors user behavior to adjust its own level of initiative for specific task types.*

> **"Every meaningful action leaves a textual trace in your knowledge base that you can read, edit, override, or grep six months later."**
*Context: Contrasting Vepol's transparent "Visible Discipline" with the black-box nature of standard AI assistants.*

---

## Actionable Insights for Developers

*   **Auditability as Trust:** Adopting Vepol provides a "Paper Trail" for AI actions. In a professional setting, this allows developers to audit AI-generated architectural decisions months after they were made by checking the `log.md` and `strategies.md` files.
*   **Context Loss Prevention:** Standard AI chatbots "start blank" every session. Vepol’s `SessionStart` hooks automatically feed the project’s `README.md`, `state.md`, and recent logs into the agent, eliminating the need for manual context re-provisioning.
*   **Incremental Automation:** Use the `auto: true` flag in `backlog.md` for low-judgment tasks (e.g., summarizing meeting notes). This allows Vepol to prove its reliability on minor tasks before the user grants it more significant autonomy.
*   **Licensing Awareness:** Vepol uses the FSL-1.1-MIT license. It is free for personal use, internal company use, and consulting. However, developers cannot use it to build a competing hosted SaaS until the 2-year MIT conversion period for each release has passed.