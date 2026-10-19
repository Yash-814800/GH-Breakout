"""Model registry: packaged models, ``registry.json``, the promotion rule and prediction (Phase 8).

Layout of one version (``data/models/<version>/`` locally, ``<version>/`` in the models repo):
``model.txt`` (LightGBM native), ``calibrator.json``, ``categories.json``, ``features.json``,
``reference.json`` (training medians for the explanation sentences), ``metrics.json``,
``card.md``. ``registry.json`` (repo root) lists the versions and the ``champion`` pointer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from breakout import features_dict
from breakout import paths as P
from breakout.config import Config
from breakout.logging import get_logger
from breakout.ml import calibrate as C
from breakout.ml import dataset as D
from breakout.ml import explain as E

log = get_logger(__name__)

REGISTRY_FILE = "registry.json"
PACKAGE_FILES = (
    "model.txt",
    "calibrator.json",
    "categories.json",
    "features.json",
    "reference.json",
    "metrics.json",
    "card.md",
)


def models_dir() -> Path:
    return P.DATA_DIR / "models"


def empty_registry() -> dict[str, Any]:
    return {"champion": None, "versions": []}


def load_registry(path: Path | None = None) -> dict[str, Any]:
    path = path or models_dir() / REGISTRY_FILE
    if not path.exists():
        return empty_registry()
    return json.loads(path.read_text())


def save_registry(reg: dict[str, Any], path: Path | None = None) -> Path:
    path = path or models_dir() / REGISTRY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, indent=2, default=str) + "\n")
    return path


def new_version(git_sha: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"{now:%Y%m%d}-{git_sha[:7]}"


def decide(
    cand: pd.DataFrame,
    b1: pd.DataFrame,
    champion: pd.DataFrame | None,
    ks: list[int],
    n_boot: int,
    k: int = 25,
) -> dict[str, Any]:
    """Promotion rule on one shared holdout block (identical rows in all three frames).

    The candidate must beat B1 and, when there is a champion, the champion on PR-AUC and mean
    precision@k (both point differences > 0 and neither paired CI entirely below 0). Frames:
    ``repo_id, snapshot_date, score, label``.
    """
    from breakout.ml.cv_report import promotion_rule

    vs_b1 = promotion_rule(cand, b1, ks, n_boot, k)
    out: dict[str, Any] = {"vs_B1": vs_b1, "promote": bool(vs_b1["beats"])}
    if champion is not None:
        vs_c = promotion_rule(cand, champion, ks, n_boot, k)
        out["vs_champion"] = vs_c
        out["promote"] = bool(vs_b1["beats"] and vs_c["beats"])
    return out


def register(
    reg: dict[str, Any], version: str, metrics: dict[str, Any], decision: dict[str, Any]
) -> dict[str, Any]:
    """Add (or replace) a version entry and move the champion pointer when it is promoted."""
    reg["versions"] = [v for v in reg["versions"] if v["version"] != version]
    reg["versions"].append(
        {
            "version": version,
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "metrics": metrics,
            "decision": decision,
        }
    )
    if decision["promote"]:
        reg["champion"] = version
    return reg


@dataclass
class Model:
    version: str
    booster: lgb.Booster
    calibrator: C.Calibrator
    categories: dict[str, list[str]]
    features: list[str]
    reference: dict[str, float]


def save_core(
    out: Path,
    booster: lgb.Booster,
    calibrator: C.Calibrator,
    categories: dict[str, list[str]],
    features: list[str],
    reference: dict[str, float],
) -> Path:
    """The files needed to predict: booster, calibrator, categories, feature list, medians."""
    out.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out / "model.txt"), num_iteration=booster.best_iteration)
    (out / "calibrator.json").write_text(json.dumps(calibrator.to_json()) + "\n")
    (out / "categories.json").write_text(json.dumps(categories, indent=1) + "\n")
    (out / "features.json").write_text(
        json.dumps(
            {"features": features, "dictionary_sha256": features_dict.dictionary_hash()}, indent=1
        )
        + "\n"
    )
    (out / "reference.json").write_text(json.dumps(reference, indent=1) + "\n")
    return out


def save_package(
    out: Path,
    booster: lgb.Booster,
    calibrator: C.Calibrator,
    categories: dict[str, list[str]],
    features: list[str],
    reference: dict[str, float],
    metrics: dict[str, Any],
    card: str,
) -> Path:
    save_core(out, booster, calibrator, categories, features, reference)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str) + "\n")
    (out / "card.md").write_text(card)
    return out


def load_model(path: Path) -> Model:
    feats = json.loads((path / "features.json").read_text())
    return Model(
        version=path.name,
        booster=lgb.Booster(model_file=str(path / "model.txt")),
        calibrator=C.Calibrator.from_json((path / "calibrator.json").read_text()),
        categories=json.loads((path / "categories.json").read_text()),
        features=feats["features"],
        reference=json.loads((path / "reference.json").read_text()),
    )


def load_champion(cfg: Config | None = None, root: Path | None = None, pull: bool = False) -> Model:
    """The champion of ``registry.json``. ``pull`` downloads missing files from the models repo."""
    root = root or models_dir()
    if pull:
        pull_registry(cfg, root)
    reg = load_registry(root / REGISTRY_FILE)
    if not reg["champion"]:
        raise LookupError("registry has no champion")
    path = root / reg["champion"]
    if pull and not (path / "model.txt").exists():
        pull_version(cfg, reg["champion"], root)
    return load_model(path)


def predict(model: Model, df: pd.DataFrame, explain: bool = True) -> pd.DataFrame:
    """``raw_score, prob, top_contribs[, explanation]`` for every row of ``df`` (index kept).

    ``df`` needs the model's feature columns (live features file or training rows).
    """
    X = D.apply_categories(df[model.features], model.categories)
    raw = np.asarray(model.booster.predict(X), dtype=float)
    out = pd.DataFrame({"raw_score": raw, "prob": model.calibrator.predict(raw)}, index=df.index)
    if explain:
        sv = E.shap_values(model.booster, X)
        feats = features_dict.load()
        contribs = [E.top_contributions(sv[i], model.features) for i in range(len(df))]
        out["top_contribs"] = contribs
        rows = df[model.features].to_dict("records")
        out["explanation"] = [
            E.explain_sentence(r, c, model.reference, feats)
            for r, c in zip(rows, contribs, strict=True)
        ]
    return out


# ---- Hugging Face ----------------------------------------------------------------------------


def upload_version(cfg: Config, version: str, root: Path | None = None) -> str | None:
    """Push ``<version>/`` files, ``registry.json`` and the model card README to the models repo."""
    from breakout.lake import hf

    root = root or models_dir()
    api = hf.get_api()
    items = [
        hf.UploadItem(root / version / f, f"{version}/{f}")
        for f in PACKAGE_FILES
        if (root / version / f).exists()
    ]
    items.append(hf.UploadItem(root / REGISTRY_FILE, REGISTRY_FILE))
    readme = P.ROOT / "docs" / "model_card.md"
    if readme.exists():
        items.append(hf.UploadItem(readme, "README.md"))
    return hf.put_small_files(api, cfg, "models", items, f"model {version}")


def pull_registry(cfg: Config | None, root: Path) -> Path:
    from breakout.config import get_config
    from breakout.lake import hf

    cfg = cfg or get_config()
    hf.download_files(hf.get_api(), cfg, "models", [REGISTRY_FILE], root)
    return root / REGISTRY_FILE


def pull_version(cfg: Config | None, version: str, root: Path) -> Path:
    from breakout.config import get_config
    from breakout.lake import hf

    cfg = cfg or get_config()
    hf.download_files(hf.get_api(), cfg, "models", [f"{version}/{f}" for f in PACKAGE_FILES], root)
    return root / version
