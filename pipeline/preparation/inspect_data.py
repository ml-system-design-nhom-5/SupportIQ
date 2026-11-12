"""Data inspection and Exploratory Data Analysis (EDA) module."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Ensure headless matplotlib backend
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pipeline.preparation.utils import (
    CORE_PRODUCT_INTENTS,
    compute_sha256,
    get_next_id,
    save_json,
)


def inspect_dataset(
    input_csv: Path | str,
    output_dir: Path | str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Inspect CSV dataset, generate statistics profile, and produce EDA figures.

    Args:
        input_csv: Path to raw or cleaned dataset CSV.
        output_dir: Path to directory where artifacts will be saved.
        run_id: Optional run ID. If None, auto-generated based on today's date.

    Returns:
        Dictionary containing inspection profile summary.
    """
    input_path = Path(input_csv)
    if not input_path.exists():
        raise FileNotFoundError(f"Input dataset not found at {input_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    if run_id is None:
        run_id = get_next_id(out_dir)

    df = pd.read_csv(input_path)
    file_sha256 = compute_sha256(input_path)

    # 1. Basic structural profile
    total_samples = len(df)
    columns = list(df.columns)
    null_counts = {col: int(df[col].isna().sum()) for col in columns}

    # 2. Text length analysis (instruction)
    if "instruction" in df.columns and total_samples > 0:
        char_lengths = df["instruction"].fillna("").astype(str).str.len()
        word_counts = df["instruction"].fillna("").astype(str).str.split().str.len()

        char_stats = {
            "min": int(char_lengths.min()),
            "max": int(char_lengths.max()),
            "mean": round(float(char_lengths.mean()), 2),
            "median": float(char_lengths.median()),
            "p90": float(np.percentile(char_lengths, 90)),
            "p95": float(np.percentile(char_lengths, 95)),
            "p99": float(np.percentile(char_lengths, 99)),
        }
        word_stats = {
            "min": int(word_counts.min()),
            "max": int(word_counts.max()),
            "mean": round(float(word_counts.mean()), 2),
            "median": float(word_counts.median()),
            "p90": float(np.percentile(word_counts, 90)),
            "p95": float(np.percentile(word_counts, 95)),
            "p99": float(np.percentile(word_counts, 99)),
        }
    else:
        char_stats = {}
        word_stats = {}

    # 3. Class and category distribution
    intent_counts = (
        df["intent"].value_counts().reset_index()
        if "intent" in df.columns
        else pd.DataFrame(columns=["intent", "count"])
    )
    intent_counts.columns = ["intent", "count"]
    intent_counts["percentage"] = (
        round(intent_counts["count"] / total_samples * 100, 3)
        if total_samples > 0
        else 0.0
    )
    intent_counts["is_core_product"] = intent_counts["intent"].isin(CORE_PRODUCT_INTENTS)
    intent_counts.to_csv(out_dir / "class_distribution.csv", index=False)

    category_counts = (
        df["category"].value_counts().to_dict()
        if "category" in df.columns
        else {}
    )

    # 4. Generate EDA Visualizations
    # Figure 1: Class Distribution
    if len(intent_counts) > 0:
        fig, ax = plt.subplots(figsize=(12, max(6, len(intent_counts) * 0.25)))
        y_pos = np.arange(len(intent_counts))
        colors = [
            "#2b5c8f" if is_core else "#7ea6d1"
            for is_core in intent_counts["is_core_product"]
        ]
        ax.barh(y_pos, intent_counts["count"], color=colors, align="center")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(intent_counts["intent"], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Sample Count")
        ax.set_title("Intent Distribution (Dark = Core 12 Product Intents)")
        plt.tight_layout()
        fig.savefig(figures_dir / "class_distribution.png", dpi=150)
        plt.close(fig)

    # Figure 2: Length Distribution
    if "instruction" in df.columns and total_samples > 0:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(word_counts, bins=min(30, max(5, int(word_counts.max()) + 1)), color="#3b82f6", edgecolor="black", alpha=0.7)
        ax.set_title("Instruction Word Count Distribution")
        ax.set_xlabel("Word Count")
        ax.set_ylabel("Frequency")
        plt.tight_layout()
        fig.savefig(figures_dir / "length_distribution.png", dpi=150)
        plt.close(fig)

    # Figure 3: Category-Intent Matrix
    if "category" in df.columns and "intent" in df.columns and total_samples > 0:
        ctab = pd.crosstab(df["category"], df["intent"])
        fig, ax = plt.subplots(figsize=(14, 8))
        im = ax.imshow(ctab.values, cmap="Blues", aspect="auto")
        ax.set_xticks(np.arange(len(ctab.columns)))
        ax.set_xticklabels(ctab.columns, rotation=90, fontsize=7)
        ax.set_yticks(np.arange(len(ctab.index)))
        ax.set_yticklabels(ctab.index, fontsize=9)
        ax.set_title("Category vs. Intent Co-occurrence Matrix")
        plt.colorbar(im, ax=ax)
        plt.tight_layout()
        fig.savefig(figures_dir / "category_intent_matrix.png", dpi=150)
        plt.close(fig)

    # 5. Compile profile summary
    profile = {
        "run_id": run_id,
        "input_file": str(input_path),
        "sha256": file_sha256,
        "total_samples": total_samples,
        "columns": columns,
        "null_counts": null_counts,
        "unique_intents": int(df["intent"].nunique()) if "intent" in df.columns else 0,
        "unique_categories": int(df["category"].nunique()) if "category" in df.columns else 0,
        "category_distribution": {k: int(v) for k, v in category_counts.items()},
        "char_stats": char_stats,
        "word_stats": word_stats,
        "figures_generated": [
            "figures/class_distribution.png",
            "figures/length_distribution.png",
            "figures/category_intent_matrix.png",
        ],
    }

    save_json(profile, out_dir / "profile.json")
    return profile


def main() -> None:
    """CLI entrypoint for inspect_data."""
    parser = argparse.ArgumentParser(description="Inspect dataset and generate EDA profile.")
    parser.add_argument("--input", required=True, help="Path to input CSV file")
    parser.add_argument("--output-dir", required=True, help="Directory to save inspection artifacts")
    parser.add_argument("--run-id", default=None, help="Run ID in DD-MM-YYYY-stt format")
    args = parser.parse_args()

    result = inspect_dataset(input_csv=args.input, output_dir=args.output_dir, run_id=args.run_id)
    print(f"Inspection complete for run_id: {result['run_id']}. Total samples: {result['total_samples']}")


if __name__ == "__main__":
    main()
