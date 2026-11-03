"""Feature extraction module using TF-IDF for intent classification."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

from pipeline.preparation.utils import get_next_id


class IntentFeaturePipeline:
    """TF-IDF feature transformation pipeline preserving domain entity placeholders."""

    def __init__(
        self,
        ngram_range: tuple[int, int] = (1, 2),
        max_features: int | None = 10000,
        min_df: int = 2,
        sublinear_tf: bool = True,
        lowercase: bool = True,
        token_pattern: str = r"(?u)\b\w+\b|\{\{[^}]+\}\}",
    ) -> None:
        self.ngram_range = ngram_range
        self.max_features = max_features
        self.min_df = min_df
        self.sublinear_tf = sublinear_tf
        self.lowercase = lowercase
        self.token_pattern = token_pattern

        self.vectorizer = TfidfVectorizer(
            ngram_range=self.ngram_range,
            max_features=self.max_features,
            min_df=self.min_df,
            sublinear_tf=self.sublinear_tf,
            lowercase=self.lowercase,
            token_pattern=self.token_pattern,
        )
        self.is_fitted = False

    def fit(self, texts: Iterable[str]) -> IntentFeaturePipeline:
        """Fit TF-IDF vocabulary and IDF weights on training texts."""
        self.vectorizer.fit(texts)
        self.is_fitted = True
        return self

    def transform(self, texts: Iterable[str]) -> csr_matrix:
        """Transform text queries into TF-IDF sparse matrix."""
        if not self.is_fitted:
            raise RuntimeError("IntentFeaturePipeline must be fitted before transforming.")
        return self.vectorizer.transform(texts)

    def fit_transform(self, texts: Iterable[str]) -> csr_matrix:
        """Fit to training texts and return transformed sparse matrix."""
        matrix = self.vectorizer.fit_transform(texts)
        self.is_fitted = True
        return matrix

    def get_feature_names(self) -> list[str]:
        """Return the list of learned vocabulary feature names."""
        if not self.is_fitted:
            raise RuntimeError("IntentFeaturePipeline is not fitted.")
        return list(self.vectorizer.get_feature_names_out())

    def save(self, path: str | Path) -> Path:
        """Serialize fitted pipeline to disk via joblib."""
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, target_path)
        return target_path

    @classmethod
    def load(cls, path: str | Path) -> IntentFeaturePipeline:
        """Deserialize feature pipeline from disk."""
        target_path = Path(path)
        if not target_path.exists():
            raise FileNotFoundError(f"Pipeline artifact not found at {target_path}")
        loaded = joblib.load(target_path)
        if not isinstance(loaded, cls):
            raise TypeError(f"Loaded object is {type(loaded)}, expected {cls.__name__}")
        return loaded


def build_and_save_train_features(
    cleaned_csv: Path | str,
    splits_csv: Path | str,
    output_dir: Path | str,
    run_id: str | None = None,
    max_features: int = 10000,
    ngram_range: tuple[int, int] = (1, 2),
) -> Path:
    """Fit feature pipeline strictly on the train partition and save tfidf.joblib."""
    clean_path = Path(cleaned_csv)
    split_path = Path(splits_csv)
    out_dir = Path(output_dir)

    if run_id is None:
        run_id = get_next_id(out_dir)

    target_dir = out_dir / run_id
    target_dir.mkdir(parents=True, exist_ok=True)

    df_clean = pd.read_csv(clean_path)
    df_splits = pd.read_csv(split_path)

    merged = df_clean.merge(df_splits, on="sample_id")
    train_df = merged[merged["partition"] == "train"]

    if train_df.empty:
        raise ValueError("No train samples found in splits assignment file!")

    pipeline = IntentFeaturePipeline(
        ngram_range=ngram_range,
        max_features=max_features,
    )
    pipeline.fit(train_df["instruction"])

    model_path = target_dir / "tfidf.joblib"
    pipeline.save(model_path)
    return model_path


def main() -> None:
    """CLI entrypoint for fitting features on the train split."""
    parser = argparse.ArgumentParser(description="Fit TF-IDF feature pipeline on train partition.")
    parser.add_argument("--cleaned-csv", required=True, help="Path to cleaned dataset CSV")
    parser.add_argument("--splits-csv", required=True, help="Path to split_assignments.csv")
    parser.add_argument("--output-dir", required=True, help="Directory to save model artifacts (e.g. artifacts/models)")
    parser.add_argument("--run-id", default=None, help="Run ID in DD-MM-YYYY-stt format")
    parser.add_argument("--max-features", type=int, default=10000, help="Maximum vocabulary size")
    args = parser.parse_args()

    model_path = build_and_save_train_features(
        cleaned_csv=args.cleaned_csv,
        splits_csv=args.splits_csv,
        output_dir=args.output_dir,
        run_id=args.run_id,
        max_features=args.max_features,
    )
    print(f"TF-IDF pipeline fit and saved to: {model_path}")


if __name__ == "__main__":
    main()
