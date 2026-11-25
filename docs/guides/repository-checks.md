# Repository checks and CI

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-11-25

How to run the repository-wide checks locally, which GitHub Actions workflows run them, and the convention that every workflow file follows. Read it before you add hooks to `.pre-commit-config.yaml` or a workflow to `.github/workflows/`. The contract tooling itself is described in [contracts/README.md](../../contracts/README.md).

## What runs where

pre-commit is the single runner for the repository-wide checks, on each commit and in CI, so every hook version is pinned once, in [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) ([WF-20](../rules/workflow.md#continuous-integration), [RULE-03](../rules/README.md#enforcement)).

```mermaid
flowchart LR
    Commit["git commit"] -->|"staged files"| Hooks["pre-commit hooks,<br/>stage pre-commit"]
    Hooks -->|"any hook fails"| Blocked["Commit blocked:<br/>fix and commit again"]
    Push["Push or pull request"] --> Repo["repository.yml:<br/>job repository-checks"]
    Push --> Con["contracts.yml:<br/>job contract-checks"]
    Push --> Be["backend.yml:<br/>jobs backend-checks,<br/>backend-tests, backend-image"]
    Push --> Ai["ai-service.yml:<br/>jobs ai-service-checks, ai-service-tests,<br/>ai-service-tests-torch,<br/>ai-service-release-command, ai-service-image"]
    Push --> Fe["frontend.yml:<br/>job frontend-checks"]
    Push --> Lr["local-run.yml:<br/>job local-run-compose"]
    Push --> LrAi["local-run.yml:<br/>job local-run-compose-ai"]
    Repo -->|"pre-commit run --all-files<br/>--hook-stage manual"| Result{"All checks pass?"}
    Con -->|"audit, pre-commit run contracts-check,<br/>bundle, mock check"| Result
    Be -->|"backend hooks, audit, tests with coverage,<br/>image build"| Result
    Ai -->|"ai-service and release command hooks, audits,<br/>tests without and with torch, pinned file,<br/>image build without modal"| Result
    Fe -->|"audit, pre-commit run frontend-check,<br/>tests, stories, build, UI flow tests"| Result
    Lr -->|"script tests, start with Compose,<br/>health checks, sign-ins, stop"| Result
    LrAi -->|"start with Compose and AI, health checks,<br/>sign-ins, no LLM call, stop"| Shown["Result shown,<br/>not a required check"]
    Result -->|"no"| Red["Merge blocked (WF-19)"]
    Result -->|"yes"| Green["Merge allowed"]
```

`deploy.yml` is not a check. The project lead runs it by hand on `main`, and it deploys `backend` only after the jobs of `backend.yml` pass again on that commit ([deploy guide](../../deploy/README.md#setup-order), step 6):

```mermaid
flowchart LR
    Lead["Project lead:<br/>Run workflow on main"] --> Checks["deploy-checks, deploy-tests,<br/>deploy-image: the jobs of backend.yml"]
    Lead -.->|"run on another ref"| Stop["deploy-migrate stops<br/>before it reads a secret"]
    Checks -->|"a job fails"| None["Nothing migrated or deployed"]
    Checks -->|"every job passes"| Migrate["deploy-migrate:<br/>backend migrate as the owner role"]
    Migrate -->|"the migration fails"| Keep["The running release keeps serving"]
    Migrate -->|"the database is at the new head"| Hook["deploy-render: the deploy hook<br/>with ref set to the commit"]
    Hook -->|"Render answers 4xx or 5xx,<br/>or no answer in 30 s"| Failed["deploy-render fails;<br/>the lead redeploys by hand"]
    Hook -->|"200, or 202 while another<br/>deploy of Render runs"| Render["Render builds and starts<br/>that commit"]
```

Each tool is justified here, as [WF-27](../rules/workflow.md#dependencies) requires. All of them have a permissive license ([WF-30](../rules/workflow.md#dependencies)), apart from the frontend licenses that [frontend/README.md](../../frontend/README.md#dependencies) says were approved, and shellcheck, which is GPL-3.0: the team approved it on 2026-11-18 as a development tool that runs only in pre-commit and is never shipped.

| Check | Tool and license | Why this tool | On commit | In CI |
|---|---|---|---|---|
| File hygiene: large files, case conflicts, shebangs, JSON and YAML syntax, merge markers, final newline, line endings, trailing whitespace | `pre-commit-hooks` 6.0.0, MIT | The standard hooks of pre-commit, one repository for every hygiene check | Yes | `repository-checks` |
| Secrets in the staged changes | gitleaks 8.30.1 (`gitleaks`), MIT | The secret scanner of [ADR-0003](../decisions/0003-tech-stack.md) | Yes | — |
| Secrets in every commit reachable from `HEAD` | gitleaks 8.30.1 (`gitleaks-history`), MIT | The same scanner, over the history of the checked-out branch | — | `repository-checks` |
| Markdown style ([docs/README.md](../README.md#files-and-formatting)), and every relative link and `#fragment` | markdownlint-cli2 0.24.0 with `markdownlint-rule-relative-links` 5.1.4, both MIT | The Markdown linter of the [enforcement table](../rules/README.md#enforcement). The rule plugin checks links and anchors offline, so no website can fail the check | Yes | `repository-checks` |
| Workflow files | actionlint 1.7.12, MIT | Checks the syntax, expressions, and action inputs of GitHub Actions workflows, which no other tool here understands | Yes | `repository-checks` |
| The bash scripts of `deploy/local/` and `eval/release/gate/` | `shellcheck-py` 0.11.0.1, MIT, which installs shellcheck 0.11.0, GPL-3.0 | The standard linter of shell scripts: unquoted expansions, unset variables, and bash features that the bash 3.2 of macOS lacks. The wrapper installs it with pip, so no system package is needed | Yes | `repository-checks` |
| The workflow convention ([Who checks each rule](#who-checks-each-rule)) | The `workflow-*` and `deploy-workflow-*` pygrep hooks of pre-commit 4.7.0, and `deploy-workflow-copies-backend`, which compares two workflows with bash, sed, and diff | Pattern checks and a file comparison that need no new tool | Yes | `repository-checks` |
| Contract lint, custom rules, example validation, and the TypeScript checks | `contracts-check`, with the tools of [contracts/README.md](../../contracts/README.md#tools) | [RULE-03](../rules/README.md#enforcement), CON-04 to CON-18 | Yes | `contract-checks` |
| High and critical vulnerabilities in the contract tools | `pnpm audit --audit-level=high` in `contracts/` | [WF-31](../rules/workflow.md#dependencies) | — | `contract-checks` |
| Contract bundles, and the sign-in flow, the `ai-service` service token, and example files through the Prism mock of each contract | `pnpm run bundle`, `pnpm run check:mock` in `contracts/` | Proves that consumers can generate code from the bundle and use the mock | — | `contract-checks` |
| `backend` formatting, lint, strict types, layer and feature boundaries, and generated models | The hooks `backend-format`, `backend-lint`, `backend-types`, `backend-imports`, and `backend-generated`, with the tools of the [`backend` README](../../backend/README.md#dependencies) | [RULE-03](../rules/README.md#enforcement), CON-26 | Yes | `backend-checks` |
| Known vulnerabilities in every locked `backend` dependency except the named-entity model, which pip-audit cannot audit and its checksum in `uv.lock` protects ([ADR-0017](../decisions/0017-named-entity-model-from-its-release-url.md), item 3) | pip-audit 2.10.1, Apache-2.0 | [WF-31](../rules/workflow.md#dependencies) | — | `backend-checks` |
| `backend` tests against PostgreSQL 17, with branch coverage | pytest 9.2.0, MIT, and coverage 7.17.2, Apache-2.0 | TEST-21 | — | `backend-tests` |
| The `backend` image build | `docker build` of `backend/Dockerfile` | ARCH-10 | — | `backend-image` |
| `ai-service` formatting, lint, strict types, layer and feature boundaries, and generated models. `ai-service-types` runs pyright with the `deploy` group, so it reads `ai-service/modal_app.py` with the Modal SDK | The hooks `ai-service-format`, `ai-service-lint`, `ai-service-types`, `ai-service-imports`, and `ai-service-generated`, with the tools of the [`ai-service` README](../../ai-service/README.md#dependencies) | Every rule that `backend` follows ([ADR-0021, CI](../decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 1), [RULE-03](../rules/README.md#enforcement), CON-26 | Yes | `ai-service-checks` |
| Known vulnerabilities in every locked `ai-service` dependency, the `deploy` group included. torch is audited as the public release of its version in `uv.lock`: PyPI does not know the local version `+cpu` of the CPU build, which comes from the same source | pip-audit 2.10.1, Apache-2.0 | [WF-31](../rules/workflow.md#dependencies) | — | `ai-service-checks` |
| `ai-service` tests on Linux without torch, with the fakes and the `deploy` group, so the tests of `modal_app.py` run. The only skips allowed are those of the tests that need torch, with their one reason: they skip by design, because `ai-service-tests-torch` runs them and allows no skip (ADR-0021, CI, statement 4, which stands above [TEST-20](../rules/testing.md#flaky-and-skipped-tests)). Any other skip fails the job | pytest 9.2.0, MIT, and its JUnit report | ADR-0021, CI, statement 4; TEST-20 | — | `ai-service-tests` |
| `ai-service` tests on Linux with torch from the PyTorch CPU index and the `deploy` group, with branch coverage of `app` and `modal_app`. Any skipped test fails the job | pytest 9.2.0, MIT, and coverage 7.17.2, Apache-2.0 | ADR-0021, CI, statement 4; TEST-21 | — | `ai-service-tests-torch` |
| The release command in `eval/release/`: formatting, lint, strict types, layer boundaries, tests with branch coverage, and known vulnerabilities. It follows the rule level of `ai-service` until `eval.yml` exists | The hooks `eval-release-format`, `eval-release-lint`, `eval-release-types`, and `eval-release-imports`, then pytest, coverage, and pip-audit, with the tools of the [release command README](../../eval/release/README.md#dependencies) | ADR-0021, CI, statement 7 | Yes, the hooks | `ai-service-release-command` |
| The pinned file of the releases: its format, and a published manifest of its release in `eval/releases/`. When the pinned file differs from the base commit, or the base cannot be fetched, also the GitHub Release of its tag, with exactly one uploaded asset `<release_id>.tar.gz` of the pinned size, read with the token of the run ([Workflow convention](#workflow-convention), rule 13; [release command README, The check of the pinned file](../../eval/release/README.md#the-check-of-the-pinned-file)) | `supportiq-release check-pinned-release`, with `--remote` for a change | [ADR-0030, Release archives](../decisions/0030-release-archives-and-the-modal-function-of-ai-service.md#release-archives), statement 5 | — | `ai-service-release-command` |
| The `ai-service` image build, with torch from the CPU index, and a run of the image that fails when `modal` of the `deploy` group can be imported in it | `docker build` of `ai-service/Dockerfile`, then `docker run` of the image | ARCH-10; [ADR-0030, The Modal function](../decisions/0030-release-archives-and-the-modal-function-of-ai-service.md#the-modal-function), statement 2 | — | `ai-service-image` |
| Format, lint, types, boundaries, and the generated client of frontend | `frontend-check`, with the tools of [frontend/README.md](../../frontend/README.md#dependencies) | [RULE-03](../rules/README.md#enforcement), [TS-02](../rules/typescript.md#toolchain), [TS-27](../rules/typescript.md#api-access) | Yes | `frontend-checks` |
| High and critical vulnerabilities, unit tests, stories, the build, and the UI flow tests | `pnpm audit`, `test:unit`, `test:stories`, `build`, `test:e2e` in `frontend/` | [WF-31](../rules/workflow.md#dependencies), [TEST-21](../rules/testing.md#coverage), [UI-32](../rules/ui.md#accessibility) | — | `frontend-checks` |
| The local run: the script tests of `local-run.sh`, then one start with Compose without AI, its health checks, a sign-in through each origin, a second start without a question, and a stop that leaves nothing ([local run design](../design/local-run.md#testing-and-evaluation)) | `deploy/local/tests/test-local-run.sh`, `deploy/local/local-run.sh`, and `deploy/local/tests/smoke-check.sh`, with the Docker and curl of the runner | WF-32, WF-33, TEST-01 | — | `local-run-compose` |
| The local run with AI: one start with Compose from the pinned release, health checks and a sign-in through each origin, the readiness of `ai-service`, a check that no text was sent to the LLM (no suggestion job, and no event of a draft step), a second start that uses the release cache without a question, and a stop that leaves nothing ([local run design](../design/local-run.md#testing-and-evaluation)). The download reads GitHub with the token of the run ([Workflow convention](#workflow-convention), rule 13) | `deploy/local/local-run.sh` and `deploy/local/tests/smoke-check.sh`, with the Docker and curl of the runner, and `actions/cache` (MIT) for the release cache, under a key made of the release ID | WF-32, WF-33, TEST-01. The cache keeps the download of the archive, about 309 MiB for `release-2026-11-23-01`, to one per release without a path filter (rule 3) | — | `local-run-compose-ai`, not a required check |

pre-commit installs the runtimes of the hooks at the versions in `default_language_version`: Go 1.27.3 for gitleaks and actionlint, and Node.js 24.22.2 for markdownlint-cli2.

Some files are outside some hooks ([ADR-0028, Checks](../decisions/0028-repository-layout-for-the-pull-request-into-main.md#checks); [ADR-0031, Checks and CI](../decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md#checks-and-ci); [ADR-0032](../decisions/0032-deleting-the-intent-policy-file-of-main.md)). Each exclusion is written on its hook, and the top-level `exclude` skips only generated code:

- The parts of `main` that remain, `pipeline/`, `artifacts/`, `tests/`, `pytest.ini`, nine documents of `docs/`, and the data folders of `main` in `data/`, are outside every hook that could change or refuse them, through `files: *outside-kept-parts`. markdownlint-cli2 therefore skips the 8 Markdown files of those data folders. Both gitleaks hooks still check them.
- The hooks that fix files also skip the frozen data of this repository, through `exclude: *frozen-data`: every file of `data/raw/` and every data file of `data/benchmarks/escalation/`. The READMEs there are still checked. `.gitattributes` turns off line-end conversion for `data/**` and `artifacts/**`.

## Set up pre-commit

1. Install [uv](https://docs.astral.sh/uv/) ([ADR-0003](../decisions/0003-tech-stack.md)).
2. Install pre-commit 4.7.0, the version that CI installs. `.pre-commit-config.yaml` refuses older versions:

   ```bash
   uv tool install --python 3.12 pre-commit==4.7.0
   ```

3. Install the git hook in your clone:

   ```bash
   pre-commit install
   ```

4. Install the contract tools, which the `contracts-check` hook calls ([contracts/README.md](../../contracts/README.md#set-up)):

   ```bash
   cd contracts && pnpm install --frozen-lockfile
   ```

5. Install the frontend tools, which the `frontend-check` hook calls ([frontend/README.md](../../frontend/README.md#set-up)):

   ```bash
   cd frontend && pnpm install --frozen-lockfile
   ```

The first run downloads Go and Node.js for the hooks and builds gitleaks and actionlint, which takes several minutes. Later runs reuse `~/.cache/pre-commit`.

## Commands

Run every command in the repository root.

| Command | What it does |
|---|---|
| `pre-commit run --all-files` | Runs the commit hooks on every tracked file |
| `pre-commit run --all-files --hook-stage manual` | Runs what the `repository-checks` job runs, including the history scan for secrets |
| `pre-commit run contracts-check --all-files` | Runs what the `contract-checks` job runs before the bundle and the mock check |
| `pre-commit run frontend-check --all-files` | Runs what the `frontend-checks` job runs before the tests |
| `pre-commit run --files <path> …` | Runs the hooks on the given files, for example new files that are not tracked yet |

`--all-files` covers tracked files only. A file that is not staged yet is checked with `--files`.

## Workflow convention

Every file in `.github/workflows/` follows these rules, including the `backend.yml`, `ai-service.yml`, and `frontend.yml` files that the component owners add ([WF-19](../rules/workflow.md#continuous-integration)). `deploy.yml` departs from rules 2 and 7 only, as those rules state. actionlint checks the syntax of every workflow, the `workflow-*` and `deploy-workflow-*` hooks of `.pre-commit-config.yaml` check every rule that a tool can check, and reviewers check the rest ([Who checks each rule](#who-checks-each-rule)).

1. **One workflow per area.** The file is `.github/workflows/<area>.yml` with `name: <area>`: `repository`, `contracts`, `backend`, `ai-service`, `frontend`, `local-run`, `deploy`. `local-run` holds the smoke tests of the [local run](local-run.md), which span every component.
2. **Triggers.** Exactly these, and nothing else ([ADR-0021, CI](../decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 3):

   ```yaml
   on:
     push:
       branches:
         - main
         - "build/**"
     pull_request:
       branches:
         - main
   ```

   The one exception is `deploy.yml`, which has only `on: workflow_dispatch:`. The project lead runs it on `main`, and its job `deploy-migrate` stops on any other ref before it reads a secret ([ADR-0016, Migrations and one-off commands](../decisions/0016-hosting-on-free-tiers.md#migrations-and-one-off-commands), items 2 and 3).

3. **No path filters.** No `paths` or `paths-ignore`, and no job-level or step-level `if:` that skips a check, so a required check always runs and always reports.
4. **Permissions.** `permissions: contents: read` at the top of the file. No job widens it. No workflow uses `pull_request_target`.
5. **Pinned actions.** Every `uses:` names a full 40-character commit SHA, followed by the version in a comment, for example `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1`. `actions/checkout` sets `persist-credentials: false`.
6. **Pinned runners.** Jobs run on `ubuntu-24.04`, not on `ubuntu-latest`.
7. **Concurrency.** Each workflow has:

   ```yaml
   concurrency:
     group: ${{ github.workflow }}-${{ github.ref }}
     cancel-in-progress: true
   ```

   The one exception is `deploy.yml`, so that one deploy runs at a time, whatever the ref, and a migration is never cancelled; a newer run waits until the running one ends:

   ```yaml
   concurrency:
     group: deploy
     cancel-in-progress: false
   ```

8. **Timeouts.** Every job sets `timeout-minutes`.
9. **Frozen installs.** Tools come from the pinned files only: `.nvmrc`, `packageManager`, and `pnpm install --frozen-lockfile` for Node.js; `.python-version` and `uv sync --locked` for Python; pre-commit 4.7.0 installed with `uv tool install --python 3.12 pre-commit==4.7.0`.
10. **Failures stay failures.** No `continue-on-error`, no `|| true` or other way to ignore an exit code, no automatic reruns, and no retry actions.
11. **Unique job names.** Every job sets a `name` that is unique across all workflows and starts with its area: `repository-checks`, `contract-checks`, `backend-…`, `ai-service-…`, `frontend-…`, `local-run-…`, `deploy-…`. Branch protection matches required checks by these names.
12. **Hooks through pre-commit.** A component's repository-wide hooks go in its marked section of `.pre-commit-config.yaml`:
    - each hook sets `stages: [pre-commit]`, so the `repository-checks` job does not run it;
    - each hook calls the component's own locked toolchain, as `contracts-check` runs `pnpm run check` inside `contracts/`, so its tool versions stay pinned in the component's lockfile;
    - the component's workflow runs its hooks with `pre-commit run <hook-id> --all-files`.

    The hooks of the release command in `eval/release/` sit in the `ai-service` section and call its own lockfile, because it follows the rule level of `ai-service` until `eval.yml` exists ([ADR-0021, CI](../decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 7).
13. **Secrets.** Only `deploy.yml` reads a repository secret, and each of its two only in the `env` of the one step that uses it: `DEPLOY_DATABASE_URL_OWNER` in the migration step and `RENDER_DEPLOY_HOOK_URL` in the step that calls the deploy hook ([ADR-0016, Migrations and one-off commands](../decisions/0016-hosting-on-free-tiers.md#migrations-and-one-off-commands), item 4). One exception: two steps read the token of the run, `github.token`, as `SUPPORTIQ_RELEASE_TOKEN`, only in the `env` of the step: the step of the pinned file in `ai-service-release-command` and the step that starts the local run with AI in `local-run-compose-ai`. The token is read-only (rule 4), and their commands send it only to `api.github.com`, for its rate limit ([ADR-0030, Download](../decisions/0030-release-archives-and-the-modal-function-of-ai-service.md#download), statement 2). No other step, job, workflow, or image build gets it. No workflow uses `secrets: inherit` or `environment:`: the repository is private on GitHub Free, which has no environment secrets.
14. **The jobs of `backend.yml` in `deploy.yml`.** `deploy.yml` repeats the jobs of `backend.yml` line for line, as `deploy-checks`, `deploy-tests`, and `deploy-image`, up to the line `# ===== end of the jobs of backend.yml =====`, so a commit is deployed only after the same checks pass on it. A change to the jobs of `backend.yml` changes `deploy.yml` in the same commit.

### Who checks each rule

The `workflow-*` and `deploy-workflow-*` hooks are pygrep hooks, which come with pre-commit, except `deploy-workflow-copies-backend`, which compares `backend.yml` and `deploy.yml` with bash, sed, and diff. Each pygrep hook fails when its pattern matches a line of a workflow or, for a required pattern, when the pattern is missing from the file. A hook cannot see what YAML means, so a rule it cannot express as a pattern stays with the reviewers.

| Rule | Checked by |
|---|---|
| 1. One workflow per area, `name: <area>` | Reviewers |
| 2. Exactly the push and pull request triggers; only `workflow_dispatch` for `deploy.yml` | `workflow-triggers`; `deploy-workflow-trigger` for `deploy.yml` |
| 3. No path filters, and no `if:` on a job or a step | `workflow-no-path-filters`, `workflow-no-if` |
| 4. `permissions: contents: read` at the top, no job-level permissions, no `pull_request_target` | `workflow-permissions-read`, `workflow-no-job-permissions`, `workflow-no-pull-request-target` |
| 5. Every `uses:` names a 40-character SHA and a `# v` comment; `actions/checkout` sets `persist-credentials: false` | `workflow-pinned-actions`, `workflow-checkout-credentials`. Reviewers check that the comment names the version of that SHA |
| 6. Jobs run on `ubuntu-24.04` | `workflow-pinned-runner` |
| 7. The concurrency group, and the one of `deploy.yml` | `workflow-concurrency`; `deploy-workflow-concurrency` for `deploy.yml` |
| 8. `timeout-minutes` on every job | `workflow-has-timeout`, `workflow-timeout-on-every-job`. Reviewers check that each value is reasonable |
| 9. Frozen installs: `pnpm install` with `--frozen-lockfile`, `uv sync` with `--locked`, no `pip install` or `npm install`, and pre-commit 4.7.0 | `workflow-frozen-installs`. Reviewers check that runtimes come from `.nvmrc`, `packageManager`, and `.python-version` |
| 10. No `continue-on-error`, no `\|\| true` or `\|\| :`, no retry actions or reruns | `workflow-no-continue-on-error`, `workflow-no-ignored-exit-code`, `workflow-no-retries`. Reviewers check other ways to ignore an exit code |
| 11. Job names unique across workflows and prefixed with their area | Reviewers |
| 12. Component hooks set `stages: [pre-commit]`, call the component's locked toolchain, and run with `pre-commit run <hook-id> --all-files` | Reviewers |
| 13. Secrets only in `deploy.yml`, each only in the step that uses it, with that step's command; no `secrets: inherit` and no `environment:`; the token of the run only in its two steps | `workflow-secrets-only-in-deploy`, `workflow-no-inherited-secrets`, `workflow-run-token-elsewhere`, `workflow-run-token-line`, `workflow-run-token-step`, `deploy-workflow-secrets`, `deploy-workflow-secret-steps`. Reviewers check a token that an expression builds from `github`, such as `toJSON(github)` |
| 14. `deploy.yml` repeats the jobs of `backend.yml` | `deploy-workflow-copies-backend` |

## Branch protection

Set these on GitHub for `main` (Settings → Branches, or a ruleset), right after the join PR is merged ([ADR-0021, Merge procedure](../decisions/0021-repository-layout-and-ai-ml-migration.md#merge-procedure), statement 10):

- Require a pull request before merging, with at least one approval ([WF-15](../rules/workflow.md#reviews)).
- Require status checks to pass, with the branch up to date before merging. Required checks: `repository-checks`, `contract-checks`, `backend-checks`, `backend-tests`, `backend-image`, `ai-service-checks`, `ai-service-tests`, `ai-service-tests-torch`, `ai-service-release-command`, `ai-service-image`, `frontend-checks`, and `local-run-compose`, which the project lead made a required check on 2026-11-18. The `deploy-*` jobs are not required checks, because they run only when the project lead runs the deploy.
- Block force pushes and deletions ([WF-07](../rules/workflow.md#branches)).

## The first CI run

GitHub Actions cannot run locally. On the first push, check:

1. All six workflows that a push starts run, and the jobs `repository-checks`, `contract-checks`, `backend-checks`, `backend-tests`, `backend-image`, `ai-service-checks`, `ai-service-tests`, `ai-service-tests-torch`, `ai-service-release-command`, `ai-service-image`, `frontend-checks`, `local-run-compose`, and `local-run-compose-ai` appear. `deploy.yml` does not start on a push. A missing workflow means a trigger or syntax problem. `frontend-checks` installs Chromium with `playwright install --with-deps chromium`.
2. Every `uses:` step resolves. "Unable to resolve action" means a wrong commit SHA.
3. `contract-checks` installs pnpm 12.16.1 and Node.js 24.22.2, and `pnpm install --frozen-lockfile` neither reports an outdated lockfile nor stops on an ignored build script.
4. `repository-checks`, `contract-checks`, `backend-checks`, `ai-service-checks`, `ai-service-release-command`, and `frontend-checks` install pre-commit 4.7.0. The first `repository-checks` run downloads Go 1.27.3 and Node.js 24.22.2 for the hooks and saves the cache; the second run is faster.
5. `repository-checks` passes `Detect hardcoded secrets in the git history`. It scans only the commits reachable from `HEAD`: other branches of the clone, such as `main`, are not scanned.
6. `pnpm audit --audit-level=high` reports no high or critical advisory except the one ignored in `contracts/pnpm-workspace.yaml`, and `pnpm run check:mock` prints seven `ok` lines: three for `backend.openapi.yaml` and four for `ai-service.openapi.yaml`.
7. `backend-tests` reaches the PostgreSQL 17 service, creates `supportiq_owner` and `supportiq_app`, and passes both coverage reports. `backend-image` builds `backend/Dockerfile`, which `local-run-compose` and `local-run-compose-ai` build again for the local run.
8. `ai-service-tests-torch` prints the torch version `2.15.0+cpu` and allows no skip, and `ai-service-tests` allows only the skips of the tests that need torch, so the tests of `modal_app.py` run in both. `ai-service-checks` audits torch as `torch==2.15.0`. `ai-service-image` builds `ai-service/Dockerfile` with torch, and its check that `modal` is not in the image passes.
9. The step for the pinned file in `ai-service-release-command` runs `check-pinned-release --remote` when the pinned file is new or changed since the base commit, and passes only after the archive of the pinned release is on GitHub ([release command README, Publish](../../eval/release/README.md#publish)). Otherwise its log says that the pinned file did not change. A `403` or `429` of the rate limit of GitHub is exit status 5: run the job again by hand (rule 10).
10. `local-run-compose` passes the script tests, starts the local run, signs in at both origins, starts it again without a question, and leaves no container after `stop`. Its log gives the durations of both starts, from which the deadlines of `deploy/local/local-run.sh` are set.
11. `local-run-compose-ai` starts the local run with AI from the pinned release. Its first run with a release downloads it and saves the release cache; on a later run, its log shows no download. `smoke-check.sh ai` passes after each start, and the second start asks nothing. A `403` or `429` of the rate limit of GitHub is exit status 5 of the download command, so the start stops with status 1 and names a network failure: run the job again by hand (rule 10). The times of its steps give the durations of both starts with AI.
12. All jobs finish within their `timeout-minutes`. Then set the branch protection above.

The first deploy is step 6 of the [deploy guide, Setup order](../../deploy/README.md#setup-order).

## Open questions

- External links are not checked yet, because a check that depends on other websites fails at random and must not block a merge. The proposal: a third workflow, `links.yml`, triggered only by `schedule` (weekly) and `workflow_dispatch`, runs lychee on every Markdown file and reports broken external links. It is never a required check, and broken links are fixed in a normal pull request. It needs a team decision, because it adds a workflow and a tool.
