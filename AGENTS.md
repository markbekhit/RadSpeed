# RadSpeed

RadSpeed is a voice transcription and reporting application for radiologists. It transcribes voice dictations and formats them into structured radiology reports using LLMs.

## Tech Stack

- **Language**: Python
- **UI**: Tkinter (cross-platform)
- **Audio**: sounddevice, soundfile, lameenc
- **LLM backends**: OpenAI API-compatible (OpenAI, Google Gemini)
- **Entry point**: `RadSpeed.py` (`VoxRad.py` remains as a compatibility wrapper)

## Project Structure

```
RadSpeed/
├── RadSpeed.py        # Entry point
├── audio/             # Voice recording and transcription
├── ui/                # Desktop UI (PyObjC)
├── llm/               # LLM integration and report formatting
├── config/            # Configuration and settings
├── utils/             # Utilities (encryption, etc.)
├── templates/         # Radiology report templates
├── guidelines/        # Medical guidelines (BIRADS, TIRADS, PIRADS, LIRADS, etc.)
└── docs/              # Documentation
```

## Workflow

This is a **solo project**. Work directly on `main` — do not create feature
branches, do not work in worktrees, do not open PRs unless the owner
explicitly asks for one.

- Pushing to `main` auto-deploys to `dictation.markbekhit.com` via fly.io
  (see CI/CD below). Always pull main before starting work
  (`git pull origin main`) so you see the actual current state of the
  codebase. The repo is large and active; assumptions about what's shipped
  based on stale branches will be wrong.
- **Always sanity-check what's actually on `main` before planning new
  features.** A lot of integration work (HL7 ORU/ORM, DICOM SR, MWL bridge,
  FHIR R4) is already shipped. Don't propose building things that exist —
  read `docs/ROADMAP.md` first, then verify against the code.
- The active product roadmap is `docs/ROADMAP.md`. Update it whenever you
  ship a phase or change strategy.

## Sandbox network & access strategy (READ FIRST)

The owner is **not a developer** and will not copy-paste logs from a browser. Codex is responsible for closing its own feedback loop. **Never** stop at "blocked by sandbox" without trying the alternatives below.

### What is reachable from this sandbox
- `api.github.com`, `github.com`, `raw.githubusercontent.com` — **directly reachable via curl/wget** (HTTP 200). Unauthenticated calls are rate-limited (60/hr); authenticated calls are 5000/hr.
- `crates.io` and the local git proxy at `127.0.0.1:38379/git/markbekhit/RadSpeed` (for git push/fetch only).
- `flyctl` works with the saved `FLY_API_TOKEN`.

### What is BLOCKED
- `cdn.playwright.dev`, `playwright.download.prss.microsoft.com` (Playwright browser downloads — HTTP 403 host_not_allowed)
- `download.mozilla.org`, `storage.googleapis.com/chromium-browser-snapshots`
- No system browsers (chromium/firefox), no apt sudo, no snap/flatpak
- Most third-party CDNs

### How to actually see GitHub Actions failures (no user copy-paste required)
1. **MCP github tools** (`mcp__github__*`) handle auth server-side — use these first for repos/PRs/issues/releases/file contents/branches. **NO workflow-run/log tools exist** in this MCP surface.
2. **Workflow self-reporting** is the canonical pattern: the workflow itself must commit diagnostics to a branch Codex can read via MCP. Use **`git clone` + `git push` with `https://x-access-token:${GITHUB_TOKEN}@github.com/...`** — NEVER use `Invoke-RestMethod` against the Contents API (it silently fails in the runner). The diagnostics branch should be `ci-diagnostics` and the file should be `ci-diag.md` so Codex reads it with one MCP call.
3. **`gh` CLI is pre-installed on GitHub-hosted runners** and auto-authenticates with `GITHUB_TOKEN`. Use it for any GitHub-API operation from inside a workflow — far more reliable than raw REST.
4. **Always upload `actions/upload-artifact@v4` with `if: always()`** including build logs (`tee` stdout/stderr into a file). User can download these directly if MCP-readable paths fail.
5. **Issues are DISABLED on this repo** — do not try to write diagnostics via `gh issue create`.

### Tauri 2.x updater format (key gotcha for this repo)
- `createUpdaterArtifacts: true` (boolean) = **v2 mode**. On Windows, NSIS is a "self-contained updater" — Tauri **does NOT create a `.nsis.zip` wrapper**. The `.exe` itself is the updater artifact and is signed directly to `RadSpeed_X.Y.Z_x64-setup.exe.sig`. `update.json` must reference the `.exe` URL.
- `createUpdaterArtifacts: "v1Compatible"` = legacy v1 mode. Tauri wraps NSIS into `.nsis.zip` + `.nsis.zip.sig`.
- The signing key must be **rsign** format (scrypt KDF), generated with `cargo tauri signer generate --ci -p ""`. The minisign `--no-password` format (`RWQ...` prefix) is rejected by Tauri.
- `TAURI_SIGNING_PRIVATE_KEY` env var contains the base64-encoded contents of the `.key` file (header + key body), NOT a file path or just the raw key line.

## Deployment & infrastructure

The owner is **not a developer** and does not use the terminal. All infrastructure operations are Codex's responsibility — never ask the owner to run terminal commands.

### Fly.io

- App name: `voxrad-v-hkvq`, region: `syd` (Sydney, Australia)
- `flyctl` is installed in the Codex environment at `/usr/local/bin/flyctl`
- **Auth token is already saved** in `.Codex/settings.local.json` as `FLY_API_TOKEN` — valid for 10 years. Codex can run `flyctl` directly in any session without asking the owner for credentials.
- Prefer `flyctl -a voxrad-v-hkvq <command>` (explicit app flag) so commands work regardless of working directory
- Volume `voxrad_data` (vol_vgn7n65eyn2eg604) is mounted at `/data` — persistent across deploys and machine replacements
- Persistent paths: `/data/users.db` (user DB), `/data/working` (templates/reports), `/data/hl7_inbox`, `/data/hl7_outbox`, `/data/sr_outbox`
- Session secret is auto-generated and persisted to `/data/session_secret.key` on first boot — users stay logged in across deploys without any manual setup
- Secrets are set via `flyctl secrets set KEY=VALUE -a voxrad-v-hkvq` — Codex does this, not the owner

### GitHub Actions CI/CD

- Deploys automatically on every push to `main` (workflow: `.github/workflows/fly-deploy.yml`)
- `FLY_API_TOKEN` is stored as a GitHub repo secret — CI can deploy without any manual steps
- The workflow: builds + pushes the Docker image, ensures `voxrad_data` volume exists, **destroys any legacy machines that lack the volume mount** (one-time migration safety), then deploys
- `fly.toml` uses `strategy = "immediate"` so a single volume is sufficient (no rolling-deploy two-machine requirement)
- To trigger a deploy: push any commit to `main`. To force a redeploy without code changes: `git commit --allow-empty -m "redeploy" && git push`

## gstack

gstack is installed globally at `~/.Codex/skills/gstack`. Use the `/browse` skill from gstack for all web browsing — never use `mcp__claude-in-chrome__*` tools.

Available skills:
- `/office-hours` — YC Office Hours: startup diagnostic + builder brainstorm
- `/plan-ceo-review` — CEO/founder plan review
- `/plan-eng-review` — Engineering plan review
- `/plan-design-review` — Design plan review
- `/design-consultation` — Design system from scratch
- `/autoplan` — Auto-review pipeline: CEO → design → eng
- `/review` — Paranoid code review
- `/ship` — One-command release with tests and PR creation
- `/land-and-deploy` — Merge → deploy → canary verify
- `/canary` — Post-deploy monitoring loop
- `/benchmark` — Performance regression detection
- `/browse` — Headless browser for QA, testing, and dogfooding
- `/qa` — Automated QA with fixes
- `/qa-only` — QA report only (no fixes)
- `/design-review` — Design audit + fix loop
- `/setup-browser-cookies` — Import cookies for authenticated browsing
- `/setup-deploy` — One-time deploy configuration
- `/retro` — Team retrospective
- `/investigate` — Systematic root-cause debugging
- `/document-release` — Auto-update docs after shipping
- `/codex` — Multi-AI second opinion via OpenAI Codex
- `/cso` — OWASP Top 10 + STRIDE security audit
- `/careful` — Warn before destructive commands
- `/freeze` — Lock edits to one directory
- `/guard` — Activate careful + freeze
- `/unfreeze` — Remove freeze
- `/gstack-upgrade` — Upgrade gstack to latest version
