# STATUS

**Last updated: 2026-07-06**

## Current state

**MVP+ shipped and functional.** Milestones 1 through 8 are delivered, plus
the post-MVP v1.5 iteration (deterministic Judge filters, see
[`docs/evaluations/post_mvp_filtres_juge_2026-05-13.md`](docs/evaluations/post_mvp_filtres_juge_2026-05-13.md)).
The full chain works end-to-end on a local machine: interview → 4-agent
pipeline → HTML report → human validation → controlled integration into the
project file.

## Development status

**On active pause since May 2026.** The tool is stable and usable as-is;
development is paused while other portfolio projects are underway. No open
regression is known at the time of writing.

## What comes next

Post-MVP iterations are specced in [`docs/BACKLOG.md`](docs/BACKLOG.md) (FR),
organised in three levels (impact vs effort), including: the Historien agent
(long-term decision memory), permanent background watch, asyncio
parallelization, opt-in cloud mode, and Octopart supply-chain integration.
Each entry is detailed enough to serve as a direct implementation spec.
