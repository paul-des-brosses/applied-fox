# VISION — Applied Fox

> *"I don't believe in AI that replaces humans, but in AI as a tool to multiply
> productivity — to accelerate and assist innovation."*

---

## Manifesto

Today's agentic AI tools for project work suffer from two defects that make
them unusable for a significant share of real engineering work.

**The first is the leak of sensitive data.** To function, these tools send
your project's content — schematics, component choices, confidential
constraints, intellectual property — to servers you do not control. That is
unacceptable for defense, industrial R&D, medical, or for anyone building
something they would rather not see copied. And this is not a theoretical
problem: serious R&D teams I have worked with simply ban these tools.

**The second is the distortion of the project.** Today's AIs tend to take
over. They want to optimize, refactor, "improve". The project often gains
efficiency, but at the cost of its personality — at the cost of the unique
vision the creator wanted to give it. When you cede the wheel to an assistant
that is too self-assured, you end up building the assistant's project, not
your own.

Applied Fox is designed **against** these two defects.

Everything runs locally by default. No project data ever leaves your machine
without explicit consent. No "discreet" API call, no "anonymized" telemetry,
no "server-side" cache. The agent that understands your project runs locally
by design. If a cloud mode ever exists, it will be a conscious, documented
choice — never a silent leak.

And the agent never decides for you. It observes the ecosystem, proposes,
justifies — but you validate every modification of the project file. The
system is built to never short-circuit your creator's judgment.

**Tagline**: *The R&D assistant that never leaves your machine, and never decides for you.*

---

## Why the name

Applied Fox is named after Lucius **Fox**, director of the *Applied Sciences
Division* at Wayne Enterprises in Christopher Nolan's Dark Knight trilogy.
Lucius designs the tools, advises technically, and threatens to resign the
day he is asked to build a mass-surveillance system. This project shares
that ethics: an R&D assistant that never leaves your machine, and never
decides for you.

---

## The long-term vision — a sovereign R&D copilot

In the long run, Applied Fox is an R&D copilot any engineering team can
adopt without giving up sovereignty. A system that understands technical
projects in depth, watches their ecosystem permanently, and supports their
decisions without ever substituting itself for the decision-makers.

Concretely, the dream copilot can:

- **Understand projects in depth**: not just read a README, but grasp the
  components, the implicit constraints, the design intentions, the project's
  life phase.
- **Watch the ecosystem permanently**: new components, alternatives, looming
  shortages, regulations that change, emerging technologies that might
  simplify everything.
- **Build its own source map**: not a frozen list, but a living map of
  where quality information lives, ranked by reliability and relevance.
- **Calibrate suggestions to project phase**: no radical redesign proposal
  the day before a delivery, no gold-plating on an exploratory prototype,
  no "what if we changed everything" when the project is contractually frozen.
- **Execute once the decision is validated**: open a GitHub issue, update a
  BOM, order a sample, modify the project file. Always after explicit human
  validation, never before.
- **Run fully locally on the creator's machine**: exportable to any R&D team
  that refuses cloud, functional offline, free indefinitely.

---

## The dream team — six specialized agents

The ultimate system looks like a real human team. Six roles, each with its
specialty, its own memory, and its way of approaching work.

### The Chief

The orchestrator. Knows the project, the creator's state of mind, the
priorities of the moment. Decides who speaks when, who digs into what, and
how conclusions percolate up. Does not do the others' work — ensures it is
done in the right order and with the right focus.

### The Scout

The autonomous watch agent. Scans the ecosystem permanently, but with
guardrails — knows which sources to consult, when information deserves to
be surfaced, and when it is just noise. Its specialized memory refines over
time: it learns what deserves the creator's attention for this specific
project. In the long run, it discovers new sources itself and evaluates them.

### The Integrator

The senior engineer who looks at proposals with a pragmatic eye. For each of
the Scout's findings, says: *is it integrable, at what cost, with what
risks?* Knows the components in place, the interactions, the constraints.
Delivers a feasibility verdict, not a desirability verdict.

### The Judge

The decision-maker. Looks at the integrability verdict, compares to the
real gain for the project's active objectives, and rules: *to consider now,
to note for later, or to reject*. Has a memory of past arbitrations — knows
why a similar proposal was rejected six months ago.

### The Reporter

The translator. Takes what survived the Judge's filter and shapes it for
the creator — one-line synthesis, ranked suggestions, transparency on what
was examined and rejected. Writes clearly what the others reasoned.

### The Historian

The long memory. Records past decisions, their reasons, their trajectory
over time. When a new finding resembles a debate already settled, the
Historian recalls it. Avoids asking the same question every six months,
and lets the creator remember why they picked a certain component two years
ago.

---

## Dream capabilities — beyond the MVP

The long-term vision includes capabilities the MVP will not cover, but which
structure the project's ambitions.

**Distributed adaptive memory.** Each agent has its own memory, enriched in
its domain. The Scout learns quality sources. The Integrator retains the
creator's implicit constraints. The Judge keeps track of arbitrations. All
of it stays local and belongs to the creator.

**Automatic source-credibility scoring.** Tell a field report from a
manufacturer's press release, an independent benchmark from a marketing
test, a community consensus from an isolated opinion. The system learns to
weight its sources.

**Autonomous source discovery and mapping.** The Scout does not wait for a
list — it identifies on its own where information exists for the current
project. Specialized forums, open-source repositories, pre-prints,
regulatory databases.

**Executive mode after validation.** Once the creator has validated a
decision, the agent can execute — modify code, open an issue, order a
component, update a BOM. Always on order, never on initiative.

**Extended watch.** Beyond hardware, the software ecosystem around the
components. Beyond products, relevant research papers. Beyond announcements,
regulatory changes and anticipable shortages.

**Cross-project synergy detection.** For the creator running several projects
in parallel, the agent can suggest pooling a component, a module, an approach.

---

## What this project is built against

It is useful to name explicitly what Applied Fox refuses to be.

**Refusal of data leakage.** Tools that claim to "respect your privacy"
while sending your prompts to their servers do not respect your privacy.
The only acceptable standard is *no transmission*. What the machine sees,
the machine keeps.

**Refusal of distortion.** Tools that rewrite your choices under the cover
of optimization, that impose their patterns, that "know better than you" —
those are tools of dispossession. Applied Fox proposes, never imposes. The
creator remains the creator.

**Refusal of permanent enrollment.** Mandatory monthly subscriptions,
features locked behind paid tiers, models that degrade when the account
lapses. Applied Fox must be able to run indefinitely, for free, on a
personal machine, with no external dependency.

**Refusal of gold-plating.** The classic trap of agentic AI: constantly
suggesting "improvements" that bring nothing to the project's finality.
Applied Fox is calibrated on the declared *active objectives*. Everything
that is not aligned with these objectives is filtered upstream, before
even reaching the creator.

**Refusal of "never shipping".** A project endlessly polished is not a
project, it is a distraction. Applied Fox must help shipping, not defer
shipping under the pretext of continuous optimization.

---

## What this project is, in one sentence

A tool I would want to have for my own projects — one that helps me see
what I cannot see in the ecosystem, without dispossessing me of what I have
to build.

Everything else — learning AI agents, portfolio recognition, possible
usefulness for others — flows from there.
