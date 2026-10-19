"""Univariate EDA of the training table: ``reports/feature_eda.md`` plus small PNGs (Phase 7, 7.4).

Contents: AUC of every numeric feature against the primary label (positives vs negatives), the top-20
distributions, NULL rates by year, and clusters of highly correlated features. Reads the exported
``training/features_labels`` Parquet only; no warehouse needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from breakout import features_dict as fd  # noqa: E402
from breakout import paths as P  # noqa: E402
from breakout.config import Config  # noqa: E402
from breakout.duck import connect  # noqa: E402
from breakout.features.build import FEATURES_LABELS_DIR, LABEL_COLUMNS, MANIFEST_PATH  # noqa: E402
from breakout.logging import get_logger  # noqa: E402

log = get_logger(__name__)

REPORT = P.ROOT / "reports" / "feature_eda.md"
NULL_JSON = P.ROOT / "reports" / "metrics" / "feature_null_rates.json"
FIG_DIR = P.ROOT / "reports" / "figures"
LABEL = "breakout_rel"
CLUSTER_RHO = 0.8
NEG_SAMPLE = 200_000
PNG_DPI = 80


def _glob() -> str:
    return f"{FEATURES_LABELS_DIR.as_posix()}/year=*/part-0.parquet"


def numeric_features(con) -> list[str]:
    cols = con.execute(
        f"describe select * from read_parquet('{_glob()}', hive_partitioning = false)"
    ).fetchall()
    num = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "FLOAT", "DOUBLE", "BOOLEAN")
    skip = {"repo_id", "snapshot_date", "bucket", *LABEL_COLUMNS}
    return [c for c, t, *_ in cols if c not in skip and t.split("(")[0] in num]


def univariate_auc(con, features: list[str]) -> pd.DataFrame:
    """AUC of each feature (NULL rows dropped) via average ranks; also the share of non-NULL rows."""
    out = []
    for c in features:
        r = con.execute(
            f"""with d as (select {c}::double as x, {LABEL}::int as y from read_parquet('{_glob()}', hive_partitioning = false)
                           where {c} is not null),
                 n as (select x, y, row_number() over (order by x) as rn from d),
                 r as (select y, avg(rn) over (partition by x) as rk from n)
                select count(*), sum(y), sum(rk) filter (where y = 1) from r"""
        ).fetchone()
        n, pos, rank_sum = r
        neg = n - (pos or 0)
        auc = (
            (rank_sum - pos * (pos + 1) / 2) / (pos * neg)
            if pos and neg and rank_sum is not None
            else np.nan
        )
        out.append({"feature": c, "n": n, "auc": auc})
    df = pd.DataFrame(out)
    total = con.execute(
        f"select count(*) from read_parquet('{_glob()}', hive_partitioning = false)"
    ).fetchone()[0]
    df["non_null_share"] = df["n"] / total
    df["auc_dir"] = np.where(df["auc"] >= 0.5, "higher = more likely", "lower = more likely")
    df["strength"] = (df["auc"] - 0.5).abs() + 0.5
    return df.sort_values("strength", ascending=False).reset_index(drop=True)


def sample_frame(con, cols: list[str], seed: int = 7) -> pd.DataFrame:
    """All positives plus a hash-sampled set of negatives (deterministic), for plots and correlations."""
    sel = ", ".join([*cols, f"{LABEL}::int as y"])
    return con.execute(
        f"""select {sel} from read_parquet('{_glob()}', hive_partitioning = false)
            where {LABEL} or hash(repo_id, snapshot_date, {seed}) % 100 < {NEG_SAMPLE * 100 // 2_500_000}"""
    ).df()


def null_rates_by_year(con, features: list[str]) -> pd.DataFrame:
    agg = ", ".join(f"avg(({c} is null)::int) as {c}" for c in features)
    df = con.execute(
        f"select year(snapshot_date) as year, {agg} from read_parquet('{_glob()}', hive_partitioning = false) group by 1 order by 1"
    ).df()
    return df.set_index("year").T


def corr_clusters(
    df: pd.DataFrame, features: list[str]
) -> tuple[list[list[str]], pd.DataFrame, list[str]]:
    """Spearman |rho| clusters (single-linkage cut at rho >= CLUSTER_RHO). Returns (clusters, corr, order)."""
    from scipy.cluster.hierarchy import fcluster, leaves_list, linkage
    from scipy.spatial.distance import squareform

    corr = df[features].corr(method="spearman").fillna(0.0)
    dist = 1.0 - corr.abs().to_numpy()
    np.fill_diagonal(dist, 0.0)
    dist = (dist + dist.T) / 2
    z = linkage(squareform(dist, checks=False), method="average")
    labels = fcluster(z, t=1.0 - CLUSTER_RHO, criterion="distance")
    order = [features[i] for i in leaves_list(z)]
    groups: dict[int, list[str]] = {}
    for f, g in zip(features, labels, strict=True):
        groups.setdefault(int(g), []).append(f)
    clusters = sorted(
        (sorted(v) for v in groups.values() if len(v) > 1), key=lambda v: (-len(v), v[0])
    )
    return clusters, corr, order


def _fig_path(name: str) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    return FIG_DIR / name


def plot_distributions(df: pd.DataFrame, top: list[str]) -> Path:
    fig, axes = plt.subplots(4, 5, figsize=(13, 8.5))
    for ax, c in zip(axes.ravel(), top, strict=False):
        pos, neg = df.loc[df.y == 1, c].dropna(), df.loc[df.y == 0, c].dropna()
        allv = pd.concat([pos, neg])
        if allv.empty:
            ax.set_visible(False)
            continue
        lo, hi = allv.quantile(0.005), allv.quantile(0.995)
        pos, neg = pos.clip(lo, hi), neg.clip(lo, hi)
        log_scale = lo >= 0 and hi > 20 * max(allv.median(), 1e-9) and hi > 50
        tf = np.log1p if log_scale else (lambda v: v)
        bins = np.histogram_bin_edges(tf(allv.clip(lo, hi)), bins=30)
        ax.hist(tf(neg), bins=bins, density=True, alpha=0.55, label="not breakout", color="#4c78a8")
        ax.hist(tf(pos), bins=bins, density=True, alpha=0.55, label="breakout", color="#e45756")
        ax.set_title(c + (" (log1p)" if log_scale else ""), fontsize=8)
        ax.tick_params(labelsize=6)
    for ax in axes.ravel()[len(top) :]:
        ax.set_visible(False)
    axes[0, 0].legend(fontsize=6)
    fig.suptitle(
        "Top-20 features by univariate AUC: positives vs negatives (density, 0.5-99.5% clipped)",
        fontsize=10,
    )
    fig.tight_layout()
    p = _fig_path("feature_distributions.png")
    fig.savefig(p, dpi=PNG_DPI)
    plt.close(fig)
    return p


def plot_null_rates(nr: pd.DataFrame) -> Path:
    keep = nr[(nr > 0.01).any(axis=1)]
    fig, ax = plt.subplots(figsize=(8, max(3, 0.22 * len(keep) + 1)))
    im = ax.imshow(keep.to_numpy(), aspect="auto", cmap="viridis", vmin=0, vmax=1)
    ax.set_xticks(range(len(keep.columns)), [str(c) for c in keep.columns], fontsize=7, rotation=90)
    ax.set_yticks(range(len(keep.index)), list(keep.index), fontsize=6)
    fig.colorbar(im, ax=ax, label="NULL share")
    ax.set_title(
        "NULL share per feature and snapshot year (features with > 1% NULL somewhere)", fontsize=9
    )
    fig.tight_layout()
    p = _fig_path("feature_null_rates.png")
    fig.savefig(p, dpi=PNG_DPI)
    plt.close(fig)
    return p


def plot_corr(corr: pd.DataFrame, order: list[str]) -> Path:
    c = corr.loc[order, order]
    fig, ax = plt.subplots(figsize=(10, 9))
    im = ax.imshow(c.to_numpy(), cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(order)), order, fontsize=5, rotation=90)
    ax.set_yticks(range(len(order)), order, fontsize=5)
    fig.colorbar(im, ax=ax, label="Spearman rho")
    ax.set_title("Feature correlation (Spearman, ordered by clustering)", fontsize=9)
    fig.tight_layout()
    p = _fig_path("feature_correlation.png")
    fig.savefig(p, dpi=PNG_DPI)
    plt.close(fig)
    return p


def _md_table(df: pd.DataFrame, fmt: dict[str, str] | None = None) -> str:
    fmt = fmt or {}
    head = "| " + " | ".join(df.columns) + " |\n|" + "|".join("---" for _ in df.columns) + "|\n"
    rows = []
    for _, r in df.iterrows():
        rows.append(
            "| "
            + " | ".join(
                (fmt.get(c, "{}")).format(r[c]) if pd.notna(r[c]) else "" for c in df.columns
            )
            + " |"
        )
    return head + "\n".join(rows) + "\n"


def run(cfg: Config) -> Path:
    con = connect()
    con.execute("SET memory_limit='1500MB'")
    con.execute("SET threads=1")
    feats = numeric_features(con)
    manifest = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}
    log.info("EDA over %d numeric features", len(feats))
    auc = univariate_auc(con, feats)
    top = list(auc.head(20)["feature"])
    df = sample_frame(con, feats)
    nr = null_rates_by_year(con, feats)
    clusters, corr, order = corr_clusters(df, feats)
    all_null: tuple = con.execute(
        "select "
        + ", ".join(f"avg(({c} is null)::int) as {c}" for c in feats)
        + f" from read_parquet('{_glob()}', hive_partitioning = false)"
    ).fetchone()  # type: ignore[assignment]
    NULL_JSON.parent.mkdir(parents=True, exist_ok=True)
    NULL_JSON.write_text(
        json.dumps(
            {
                f: {
                    "all": round(float(all_null[i]), 6),
                    **{str(y): round(float(nr.loc[f, y]), 6) for y in nr.columns},
                }
                for i, f in enumerate(feats)
            },
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )
    figs = [plot_distributions(df, top), plot_null_rates(nr), plot_corr(corr, order)]
    prev = con.execute(
        f"""select year(snapshot_date) y, count(*), sum({LABEL}::int), avg({LABEL}::int)
            from read_parquet('{_glob()}', hive_partitioning = false) group by 1 order by 1"""
    ).fetchall()
    con.close()
    dic = fd.load()
    md = ["# Feature EDA (Phase 7)", ""]
    md.append(
        f"Training table: {manifest.get('rows_total', '?'):,} candidate-snapshot rows, "
        f"{len(manifest.get('features', []))} features, label `{LABEL}`. dbt git sha "
        f"`{manifest.get('dbt_git_sha', '?')}`, dictionary sha256 `{str(manifest.get('dictionary_sha256', '?'))[:12]}`. "
        "Univariate numbers only; they describe association, not a model (Phase 8).\n"
    )
    md.append("## Positive rate by year\n")
    md.append(
        _md_table(
            pd.DataFrame(prev, columns=["year", "rows", "positives", "positive rate"]).astype(
                {"year": "int64", "rows": "int64", "positives": "int64"}
            ),
            {"year": "{:d}", "rows": "{:,d}", "positives": "{:,d}", "positive rate": "{:.3%}"},
        )
    )
    md.append("## Top 20 features by univariate AUC\n")
    md.append(
        "AUC of the raw feature as a score for `breakout_rel` over all rows with a non-NULL value "
        "(0.5 = no signal; below 0.5 the feature points the other way). The velocity baseline B1 "
        "(`stars_7d`) has ROC-AUC 0.821 pooled (Phase 6).\n"
    )
    t = auc.head(20).copy()
    t["tier"] = t["feature"].map(lambda f: dic.get(f, {}).get("tier", "?"))
    md.append(
        _md_table(
            t[["feature", "tier", "auc", "auc_dir", "non_null_share"]],
            {"auc": "{:.3f}", "non_null_share": "{:.1%}"},
        )
    )
    md.append("![Top-20 distributions](figures/feature_distributions.png)\n")
    md.append("## Weakest features (closest to AUC 0.5)\n")
    w = auc.dropna(subset=["auc"]).tail(10)[["feature", "auc", "non_null_share"]]
    md.append(_md_table(w, {"auc": "{:.3f}", "non_null_share": "{:.1%}"}))
    md.append("## NULL rates by year\n")
    md.append(
        "Tier B (payload detail) is expected to be NULL before `history.detail_start_date` (2023-06-01), "
        "never filled with 0. Features with > 1% NULL in some year:\n"
    )
    keep = nr[(nr > 0.01).any(axis=1)].copy()
    keep.columns = [str(c) for c in keep.columns]
    keep.insert(0, "tier", [dic.get(f, {}).get("tier", "?") for f in keep.index])
    keep = keep.reset_index().rename(columns={"index": "feature"})
    md.append(_md_table(keep, {c: "{:.0%}" for c in keep.columns if c not in ("feature", "tier")}))
    md.append("![NULL rates](figures/feature_null_rates.png)\n")
    md.append(f"## Correlation clusters (|Spearman rho| >= {CLUSTER_RHO})\n")
    md.append(
        f"Average-linkage clusters on a sample of {len(df):,} rows (all positives plus a hash sample of "
        "negatives). Features in one cluster carry mostly the same information; tree models cope, linear "
        "models and SHAP attributions are affected.\n"
    )
    for i, cl in enumerate(clusters, 1):
        md.append(f"{i}. {', '.join(f'`{c}`' for c in cl)}")
    md.append("\n![Correlation](figures/feature_correlation.png)\n")
    REPORT.write_text("\n".join(md) + "\n")
    for p in figs:
        log.info("%s %.0f KB", p.name, p.stat().st_size / 1024)
    return REPORT
