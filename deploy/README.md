# Deploy

This guide sets up the demo on the free plans that [ADR-0016](../docs/decisions/0016-hosting-on-free-tiers.md) decides: the setup order, the settings of each platform, the checks before and after the first deploy, and what is still open. The parts and how they connect are in [ADR-0016, Overview](../docs/decisions/0016-hosting-on-free-tiers.md#overview).

This guide holds no real value: no URL, project reference, token, or password. Each secret lives only in the settings of the platform that uses it ([ADR-0016, Secrets](../docs/decisions/0016-hosting-on-free-tiers.md#secrets)).

## Setup order

1. **Supabase.** Create one free project in `ap-southeast-1` ([ADR-0016, PostgreSQL on Supabase](../docs/decisions/0016-hosting-on-free-tiers.md#postgresql-on-supabase)). Turn on "Enforce SSL on incoming connections" ([TLS to PostgreSQL](#tls-to-postgresql)). Run the [PostgreSQL checks](#postgresql-checks) and record their results.
2. **The app role.** In `backend/.env` on your machine, set `DATABASE_URL_OWNER` and `DATABASE_URL_APP` to the session pooler URLs of the two roles, without a query, and set `DATABASE_TLS` to `verify-full`, because `.env.example` sets `disable` for the local cluster ([TLS to PostgreSQL](#tls-to-postgresql)). Run `uv run backend create-app-role` in `backend/` ([backend README, Commands](../backend/README.md#commands)).
3. **Modal.** Set up the workspace and deploy `ai-service` ([Modal](#modal)). Keep the URL that `modal deploy` prints and the service token for the next step.
4. **Render.** Create one free web service in Singapore, built from `backend/Dockerfile`. Set `PORT` to `8000`, turn auto-deploy off, and create a deploy hook ([ADR-0016, `backend` on Render](../docs/decisions/0016-hosting-on-free-tiers.md#backend-on-render)). Enter the [Render settings](#render-settings).
5. **GitHub.** Add two repository secrets, which only the deploy workflow reads ([ADR-0016, Migrations and one-off commands](../docs/decisions/0016-hosting-on-free-tiers.md#migrations-and-one-off-commands), item 4):
   - `DEPLOY_DATABASE_URL_OWNER`: the session pooler URL of `supportiq_owner.<project-ref>`, port 5432, with the scheme `postgresql+asyncpg`, without a query ([TLS to PostgreSQL](#tls-to-postgresql));
   - `RENDER_DEPLOY_HOOK_URL`: the deploy hook URL as Render shows it, with its `key`.
6. **First deploy.** On GitHub, open Actions, select the workflow `deploy`, and run it on the branch `main`. It runs the jobs of `backend.yml` again, then `backend migrate` as the owner role, then calls the deploy hook with `ref` set to that commit. A failed job or a failed migration deploys nothing, and a run on another branch stops before the migration ([repository checks, What runs where](../docs/guides/repository-checks.md#what-runs-where)).
7. **Seed.** In `backend/.env` on your machine, set the four `SEED_PASSWORD_*` settings. Run `uv run backend seed` in `backend/`.
8. **Cloudflare Pages.** Create one Pages project and enter the [Pages settings](#cloudflare-pages-settings) ([ADR-0016, `frontend` and the ingress on Cloudflare Pages](../docs/decisions/0016-hosting-on-free-tiers.md#frontend-and-the-ingress-on-cloudflare-pages)).
9. **Grafana Cloud.** Create one free stack with 2 named Editors and 1 shared Viewer. Keep the Viewer's password in the team's password manager ([ADR-0016, Telemetry on Grafana Cloud](../docs/decisions/0016-hosting-on-free-tiers.md#telemetry-on-grafana-cloud)).
10. **UptimeRobot.** Create one monitor that sends `GET /health/ready` straight to the Render URL every 5 minutes, not through the Pages Function ([ADR-0016, `backend` on Render](../docs/decisions/0016-hosting-on-free-tiers.md#backend-on-render), item 5). No monitor calls `ai-service` on Modal: it scales to zero ([Modal](#modal)).
11. **Checks.** Work through the [first-deploy checklist](#first-deploy-checklist).

## TLS to PostgreSQL

Every connection to Supabase leaves the host that opens it, so it uses TLS ([SEC-28](../docs/rules/security-and-privacy.md#transport-and-runtime)):

1. In Supabase, open Database Settings, then SSL Configuration, and turn on "Enforce SSL on incoming connections". The database restarts for a few minutes, and the setting applies to the session pooler too. From then on, Supabase refuses every connection without TLS.
2. `DATABASE_TLS` is `verify-full` for every connection to Supabase. It is the default, so Render leaves it unset; the job `deploy-migrate` sets it in its environment; and `backend/.env` on your machine sets it, because `.env.example` sets `disable` for the local cluster.
3. With `verify-full`, `backend` requires a server certificate signed by the root authority of Supabase and checks that it names the host of the URL. The authority is `backend/certs/supabase-root-ca.crt`, the default of `DATABASE_CA_FILE`, relative to the working directory, so Render, the deploy workflow, and your machine set no authority ([backend README, TLS to the database](../backend/README.md#tls-to-the-database)). The image copies it, and the deploy workflow runs from the checkout of `backend/`. If Supabase replaces its authority, download the new one from Database Settings, SSL Configuration, and replace the file and its record in the backend README together.
4. No URL of the database holds a query: not `DATABASE_URL_APP` on Render, not the secret `DEPLOY_DATABASE_URL_OWNER`, and not the two URLs in `backend/.env`. A URL entered before this rule may still end with `?ssl=require`: remove the query on Render and in the secret before the next deploy. `backend` refuses any query at startup with a `settings.invalid` line that names the setting, never its value.

## Render settings

[backend/.env.example](../backend/.env.example) lists every setting with its meaning and default. Set these on Render; leave the others unset, so their defaults apply:

| Setting | Value |
|---|---|
| `DATABASE_URL_APP` | The session pooler URL of `supportiq_app.<project-ref>`, port 5432, without a query ([ADR-0016, PostgreSQL on Supabase](../docs/decisions/0016-hosting-on-free-tiers.md#postgresql-on-supabase), item 1; [TLS to PostgreSQL](#tls-to-postgresql)) |
| `ALLOWED_ORIGINS` | Only the production origin of the Pages project ([ADR-0016, `frontend` and the ingress on Cloudflare Pages](../docs/decisions/0016-hosting-on-free-tiers.md#frontend-and-the-ingress-on-cloudflare-pages), item 9) |
| `BACKEND_BUILD_VERSION` | The commit that Render deploys ([Open questions](#open-questions)) |
| `AI_SERVICE_BASE_URL` | The URL of the web function that `modal deploy` prints ([Modal, Each deploy](#each-deploy)) |
| `AI_SERVICE_TOKEN` | The `SERVICE_TOKEN` of the Modal Secret `supportiq-ai-service` ([Modal, Once](#once)) |
| `TRACE_EXPORTER` | `none`, until `backend` has a setting for the OTLP authorization header ([Open questions](#open-questions)) |

Never set `DATABASE_URL_OWNER` on Render ([ADR-0016, `backend` on Render](../docs/decisions/0016-hosting-on-free-tiers.md#backend-on-render), item 3).

The Dockerfile installs with `uv sync --locked`, so the Render build uses `uv.lock`, and it downloads the named-entity model from github.com ([ADR-0017](../docs/decisions/0017-named-entity-model-from-its-release-url.md#decision), items 1 and 2).

## Cloudflare Pages settings

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `VITE_FRONTEND_BUILD_VERSION=$CF_PAGES_COMMIT_SHA pnpm run build` ([admin UI design](../docs/design/admin-ui.md#developer-details-in-the-admin-area)) |
| Build output directory | `dist`, the output of `vite build` |
| `NODE_VERSION` | `24.22.2` |
| Production branch | `main`, from the join with the AI and ML code on |
| Preview deployments | Off |
| When the daily Functions limit is used up | Fail closed |
| `VITE_BACKEND_WAKE_ORIGIN` | The Render origin ([backend wake-up design](../docs/design/backend-wake-up.md#rules)) |
| `VITE_DEV_MODE` | Unset, so dev mode is off in the build ([console UI design](../docs/design/console-ui.md#frontend-settings)) |
| The `backend` URL of the Pages Function | `SUPPORTIQ_BACKEND_URL`, set to the Render origin ([frontend README, Deploy on Cloudflare Pages](../frontend/README.md#deploy-on-cloudflare-pages)). The Function is [`frontend/functions/`](../frontend/functions/) with its code in [`frontend/ingress/`](../frontend/ingress/), and its routes are [`frontend/public/_routes.json`](../frontend/public/_routes.json) |

## Modal

`ai-service` runs on Modal Starter as the app `supportiq-ai-service`, defined in [`ai-service/modal_app.py`](../ai-service/modal_app.py) ([ADR-0018](../docs/decisions/0018-hosting-of-ai-service-on-modal.md), [ADR-0030, The Modal function](../docs/decisions/0030-release-archives-and-the-modal-function-of-ai-service.md#the-modal-function)). It serves one published release, which the project lead downloads with the release command and adds to the image. The function has 2 CPU cores and 2 GiB of memory, takes up to 10 concurrent inputs on at most 1 container, stays warm for 20 minutes after the last request, and scales to zero. The two health checks are open; every other route checks the service token. The steps and their reasons are in the [release download and Modal deploy design](../docs/design/release-download-and-modal-deploy.md#the-modal-app).

The app `supportiq-ai` of the trial stays until the whole flow works on `supportiq-ai-service`, and is then stopped ([ADR-0021, Merge procedure](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#merge-procedure), statement 10).

### Once

1. **Modal command line.** In `ai-service/`, install the `deploy` group and sign in. The sign-in opens the browser and keeps the Modal token outside the repository.

   ```bash
   uv sync --locked --group deploy
   ```

   ```bash
   uv run --locked --group deploy modal setup
   ```

2. **Spend limit.** On the Usage & Billing page of the Modal workspace, set a spend limit before the first deploy. The project lead chooses the amount. When the limit is reached, Modal stops the function, and `backend` falls back to manual handling ([ADR-0030, The Modal function](../docs/decisions/0030-release-archives-and-the-modal-function-of-ai-service.md#the-modal-function), statement 8; [Modal: Budgets](https://modal.com/docs/guide/budgets)). Anyone can keep a container warm through the open health checks, and one container kept warm all month costs about $79, beyond the $30 credit (statement 7).
3. **Gemini API key.** Create a new key for this deployment only ([SEC-13](../docs/rules/security-and-privacy.md#secrets)), in a Google Cloud project with an active billing account. Only then is its use a Paid Service, whose prompts and responses Google does not use to improve its products ([SEC-07](../docs/rules/security-and-privacy.md#data-sent-to-llm-providers); ADR-0030, statement 9). No command tells a paid key from a free one, so check it by eye when you create it ([AI Studio: Billing](https://aistudio.google.com/docs/billing), read on 2026-11-23):
   - in AI Studio, the Projects page shows a paid tier (Tier 1, Tier 2, or Tier 3), not Free, in the column "Billing Tier" for the key's project; or the API keys page shows "Paid" under "Plan";
   - a project on the Free tier gets billing through the button "Set up billing" in that column;
   - record "paid tier checked" with the date in [Runs by hand](#runs-by-hand), step 5. Never record the key or a part of it.
4. **Modal Secret.** Create the Secret `supportiq-ai-service` with the two keys `GEMINI_API_KEY` and `SERVICE_TOKEN`. The app reads only this Secret and requires both keys; it never sets a value, a default, or a stand-in. Choose one of two ways. Neither writes a value to a file or to the shell history.
   - **In the Modal dashboard** ([Modal: Secrets](https://modal.com/docs/guide/secrets)). Paste each value into its field. Make the service token with `openssl rand -hex 32 | pbcopy`, which copies it without showing it on macOS; on Linux, pipe it into `xclip -selection clipboard` instead.
   - **With the command line**, in `ai-service/`. The shell expands both values, so the history holds only their names. While `modal secret create` runs, its arguments hold the values, so `ps` on that machine shows them for that time.

     ```bash
     read -rs GEMINI_API_KEY
     ```

     ```bash
     SERVICE_TOKEN="$(openssl rand -hex 32)"
     ```

     ```bash
     uv run --locked --group deploy modal secret create supportiq-ai-service GEMINI_API_KEY="$GEMINI_API_KEY" SERVICE_TOKEN="$SERVICE_TOKEN"
     ```

     Copy the service token for Render with `printf '%s' "$SERVICE_TOKEN" | pbcopy` on macOS, or into `xclip -selection clipboard` on Linux, then:

     ```bash
     unset GEMINI_API_KEY SERVICE_TOKEN
     ```

5. **Render.** Paste the same service token into the Render setting `AI_SERVICE_TOKEN` ([Render settings](#render-settings)). On the first setup, the Render service does not exist yet: keep the token for [Setup order](#setup-order), step 4.

Never put the Gemini key or the service token into a `.env` file for Modal, a file of the repository, or a message. A Secret from a `.env` file (`--from-dotenv`) is not used.

### Each deploy

Run both commands from the repository root. The first downloads the pinned release into the cache, or finds it there, and prints its folder ([release command README, Release download](../eval/release/README.md#release-download)). It asks before it downloads; `--yes` answers for it.

```bash
release_folder="$(uv run --locked --project eval/release supportiq-release download-release)"
```

```bash
SUPPORTIQ_RELEASE_FOLDER="$release_folder" uv run --locked --project ai-service --group deploy modal deploy ai-service/modal_app.py
```

- Before Modal receives anything, `modal_app.py` checks on your machine that `deploy/llm-prices.env` has its format and that its model and prices pass the rules of `Settings` of `ai-service`, that `SUPPORTIQ_RELEASE_FOLDER` is an absolute path of a folder, not a link, that `verify_release` passes on it, and that its manifest is byte for byte the one in `eval/releases/`. Any failure stops `modal deploy`. A failed download leaves `release_folder` empty, so the deploy stops too.
- Only `pyproject.toml`, `uv.lock`, `README.md`, and `app/` of `ai-service/` go into the build context, so a local `ai-service/.env` never reaches Modal.
- `modal deploy` prints the URL of the web function. Enter it in the Render setting `AI_SERVICE_BASE_URL` ([Render settings](#render-settings)). On the first setup, keep it for [Setup order](#setup-order), step 4.
- To deploy another release, pass `--release <release_id>` to `download-release`. To change the model or its prices, change [`llm-prices.env`](llm-prices.env) with its source and the date the page was read, commit it, and deploy again. The local run reads the same file.

### Publish a release

A release reaches Modal and the local run only through its release archive on GitHub. Publish it in the order of the [release command README, Publish](../eval/release/README.md#publish): commit the manifest, `pack-release --pin`, upload the archive in the browser, `download-release --release <release_id> --yes`, `check-pinned-release --remote`, and only then commit and push the pinned file. Immutable releases were off when both releases were uploaded (see the tables below). They stay off by the project lead's decision of 2026-11-23, until the system has taken shape, and [ADR-0018, Follow-ups](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#follow-ups) stays open until then. An uploaded archive is never replaced or deleted.

The form of a GitHub Release preselects the default branch, `main`, as the target of a new tag: choose the branch whose tip is the pushed commit that holds the manifest. No command checks this, so read the commit of the tag before `download-release`, and compare the manifest of that commit with the one in git, which prints nothing when both are equal. The field `target_commitish` of the GitHub Release does not follow a moved tag, so it proves nothing.

```bash
curl -fsS https://api.github.com/repos/ml-system-design-nhom-5/SupportIQ/git/ref/tags/<release_id>
```

```bash
git show <commit>:eval/releases/<release_id>/release-manifest.json | cmp - eval/releases/<release_id>/release-manifest.json
```

The publish of `release-2026-11-18-02`, contract 1.0.0, on 2026-11-23. The reviewer checked each value against the output of the runs and against the public GitHub API, read without a token. An exit status that nobody printed is not recorded:

| Fact | Value |
|---|---|
| `pack-release`, run twice into two new folders | Each run left an archive of 324312182 bytes, and the run with `--pin` wrote the pinned file |
| SHA-256 of the archive | `42803346175676457b49e7fb0dbe13c9f4206ca78d60877b3898e5791bcf5823`, the same for both runs, so its bytes repeat. GitHub reports the same digest for the uploaded asset |
| `archive_size_bytes` | `324312182`. The plan that `download-release` prints shows 310 MiB, and 385 MiB unpacked |
| Pinned file | `release_id=release-2026-11-18-02` and `archive_size_bytes=324312182` |
| GitHub Release | Tag `release-2026-11-18-02`, published, not a draft or a prerelease, uploaded in the browser. Its only asset is `release-2026-11-18-02.tar.gz`, in the state `uploaded`, of 324312182 bytes |
| Tag | `release-2026-11-18-02` points to the commit `425981f`, which holds the published manifest byte for byte |
| Immutable release | `immutable: false`: the setting was off at the upload, so GitHub does not stop a change of the asset. The manifest in git still refuses a changed byte of any file of the release: `download-release` exits with status 6 |
| `download-release`, anonymous, into an empty cache | Left the release in the download folder, with no hidden partial entry |
| Download folder | `$HOME/.cache/supportiq/releases/release-2026-11-18-02`: 18 files with mode `0644`, folders with mode `0755`, no entry of another type, and the same files as the packed release folder (`diff -rq`) |
| `download-release` again | A cache hit: "Release release-2026-11-18-02 is in the cache and checked.", the folder on standard output, exit status 0 |
| `check-pinned-release --remote`, anonymous | `pinned release_id=release-2026-11-18-02 archive_size_bytes=324312182 github=checked`, exit status 0 |

The publish of `release-2026-11-23-01`, contract 1.0.0, on 2026-11-23: the first release that serves KB documents, with KB v2.1. The reviewer gave the output of the runs, and the files and the public GitHub API, read without a token, were checked again for this table. An exit status that nobody printed is not recorded. The gate calls no LLM provider; the runs with the real LLM are recorded in [Runs with the real AI](#runs-with-the-real-ai):

| Fact | Value |
|---|---|
| Gate run | `run-gate.sh` at the commit `86910f4`, with the case set `escalation/interim-v2`, from 22:40:52 to 22:56:52 (UTC+7), exit status 0. Passed: 41 of 41 cases, the three checks on the candidate, and the guardrail tests (55 of `ai-service`, 22 of `backend`) with no failure, error, or skip. The LLM step of the gate recorded 24 calls, one for each case that expects a draft, and sent none to a provider |
| Record in git | [`gate-run.json`](../eval/releases/release-2026-11-23-01/gate-run.json), in `supportiq-gate-run/interim-2`, SHA-256 `d7fa06ed3f34d490b0df44dfbdbe112a14c6ce263fc338216643b548960a1d5c`, committed in `9f5b584` |
| Published manifest | [`release-manifest.json`](../eval/releases/release-2026-11-23-01/release-manifest.json), SHA-256 `751edd44cff4deaf09704fcf1f283b76900a7251bb4c6dcf38f74c7c54916a3f`, committed in `9f5b584`. It equals the manifest of the candidate (SHA-256 `f7b34762d984f26ff409c9c0a9148137e1201065adc9bd4482fdcbe348775ff9`) apart from `gate_run` |
| Assets that did not change | The model, the prompts, and the routing have the versions, paths, and SHA-256 values of `release-2026-11-18-02`, as the [gate design](../docs/design/gate-for-a-release-with-kb-documents.md#data-57-item-2-against-release-2026-11-18-02) requires. The encoder files of the index also have the paths and SHA-256 values of that release |
| Archive | 324316560 bytes, SHA-256 `6df4d02b226bc2cf788a018737d51f6e2a5e11a8f0e401355d720e52359d78e6`. GitHub reports the same digest for the uploaded asset |
| Pinned file | `release_id=release-2026-11-23-01` and `archive_size_bytes=324316560`, committed in `689575a` |
| GitHub Release | Tag `release-2026-11-23-01`, published at 2026-11-23T16:19:00Z, the latest release, not a draft or a prerelease. Its only asset is `release-2026-11-23-01.tar.gz`, in the state `uploaded`, of 324316560 bytes |
| Tag | First created on `67d8fc4`, then the tip of `main`, which does not hold the manifest. The project lead moved it to `9f5b584`, which holds the published manifest byte for byte; the public API showed it there at 23:31:35 (UTC+7). The asset did not change. `target_commitish` still says `main` |
| Immutable release | `immutable: false`, by the project lead's decision of 2026-11-23 |
| `download-release --yes` | Downloaded and checked the release |
| Download folder | `$HOME/.cache/supportiq/releases/release-2026-11-23-01`: 18 files with mode `0644`, folders with mode `0755`, no entry of another type, and the same files as the published release folder (`diff -rq`) |
| `check-pinned-release --remote` | `github=checked`, and the same when run again after the tag was moved |

The download folders are recorded with the home folder written as `$HOME`.

### Runs by hand

These runs are recorded here without any value of a secret ([release download and Modal deploy design, Testing and evaluation](../docs/design/release-download-and-modal-deploy.md#testing-and-evaluation)).

Steps 1 and 3, and step 2 without the token, run before the implementation PR of [#41](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/41) is ready. The project lead decided on 2026-11-25 that the download with a token (step 2) and steps 4, 5, and 6 follow the merge, before step 7, because the redeploy to Modal and Render comes after the merge. [#41](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/41) stays open until they are recorded. Until then, three things are unproven, because none is recorded: a Modal deploy of this app, the refusal of a deploy without the Secret, and the paid tier of the Gemini key. No real key of a deployment is used before step 5 is recorded:

| Step | Run | Date | Result |
|---|---|---|---|
| 1 | `pack-release --pin` of the published folder of `release-2026-11-18-02`, twice, with the same SHA-256 of the archive both times ([Publish a release](#publish-a-release)) | 2026-11-23 | Passed: the same SHA-256 both times |
| 2 | The upload, then `download-release --release release-2026-11-18-02 --yes` into an empty cache, once anonymously and once with a token, and a second run that is a cache hit | 2026-11-23 | The upload, the anonymous download, and the cache hit passed. The download with a token is not run yet |
| 3 | `check-pinned-release --remote` | 2026-11-23 | Passed, exit status 0 |
| 4 | `modal deploy` with a relative `SUPPORTIQ_RELEASE_FOLDER` deploys nothing. Then `modal deploy` without the Secret: record what Modal does, refuse the deploy or fail the container with `settings.invalid` in its logs, which also answers when Modal checks the required keys | | Not run yet |
| 5 | The tier of the Gemini key's project is a paid tier, checked by eye in AI Studio ([Once](#once), step 3): "paid tier checked" | | Not run yet |
| 6 | `modal deploy` with the Secret and the downloaded folder: Modal builds `ai-service/Dockerfile` and runs its runtime next to `/opt/venv`; `GET /health/live` and `GET /health/ready` answer `204` without a token, and `POST /v1/analyses` without a token answers `401` ([ADR-0018, Validation](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#validation)) | | Not run yet |

Before the PR, the path from `backend` to `ai-service` is proven by the local run with AI on the pinned release ([local run design](../docs/design/local-run.md)).

After the merge, with the first run of the workflow `deploy` on `main`. `deploy.yml` runs only by hand, and its job `deploy-migrate` stops on any other ref, so no `backend` with this code reaches Render before the merge:

| Step | Run | Date | Result |
|---|---|---|---|
| 7 | `backend` on Render with `AI_SERVICE_BASE_URL` and `AI_SERVICE_TOKEN`: a ticket of a demo customer gets an analysis and a routing recommendation in the console. With `release-2026-11-18-02` it abstains or escalates without an LLM call | | Not run yet |

### Measurements

The measurements of [ADR-0018, Validation](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#validation). No number is recorded before it is measured.

| Measurement | How | Date | `release_id` | Value |
|---|---|---|---|---|
| Cold start | The time of the first `GET /health/ready` after more than 20 minutes without a request, with `curl` from the deploying machine, and `duration_ms` of `model.loaded` in the Modal logs | | | Not measured yet |
| Latency of `createAnalysis` | `analysis_ms` of the responses and the duration of `request.completed` in the Modal logs. This is not the path from Render ([Open questions](#open-questions)) | | | Not measured yet |
| Memory in use | As Modal reports it for the container | | | Not measured yet |

The latency and the cost of a draft are not measured yet. `release-2026-11-18-02` makes no LLM call, and the drafts of `release-2026-11-23-01`, which serves KB documents, are not measured on the Modal deployment yet.

### Roll back on Modal

Download the previous release with `download-release --release <release_id>` and deploy it again ([Each deploy](#each-deploy)). Its archive is still on GitHub, because no archive is ever deleted. To stop the AI part instead, stop the app `supportiq-ai-service` in the Modal dashboard: `backend` falls back to manual handling. To make the local run take the previous release, revert the commit of the pinned file.

## PostgreSQL checks

Run these when the project is created, before the first deploy ([ADR-0016, PostgreSQL on Supabase](../docs/decisions/0016-hosting-on-free-tiers.md#postgresql-on-supabase), item 3).

| Check | Result |
|---|---|
| Both roles log in through the session pooler | Not run yet |
| A connection without TLS is refused, after "Enforce SSL on incoming connections" is on | Not run yet |
| `psql` with `sslmode=verify-full` and the root authority of `backend/certs/` reaches the session pooler (`select 1`) | Passed on 2026-11-17 |
| The TLS handshake of Python with the root authority of `backend/certs/` passes for the session pooler: Python checks certificates more strictly than `psql` | Passed on 2026-11-17 |
| `backend migrate` with `DATABASE_TLS=verify-full` reaches the session pooler | Not run yet |
| The pool of `backend`, 5 connections plus 10 overflow, fits the pool size of `supportiq_app`, 15 by default | Not run yet |
| The PostgreSQL major version is 17, the version that CI tests | Not run yet |
| The keep-alive keeps the project out of the pause after 1 week without activity | Not run yet |

## First-deploy checklist

The checks of [ADR-0016, Validation](../docs/decisions/0016-hosting-on-free-tiers.md#validation), and two of later decisions.

| Check | Result |
|---|---|
| The workflow migrates before it calls the deploy hook, and Render shows the migrated commit as deployed | Not run yet |
| A failed migration deploys nothing | Not run yet |
| Sign-in sets the cookie on the Pages origin | Not run yet |
| A write with another `Origin` returns `403` | Not run yet |
| A trace of one request is visible in Grafana Cloud | Not run yet |
| The measurement of ADR-0016, Context, repeated through the Function of this deployment | Not run yet |
| With the keep-alive paused for 17 minutes, opening the app sends the wake request, and sign-in succeeds once `backend` runs ([backend wake-up design](../docs/design/backend-wake-up.md#testing-and-evaluation)) | Not run yet |
| The NFR-08 load test against the deployed demo, with the sign-in latency on the free instance | Not run yet |
| The suggestion progress stream stays open through the Function beyond 10 000 ms ([ADR-0022](../docs/decisions/0022-server-sent-events-for-suggestion-progress.md#decision), statement 8) | Not run yet |
| `backend` starts with the named-entity model, and its memory and the p95 of pseudonymization fit the free instance ([ADR-0017](../docs/decisions/0017-named-entity-model-from-its-release-url.md#validation)) | Not run yet |

## Removal of the application of `main`

[ADR-0021](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#removal-of-the-application-of-main) removes the application of `main`. `apps/frontend` never entered this tree ([ADR-0028](../docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md#what-is-not-brought)), and [ADR-0031](../docs/decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md) retires `apps/backend` and `apps/demo` through PR #47, now [#48](https://github.com/ml-system-design-nhom-5/SupportIQ/pull/48). Its checklist is the condition of the PR into `main`: that PR opens only when every row names its proof ([ADR-0031, The checklist of ADR-0021](../docs/decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md#the-checklist-of-adr-0021)). The proofs are recorded here, because an accepted ADR is not edited ([documentation handbook, ADRs](../docs/README.md#adrs)).

### Rows covered by existing tests

These rows are covered by the tests below (ADR-0021, Removal of the application of `main`, statement 3). Every row is also covered by the contract tests of `backend`: `backend/tests/contract/test_operations.py`, `backend/tests/contract/test_permissions.py`, and `backend/tests/contract/test_schemathesis.py`.

| Row of the checklist | Tests of `backend` | Tests of `frontend` |
|---|---|---|
| Sign-in and sessions | `backend/tests/integration/accounts/test_sign_in.py`, `backend/tests/integration/accounts/test_sessions.py`, `backend/tests/unit/accounts/test_sign_in.py`, `backend/tests/unit/accounts/test_session_rules.py`, `backend/tests/unit/accounts/test_session_use_cases.py` | `frontend/src/features/session/components/sign-in-page.test.tsx`, `frontend/src/features/session/components/require-session.test.tsx`, `frontend/src/features/session/components/sign-out-button.test.tsx`, `frontend/src/features/session/model/session.test.ts`, `frontend/e2e/session.spec.ts` |
| Shop: products, orders, customer tickets | `backend/tests/integration/commerce/test_shop.py`, `backend/tests/integration/tickets/test_create_shop_ticket.py`, `backend/tests/integration/tickets/test_read_shop_tickets.py`, `backend/tests/integration/tickets/test_idempotent_ticket_creation.py`, `backend/tests/unit/commerce/test_shop_use_cases.py`, `backend/tests/unit/tickets/test_shop_tickets.py` | `frontend/src/features/shop-catalog/components/products-page.test.tsx`, `frontend/src/features/shop-catalog/components/product-page.test.tsx`, `frontend/src/features/shop-orders/components/orders-page.test.tsx`, `frontend/src/features/shop-orders/components/order-page.test.tsx`, `frontend/src/features/shop-support/components/support-page.test.tsx`, `frontend/src/features/shop-support/components/order-support-section.test.tsx`, `frontend/src/features/shop-support/components/order-support-sending.test.tsx`, `frontend/e2e/shop-catalog.spec.ts`, `frontend/e2e/shop-order.spec.ts` |
| Admin: accounts, role and status changes | `backend/tests/integration/accounts/test_account_list.py`, `backend/tests/integration/accounts/test_account_changes.py`, `backend/tests/integration/accounts/test_account_creation.py`, `backend/tests/integration/accounts/test_password_reset.py`, `backend/tests/integration/accounts/test_account_change_concurrency.py`, `backend/tests/integration/guardrails/test_admin_boundary.py`, `backend/tests/unit/accounts/test_admin_rules.py`, `backend/tests/unit/accounts/test_admin_use_cases.py` | `frontend/src/features/admin-accounts/components/accounts-page.test.tsx`, `frontend/src/features/admin-accounts/components/accounts-page-changes.test.tsx`, `frontend/src/features/admin-accounts/components/account-dialogs.test.tsx`, `frontend/e2e/admin-accounts.spec.ts` |
| Admin: versions in use | `backend/tests/integration/suggestions/test_admin_versions.py`, `backend/tests/unit/suggestions/test_admin_versions.py` | `frontend/src/features/admin-versions/components/versions-page.test.tsx`, `frontend/src/features/admin-versions/model/versions-in-use.test.ts`, `frontend/e2e/admin-versions.spec.ts` |
| Console: ticket list, ticket, views, KB | `backend/tests/integration/tickets/test_console_queues.py`, `backend/tests/integration/tickets/test_console_workspace.py`, `backend/tests/integration/tickets/test_console_ticket_view.py`, `backend/tests/integration/suggestions/test_console_kb_document_version.py`, `backend/tests/unit/tickets/test_console_use_cases.py`, `backend/tests/unit/tickets/test_console_views.py`, `backend/tests/unit/suggestions/test_kb_document_version_read.py` | `frontend/src/features/console-tickets/components/ticket-inbox.test.tsx`, `frontend/src/features/console-tickets/components/ticket-workspace-page.test.tsx`, `frontend/src/features/console-tickets/components/ticket-workspace-sources.test.tsx`, `frontend/src/features/console-tickets/model/kb-document.test.ts`, `frontend/e2e/console-workspace.spec.ts` |
| Reports | `backend/tests/integration/reports/test_console_report_figures.py`, `backend/tests/integration/reports/test_console_report_ai_figures.py`, `backend/tests/integration/reports/test_console_report_requests.py`, `backend/tests/integration/guardrails/test_report_holds_no_customer_data.py`, `backend/tests/unit/reports/test_console_report.py`, `backend/tests/unit/reports/test_report_rules.py` | `frontend/src/features/console-reports/components/reports-page.test.tsx`, `frontend/src/features/console-reports/model/report.test.ts`, `frontend/src/features/console-reports/model/reports-access.test.ts`, `frontend/e2e/console-reports.spec.ts` |

### Runs with the real AI

Each row below is run by hand with the real AI, because CI never calls an LLM (ADR-0021, Removal of the application of `main`, statement 1). Before the PR into `main`, the rows run in the strict end-to-end round on `release-2026-11-23-01`, the first release that serves KB documents, with the local run with AI ([ADR-0031, The checklist of ADR-0021](../docs/decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md#the-checklist-of-adr-0021), statement 2). Two people grade the same drafts, and a row records counts only, never the text of a message or of a draft ([gate design, Groundedness](../docs/design/gate-for-a-release-with-kb-documents.md#groundedness); [SEC-02](../docs/rules/security-and-privacy.md#data-classification)). The runs against Render follow the merge ([Runs by hand](#runs-by-hand), step 7).

| Row of the checklist | Date | Commit | `release_id` | Steps | Result |
|---|---|---|---|---|---|
| Suggestions and drafts in the console; `apps/demo` (running the pipeline, feedback, history) | 2026-11-25 | `3a3a6d5` | `release-2026-11-23-01` | Local run with AI. A script, run by the project lead, acted in the browser. `customer-1` to `customer-3` sent 14 frozen simulated messages, one for each document version of KB v2.1, and one message with invented personal data. The `as_of` of the first and the last ticket: 01:52:56Z and 01:54:34Z. `staff-1` opened the 15 tickets and, where the AI asked for the intent, chose the one prepared for the message. Counts read from the local database in read-only sessions | 30 suggestions, 12 intents chosen by staff. 10 of the 14 messages have a draft. The other four have none: one `no_valid_document` after an LLM call, one `out_of_scope_intent`, and two `low_confidence`, where the prepared intent was not among the candidates and staff chose none. The message with personal data has none. Feedback: the row below. History: not part of the run; existing tests cover the Closed queue (`frontend/e2e/console-workspace.spec.ts`, `backend/tests/integration/tickets/test_console_queues.py`). Groundedness: Not run yet. [Limits of the run](#limits-of-the-run-of-2026-11-25) |
| FR-04, FR-06, FR-07, FR-09 | 2026-11-25 | `3a3a6d5` for the tickets, and `630a65e`, an inference, for the decisions; of the components, only `frontend/` differs | `release-2026-11-23-01` | The same 15 tickets. A second script, run by the project lead, acted in the browser from 03:37:54Z to 03:38:45Z as `staff-1` and `manager-1`: approve and send; edit and send; reject, write, and send; escalate; look for Send reply as staff on a ticket that requires authority; propose as staff and send as manager; then create one ticket with an invented address. Its reason codes for reject and escalate are its own choices, not a judgment | FR-04: no ticket had a reply before a staff action, and the 4 replies each belong to a ticket with a staff decision (2 from a draft, 1 after a rejected draft, 1 from a proposal). FR-06: 8 of the 15 tickets require authority; `staff-1` had no Send reply on the one it opened; the proposal reached the customer only after `manager-1` sent it; 0 replies to those tickets came from a role other than manager. FR-07: 5 decisions, each with its actor (approve 2, edit 1, reject 1, escalate 1), and audit entries `decision.recorded` 5, `reply.sent` 4, `reply_proposal.submitted` 1, `ticket.escalated` 1, `intent.overridden` 12, `message.pseudonymized` 31, and `suggestion.part_completed` 60. Every completed analysis and draft part (27 and 27) names `release-2026-11-23-01` and its versions; the 3 suggestions that ended `ai_service_unavailable` name none. FR-09: 31 stored requests (30 of the 15 tickets and 1 of the ticket with the address), none missing and 0 that hold an original value of their pseudonym map, with the types `EMAIL`, `NAME`, `ORDER_ID`, `PHONE`, and `ADDRESS`; the invented personal data and the invented address are in none of their requests. [Limits of the run](#limits-of-the-run-of-2026-11-25) |

#### Limits of the run of 2026-11-25

- **Groundedness is not graded.** Two graders did not grade the drafts, so NFR-04 is not measured ([DATA-46, DATA-48](../docs/rules/data-and-ml.md#evaluation-and-reporting)). The staff decisions ran before any grading, so a later grading of these drafts by two people would not be the planned one. No reading of the drafts that require authority by a person is recorded.
- **Mechanical checks are not grading.** A script without an LLM checked the 10 drafts (10 segments): 0 segments without a citation; 11 citations of KB documents, all in KB v2.1, and 0 whose snippet is not in its document; 0 segments with a number that neither its document nor the request holds; the lowest share of words in common with the cited document is 0.65. The script did not check the 25 order citations. A second script counted phrases that commit the business to a refund, a cancellation, a payment, or an exception: 0 in the 10 drafts. It is a proxy, not a reading.
- **Written after the drafts existed.** The reviewer wrote both scripts after the drafts existed, and states not to have read a text of a draft of the round; both print counts. The first was changed once, because its first version skipped drafts with order citations, and its numbers here are from the second version.
- **Commit of the decisions.** Their record names no commit. `630a65e` was committed at 03:31:13Z, the worktree was clean when the reviewer looked, the project lead then ran `start`, which rebuilds the image of `frontend` from the working tree, and the script began at 03:37:54Z. The commit is an inference.
- **`ai_service_unavailable`.** Each of the 3 suggestions that ended this way was followed by a suggestion with the trigger `retry`, which `backend` starts when staff open a ticket whose suggestion failed and can be retried ([console UI design, Flow](../docs/design/console-ui.md#flow)).
- **`message.pseudonymized`.** The 31 entries of the 15 tickets are one more than their stored requests. The extra one is not explained.
- **Reviewer's tool output.** The counts of the ticket with the address, of the commitment phrases, and of the suggestions per ticket are the reviewer's tool output of 2026-11-25, copied into the record of the run.
- **LLM use.** 12 draft parts used the LLM, with 12,994 input and 1,782 output tokens and 8,358 micro-USD. This is no measurement of cost or latency.
- **Reports.** The Reports page opened for `manager-1`. Its figures were not compared with the decisions.
- No text of a message or a draft is recorded here ([SEC-02](../docs/rules/security-and-privacy.md#data-classification)). No run against Render is recorded.

## Every month

Check that the Render free hours, the Functions requests, the database size, and the Grafana Cloud usage stay within the free limits ([ADR-0016, Validation](../docs/decisions/0016-hosting-on-free-tiers.md#validation)). Check that the Modal usage stays within the $30 credit and the spend limit, and the Gemini usage of the billing project ([Modal](#modal)).

## Roll back

Call the deploy hook with `ref` set to the previous commit. Every migration keeps the previous release working, so the database stays as it is ([ADR-0016, Migrations and one-off commands](../docs/decisions/0016-hosting-on-free-tiers.md#migrations-and-one-off-commands), item 5). `ai-service` on Modal rolls back on its own ([Roll back on Modal](#roll-back-on-modal)).

## Open questions

- `backend` has no setting for the OTLP authorization header yet ([ADR-0016, Follow-ups](../docs/decisions/0016-hosting-on-free-tiers.md#follow-ups)). Until it has, traces stay off on Render.
- Which variable of Render fills `BACKEND_BUILD_VERSION` with the deployed commit.
- Whether `backend` accepts only requests that come through the Function, and how the per-client rate limit is enforced ([ADR-0016, Open questions](../docs/decisions/0016-hosting-on-free-tiers.md#open-questions)).
- Whether the free tier of Grafana Cloud offers the Singapore region at sign-up ([ADR-0016, Platforms](../docs/decisions/0016-hosting-on-free-tiers.md#platforms)).
- Two facts of the Modal build that only the first `modal deploy` proves: that Modal builds the two-stage `ai-service/Dockerfile`, and that its runtime works next to `/opt/venv` ([Runs by hand](#runs-by-hand), step 6). If either fails, the fallback image of the [release download and Modal deploy design, Alternatives considered](../docs/design/release-download-and-modal-deploy.md#alternatives-considered) needs the project lead's approval.
- How the latency of `createAnalysis` is measured from `backend`: `ai_service.called` holds no duration, and traces are off on Render ([release download and Modal deploy design, Open questions](../docs/design/release-download-and-modal-deploy.md#open-questions)).
- How `min_containers` is turned on for a demo day, which waits for the measured cold start ([ADR-0018, Platform and scaling](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#platform-and-scaling), statement 2): a deploy with another value, or the Modal dashboard.
