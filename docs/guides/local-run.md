# Local run of the whole system

> **Status:** Active · **Owner:** project lead · **Last reviewed:** 2026-11-18

This guide starts the whole SupportIQ system on your machine with one command: PostgreSQL 17, `backend` with the simulated demo data, `frontend`, and optionally `ai-service` and the local Grafana stack. It is for testers and developers of the team. The [local run design](../design/local-run.md) records why it works this way.

## Requirements

- Linux, macOS, or Windows with WSL2. On Windows, run `deploy/local/local-run.sh` inside WSL2, with the WSL integration of Docker Desktop turned on for your distribution (Settings, Resources, WSL integration).
- bash, and Docker Engine 25 or later (the Docker API 1.44 or later) with Compose 2.20.2 or later (`docker compose`, not `docker-compose`) and BuildKit (`docker buildx`). Docker Desktop and Colima both work. On Linux, install Docker as [the Docker documentation](https://docs.docker.com/engine/install/) shows: the `docker.io` package of a distribution can be older.
- A clone of this repository. Docker Desktop and Colima share only your home folder with their virtual machine by default, so keep the clone, and a release folder, under your home folder.
- Your normal user. The script refuses to run as root or with `sudo`.

`start` checks every requirement before it changes anything. When one is missing, it names it, prints the command that installs it, and stops. It installs nothing itself.

## Start

Run this in the repository root:

```bash
deploy/local/local-run.sh start
```

1. It checks the requirements, and that the ports 5173, 8000, and the port of PostgreSQL on `127.0.0.1` are free ([The PostgreSQL port](#the-postgresql-port)).
2. When this start downloads or creates something, such as on the first start, it prints its plan and asks once: `Proceed? [y/N]`. Only `y` goes on, and `--yes` answers the question: `deploy/local/local-run.sh start --yes`. The plan names every action: creating `.local-run/` with random local passwords, building the images, creating the database with the demo data, the port of PostgreSQL, and the migrations.
3. It builds the images of `backend` and `frontend` from your working tree, one at a time, starts the parts, and waits until each one is healthy. It then prints what the setup did, such as `database.migrated` and `seed.loaded`, the URLs, the demo accounts, and how to connect to PostgreSQL.

Open <http://localhost:5173> or <http://127.0.0.1:5173>.

The first start builds the images and takes the longest. A later start that downloads and creates nothing asks no question: it prints one line, rebuilds the images from the cache, runs the pending migrations, and keeps the data of the database. When a file that an image installs its dependencies from changed, for example after a `git pull`, that rebuild downloads every package of that image again, without a question. These files are `pyproject.toml`, `uv.lock`, and `README.md` of `backend/` and of `ai-service/`, and `package.json`, `pnpm-lock.yaml`, and `pnpm-workspace.yaml` of `frontend/`. In a test run, a change of `ai-service/README.md` made the next start with AI take 1386 s, because the image downloaded torch again. When the local run already runs in the same mode, `start` prints the URL and changes nothing: the parts keep the code of their last start. To run the changes of your working tree, run `stop`, then `start`.

Ctrl+C during `start` stops the parts that this start launched, keeps the data, and ends with status 130.

## Demo accounts

The demo data is the simulated seed of `backend` ([backend README, Demo accounts](../../backend/README.md#demo-accounts)).

| Login name | Role | Password |
|---|---|---|
| `customer-1`, `customer-2`, `customer-3` | `customer` | `SEED_PASSWORD_CUSTOMER` |
| `staff-1`, `staff-2` | `staff` | `SEED_PASSWORD_STAFF` |
| `manager-1`, `manager-2` | `manager` | `SEED_PASSWORD_MANAGER` |
| `admin-1`, `admin-2` | `admin` | `SEED_PASSWORD_ADMIN` |

The first start generates each password into `.local-run/secrets.env`, which git ignores and only you can read. `start` never prints a password, and a `SEED_PASSWORD_*` of your shell does not replace one. To read the four, run:

```bash
grep '^SEED_PASSWORD_' .local-run/secrets.env
```

## The PostgreSQL port

PostgreSQL listens on `127.0.0.1:5434` by default, so a PostgreSQL of your own on 5432, or the cluster of the backend README on 5433, keeps its port. To use another port, set `LOCAL_DB_PORT` before `start`:

```bash
LOCAL_DB_PORT=5440 deploy/local/local-run.sh start
```

- `start` stops when the value is not a port number from 1 to 65535, or when the port is taken. It never picks another port by itself.
- The start that creates the database records its port in `.local-run/db-port`. A later start with another port warns that every tool connected to the old port, such as `psql` or a test run, must change, and asks the question again.
- The last message of `start` gives the connection: host `127.0.0.1`, the port, the database `supportiq`, and the user `supportiq_owner`, whose password is `LOCAL_DB_OWNER_PASSWORD` in `.local-run/secrets.env`.

## Modes

### Without AI

This is the default. No `ai-service` runs, so every suggestion part ends unavailable and staff handle each ticket manually.

### With AI

```bash
deploy/local/local-run.sh start --with-ai <release folder>
```

- The release folder holds `release-manifest.json` and every file that it names, as `supportiq-release publish-candidate` writes it ([release command README, Publish](../../eval/release/README.md#publish)). The download of a published release comes with [#41](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/41); until then, use a folder that you published yourself.
- Set `GEMINI_API_KEY`, `LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS`, and `LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS` in your shell first: `ai-service` requires all three at startup ([ai-service README, Set up](../../ai-service/README.md#set-up)). `start` stops and names each missing one. The key goes only to `ai-service` and is never written to a file.
- `ai-service` checks every file of the folder against the manifest and stops when one differs or when the folder holds another file, such as a `.DS_Store` of macOS. `start` then stops before `backend` starts.
- It also needs the port 8001. The image installs torch, so it runs on Apple silicon and on Intel machines alike.
- With the first release, `release-2026-11-18-02`, no request gets a draft: each one abstains or is escalated, without an LLM call ([ai-service README, Known limits](../../ai-service/README.md#known-limits)).
- On a virtual machine with 2 CPUs and 4 GiB, the first analysis after a start took 6.4 s in one test run and 6.8 s in another, and the later ones under 1 s. `backend` waits 3 s for an analysis, so the first suggestion can show its analysis as unavailable. Staff can run the AI again on that ticket with Try AI again in the console.

### With the local Grafana stack

```bash
deploy/local/local-run.sh start --observability
```

- It adds one `grafana/otel-lgtm` container ([ADR-0007](../decisions/0007-observability-stack.md), statement 4), and `backend` sends its traces to it. Open <http://localhost:3000> and look for the traces of `backend` in the Explore view. `backend` exports no logs or metrics yet, and `ai-service` sends no span.
- It also needs the port 3000. On a virtual machine with 2 CPUs and 4 GiB, together with `ai-service`, `otel-lgtm` was healthy after 281 to 408 s in three test runs, and `start` waits for it. The telemetry stays in the container and is gone after `stop`. Grafana sends no usage statistics and installs no plugin.
- Sign in to Grafana as the user `admin`, a Grafana account of its own, not the demo account `admin-1` of SupportIQ. Its password is `LOCAL_GRAFANA_ADMIN_PASSWORD` from your shell when you set it; otherwise `start` generates one into `.local-run/secrets.env`, where `grep '^LOCAL_GRAFANA_ADMIN_PASSWORD=' .local-run/secrets.env` shows it.
- Anonymous access is off. The image `grafana/otel-lgtm:0.41.0` would let any visitor in with the role Admin (its `docker/run-grafana.sh` sets `GF_AUTH_ANONYMOUS_ENABLED=true` by default), so `compose.yaml` sets `GF_AUTH_ANONYMOUS_ENABLED=false`. Grafana listens on `127.0.0.1` only.

The options combine, for example `start --with-ai <release folder> --observability`. To change the mode, run `stop` first.

Together, the two options need more of the machine. In test runs with both, on a virtual machine of Docker with 2 CPUs and 4 GiB:

- `ai-service` was healthy after 259 to 419 s, and `otel-lgtm` after 281 to 408 s, in three runs;
- each analysis then took about 94 s, much longer than `backend` waits, so every ticket went to manual handling (`ai_service_unavailable`);
- the health check of `ai-service` took longer than its 5 s, so Compose marked it unhealthy.

With `--with-ai` alone on the same machine, the analyses took 6.4 s, then 0.26 s. Give the virtual machine more CPUs and memory (Docker Desktop: Settings, Resources; Colima: `colima stop`, then `colima start --cpu <count> --memory <GiB>`), or start one option at a time.

## Logs, status, and stop

```bash
deploy/local/local-run.sh logs
deploy/local/local-run.sh logs backend
deploy/local/local-run.sh status
deploy/local/local-run.sh stop
```

- `logs` follows the logs of every part, and `logs <part>` those of one part: `postgres`, `backend-setup`, `backend`, `frontend`, `ai-service`, or `otel-lgtm`. Ctrl+C ends only the viewing; the parts keep running.
- `status` lists each part with its state, its health, and its port.
- `stop` removes the containers and keeps the database volume, so the next start finds your data. With nothing running, it says so.

## Run the backend tests against the local database

The local PostgreSQL lets you run every test of `backend` without installing PostgreSQL. After the [backend Set up](../../backend/README.md#set-up) steps 1 and 4, while the local run runs, run this in `backend/`:

```bash
DATABASE_URL_OWNER="postgresql+asyncpg://supportiq_owner:$(sed -n 's/^LOCAL_DB_OWNER_PASSWORD=//p' ../.local-run/secrets.env)@127.0.0.1:$(cat ../.local-run/db-port)/supportiq" \
DATABASE_URL_APP="postgresql+asyncpg://supportiq_app:$(sed -n 's/^LOCAL_DB_APP_PASSWORD=//p' ../.local-run/secrets.env)@127.0.0.1:$(cat ../.local-run/db-port)/supportiq" \
uv run pytest
```

Each test worker creates and drops its own database, so the tests never touch the data of the local run.

## Compose without the script

Once `.local-run/secrets.env` exists, the same project also runs with Compose alone, in the repository root:

```bash
docker compose --file deploy/local/compose.yaml --env-file deploy/local/local-run.env --env-file .local-run/secrets.env up --build --wait
```

This builds the images in parallel, asks nothing, and does not check the ports or record the port of PostgreSQL. It runs the mode without AI only. For the profiles `ai` and `observability`, use the script: it sets the release folder and your user for `ai-service`, and the trace export of `backend` and the Grafana password for `otel-lgtm`, which Compose alone leaves unset.

## Remove the local data

`stop` deletes nothing. To start again from an empty database, run these yourself, in the repository root:

```bash
docker compose --project-name supportiq-local down --volumes
rm -r .local-run
```

Remove both together: new passwords in a new `secrets.env` do not open the database of the old volume. To also remove the images, run `docker image rm supportiq-local-backend supportiq-local-frontend`, and `supportiq-local-ai-service` if you used AI.

## When something fails

| Message | What to do |
|---|---|
| `port … on 127.0.0.1 is taken` | Stop what uses the port, such as a dev server on 5173. For PostgreSQL, set `LOCAL_DB_PORT` to a free port |
| `Docker does not run` | Start Docker Desktop, or run `colima start` |
| `Docker Compose 2.20.2 or later is needed` or `Docker Engine 25 or later is needed` | Update Docker; the message names the version that you have |
| `.local-run/secrets.env is missing, but the volume … still holds the database` | Only the passwords of the lost file open that database: remove the local data as above, then start again |
| `do not run it as root or with sudo` | Run it again as your normal user |
| `the local run already runs in another mode` | Run `stop`, then `start` with the options you want |
| `a part did not get ready` | Read its log with `logs <part>`, then run `stop` |
| `ai-service did not get ready, so backend and frontend were not started` | Read `logs ai-service`: a `release.invalid` line names the reason, such as `file_unlisted` for an extra file in the release folder. Then run `stop` |
| `another start holds .local-run/start.lock` | Wait for the other start, or remove that folder when no start runs |
| `.local-run/secrets.env lacks …` | Add the missing line, or remove the local data as above |
