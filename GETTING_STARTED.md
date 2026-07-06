# Getting Started — Applied Fox

> Installation and first run. Allow 20-30 min (including LLM model download).

## Prerequisites

| Tool | Version | Link |
|-------|---------|------|
| Python | ≥ 3.11 | https://www.python.org |
| Ollama | latest stable | https://ollama.com/download |
| Git | any recent version | https://git-scm.com |

## Installation

```bash
# 1. Clone the repo
git clone <repo-url>
cd applied-fox

# 2. Auto-setup: venv + dependencies + Ollama check + model download
bash setup.sh

# 3. Activate the venv
source .venv/bin/activate          # Linux / macOS / WSL2
.venv\Scripts\activate             # Windows PowerShell

# 4. Install the package in editable mode (exposes the `applied-fox` command)
pip install -e .
```

## Verification

```bash
# Should print the CLI help
applied-fox --help

# Should print "ChatOllama"
python -c "from src.llm import get_llm; print(type(get_llm('interviewer', {})).__name__)"
```

If `applied-fox: command not found` on Windows, the Python `Scripts/` folder is not in your PATH. Workaround: use `python -m src.cli ...` or add `%LocalAppData%\Programs\Python\PythonXY\Scripts\` to your system PATH.

## Recommended mode: interactive menu (Milestone 7)

```bash
# Without arguments, opens the multi-project TUI.
applied-fox
```

This mode:
- lists your project files with phase + last update date
- offers per project: `run` (with real progress bar), browse past runs
  (HTML opens in browser), validate/integrate suggestions from last run,
  update the project file
- automatically chains `run → validate → integrate` (with confirmation
  between steps)
- resolves run paths for you (no need to copy timestamps manually)

The menu reads `paths.projects_dir` in `~/.applied-fox/config.yaml` (default
`~/.applied-fox/projects`). Point it to wherever you keep your project files.

## Direct commands

### Create a project file

Three modes depending on your comfort:

```bash
# Mode 1 — Interactive guided questionnaire
#   Recommended if you're new or unfamiliar with the structure.
#   Includes: LLM enrichment, final recap+correction, consistency check.
applied-fox interview create

# Mode 2 — Empty .md skeleton to fill in your editor
#   Recommended if you know your project and prefer editing text directly.
#   Generates a pre-structured .md with help comments, opens in your editor.
applied-fox interview skeleton

# Mode 3 — Update an existing project file
#   Re-prompts each field with current value, accepts "skip".
applied-fox interview update --project ~/.applied-fox/projects/my_file.md
```

### Launch a watch cycle on a project

```bash
applied-fox run --project ~/.applied-fox/projects/my_file.md
```

Produces in `~/.applied-fox/runs/<timestamp>_<project>/`:
- `01_eclaireur_findings.json`: structured findings
- `01_eclaireur_sources.json`: queries run + filter stats
- `02_integrateur_verdicts.json`: Integrator verdicts
- `03_juge_verdicts.json`: Judge verdicts
- `04_rapport.md` / `04_rapport.html`: human report
- `04_validated_suggestions.json`: structured suggestions for validation

Incremental mode (enabled by default) only surfaces new findings between
two runs.

### Validate and integrate suggestions (Milestone 6)

After a `run`, the loop closes in two steps:

```bash
# 1. Validate/reject suggestions via a Rich TUI
#    For each: accept / reject / defer (+ optional reason).
applied-fox validate --run ~/.applied-fox/runs/<timestamp>_<project>

# 2. Apply accepted suggestions to the project file.
#    For each: dialog on open questions + 3 validation layers
#    before writing.
applied-fox interview integrate \
    --project ~/.applied-fox/projects/<your_file>.md \
    --validated ~/.applied-fox/runs/<timestamp>_<project>/05_user_validated.json
```

The `integrate` mode is **sequential and resumable**: each suggestion is
written to the `.md` before moving to the next. If you interrupt midway,
what has been written stays safe, and the next iteration reads the
most up-to-date state.

## How the `interview create` questionnaire works

The interview applies three mechanisms to stay non-blocking while still
collecting usable signal:

1. **Optional enrichment**: on vague answers, the LLM offers a precision
   question. Type `skip` to keep your initial answer.
2. **Blocked skip**: on critical sections (Description, Objectives,
   Constraints), skip is refused if the answer is too short (< 4 words
   without a technical indicator). Prevents producing an unusable file.
3. **Recap + correction**: at the end, a numbered recap lets you edit
   any field before final save. Type the number to edit, or Enter to validate.

A post-questionnaire consistency check signals (non-blocking):
- components declared but absent from any interaction;
- interactions referencing an unknown name;
- components potentially forgotten given the description.

## Configure the watch sources

**Reddit** is the only source active without a key. The implementation uses
Reddit's public JSON endpoints with a SQLite cache (12h TTL).

The file `~/.applied-fox/config.yaml` controls behavior. Recommended config
to start (tuned for a first run under ~20 min on RTX 3070):

```yaml
paths:
  runs_dir: ~/.applied-fox/runs
  state_dir: ~/.applied-fox/state
  cache_dir: ~/.applied-fox/cache

# Per-agent models — calibrated post-Milestone 8 eval on RTX 3070 8 GB.
# To adapt to other hardware, see docs/HARDWARE.md.
ollama:
  base_url: http://localhost:11434
  num_ctx: 8192
  timeout_seconds: 120
  models:
    # interviewer hardcoded to local mistral 7B (CLAUDE.md rule 3 constraint)
    integrateur: mistral:7b-instruct-q4_K_M    # mechanical task, 7B suffices
    juge:        qwen3:8B                       # meta-reasoning → Qwen3
    rapporteur:  mistral:7b-instruct-q4_K_M    # 1 synthesis call, 7B suffices

# Disk LLM cache (auto-invalidation on prompt change).
# A re-run on the same project goes from ~30 min to ~5 min.
cache:
  llm_enabled: true

sources:
  reddit:
    enabled: true
    limit_per_query: 8       # max posts per query
    filters:
      min_score: 10          # lower = more noise
      max_age_days: 365

  rss:
    enabled: true
    cache_ttl_hours: 24
    filters:
      max_age_days: 90

  github:
    enabled: true             # requires GITHUB_TOKEN in .env
    limit_per_query: 3        # top repos by stars
    cache_ttl_hours: 24
    filters:
      min_stars: 10
      max_age_days: 365

filters:
  enable_alignment_check: true
  enable_freshness_check: true
  enable_dedup: true
  enable_incremental_mode: true
  # Hard cap after all filters — bounds downstream LLM time.
  # Raise to 80 for exhaustive watch, lower to 20 for fast preview.
  max_after_filter: 30
```

### Tune for your machine

| If you want… | Change |
|---|---|
| **Faster first run** | `max_after_filter: 40` → ~10 min cold |
| **Exhaustive watch** | `max_after_filter: 200` or disable (comment the line) → ~50 min cold |
| **Less Reddit noise** | `min_score: 20` |
| **More RSS coverage** | `rss.filters.max_age_days: 180` |

See [`docs/CONFIG_SCHEMA.md`](docs/CONFIG_SCHEMA.md) (FR) for the full schema and [`docs/HARDWARE.md`](docs/HARDWARE.md) (FR) for hardware adaptations.

## Troubleshooting

**`ollama: command not found`**
→ Ollama is not installed or not in PATH. See https://ollama.com/download

**`ollama pull` fails**
→ The model name may have changed. Check https://ollama.com/library/mistral and update the name in `~/.applied-fox/config.yaml`.

**`ImportError: No module named 'langchain_ollama'`**
→ The venv is not activated, or `pip install -e .` hasn't been run.

**`applied-fox: command not found`**
→ On Windows, `pip install -e .` installs the script in a folder not in your PATH. Workaround: `python -m src.cli ...` or add `Scripts/` to PATH.

**LLM timeout**
→ Raise `ollama.timeout_seconds` in `~/.applied-fox/config.yaml` (default 120s, raise to 240s on CPU only).

**Pipeline produces 0 findings**
→ Normal on a 2nd run with incremental mode active (all already seen). To reset: delete `~/.applied-fox/state/<project>_seen.json`.

---

*Guide updated at final MVP (Milestone 8 + v1.5). All commands are available.*
