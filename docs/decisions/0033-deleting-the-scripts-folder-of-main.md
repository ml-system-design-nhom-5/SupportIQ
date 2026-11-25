# ADR-0033: Deleting `scripts/` of `main`

- **Status:** Accepted
- **Date:** 2026-11-25
- **Deciders:** Project lead
- **Related:** [ADR-0028](0028-repository-layout-for-the-pull-request-into-main.md), [ADR-0031](0031-retiring-apps-and-the-evaluation-runners-of-main.md), [ADR-0032](0032-deleting-the-intent-policy-file-of-main.md), PR [#48](https://github.com/ml-system-design-nhom-5/SupportIQ/pull/48)

## Context

[ADR-0031](0031-retiring-apps-and-the-evaluation-runners-of-main.md#what-is-retired), statements 1 and 4, keep one of the 20 scripts of `main`, `scripts/clean_test_cache.ps1`, because #47 (now #48) does not remove it. On 2026-11-25 the project lead decided to delete it too, knowing that ADR-0031 keeps it. The author of #48, who kept the file, also asked for its deletion, as the project lead said. The original author of the script was not asked.

Checked on 2026-11-25 in `build/release-download` at `ae07d6d`:

- **The file.** PowerShell, 106 lines, 5,033 bytes with LF line ends, blob `4c095c711f1e98094dce7fde46f7d111ffb8d562`, SHA-256 `0417bc9e480c73dafdb7d72444cb5d3e90bdb0f06b0bb8d4fbdd40be349e511c`. The blob is the same at `f6c1473`, which is an ancestor of `main`. It lists the pytest caches of the folders of `main`, and removes them with `-Apply`.
- **Nothing runs it.** No workflow, hook, test, Dockerfile, or other script names it. `tests/README.md`, section 3, tells people to run it by hand, and `README.md` names it in its layout table.
- **Nothing else is in `scripts/`.** The hook pattern `outside-kept-parts` of `.pre-commit-config.yaml` excludes the folder.
- **`.gitignore`** already ignores `.pytest_cache/`.

`tests/README.md` is a file of `main` that #48 changes, so it no longer has the bytes of `f6c1473`.

## Decision drivers

1. **Correctness:** no document tells people to run a file that is not in the tree, and no hook excludes a folder that does not exist.
2. **Traceability:** the file stays readable in the history, and no record of a run changes.
3. **One AI codebase:** the PR into `main` carries no helper of the retired evaluation code ([ADR-0031, Decision drivers](0031-retiring-apps-and-the-evaluation-runners-of-main.md#decision-drivers), item 5).

## Considered options

1. Delete the file and the folder.
2. Keep the file, as ADR-0031 states.

## Decision

We adopt option 1. The statements below are normative.

1. We will delete `scripts/clean_test_cache.ps1`, so the tree has no `scripts/` folder, with the part `scripts` of the pattern `outside-kept-parts` of `.pre-commit-config.yaml`.
2. The file stays in the history: `git show f6c1473:scripts/clean_test_cache.ps1` prints it.
3. `tests/README.md` loses its section 3, which tells people to run the file. This is a correction of a kept document of `main` in this repository, because its author's version names a file that is not in the tree. The rest of the document does not change.
4. No record changes: `artifacts/`, the history, and the accepted ADRs, which name `scripts/` as it was.

### Passages of other ADRs that this ADR replaces

| Passage | Replaced by |
|---|---|
| ADR-0031, [What is retired](0031-retiring-apps-and-the-evaluation-runners-of-main.md#what-is-retired), statement 1: "19 of the 20 scripts of `scripts/`" | All 20 scripts (statement 1) |
| ADR-0031, What is retired, statement 4: "and `scripts/`" among the files that #47 does not remove | Statement 1 |
| ADR-0031, [Checks and CI](0031-retiring-apps-and-the-evaluation-runners-of-main.md#checks-and-ci), statement 3: "`scripts/`" | Statement 1 |
| ADR-0031, [Passages of other ADRs that this ADR replaces](0031-retiring-apps-and-the-evaluation-runners-of-main.md#passages-of-other-adrs-that-this-adr-replaces): the row of ADR-0028, Scripts, "Only `clean_test_cache.ps1` stays" | No script stays |
| ADR-0031, [Changes to approved documents](0031-retiring-apps-and-the-evaluation-runners-of-main.md#changes-to-approved-documents): the parts of the rows of `README.md` and of the local run design on `scripts/` | Statement 1 |
| ADR-0031, [Validation](0031-retiring-apps-and-the-evaluation-runners-of-main.md#validation), first item: "and `scripts/` holds only `clean_test_cache.ps1`" | [Validation](#validation), item 1 |

The rest of ADR-0031 still holds. `docs/design/local-run.md` says that "the tree after the join has no `scripts/`", which the deletion makes true again, so it does not change.

## Consequences

### Positive

- The tree has no `scripts/` folder, and one hook exclusion goes with it.
- No document names a script that is not in the tree, apart from the kept documents of `main` and the ADRs, which are records.

### Negative

- Whoever used the script removes the pytest caches by hand. Git already ignores `.pytest_cache/`.
- The agreement of the author of #48 is relayed by the project lead, and covers the deletion of the file. The original author of the script was not asked, and no agreement is recorded for the change of `tests/README.md`.
- `docs/AI_PIPELINE_METRIC_IMPROVEMENTS.md`, `docs/guides/evaluation-evidence.md`, and the ADRs still name scripts of `main`.

## Pros and cons of the options

### Delete the file and the folder

- Good, because nothing runs the file, and the folder of `main` is gone from the PR into `main`.
- Bad, because a document of `main`, `tests/README.md`, changes in this repository, and no agreement of its author is recorded.

### Keep the file

- Good, because ADR-0031 and #48 keep it, and `tests/README.md` does not change.
- Bad, because `scripts/` stays for one file that no check, test, or workflow uses.

## Validation

1. `git ls-tree -r --name-only HEAD -- scripts` prints nothing, and `git show f6c1473:scripts/clean_test_cache.ps1 | shasum -a 256` prints `0417bc9e…511c`.
2. `git grep -n clean_test_cache HEAD -- . ':!docs/decisions' ':!artifacts'` prints nothing.
3. `pre-commit run --all-files --hook-stage manual` passes in CI after the deletion, its check of relative links included.
4. Revisit when a script of `main` is needed again; it comes from the history.
