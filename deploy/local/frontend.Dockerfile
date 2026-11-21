# The local image of frontend (docs/design/local-run.md): the Vite dev server, which proxies /v1
# and /health to SUPPORTIQ_BACKEND_URL, so the session cookie stays on the page's origin. It is
# not the production image of ARCH-10 (#4). Its build context is frontend/, and BuildKit reads
# frontend.Dockerfile.dockerignore next to this file, an allow-list. The base image is pinned by
# digest (WF-20). The image holds no secret and no development credential (SEC-29).

# Node.js 24.22.2, the version of ../../.nvmrc, as a multi-platform index (amd64 and arm64).
FROM node:24.22.2-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9

# Corepack runs the pnpm of packageManager without asking, as the user `node` of the image, and
# pnpm does not offer another version: packageManager pins it.
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    npm_config_update_notifier=false
WORKDIR /srv/frontend
RUN chown node:node /srv/frontend
USER node

# The dependencies first, from the lockfile only, so a change of the code reuses this layer.
COPY --chown=node:node package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack pnpm install --frozen-lockfile
COPY --chown=node:node . .
# Pre-bundle the dependencies into the image. Otherwise the dev server bundles them at its first
# request, and on a slow machine a proxied request, such as a sign-in, waits more than 10 s.
# `vite optimize` is deprecated in Vite 8.3.5 but kept; a newer Vite without it stops this build.
RUN corepack pnpm exec vite optimize

# Inside the container the dev server listens on every interface, because a published port
# reaches it through the network interface of the container; compose.yaml publishes the port on
# 127.0.0.1 only.
EXPOSE 5173
CMD ["corepack", "pnpm", "exec", "vite", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
