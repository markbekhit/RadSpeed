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

## Access and troubleshooting

Close the feedback loop without asking the owner to copy logs or run commands.
Use the authenticated `gh` CLI or GitHub connector for repository and Actions
data, `flyctl` for Fly.io, and the user's Chrome profile for testing that needs
signed-in browser state. Retry transient failures and use another available
tool before reporting a blocker. Never place credentials in command-line URLs,
commits, diagnostics branches, artifacts, or chat output.

### GitHub Actions diagnostics

- Inspect checks and logs directly with the authenticated `gh` CLI; use the
  GitHub connector for repository, PR, and issue context where useful.
- Workflows should upload useful build logs with `actions/upload-artifact@v4`
  and `if: always()` so failures remain diagnosable.
- Issues are disabled on this repository; do not use issues as a diagnostics
  transport.

### Tauri 2.x updater format (key gotcha for this repo)
- `createUpdaterArtifacts: true` (boolean) = **v2 mode**. On Windows, NSIS is a "self-contained updater" — Tauri **does NOT create a `.nsis.zip` wrapper**. The `.exe` itself is the updater artifact and is signed directly to `RadSpeed_X.Y.Z_x64-setup.exe.sig`. `update.json` must reference the `.exe` URL.
- `createUpdaterArtifacts: "v1Compatible"` = legacy v1 mode. Tauri wraps NSIS into `.nsis.zip` + `.nsis.zip.sig`.
- The signing key must be **rsign** format (scrypt KDF), generated with `cargo tauri signer generate --ci -p ""`. The minisign `--no-password` format (`RWQ...` prefix) is rejected by Tauri.
- `TAURI_SIGNING_PRIVATE_KEY` env var contains the base64-encoded contents of the `.key` file (header + key body), NOT a file path or just the raw key line.

## Deployment & infrastructure

The agent owns routine infrastructure operations and should not ask the owner to
run terminal commands.

### Fly.io

- App name: `voxrad-v-hkvq`, region: `syd` (Sydney, Australia)
- `flyctl` is installed at `/opt/homebrew/bin/flyctl`; prefer resolving it from
  `PATH` rather than hard-coding the location.
- Use the existing authenticated Fly.io session or environment credential. Do
  not document, print, or move the token.
- Prefer `flyctl -a voxrad-v-hkvq <command>` (explicit app flag) so commands work regardless of working directory
- Volume `voxrad_data` (vol_vgn7n65eyn2eg604) is mounted at `/data` — persistent across deploys and machine replacements
- Persistent paths: `/data/users.db` (user DB), `/data/working` (templates/reports), `/data/hl7_inbox`, `/data/hl7_outbox`, `/data/sr_outbox`
- Session secret is auto-generated and persisted to `/data/session_secret.key` on first boot — users stay logged in across deploys without any manual setup
- The agent sets required secrets with `flyctl secrets set` without echoing
  their values or committing them.

### GitHub Actions CI/CD

- Deploys automatically on every push to `main` (workflow: `.github/workflows/fly-deploy.yml`)
- `FLY_API_TOKEN` is stored as a GitHub repo secret — CI can deploy without any manual steps
- The workflow: builds + pushes the Docker image, ensures `voxrad_data` volume exists, **destroys any legacy machines that lack the volume mount** (one-time migration safety), then deploys
- `fly.toml` uses `strategy = "immediate"` so a single volume is sufficient (no rolling-deploy two-machine requirement)
- To trigger a deploy: push any commit to `main`. To force a redeploy without code changes: `git commit --allow-empty -m "redeploy" && git push`

## Browser tooling

Use a purpose-built connector first. Use Chrome when login state is required,
and a headless or isolated browser for public pages and repeatable QA. gstack
skills may be used when installed and suited to the task; they are not a reason
to avoid a better available browser tool.
