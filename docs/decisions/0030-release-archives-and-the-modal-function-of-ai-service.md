# ADR-0030: Release archives and the Modal function of `ai-service`

- **Status:** Accepted
- **Date:** 2026-11-23
- **Deciders:** Project lead
- **Related:** [ADR-0018](0018-hosting-of-ai-service-on-modal.md), [ADR-0021](0021-repository-layout-and-ai-ml-migration.md#release-and-the-offline-evaluation-gate), [release download and Modal deploy design](../design/release-download-and-modal-deploy.md), [local run design](../design/local-run.md), [DATA-36, DATA-56, DATA-57](../rules/data-and-ml.md#models-and-artifacts), [SEC-07](../rules/security-and-privacy.md#data-sent-to-llm-providers), [SEC-10](../rules/security-and-privacy.md#secrets), [SEC-29](../rules/security-and-privacy.md#transport-and-runtime), [ARCH-42](../rules/architecture.md#component-boundaries), [#41](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/41)

## Context

[ADR-0018](0018-hosting-of-ai-service-on-modal.md) decides that `ai-service` runs on Modal from a published release whose files are assets of GitHub Releases. Issue [#41](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/41) builds the download and the Modal app. Six facts make parts of ADR-0018 wrong or incomplete:

1. **The repository is public.** The GitHub REST API returns `"private": false` for the organization repository (checked on 2026-11-22). ADR-0018, Deploy, statement 2, requires a fine-grained token for the download, but a public release asset downloads without one. Anonymous requests have a primary rate limit of 60 requests per hour per IP address, a personal access token 5,000 per hour, and `GITHUB_TOKEN` in GitHub Actions 1,000 per hour per repository ([GitHub: Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api), read on 2026-11-23).
2. **The local run needs the same download.** The revision of 2026-11-22 of the [local run design](../design/local-run.md) runs `ai-service` by default with a release downloaded into a cache. It needs the release ID and the download size in plain text that bash 3.2 reads, before anything is installed.
3. **A release is 18 files.** `release-2026-11-18-02` holds 17 asset files and its manifest, 403,105,419 bytes in all ([`release-manifest.json`](../../eval/releases/release-2026-11-18-02/release-manifest.json)). ADR-0018, Deploy, statement 1, downloads "each asset", so every release would mean 18 uploads in the browser.
4. **Modal runs every container as root.** "Modal containers always run as root (uid 0)", and "The USER instruction is ignored" ([Modal: Existing images](https://modal.com/docs/guide/existing-images), read on 2026-11-23). [SEC-29](../rules/security-and-privacy.md#transport-and-runtime) requires non-root containers, and `ai-service/Dockerfile` sets the user `ai-service` (UID 10001).
5. **The Modal defaults do not fit `ai-service`.** By default, a container requests 0.125 CPU cores ([Modal: Resources](https://modal.com/docs/guide/resources)), takes one input at a time ([Modal: Concurrent inputs](https://modal.com/docs/guide/concurrent-inputs)), and a `@modal.web_server` waits 5 seconds for its port ([Modal: web_server](https://modal.com/docs/sdk/py/latest/web_server); all read on 2026-11-23). `ai-service` runs its two models with `MODEL_CPU_THREADS`, 2 by default. It opens its port only after it has checked the release and loaded both models. `backend` runs 5 suggestion workers in its one replica (`SUGGESTION_WORKERS_PER_REPLICA`). The cost estimate of ADR-0018, Platform and scaling, statement 2, about $16 for a month, matches the default CPU request: 0.125 × $0.0000131 × 2,592,000 s + 2 × $0.00000222 × 2,592,000 s ≈ $15.75.
6. **The terms of the Gemini API depend on billing.** [SEC-07](../rules/security-and-privacy.md#data-sent-to-llm-providers) requires a plan under which API data is not used for training and is retained as briefly as the provider allows, and asks the LLM provider ADR to record the terms that were checked. No ADR records them yet. The "Gemini API Additional Terms of Service", "Effective March 23, 2026" ([Gemini API terms](https://ai.google.dev/gemini-api/terms), which redirects to `aistudio.google.com/docs/terms`, read on 2026-11-23), state:
   - for Unpaid Services, Google uses the content to "provide, improve, and develop Google products and services and machine learning technologies", "human reviewers may read, annotate, and process your API input and output", and "Do not submit sensitive, confidential, or personal information to the Unpaid Services";
   - for Paid Services, Google "doesn't use your prompts ... or responses to improve our products", and "Google logs prompts and responses for a limited period of time, solely for detecting and preventing violations of the Prohibited Use Policy". No number of days is stated;
   - "Your access to Gemini API is a 'Paid Service' only when accessing the API through a Cloud Project associated with an active billing account."

   In AI Studio, the Projects page shows the tier of each project in the column "Billing Tier" (Free, Tier 1, Tier 2, or Tier 3), and an API key inherits "the tier limits and billing status of the project" ([AI Studio: Billing](https://aistudio.google.com/docs/billing), read on 2026-11-23).

[ARCH-42](../rules/architecture.md#component-boundaries) puts deployment configuration in `deploy/`, with two exceptions that live where their platform reads them. A Modal app is Python code that `ai-service`'s toolchain must check and test, and it deploys the image of `ai-service/Dockerfile`.

## Decision drivers

1. **Safety:** no secret enters the repository, an image, a log, or a command that a teammate copies; the server process runs as a non-root user; nothing unchecked is served; and the LLM provider does not use the prompts to improve its products ([SEC-09](../rules/security-and-privacy.md#secrets), SEC-29, [DATA-56](../rules/data-and-ml.md#models-and-artifacts), SEC-07).
2. **Traceability:** the manifest in git is the only source of trust for a release, and a published asset never changes ([DATA-36](../rules/data-and-ml.md#models-and-artifacts)).
3. **Reliability and latency:** one container serves the concurrent calls of `backend` without a second cold start, and has enough CPU for its models (NFR-08).
4. **Effort:** one upload per release in the browser, one download command for the Modal deploy and the local run, and no `gh`.
5. **Cost:** within the Modal Starter credit outside demo days.

## Considered options

1. One `tar.gz` archive per release, an optional token, and a Modal web server that starts `ai-service serve` as its own user, with 2 CPU cores, concurrent inputs, and one container.
2. Each file as its own asset, as ADR-0018 states, with a required token.
3. A Modal ASGI function that builds the application of `ai-service` in the Modal process, with the Modal defaults.

## Decision

We adopt option 1. The statements below are normative.

### Release archives

1. Each published release has exactly one GitHub Release asset, `<release_id>.tar.gz`. Its tag is the release ID itself, so no `releases/latest` lookup is needed ([CON-15](../rules/contracts.md#api-conventions)). The archive holds the manifest and every file that it names, at their paths in the release folder, as regular files only.
2. The archive is written by `supportiq-release pack-release` from a release folder whose manifest is byte for byte the one in `eval/releases/<release_id>/`. It is never packed by hand. With the same files and the same versions of Python and zlib, the command writes the same bytes ([design, The release archive](../design/release-download-and-modal-deploy.md#the-release-archive)).
3. An uploaded archive is never replaced or deleted. A changed release is a new release ID ([DATA-36](../rules/data-and-ml.md#models-and-artifacts), [ARCH-40](../rules/architecture.md#versioned-assets)).
4. The newest published release is named in git, in `eval/releases/pinned-release.txt`, with the size of its archive. GitHub's latest release is never used.
5. A publish runs in this order: pack, upload the archive, then commit and push the pinned file. CI fails a change of the pinned file when GitHub has no archive of that size for its tag.

### Download

1. One command, `supportiq-release download-release`, serves both the Modal deploy and the local run.
2. A token is optional. When `SUPPORTIQ_RELEASE_TOKEN` is set and not empty, it is sent as `Authorization: Bearer <token>` to `api.github.com` only. It is never sent after a redirect, never printed, and never written to a file. Without it, the download is anonymous.
3. The manifest in git is the source of trust. The command refuses an archive whose manifest differs from it by one byte, or that holds a member the manifest does not name, a missing member, or a member that is not a regular file. It checks every file with `verify_release` of `ai-service`, the check that `ai-service serve` runs at startup ([DATA-56](../rules/data-and-ml.md#models-and-artifacts), [CODE-52](../rules/code.md#consistency-and-change)).
4. A release becomes visible in the cache only by an atomic rename, after every check has passed. A failure leaves the cache as it was.

### The Modal function

1. The Modal app is `ai-service/modal_app.py`, next to the Dockerfile whose image it deploys, so the toolchain of `ai-service` checks and tests it. This adds a third exception to [ARCH-42](../rules/architecture.md#component-boundaries). The rest of `deploy/` keeps its place, and `deploy/README.md` holds the steps.
2. The app is named `supportiq-ai-service`. Its image is built from `ai-service/Dockerfile`. The checked release folder is added to it with `add_local_dir` and `copy=True`. The `modal` package is in the dependency group `deploy` of `ai-service`, which the Dockerfile does not install.
3. The function is a `@modal.web_server` on port 8000. It starts `ai-service serve` as the image's user `ai-service`, so the process that serves requests is not root, although Modal runs the container as root. It returns only when the port accepts a connection. When `ai-service serve` exits first, for example with `release.invalid`, the function fails at once with that exit status, so a bad release never waits for the whole startup timeout.
4. The function requests 2 CPU cores, the default of `MODEL_CPU_THREADS`, and 2 GiB of memory (ADR-0018, Platform and scaling, statement 3). The startup timeout of the web server is 300 seconds, the default `timeout` of a Modal function, instead of the 5 seconds of `@modal.web_server`. The measured cold start sets its final value.
5. The function takes up to 10 concurrent inputs. `backend` calls `ai-service` from its 5 suggestion workers and from three console and admin operations: `getConsoleKbDocumentVersion`, `getAdminVersions`, and the KB check of `recordTicketView`. The two health checks are open to anyone. 10 covers the 5 workers, a few reads, and calls of the health checks, so none of them starts a second container. The function runs at most 1 container. A request beyond that queues ([Modal: Web endpoints](https://modal.com/docs/guide/webhooks)), and `backend` times it out into manual handling.
6. The Gemini API key and the service token come only from the Modal Secret `supportiq-ai-service`, read with `modal.Secret.from_name` with both keys required. The app never sets either value, a default, or a stand-in. The model and its two prices come from the committed price file `deploy/llm-prices.env`, which the local run reads too.
7. The cost estimate of ADR-0018, Platform and scaling, statement 2, becomes, from the same price list and not measured: one warm hour costs 2 × $0.0000131 × 3,600 + 2 × $0.00000222 × 3,600 ≈ $0.11 in the base region, so the $30 credit of a month covers about 270 warm hours. One container kept running all month costs about $79, so `min_containers=1` stays limited to demo days.
8. The Modal workspace has a spend limit. "When the spend limit is reached, Modal stops workloads that would incur additional out-of-pocket charges" ([Modal: Budgets](https://modal.com/docs/guide/budgets), read on 2026-11-23). The project lead sets it on the Usage & Billing page before the first deploy, so a container that anyone keeps warm through the open health checks cannot charge more than the limit.
9. The Gemini API key of the Modal Secret belongs to a Google Cloud project with an active billing account, so its use is a Paid Service under the terms of Context, fact 6, as [SEC-07](../rules/security-and-privacy.md#data-sent-to-llm-providers) requires. No command and no look at the key tells a paid key from a free one, so the project lead checks the tier of the project by eye when the key is created, and `deploy/README.md` records "paid tier checked" with the date, never the key. This ADR records the terms of SEC-07 for the Modal deployment. The choice of Gemini as the provider stays with its own ADR ([ADR-0021, Python and dependencies](0021-repository-layout-and-ai-ml-migration.md#python-and-dependencies), statement 4). The key of the local run is decided in the [local run design](../design/local-run.md).

### Passages of ADR-0018 that this ADR replaces

| Passage of ADR-0018 | Replaced by |
|---|---|
| Overview, the edge "download with a token, checksums checked" | Download, statements 2 and 3: the token is optional; the archive is checked against the manifest in git |
| Platform and scaling, statement 2, the sentence of the estimate ("one container with 2 GiB of memory running all month costs about $16 …") | The Modal function, statement 7 |
| Deploy, the first message of the sequence diagram ("GET releases/tags/{tag}, then each asset …") and statement 1, the words "then each asset with `Accept: application/octet-stream`" | Release archives, statement 1: the one asset `<release_id>.tar.gz` is downloaded the same way, following a `302` |
| Deploy, statement 2 | Download, statement 2 |
| Deploy, statement 3, the words "the download script checks each checksum against the release manifest" | Download, statement 3 |
| Secrets, the row "The token that downloads release assets" | The token is optional, in the environment of the person who runs the download, only when that person sets it |
| Consequences, Negative, "The token that downloads release assets can read the whole organization repository" | It holds only for a person who sets a token |

The rest of ADR-0018 still holds: Modal Starter, no pinned region, scale to zero with 20 minutes warm, 2 GiB of memory, the service token in code, the open health checks, egress in code, the artifact store, and trust in Modal as a host.

## Consequences

### Positive

- One upload per release, and the same command and checks for the Modal deploy and the local run.
- A guest clones the repository and downloads a release without a GitHub account.
- The pinned file and its CI check keep `git pull` and the newest archive in step.
- The process that handles requests is not root, and no secret is in the image or in the repository.
- A concurrent call of `backend` does not start a second container, and the models get 2 cores.

### Negative

- An anonymous download shares 60 requests per hour with every other client of its IP address. A download needs 2 requests, and a token raises the limit.
- If the repository becomes private, every download needs a token again, as ADR-0018 stated.
- The archive must be downloaded whole, about 400 MB, even when one file changed. Most of it is the two weight files, which change with the model anyway.
- With 2 cores, a warm hour costs about 7 times the estimate of ADR-0018. The credit runs out sooner when containers stay warm.
- One container means requests beyond 10 queue, and a burst can time out into manual handling.
- The health checks are open, so anyone who calls them more often than every 20 minutes keeps a container warm, about $79 a month. The spend limit then stops `ai-service`, and `backend` falls back to manual handling until the next billing cycle or a higher limit.
- After its port is open, a server process that exits leaves the container without a server until Modal stops it. `backend` gets errors or timeouts and falls back to manual handling.
- The container still runs as root around the server process. Only the server process drops to its user.
- The paid Gemini key is charged for each token once a release calls the LLM. `release-2026-11-18-02` serves no KB document and makes no LLM call, so it costs $0 in tokens.
- Two parts of the Modal app are not stated in the Modal documentation and are first proved by the first deploy: the build of the two-stage `ai-service/Dockerfile`, and the Modal runtime next to the virtual environment of the image ([design, Open questions](../design/release-download-and-modal-deploy.md#open-questions)).

### Follow-ups

- ADR-0018, Follow-ups: check whether the organization repository can turn on immutable releases (DATA-36). It becomes a step of the first publish in `deploy/README.md`.
- Issue [#34](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/34), which adds `eval.yml`, moves the CI step of the pinned file together with the other checks of the release command (ADR-0021, CI, statement 7).

## Pros and cons of the options

### One archive, an optional token, a web server with its own user

- Good, because one upload per release, guests need no token, the process runs `ai-service serve` exactly as CI and the local run do, with the same startup checks and events, and the settings fit `ai-service` and `backend`.
- Bad, because a whole archive is downloaded every time, the 2 cores cost more, and two build facts wait for the first deploy.

### Each file as an asset, with a required token

- Good, because a client can download only the files it lacks, and it is what ADR-0018 states.
- Bad, because 18 uploads per release in the browser, every guest needs a token for a public repository, and the local run would need a list of assets before anything is installed.

### An ASGI function with the Modal defaults

- Good, because Modal runs the application in its own process, with fewer moving parts.
- Bad, because the application would be built outside `ai-service serve`, so the composition root would need a new public entry point and a copy of its handling of `settings.invalid` and `release.invalid` (CODE-52). With the Modal defaults, the models would get 0.125 cores, each concurrent call could start a cold container, and the server would run as root.

## Validation

- The tests of the design pass: the download refuses every unsafe or wrong archive, never sends the token after a redirect, and never prints it; the Modal app never sets a secret value ([design, Testing and evaluation](../design/release-download-and-modal-deploy.md#testing-and-evaluation)).
- The first upload of `release-2026-11-18-02` is downloaded into an empty cache and passes `verify_release`, and a second download is a cache hit without a request.
- The first `modal deploy` builds the image and serves `GET /health/ready` with `204`. A call without the service token gets `401`.
- A deploy with a wrong release folder deploys nothing. A deploy without the Secret is run once, and `deploy/README.md` records what Modal did: refused the deploy, or failed the container. Either way, `ai-service` never runs with another key.
- A release that `ai-service` refuses fails the container within seconds, with `release.invalid` in the Modal logs, not after the startup timeout.
- The cold start, the latency, and the memory in use are recorded in `deploy/README.md` (ADR-0018, Validation).
- Revisit when the repository becomes private, when the measured cold start or memory shows that 2 cores, 2 GiB, or one container do not fit, or when Modal documents the two facts that the first deploy proves.
