# Vepol — Mind Map

Visual map of the system, generated from Vepol's public docs (README, LICENSE-FUTURE, COMMERCIAL, methodology, hub schema).

GitHub renders the diagram below natively. For an editable JSON tree (use with mind-map tools), see `vepol-mindmap.json` in this folder.

```mermaid
mindmap
  root((Vepol AI Operating Environment))
    Core Concept
      Substance-field model &lpar;TRIZ&rpar;
      User + AI Agents + Knowledge Field
      Karpathy-style LLM Wiki
      Single source of truth
    Architecture & Components
      Universal Core &lpar;scripts/schema&rpar;
      User Overlay &lpar;~/knowledge/&rpar;
      Claude Code &lpar;Primary Orchestrator&rpar;
      Codex &lpar;Secondary Orchestrator&rpar;
      Knowledge-base Hub
    Knowledge Structure
      Local project wiki &lpar;<project>/knowledge/&rpar;
      Global hub categories &lpar;~/knowledge/&rpar;
      Coordination Triad &lpar;backlog, escalations, incidents&rpar;
      Strategy & State &lpar;strategies.md, state.md&rpar;
      Daily logs & Session captures
    Workflow Principles
      Spec-driven development
      TRIZ-grounded design
      Cross-agent plan review
      Knowledge-gap delegation
      Zero split-brain discipline
    Operating Rules
      Immutable raw sources
      No direct editing of other projects
      Mandatory incident recording
      Privacy-aware sync &lpar;Seed as IaC&rpar;
      Russian content / English metadata
    Licensing &lpar;FSL-1.1-MIT&rpar;
      Free for personal/internal use
      Allowed for professional services
      Restricted for competing SaaS
      Automatic MIT conversion after 2 years
    Technical Stack
      macOS 13+ environment
      Node.js & Bun runtimes
      Ripgrep & Git integration
      Obsidian for visual navigation
```

---

*Generated via NotebookLM (Google) from public Vepol documentation. Re-generate with `notebooklm generate mind-map` after major doc changes.*