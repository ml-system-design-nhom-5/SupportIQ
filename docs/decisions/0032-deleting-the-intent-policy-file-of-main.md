# ADR-0032: Deleting `intent_policy.v2.json` of `main`

- **Status:** Accepted
- **Date:** 2026-11-25
- **Deciders:** Project lead
- **Related:** [ADR-0021](0021-repository-layout-and-ai-ml-migration.md), [ADR-0025](0025-routing-configuration-of-the-first-release.md), [ADR-0028](0028-repository-layout-for-the-pull-request-into-main.md), [ADR-0031](0031-retiring-apps-and-the-evaluation-runners-of-main.md), PR [#48](https://github.com/ml-system-design-nhom-5/SupportIQ/pull/48), issue [#15](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/15), [data and ML rules](../rules/data-and-ml.md) (DATA-06, DATA-23, DATA-58)

## Context

[ADR-0031](0031-retiring-apps-and-the-evaluation-runners-of-main.md#what-is-retired), statement 3, keeps `apps/core_backend/config/policies/intent_policy.v2.json` as the only file of `apps/`, because the manifests of three system suites pin it and [ADR-0025](0025-routing-configuration-of-the-first-release.md#the-configuration), statement 3, names it as the input of the tuning issue [#15](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/15). PR #48, with the same two commits as PR #47, deletes the file with the rest of `apps/`; its merge, `b348c5a`, keeps it, as ADR-0031 states. On 2026-11-25 the project lead decided to delete it, knowing that ADR-0031 keeps it.

Checked on 2026-11-25 in `build/release-download` at `b348c5a`:

- **The file.** Blob `a30ea06314611ce39b3302dec986564936de49e0`, 4,092 bytes with LF line ends, SHA-256 `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`. The blob is the same at `f6c1473`, at `19ece5d`, and on the branch. `f6c1473` is an ancestor of `main`.
- **What runs never reads it.** No file of `frontend/`, `backend/`, `ai-service/`, `contracts/`, `deploy/`, `eval/`, or `ml/` names it, so neither `ai-service` nor the offline evaluation gate reads it. `ai-service` serves the values of [`routing.json`](../../ai-service/routing/main-untuned-v1/routing.json).
- **The kept code of `main` never reads it.** In `pipeline/`, `tests/`, and `scripts/`, only a comment names it (`pipeline/training/train_distilbert_robust.py`, line 63). `load_suite` of `pipeline/evaluation/contracts.py` reads a suite manifest, but hashes only the manifest and opens no file that it pins.
- **The checks name it twice:** `.gitattributes`, which turns off its line-end conversion, and the pattern `outside-kept-parts` of `.pre-commit-config.yaml`. No workflow names it.
- **Records name it.** The three manifests (`data/benchmarks/system/v1/suite_manifest.json`, `v2/acceptance/suite_manifest.json`, `v2/dev/suite_manifest.json`) pin its path and SHA-256, and 19 files of `artifacts/` name it.
- **The values of `main`.** `routing.json` holds τ 0.70, δ 0.10, and the four sensitive intents of the file. It does not hold the per-intent values, because its format has one τ and one δ. ADR-0025 lists those: the 12 per-intent values of τ and the 0.15 of δ for three intents ([What `main` has](0025-routing-configuration-of-the-first-release.md#what-main-has)). The field `team_mapping` is in no document, and is the same in the five files `artifacts/training/intent-v1.2.0/round-1/` to `round-5/intent_policy.json`, which stay.

## Decision drivers

1. **Safety:** the deletion changes no routing value, no release, and no result of the offline evaluation gate.
2. **Traceability:** the exact bytes that the manifests pin and that ADR-0025 names can still be read and checked.
3. **Integrity of the frozen data:** no manifest of a frozen suite is edited ([DATA-23](../rules/data-and-ml.md#splits-and-evaluation-protocol)).
4. **One AI codebase:** the PR into `main` carries no folder of the retired application ([ADR-0031, Decision drivers](0031-retiring-apps-and-the-evaluation-runners-of-main.md#decision-drivers), item 5).

## Considered options

1. Delete the file. It stays in the history.
2. Keep the file at its path, as ADR-0031 states.
3. Move the file into `data/`, with the new path in ADR-0025 as a link fix.

## Decision

We adopt option 1. The statements below are normative.

1. We will delete `apps/core_backend/config/policies/intent_policy.v2.json`, with its line in `.gitattributes` and its line in the pattern `outside-kept-parts` of `.pre-commit-config.yaml`, in one commit of its own after `b348c5a`. The tree then holds no file of `apps/`.
2. The file stays in the history, and nothing copies it to another path. `git show f6c1473:apps/core_backend/config/policies/intent_policy.v2.json` prints the pinned bytes, and so does the same command with `b348c5a`.
3. The three manifests of the system suites are frozen and are not edited. Each keeps the path and the SHA-256 of the file, and that path is not in the tree. The runners that checked the manifests are retired by #48 ([ADR-0031, What is retired](0031-retiring-apps-and-the-evaluation-runners-of-main.md#what-is-retired), statement 1). Whoever checks a manifest by hand takes the file from the history.
4. The routing configuration `main-untuned-v1` does not change, and ADR-0025 stays in force:
   - the link of its line 27 goes to the file at `f6c1473` on GitHub, as a broken-link fix ([documentation handbook, ADRs](../README.md#adrs));
   - the per-intent values stay an input of #15, from the lists of ADR-0025 and from the history, no longer from a file of the tree.
5. No other record changes: the files of `artifacts/`, the comment in `pipeline/training/train_distilbert_robust.py`, which is a file of `main`, and the accepted ADRs, apart from the link of statement 4.

### Passages of other ADRs that this ADR replaces

| Passage | Replaced by |
|---|---|
| ADR-0031, [What is retired](0031-retiring-apps-and-the-evaluation-runners-of-main.md#what-is-retired), statement 3 | Statements 1 to 3 |
| ADR-0031, [Checks and CI](0031-retiring-apps-and-the-evaluation-runners-of-main.md#checks-and-ci), statement 3: "and `intent_policy.v2.json`", with its reference | Statement 1 |
| ADR-0031, [Passages of other ADRs that this ADR replaces](0031-retiring-apps-and-the-evaluation-runners-of-main.md#passages-of-other-adrs-that-this-adr-replaces), last paragraph: "ADR-0025 does not change while `intent_policy.v2.json` stays at its path" | Statement 4 |
| ADR-0031, [Changes to approved documents](0031-retiring-apps-and-the-evaluation-runners-of-main.md#changes-to-approved-documents): the row of `.gitattributes`, and "except `intent_policy.v2.json`" in the row of repository checks | Statement 1 |
| ADR-0031, [Validation](0031-retiring-apps-and-the-evaluation-runners-of-main.md#validation): the first item for `apps/`, and the fifth item | [Validation](#validation), items 1 and 2 |
| ADR-0031, [Open questions](0031-retiring-apps-and-the-evaluation-runners-of-main.md#open-questions), item 1 | Statements 1 to 4 |
| ADR-0028, [Checks](0028-repository-layout-for-the-pull-request-into-main.md#checks), statement 5: the words on `intent_policy.v2.json` | Statement 1 |
| ADR-0028, [Passages of other ADRs that this ADR replaces](0028-repository-layout-for-the-pull-request-into-main.md#passages-of-other-adrs-that-this-adr-replaces), item 2: the path of the link of ADR-0025, line 27 | Statement 4 |
| ADR-0025, [The configuration](0025-routing-configuration-of-the-first-release.md#the-configuration), statement 3: "They stay in `intent_policy.v2.json` as an input of the tuning issue" | Statement 4 |
| ADR-0021, [Where the code of `main` goes](0021-repository-layout-and-ai-ml-migration.md#where-the-code-of-main-goes), row of `intent_policy.v2.json`: its place, and "Kept byte for byte, like `mock_orders.json`, because the suites' manifests pin its SHA-256" | Statements 1 to 3 |
| ADR-0021, [Large files and data](0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 3: `intent_policy.v2.json` among the frozen data | Statements 1 and 2 |

The rest of these ADRs still holds.

## Consequences

### Positive

- The tree holds no file of `apps/`, and one hook exclusion and one line of `.gitattributes` go with it.
- No release, routing value, or gate result changes.
- The history keeps the exact bytes, so every record that names the SHA-256 can still be checked.

### Negative

- Each of the three manifests pins a path that is not in the tree, so a check of every pinned file against the tree fails for that entry.
- The input of #15 is in the history and in ADR-0025, not in a file that tuning code can open.
- The comment in `pipeline/training/train_distilbert_robust.py` and 19 files of `artifacts/` name a file that is not in the tree.

### Follow-ups

- The documents that describe the layout and the hook exclusions change in the commit of [ADR-0031, Changes to approved documents](0031-retiring-apps-and-the-evaluation-runners-of-main.md#changes-to-approved-documents), which follows the deletion.
- Issue #15 gets a comment that links this ADR.

## Pros and cons of the options

### Delete the file

- Good, because no file of `apps/` enters the PR into `main`, and nothing that runs reads the file.
- Bad, because three frozen manifests name a path that is not in the tree, and the input of #15 is no longer a file of the tree.

### Keep the file at its path

- Good, because the manifests, the link of ADR-0025, and the input of #15 stay valid without a note, as ADR-0031 recommended.
- Bad, because `apps/` stays in the tree for one file that nothing reads.

### Move the file into `data/`

- Good, because #15 keeps a file of the tree as its input, and `apps/` is gone.
- Bad, because the manifests still name a path that is not in the tree, and the copy needs a place, a checksum manifest ([DATA-09](../rules/data-and-ml.md#data-layout)), and an owner, for a file that nothing reads.

## Validation

1. `git ls-tree -r --name-only HEAD -- apps` prints nothing.
2. `git show f6c1473:apps/core_backend/config/policies/intent_policy.v2.json | shasum -a 256` prints the SHA-256 that the three manifests pin, `8789ee26…7be7`, and `git diff --name-only f6c1473 HEAD -- data/benchmarks/system` prints nothing.
3. `git grep -l intent_policy HEAD -- .gitattributes .github .pre-commit-config.yaml ai-service backend contracts deploy eval frontend ml scripts tests` prints nothing.
4. `pre-commit run --all-files --hook-stage manual` passes in CI after the deletion, its check of relative links included.
5. Revisit when #15 publishes a tuned routing configuration, or when a system evaluation that checks every pinned file is designed.
