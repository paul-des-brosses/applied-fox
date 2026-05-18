"""
Harness d'évaluation isolée du Juge.

Permet de tester un (modèle, prompt) du Juge SANS rejouer tout le pipeline.
Réutilise les artefacts `01_eclaireur_findings.json` et
`02_integrateur_verdicts.json` d'un run précédent.

Usage :
    python scripts/eval_juge.py <run_dir> [--model qwen3.5:9b] [--project <md>]

Exemple :
    python scripts/eval_juge.py ~/.applied-fox/runs/20260513_093413_smart_greenhouse_v14
    python scripts/eval_juge.py <run_dir> --model mistral-nemo:latest

Mesure :
    - temps total / temps moyen par appel
    - taux d'échec JSON
    - distribution des verdicts (relevance, timing)
    - écrit `juge_eval_<model>.json` dans le run_dir

Pourquoi ce harness :
    Itérer sur le Juge en 3-5 min au lieu de 15-45 min (full pipeline).
    Cf. audit Jalon 8 — bottleneck identifié sur l'agent Juge en 7B Q4.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

# Permet de lancer le script depuis la racine du repo OU depuis scripts/
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from dotenv import load_dotenv

load_dotenv(override=False)

import yaml  # noqa: E402

from src.agents.juge import _build_judge_context, _evaluate_one  # noqa: E402
from src.models import Finding, IntegrationVerdict, ProjectModel  # noqa: E402
from src.validation.structural import parse_and_validate  # noqa: E402


def _detect_project_md(run_dir: Path) -> Optional[Path]:
    """
    Essaie de retrouver la fiche .md du projet à partir du nom du run_dir.

    Convention de nommage : `<timestamp>_<project_slug>[_suffix]`.
    On extrait le slug, on cherche `projects/<slug>.md` à la racine du repo.
    """
    name = run_dir.name
    # Retire timestamp prefix `20260513_093413_`
    parts = name.split("_", 2)
    if len(parts) < 3:
        return None
    after_ts = parts[2]
    # Retire suffixe versionning éventuel (_v14, _v14b, _v12...)
    for suffix in ("_v14b", "_v14", "_v13", "_v12", "_v11"):
        if after_ts.endswith(suffix):
            after_ts = after_ts[: -len(suffix)]
            break
    candidate = _repo_root / "projects" / f"{after_ts}.md"
    return candidate if candidate.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Évalue le Juge en isolation sur un run existant."
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Dossier du run (contient 01_eclaireur_findings.json + 02_integrateur_verdicts.json)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override du modèle Juge (ex: qwen3.5:9b, mistral-nemo:latest). "
             "Si absent, utilise la config par défaut.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Chemin explicite vers la fiche .md du projet. "
             "Si absent, déduit du nom du run_dir.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".applied-fox" / "config.yaml",
        help="Chemin config.yaml (défaut : ~/.applied-fox/config.yaml).",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=0,
        help="Limite le nombre de findings testés (0 = tous).",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    if not run_dir.exists():
        print(f"[ERR] run_dir introuvable : {run_dir}")
        return 1

    findings_path = run_dir / "01_eclaireur_findings.json"
    verdicts_path = run_dir / "02_integrateur_verdicts.json"
    for p in (findings_path, verdicts_path):
        if not p.exists():
            print(f"[ERR] Artefact manquant : {p}")
            return 1

    # ── Charger config + override modèle Juge ────────────────────
    cfg: dict = {}
    if args.config.exists():
        cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    if args.model:
        cfg.setdefault("ollama", {}).setdefault("models", {})["juge"] = args.model

    juge_model = cfg.get("ollama", {}).get("models", {}).get("juge", "(default profile)")
    print(f"[INFO] Juge model         = {juge_model}")
    print(f"[INFO] Run dir            = {run_dir}")

    # ── Charger la fiche projet ──────────────────────────────────
    project_md = args.project
    if project_md is None:
        project_md = _detect_project_md(run_dir)
    if project_md is None or not project_md.exists():
        print(f"[ERR] Fiche projet introuvable. Précise --project <path>.")
        return 1
    print(f"[INFO] Project md         = {project_md}")

    md_content = project_md.read_text(encoding="utf-8")
    project, errors = parse_and_validate(md_content)
    if project is None:
        print(f"[ERR] Fiche projet invalide :")
        for e in errors:
            print(f"  - {e}")
        return 1

    # ── Charger findings + verdicts intégrateur ─────────────────
    findings_raw = json.loads(findings_path.read_text(encoding="utf-8"))
    verdicts_raw = json.loads(verdicts_path.read_text(encoding="utf-8"))

    findings = {f["id"]: Finding(**f) for f in findings_raw}
    int_verdicts = {
        fid: IntegrationVerdict(**v)
        for fid, v in verdicts_raw.items()
    }

    # ── Filtre : on ne juge QUE les findings marqués integrable=True ──
    integrable_pairs = [
        (findings[fid], v)
        for fid, v in int_verdicts.items()
        if v.integrable and fid in findings
    ]
    total = len(integrable_pairs)
    if args.max_findings > 0:
        integrable_pairs = integrable_pairs[: args.max_findings]
    print(f"[INFO] Findings intégrables: {total} (test sur {len(integrable_pairs)})")

    # ── Boucle d'évaluation ──────────────────────────────────────
    judge_context = _build_judge_context(project)
    results: list[dict] = []
    durations: list[float] = []
    failures = 0

    print()
    print(f"{'#':>3}  {'time':>5}  {'rel':<7} {'tim':<18} {'title'}")
    print("-" * 100)

    t_start = time.time()
    for i, (finding, iv) in enumerate(integrable_pairs, start=1):
        t0 = time.time()
        verdict = _evaluate_one(finding, iv, judge_context, project, cfg, max_retries=1)
        dt = time.time() - t0
        durations.append(dt)
        if verdict is None:
            failures += 1
            print(f"{i:>3}  {dt:>4.1f}s  [FAIL]  -                  {finding.title[:60]}")
            results.append({
                "finding_id": finding.id,
                "title": finding.title,
                "status": "fail",
                "duration_s": round(dt, 2),
            })
        else:
            print(
                f"{i:>3}  {dt:>4.1f}s  {verdict.relevance:<7} "
                f"{verdict.timing_recommendation:<18} {finding.title[:60]}"
            )
            results.append({
                "finding_id": finding.id,
                "title": finding.title,
                "status": "ok",
                "duration_s": round(dt, 2),
                "relevance": verdict.relevance,
                "timing": verdict.timing_recommendation,
                "real_gain_summary": verdict.real_gain_summary,
                "rationale": verdict.rationale,
            })

    total_time = time.time() - t_start

    # ── Stats ────────────────────────────────────────────────────
    from collections import Counter
    succeed = [r for r in results if r["status"] == "ok"]
    rel_dist = Counter(r["relevance"] for r in succeed)
    tim_dist = Counter(r["timing"] for r in succeed)

    print()
    print("─" * 60)
    print(f"Modèle Juge        : {juge_model}")
    print(f"Findings testés    : {len(integrable_pairs)}")
    print(f"Succès JSON        : {len(succeed)}/{len(integrable_pairs)} "
          f"({100 * len(succeed) / max(1, len(integrable_pairs)):.1f}%)")
    print(f"Échecs JSON        : {failures}")
    print(f"Temps total        : {total_time:.1f}s")
    print(f"Temps moyen/appel  : {sum(durations) / max(1, len(durations)):.1f}s")
    print(f"Distribution rel.  : {dict(rel_dist)}")
    print(f"Distribution timing: {dict(tim_dist)}")

    # ── Sauvegarde résultats ─────────────────────────────────────
    safe_model = juge_model.replace(":", "_").replace("/", "_")
    out_path = run_dir / f"juge_eval_{safe_model}.json"
    out_path.write_text(
        json.dumps({
            "model": juge_model,
            "total_findings": len(integrable_pairs),
            "success_count": len(succeed),
            "failure_count": failures,
            "total_time_s": round(total_time, 1),
            "avg_call_s": round(sum(durations) / max(1, len(durations)), 2),
            "relevance_distribution": dict(rel_dist),
            "timing_distribution": dict(tim_dist),
            "results": results,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[OK] Résultats sauvegardés : {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
