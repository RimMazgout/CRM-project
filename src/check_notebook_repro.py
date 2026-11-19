"""Verifie que les notebooks donnent le meme resultat a chaque execution.

Usage (depuis la racine du depot) :
    python src/check_notebook_repro.py          # les trois notebooks
    python src/check_notebook_repro.py 04       # un seul : 02, 03 ou 04

Chaque notebook est execute deux fois, a chaque fois sur une copie temporaire (le notebook
versionne n'est pas modifie). Apres chaque execution on calcule des empreintes :
  * fichiers parquet : empreinte du CONTENU (valeurs triees par client), pas des octets ;
  * fichiers CSV : SHA-256 des octets.
Le script echoue (code 1) si les deux executions different, ou si elles different des
resultats presents avant le test.

Les notebooks sont des fichiers .ipynb ; l'execution utilise `python -m nbconvert` (celui du
venv). Ne pas utiliser `python -m jupyter`, qui peut appeler une autre installation.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

NOTEBOOKS = {
    "02": {
        "path": ROOT / "notebooks" / "02_rfm_segmentation.ipynb",
        "parquet": [ROOT / "data" / "processed" / "rfm_segments_2011-09-01.parquet"],
        "csv": [ROOT / "reports" / "rfm_segments_summary.csv"],
    },
    "03": {
        "path": ROOT / "notebooks" / "03_churn_prediction.ipynb",
        "parquet": [ROOT / "data" / "processed" / "churn_test_predictions.parquet"],
        "csv": [ROOT / "reports" / name for name in (
            "churn_metrics.csv", "churn_snapshots.csv", "churn_by_segment.csv", "churn_returns_sensitivity.csv",
            "churn_threshold_consistency.csv", "churn_segments_nb02_vs_nb03.csv")],
    },
    "04": {
        "path": ROOT / "notebooks" / "04_campaigns_simulation.ipynb",
        "parquet": [ROOT / "data" / "processed" / "campaign_targets_2011-09-01.parquet"],
        "csv": [ROOT / "reports" / name for name in (
            "campaigns_targets.csv", "campaigns_assumptions.csv", "campaigns_simulation.csv", "campaigns_breakeven_sensitivity.csv")],
    },
}


def fingerprint(cfg: dict) -> dict:
    out = {}
    for p in cfg["parquet"]:
        df = pd.read_parquet(p)
        df = df.sort_values(df.columns[0]).reset_index(drop=True)
        out[p.name] = hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest().upper()[:16]
    for p in cfg["csv"]:
        out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest().upper()[:16]
    return out


def outputs_exist(cfg: dict) -> bool:
    return all(p.exists() for p in cfg["parquet"] + cfg["csv"])


def run_once(cfg: dict, i: int) -> dict:
    # Copie temporaire placee dans notebooks/ (le notebook retrouve la racine du depot a partir
    # de son dossier). Supprimee ensuite : le notebook versionne n'est jamais modifie.
    nb = cfg["path"]
    nb_copy = nb.with_name(f"_repro_run{i}_{nb.name}")
    shutil.copy(nb, nb_copy)
    try:
        cmd = [sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace", str(nb_copy)]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            print(res.stdout[-2000:], res.stderr[-3000:])
            raise SystemExit(f"Execution {i} de {nb.name} en echec.")
    finally:
        nb_copy.unlink(missing_ok=True)
    return fingerprint(cfg)


def check(key: str) -> bool:
    cfg = NOTEBOOKS[key]
    print(f"=== notebook {key} : {cfg['path'].name}")
    before = fingerprint(cfg) if outputs_exist(cfg) else None
    runs = [run_once(cfg, i) for i in (1, 2)]
    for i, r in enumerate(runs, 1):
        print(f"execution {i} : {r}")
    ok = runs[0] == runs[1]
    print("Deux executions identiques :", ok)
    if before is not None:
        same = runs[1] == before
        print("Identique a l'etat precedent :", same)
        ok = ok and same
    return ok


def main() -> None:
    keys = [a for a in sys.argv[1:] if a in NOTEBOOKS] or list(NOTEBOOKS)
    results = {k: check(k) for k in keys}
    print("Resultat :", results)
    raise SystemExit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
