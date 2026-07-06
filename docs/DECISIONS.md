# DECISIONS — Structured design-decision log

This document records all MVP design decisions along with their justifications. For each decision: context, options considered, decision, rationale, accepted trade-off.

Decisions are grouped by theme. The first four sections cover the **non-negotiable fundamental constraints** — what is frozen for the life of the project. The following sections cover the MVP implementation choices.

---

## 1. Design — Everything possible locally

### Context
The project exists as a reaction to current agentic tools that exfiltrate project data to third-party servers. This exfiltration is a deal-breaker for sensitive projects (critical-site security work, R&D, defense, medical, sensitive industry).

### Options considered
- **Option A** — Everything local, by design, with no possible exception.
- **Option B** — Local by default, opt-in switch to a cloud API with explicit user consent.
- **Option C** — Cloud by default, opt-in local mode for advanced users.

### Decision
**Option B with per-module asymmetry**:
- The **Interview** module (which ingests the project's intimate content) is local **exclusively**, in all versions. Non-negotiable fundamental constraint: the Interview never leaves the machine. No API mode is planned for this module.
- The watch modules (Éclaireur / Scout, Intégrateur / Integrator, Juge / Judge, Rapporteur / Reporter) are local by default in the MVP, and will be able to switch to a cloud API in V2 (`hybrid` mode) with explicit user consent.

### Rationale
The most sensitive data is the project sheet itself — components, constraints, design intentions. This data flows through the Interview and has no reason to leave the machine. The watch agents, on the other hand, mostly handle public information (component specs, Reddit posts, datasheets), and their prompts contain the project `.md`, which poses a lesser but real risk — hence the choice of local by default in the MVP, and cloud opt-in in V2.

### Accepted trade-off
- Lower raw performance than a cloud Claude Opus or GPT-5.
- Weaker first-pass reasoning quality with a local 14B than with a frontier model.
- These trade-offs are offset by the sovereignty guarantee and by the fast pace of improvement of open-source local models.

---

## 2. Design — Hot-swappable LLM

### Context
The model ecosystem evolves quickly. Today's reference model may be surpassed in three months. The system must be able to switch between models without a refactor.

### Options considered
- **Option A** — Code coupled to a single provider (Ollama in the MVP), to be refactored later.
- **Option B** — Provider abstraction from the MVP onward, structurally multi-provider, but a single option tested and exposed.
- **Option C** — Multi-provider exposed from the MVP, several options documented and maintained.

### Decision
**Option B**. The code is structured around a `get_llm(role, config)` function that can route to any provider supported by LangChain (Ollama, Anthropic, OpenAI, Mistral, Groq), but the MVP exposes and documents only the local Ollama mode. The other routes exist in the code but are neither tested nor documented as frontline options.

### Rationale
- Low initial implementation cost (LangChain already provides the abstraction).
- Allows switching the local model in under 5 minutes via a single config line (an explicit validation test in the roadmap).
- Avoids the classic trap of an emergency refactor when a better model appears.
- MVP discipline preserved: we do not maintain three providers in parallel in the MVP, we expose only one mode.

### Accepted trade-off
- One extra abstraction layer from the start, even though only one route is used.
- Slight complexity in model management: multi-provider support must be kept in mind even for tests that will only ever use Ollama.

---

## 3. Design — Hardware adaptable

### Context
Target users have very disparate hardware configurations — from a powerful workstation (dedicated GPU, large RAM) to a modest ultraportable (integrated GPU, limited RAM). The project must run across this entire range without requiring refactoring.

### Options considered
- **Option A** — A single target model, fixed configuration.
- **Option B** — Three predefined machine profiles (`small`, `medium`, `large`), with graceful degradation.
- **Option C** — Automatic resource detection and dynamic profile selection.

### Decision
**Option B** with three profiles:
- `small`: 7B Q4 model (modest laptop, ≥ 16 GB RAM, GPU optional).
- `medium`: 14B Q4 model (decent machine, ≥ 32 GB RAM or 8 GB+ GPU).
- `large`: 32B Q4 model (powerful machine, 16 GB+ GPU or 64 GB RAM).

The profile is set in the config. The user can override the exact model (e.g. to test a specific Mistral Small 3).

### Rationale
- Three profiles cover the realistic range of student/engineer machines without excessive complexity.
- The minimum supported configuration (7B Q4 on 16 GB RAM, GPU optional) remains in line with what Unity or SolidWorks run on a decent student laptop — thus consistent with the target audience.
- Automatic detection (Option C) would add a dependency and a failure case for marginal gain — a user capable of installing Ollama is capable of choosing a profile.

### Accepted trade-off
- The user must choose their profile manually (but the `small` default works everywhere).
- The chosen profile may be suboptimal if the user does not know their machine — mitigated by a clear documentation page.

---

## 4. Design — Strict `.md` format

### Context
All downstream agents need a reliable, usable representation of the project. This representation must be at once human-readable (so it can be edited manually), structured (so it can be validated), versionable (git-friendly), and self-contained (readable without the conversation's context).

### Options considered
- **Option A** — Pure JSON, validatable but not very human-readable.
- **Option B** — YAML, a balance between readability and structure.
- **Option C** — Free-form Markdown, readable but not validatable.
- **Option D** — Strict structured Markdown, validatable by parsers + Pydantic.

### Decision
**Option D** — Two-tier structured Markdown:
- Fixed mandatory sections (Identité, Description, Objectifs actifs, Prochain rendu, Composants, Stack software, Interactions, Contraintes non négociables, Changements).
- Adaptive **Contraintes** section: free-form subsections (Performance, Énergie, Connectivité, Environnementales, Budget, etc.), each criterion expressed either as a defined value, or as `N/A`, or as `TBD` with a justification.

The full spec lives in [`MD_SCHEMA.md`](MD_SCHEMA.md).

### Rationale

This is a deliberately harder choice than JSON, for a precise reason: a project sheet has two lives. It is read by machines (the agents), but it is also read, corrected, and committed by a human outside the tool. JSON handles the first life well, the second one less so.

**Readable git diffs.** A `git diff` on a `.md` sheet after an integration run is immediately understandable ("the BME680 component was added, objective X was updated"). On JSON, it is quote-and-comma noise.

**Self-documenting format.** You open a sheet without knowing the schema and you understand what you are reading. A Markdown table with `| BME680 | capteur T/H | validé | critique |` is more natural to read than a JSON object with the same keys.

**Two correction paths, not one.** If a sheet is wrong or incomplete, the user can either edit it directly in their text editor, or go back through `applied-fox interview update`, which walks through each field proposing the current value. This second path is particularly useful after a run that modified the sheet: you can verify field by field that the integration is correct, without touching the raw file.

**A real engineering problem.** Building a format that is both hand-editable and machine-validatable is a genuine problem. The custom parser (`src/validation/structural.py`) is the solution to it — not a workaround.

**What we do not claim.** That JSON would be hard to edit by hand (false, VSCode handles it fine). That LLMs understand Markdown better than JSON in context (unmeasured). These arguments are not part of the rationale.

### Accepted trade-off
- More code to write for parsing/validation than for pure JSON.
- The parser has known fragility points (accents in section titles, spacing around the `:` in KV lists, interactions silently ignored if badly formatted) — mitigated by the normalization in `_norm()` and explicit error messages.

---

## 5. Symmetric 3-layer validation

### Context
The project `.md` is the system's central artifact. If the sheet is inconsistent or incomplete, all downstream agents produce noise. Simple validation is not enough — a `.md` can be structurally valid yet semantically wrong.

### Options considered
- **Option A** — Pydantic validation only.
- **Option B** — Pydantic validation + human review.
- **Option C** — Three layers: deterministic rules, transmission test by a third-party LLM, human validation.

### Decision
**Option C**, applied *symmetrically* to the initial creation of the `.md` AND to any subsequent modification (integrate mode after a suggestion is validated).

- **Layer 1 — Deterministic validation** (Pydantic + Markdown parsers):
  - Level 1: mandatory sections present.
  - Level 2: correct internal structure (table columns, correct enumerated values, date formats).
  - Level 3: internal semantic consistency (components referenced in Interactions exist in the Composants table, dates consistent with the phase, etc.).
- **Layer 2 — LLM transmission test**: an LLM reads the `.md` *without* the conversation's context and produces a plain-language summary of what it understands about the project. This layer tests whether the `.md` is self-contained — the other downstream agents will only ever have this file.
- **Layer 3 — Explicit final human validation** by the user.

If a layer fails, we do not move on to the next.

### Rationale
- Layer 1 catches pure structural errors (cheap).
- Layer 2 catches semantic errors that Pydantic cannot see (a `.md` that mentions a sensor without stating its function passes Pydantic but fails the transmission test).
- Layer 3 keeps the human as the last line of defense — aligned with the principle "never decides in your place".
- Creation/modification symmetry: a `.md` modified after a validated suggestion must pass the same checks as a fresh `.md`, otherwise consistency debt accumulates with each cycle.

### Accepted trade-off
- Additional cost on every modification (layer 2 requires a dedicated LLM call).
- User friction if a simple modification triggers all three layers — accepted: the project sheet is the critical artifact, its quality takes precedence over smoothness.

---

## 6. LangGraph rather than CrewAI, smolagents, or custom Python

### Context
The system is multi-agent. We must choose an orchestration framework or write our own.

### Options considered
- **Option A** — LangGraph (LangChain).
- **Option B** — CrewAI.
- **Option C** — smolagents (Hugging Face).
- **Option D** — Custom orchestration in pure Python.

### Decision
**Option A — LangGraph.**

### Rationale
- De facto standard in 2026 in the serious agentic ecosystem.
- Native shared-state management (`TechWatchState`), which fits the Éclaireur → Intégrateur → Juge → Rapporteur flow perfectly.
- Built-in run persistence, useful for intermediate artifacts (`runs/[timestamp]_[projet]/`).
- Nearly free provider abstraction via LangChain (direct link with the hot-swap decision).
- Conditional branching (a non-integrable finding is short-circuited before the Juge) is idiomatic.
- CrewAI: geared toward "agents talking to each other", too conversational for our structured flow. smolagents: too minimal, lacks state management. Custom: would rebuild LangGraph, but worse.

### Accepted trade-off
- Dependency on a fast-moving framework (the LangGraph API has changed several times).
- Initial learning curve — mitigated by the portfolio value (LangGraph is what recruiters recognize).

---

## 7. Four LLM agents + orchestrator graph, not six agents

### Context
The long-term vision calls for six agents (Chef, Éclaireur, Intégrateur, Juge, Rapporteur, Historien). Should the MVP already implement all of them?

### Options considered
- **Option A** — Implement all six agents in the MVP.
- **Option B** — Implement four LLM agents + delegate the Chef's role to the LangGraph graph + defer the Historien.
- **Option C** — Merge everything into a single monolithic agent for the MVP.

### Decision
**Option B**. In the MVP: four LLM agents (Éclaireur, Intégrateur, Juge, Rapporteur) + the LangGraph graph taking on the Chef's role + the Historien pushed to the backlog.

### Rationale
- The Chef's role in the MVP is purely orchestrational (who speaks when, in what order). LangGraph fulfills this natively, at no LLM cost.
- The Historien implies structured persistent long-term memory — a complex feature in itself, deserving a dedicated post-MVP milestone.
- Four LLM agents are enough to validate the architecture, prove the value, and generate a useful report.
- An LLM Chef can be added in V2 if the need emerges (e.g. a project where dynamic task prioritization becomes critical).

### Accepted trade-off
- No "real" long-term memory in the MVP — the "Changements" section of the `.md` plays this role minimally, which is sufficient for the first cycles.
- Coordination fixed by the graph's code, less flexible than an LLM Chef — accepted for the MVP.

---

## 8. MVP sources — Reddit, GitHub, RSS — no scraping

### Context
We must choose where the Éclaireur goes looking for information. The ecosystem offers dozens of possible sources; the MVP must cover a representative diversity without spreading thin.

### Options considered
- **Option A** — A single well-integrated source (e.g. Reddit).
- **Option B** — Three representative sources, three different integration patterns.
- **Option C** — Ten+ sources, maximum coverage.
- **Option D** — Include web scraping for sources without an API.

### Decision
**Option B**. Three sources, three patterns:
1. **Reddit (public endpoints)** — community feedback (free, generous quota).
2. **GitHub API** — open-source ecosystem around the components (token via `GITHUB_TOKEN`).
3. **Tech press RSS** — Hackaday, CNX-Software, Adafruit Blog, Electronics Weekly, EE Times for manufacturer announcements.

**No scraping in the MVP.**

Octopart (Nexar API) had initially been selected as a 4th source but was deferred to V2 (see [`BACKLOG.md`](BACKLOG.md) Level 2). Rationale: its GraphQL integration with OAuth adds a 4th integration pattern that the MVP does not justify — the 3 existing patterns (REST without auth, REST with token, RSS parsing) are enough to validate the extensible architecture. The specialized supply-chain source will join V2 once the total cost (auth + tests + maintenance) is justified by proven usage.

### Rationale
- Three sources cover three complementary angles: field feedback (Reddit), software ecosystem (GitHub), official announcements (RSS).
- Each source uses a different integration pattern (public REST, REST with token, RSS parsing) — demonstrates the extensible architecture without overloading it.
- No scraping: a legally gray area (ToS often ambiguous), painful maintenance (sites change), bad portfolio signal (a serious project respects the platforms' terms of use).
- A single source (Option A) would not validate the multi-source architecture. Ten sources (Option C) would drown the MVP in maintenance.

### Accepted trade-off
- No official supply-chain source in the MVP (prices, availability, distributors) — the user compensates by reading the component pages of suggestions by hand. To be solved in V2 via Octopart.
- Incomplete coverage (no Hackster, no direct datasheet databases, no arXiv papers) — accepted, these sources join the backlog.
- Dependency on third-party APIs — mitigated by caching and graceful degradation (if Reddit is down, the report goes out without Reddit).

---

## 9. Incremental mode from the MVP onward — not in the backlog

### Context
Without an incremental mode, each agent run re-presents the same findings as the previous run. The user loses trust immediately. This is a major signal-quality problem.

### Options considered
- **Option A** — Incremental mode in the post-MVP backlog.
- **Option B** — Incremental mode from the MVP onward, simple: hashes of already-presented findings stored on disk.

### Decision
**Option B**. Ideation block 9 explicitly moved this feature from the backlog into the MVP. Implementation: `~/.applied-fox/state/[projet]_seen.json` contains the hashes of already-presented findings; at launch, the Éclaireur filters.

### Rationale
- Without this feature, the second-run user experience is disastrous — and there is generally no third run.
- Very low implementation cost (one JSON file, one hash function).
- Strong relevance: aligns the system with realistic usage (running the watch every week, not just once).

### Accepted trade-off
- The hash must be stable (`nom_composant + titre + source`) — if the source changes the title slightly, the finding is re-presented. Acceptable in the MVP, to be refined in V2 (semantic similarity).

---

## 10. Deterministic filtering upstream of the LLM

### Context
Without upstream filtering, the Éclaireur sends the LLM dozens of findings, most of which are obviously irrelevant (wrong component, too old, negligible community score). This costs tokens, slows the pipeline, and drowns the signal.

### Options considered
- **Option A** — Send everything to the LLM, let it filter.
- **Option B** — Deterministic upstream filter (hard rules), only relevant material reaches the LLM.

### Decision
**Option B — non-negotiable rule.**

Criteria of the deterministic filter:
- Alignment with the components declared in the sheet.
- Alignment with the declared active objectives (see next decision).
- Freshness (no findings older than N months, depending on the source).
- Minimum community score (for Reddit: score > threshold, for GitHub: stars > threshold).

### Rationale
- Eliminates 60-70% of the noise before the LLM call.
- Significant token savings — critical for the MVP's viability locally (a 14B Q4 with a saturated context becomes slow quickly).
- Improves signal quality: the LLM works on pre-sorted material, its output is more reliable.
- The deterministic filter is unit-testable — no LLM needed to validate that it does its job.

### Accepted trade-off
- Theoretical risk of filtering out a relevant finding that does not match the criteria — mitigated by keeping the filtered findings in `01_eclaireur_sources.json` for audit.
- Threshold configuration to be iterated over time — not an MVP blocker.

---

## 11. Teleological alignment with active objectives

### Context
A major risk of watch AIs: gold-plating. The agent constantly suggests "improvements" that contribute nothing to the project's purpose, because it optimizes on abstract metrics (perf, price, modernity) without checking whether those metrics matter for *this project at this moment*.

### Options considered
- **Option A** — The agent evaluates findings on universal metrics.
- **Option B** — The agent evaluates findings strictly against the active objectives declared in the project sheet.

### Decision
**Option B — fundamental design rule.**

A finding not aligned with the declared active objectives is rejected automatically, in two places:
1. In the **Éclaireur's system prompt** (explicit instruction).
2. In the **deterministic filter upstream of the LLM** (hard rule).

### Rationale
- Aligns the system with the project's philosophy: help ship, not postpone under the guise of optimization.
- Avoids the classic trap of "intelligent" tools that produce noise disguised as technical relevance.
- Forces the user to make their active objectives explicit in the sheet — secondary benefit: they think it through themselves.
- Dual enforcement (prompt + deterministic filter) guarantees robustness even if the LLM goes off the rails.

### Accepted trade-off
- A discovery that would fall outside the scope of the active objectives (but could reshape those objectives) will be filtered out. Conscious and accepted: if a finding is strong enough that it should reshape the objectives, it will resurface at the next run after the user has adjusted the sheet.

---

## 12. No feedback section exploited in the MVP

### Context
A tempting idea: let the user comment on each suggestion ("too expensive", "already tried", "not relevant") so that the Juge learns. But this feature carries risks.

### Options considered
- **Option A** — Feedback section exploited by the Juge from the MVP onward.
- **Option B** — Feedback section displayed but not exploited (cosmetic).
- **Option C** — No feedback section at all in the MVP.

### Decision
**Option C.**

### Rationale
- **Cumulative risks unacceptable in the MVP**:
  - *Context pollution* — feedback accumulated over many runs grows the prompt without control, degrading local LLM performance.
  - *Uncontrollable cascade* — a piece of feedback misinterpreted by the Juge influences all subsequent runs, and it becomes hard to trace a drift back to its cause.
  - *Difficult debugging* — distinguishing a bad suggestion caused by a bad prompt from a bad suggestion caused by earlier, poorly calibrated feedback is very costly.
- No dead functionality (Option B) — displaying something useless degrades the perception of quality.
- Backlog: the feature will come back with a clean design (the Historien will carry it).

### Accepted trade-off
- The user cannot "teach" the system their preferences in the MVP. Mitigated by: they can edit the project sheet, which remains the source of truth.

---

## 13. Modifying the `.md` via the Interviewer in "integrate" mode

### Context
When a suggestion is validated by the user, the `.md` must be modified. Who does it? A new dedicated module? The Rapporteur? The Interviewer?

### Options considered
- **Option A** — Dedicated `.md` modification module.
- **Option B** — The Rapporteur modifies it directly.
- **Option C** — The Interviewer in "integrate suggestion" mode receives the `ValidatedSuggestion` object and modifies the `.md`.

### Decision
**Option C.**

### Rationale
- **Architectural elegance**: the Interviewer is already the only module that knows how to build a valid `.md` passing the three validation layers. Reusing this module guarantees that any modification respects the same invariants as the initial creation.
- **Single point of validation**: one single place in the code validates a `.md`. No duplication, no possible divergence between "creation" and "modification".
- **No duplication** of the `.md` generation prompts.
- **Narrative consistency**: the Interviewer already converses with the user; it is the right agent to clarify the `open_questions` of a `ValidatedSuggestion`.

### Accepted trade-off
- The Interviewer becomes a two-mode module (`create` + `integrate`) — accepted, it is a clean logical decoupling.
- The cost of one extra LLM call per modification (validation layer 2 included) — accepted, the quality of the project sheet takes precedence.

---

## 14. Local mode alone exposed in the MVP, multi-provider in V2

### Context
The code is structurally hot-swappable (see decision 2). Should several providers be exposed from the MVP, or a single one?

### Options considered
- **Option A** — A single exposed and documented mode (`local` via Ollama).
- **Option B** — Two exposed modes (`local`, `hybrid`).

### Decision
**Option A** in the MVP. V2 will add **a single** additional mode:
- `hybrid`: Interview always local (non-negotiable fundamental constraint, see §1) + watch agents on a cloud API with explicit user consent.

A `full_api` mode (Interview via API) was considered but explicitly ruled out: it would contradict fundamental constraint no. 1 ("Interview exclusively local"). The Interview ingests the project's most sensitive data and will never leave the machine.

### Rationale
- **MVP discipline**: maintaining, testing, and documenting three modes in the MVP would triple the workload. We prefer one perfect mode to three mediocre ones.
- **Consistency with the project's identity**: the core pitch is local. Launching the MVP with "and there's also an API mode" dilutes the message.
- **The code stays ready**: the `get_llm()` function already accepts any provider; the V2 transition will mostly be documentation and tests.
- Security: API keys (V2) will be referenced via environment variables only, never hard-coded in the config.

### Accepted trade-off
- Users who would want to test with a Claude or a GPT-5 from the MVP will have to patch the code — accepted, they are not the MVP's target users.

---

## 15. Rich TUI rather than a web app in the MVP

### Context
How does the user interact with the agent? Terminal, web, desktop app?

### Options considered
- **Option A** — TUI with Rich (interactive terminal).
- **Option B** — TUI with Textual (full-screen terminal).
- **Option C** — Web app (Flask/FastAPI + frontend).
- **Option D** — Native desktop app.

### Decision
**Option A — Rich TUI.**

The final report is displayed via an **automatic opening as rendered HTML in the browser** (conversion via `markdown2` or `mistune` + a simple HTML template), in parallel with the TUI which prompts `Valider rapport (Y/N)`.

### Rationale
- **Low implementation cost**: Rich is already the standard Python tool for this kind of interaction.
- **Consistency with the target audience**: engineers, developers, technical students — all used to the terminal.
- **No web stack to maintain**: a web project adds a server, routes, a frontend, CORS — a whole layer the MVP does not need to carry.
- **Report as HTML in the browser**: a better reading experience for the final report, without imposing a web UI for everything else.
- Textual (Option B): oversized for the need, adds a heavy dependency.
- Web app (Option C): will go to the backlog, but not before the core is solid.

### Accepted trade-off
- No rich visual experience during the interview itself — accepted, content takes precedence over form at this stage.
- Not accessible to non-technical users — accepted, they are not the MVP audience.

---

## 16. Report as HTML in the browser + TUI validation

### Context
The final report is the artifact the user consults. How should it be presented so that it is both pleasant to read and usable for validation?

### Options considered
- **Option A** — Report as raw Markdown in the terminal.
- **Option B** — Report rendered as HTML, opened in the browser, validation in the terminal.
- **Option C** — Everything in the Rich TUI (Markdown rendering + validation).

### Decision
**Option B.**

Pipeline: the Rapporteur produces Markdown → conversion to HTML via `markdown2` or `mistune` → automatic opening in the default browser → in parallel, the TUI prompts `Valider rapport (Y/N)`.

If `Y`: launches the suggestion-by-suggestion validation sequence via the Interviewer in "integrate" mode.

### Rationale
- The final report deserves a polished presentation (narrative link with the portfolio storytelling).
- The user can scroll comfortably in their browser while they decide.
- The terminal remains the place for validation and interaction — a clean read/act separation.

### Accepted trade-off
- Dependency on the default browser — mitigated by a raw Markdown fallback if the opening fails.
- Slight delay at opening — negligible.

---

## 17. Inter-agent communication via Pydantic JSON + retry

### Context
The agents exchange structured data (Findings, Verdicts, Suggestions). Format?

### Options considered
- **Option A** — Free-form Markdown between agents.
- **Option B** — JSON validated by Pydantic, retry on parsing error.
- **Option C** — The LLM's native function calling.

### Decision
**Option B.** Free-form Markdown is only used for the final user-facing output (the report).

### Rationale
- Robustness: Pydantic + retry catches structural hallucinations.
- Auditability: every intermediate artifact is serialized cleanly into `runs/[timestamp]_[projet]/`.
- Function calling (Option C) varies by provider — incompatible with the hot-swap goal.
- Free-form Markdown (Option A) is too fragile for internal orchestration.

### Accepted trade-off
- The cost of an occasional retry when the LLM produces malformed JSON — the MVP target is < 5% retries.

---

## 18. Self-hosted LangFuse as a dev tool (optional)

### Context
During development, we want to be able to inspect LLM traces (prompts, latencies, tokens, errors) for debugging.

### Options considered
- **Option A** — Custom Python logs.
- **Option B** — Hosted LangSmith (cloud).
- **Option C** — Self-hosted LangFuse (Docker, local).

### Decision
**Option C** recommended for development, **Option B** acceptable for personal use only (free up to a certain volume).

The end user needs neither — it is strictly a dev tool, optional.

### Rationale
- Consistency with the local philosophy: self-hosted LangFuse = no trace leakage.
- Free, Docker compose in a few minutes.
- LangSmith is acceptable for personal use if the user prefers cloud convenience — their personal project does not have the sensitivity of a client R&D project.

### Accepted trade-off
- Docker setup for LangFuse — accepted, it is a one-time step.

---

## 19. Interview mechanics: assisted enrichment rather than strict validator

### Context
The initial design of the Interview module planned for an LLM acting as a strict validator: for each free-text answer, the LLM returned a binary `OK / REJECT` verdict and looped through up to two clarification follow-ups on rejection. This design was tested and raised two UX problems:
- The user experienced the interview as an exam ("your answer is rejected, try again").
- On questions where the initial answer was technically valid but simply short, the LLM generated superfluous follow-ups.

### Options considered
- **Option A** — Keep the strict validator, tune the prompts to reduce false rejections.
- **Option B** — Replace it with an enrichment system: the answer is accepted outright, the LLM proposes **a single** optional clarifying question with a `skip` keyword to keep the initial answer.
- **Option C** — Remove all LLM assistance in interview mode, keep only the regex pre-checks.

### Decision
**Option B**.

The initial answer is always accepted. The LLM is repositioned as an assistant, not a judge — it proposes a clarification, and the user can type `skip` to move on. On critical sections (Description, Objectifs, Contraintes), `skip` is blocked only if the initial answer is manifestly insufficient (< 4 words AND no technical indicator).

### Rationale
- **Philosophical consistency**: "the agent never decides in your place" implies that the LLM must not reject human answers, only suggest.
- **Signal preservation**: the deterministic regex pre-checks (numbers+units, known technical acronyms) capture ~80% of the obvious cases without an LLM call. The LLM only steps in on answers that are verbally long but technically empty.
- **Blocked skip = targeted guardrail**: prevents a user from generating a project sheet unusable by the watch pipeline (empty description → 0 aligned findings).
- **Downstream safety net**: the post-questionnaire recap+correction (see Milestone 1bis in `ROADMAP_MVP.md`) allows going back to correct any field before the final save.

### Accepted trade-off
- Slightly lower average quality for users determined to minimize their effort (repeated skip → thinner sheet).
- Mitigation: final recap + blocked skip on critical sections + downstream teleological alignment that rejects non-aligned findings.

---

## 20. Removal of the "profile small/medium/large" abstraction and per-role model selection

### Context
The initial design (see original CLAUDE.md rule 3) planned for three hardware profiles: `small` (7B Q4 everywhere), `medium` (14B Q4), `large` (32B Q4). Each profile mapped ONE model to ALL agents. The Milestone 8 evaluation (see `docs/evaluations/modeles_perf_2026-05-13.md`) showed this mapping is bad: a Juge needs more intelligence than a Rapporteur, regardless of the hardware.

### Measurements that forced this decision
- On an RTX 3070 8 GB with `mistral:7b` everywhere: 0% rejections on the Juge side → 71% non-aligned findings in the final report.
- On an RTX 3070 8 GB with `mistral:7b` everywhere + `qwen3:8B` for the Juge only: ~50% justified rejections, alignment rises to 66-82% depending on the project.
- `qwen2.5:14b`, initially planned for the "medium" profile, is obsolete as of May 2026 — `qwen3:8B` (newer and smaller) outperforms it on LLM-as-a-judge (see CodeJudgeBench).
- `qwen3.5:9b` does not fit in 8 GB VRAM (26% CPU offload) — thus unusable on the reference configuration.

### Options considered
- **Option A** — Keep the 3 profiles, update the model list every 3 months.
- **Option B** — Remove the profiles, keep the `get_llm("role", config)` hot-swap with per-role mapping in `config.yaml`.
- **Option C** — Hardcode a single mapping, without hot-swap.

### Decision
**Option B**.

Removal of the `profile:` key in `config.yaml` and of `_PROFILE_MODELS` in `src/llm/__init__.py`. Replaced by a per-role mapping (`_DEFAULT_MODELS`) with an optional override via `ollama.models.<role>` in `config.yaml`. Creation of `docs/HARDWARE.md`, which documents the variants per hardware ("if you have ≥ 12 GB VRAM, upgrade the Juge to `qwen3:14b`").

### Rationale
- **Field measurement**: 4 Milestone 8 iterations showed that judgment quality (Juge) is what caps the system. Optimize that link first, keep the rest light.
- **Maintenance**: maintaining 3 profiles × 5 roles = 15 cells to validate at each model release, versus 5 (1 per role). The hardware-based abstraction infers the optimal model poorly.
- **Honesty with the user**: an abstract "medium" profile makes a vague promise. A named mapping (`juge: qwen3:8B`) is testable and reproducible.
- **Token economy**: pay the heavy latency (qwen3:8B = 14 s/call) only on the one agent that benefits from it. Mistral 7B stays everywhere else (6.5 s/call).

### Accepted trade-off
- Slight extra complexity in `config.yaml` (4 lines instead of a single `profile: small`).
- Mitigated by `docs/HARDWARE.md`, which pre-digests the common variants.

---

## Summary — structuring decisions on one page

| # | Decision | Nature |
|---|----------|-----------|
| 1 | Everything local by default (Interview local in the MVP, cloud opt-in in V2 by explicit choice) | Non-negotiable in the MVP |
| 2 | Hot-swappable LLM via the `get_llm()` abstraction | Non-negotiable |
| 3 | ~~Three hardware profiles~~ → Per-role mapping (see §20) | Architecture |
| 4 | Strict two-tier `.md` format | Non-negotiable |
| 5 | Symmetric 3-layer validation for creation / modification | Architecture |
| 6 | LangGraph as the orchestration framework | Architecture |
| 7 | 4 LLM agents + graph as Chef + Historien in the backlog | Architecture |
| 8 | 4 MVP sources, no scraping | Scope |
| 9 | Incremental mode from the MVP onward | Scope |
| 10 | Deterministic filtering upstream of the LLM | Architecture |
| 11 | Teleological alignment with active objectives | Fundamental design |
| 12 | No feedback section exploited in the MVP | Scope |
| 13 | `.md` modification via the Interviewer in integrate mode | Architecture |
| 14 | Local mode alone exposed in the MVP | Scope |
| 15 | Rich TUI + HTML report in the browser | UX |
| 16 | Report as HTML in the browser + TUI validation | UX |
| 17 | Pydantic JSON communication + retry | Architecture |
| 18 | Optional self-hosted LangFuse | Dev tool |
| 19 | Assisted enrichment rather than strict validator in the interview | UX / Design |
| 20 | Profiles removed, per-role model mapping (qwen3:8B for the Juge) | Architecture |
