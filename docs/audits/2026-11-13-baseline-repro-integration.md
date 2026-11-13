# Traditional baseline reproducibility integration

Integrated B evidence through `a9723c7`. Run `13-11-2026-01` is a fresh CPU-only TF-IDF + Logistic Regression run using the frozen Bitext data/splits. It replaces the incomplete evidence of run `13-11-2026-00`; that run's missing OOF file remains explicitly documented rather than reconstructed.

Coordinator verification in root:

- All 13 output hashes match. The serialized bundle is copied byte-for-byte into the stable root artifact run directory and remains gitignored; 12 other outputs, including the OOF CSV, are tracked.
- The retained preparation manifest, cleaned data and split-assignment hashes match. The split report hash matches the root-relative `artifacts/preparation/03-11-2026-02/split_report.json`; preserved machine-specific paths require relocation when replaying elsewhere.
- Recomputed from the tracked OOF: 37,911 unique samples, 46 labels, 10 folds; mean fold Macro-F1 0.9892201150363482, population standard deviation 0.0014374825743039214, sample standard deviation 0.0015152396772008744, 413 errors.

The >=0.85 traditional baseline target and comparison evidence are supported. This does not prove better real-world drafting coverage or promote any classifier. No extra model fits or provider calls were made by the coordinator, and no application reload is required for these evidence-only files.
