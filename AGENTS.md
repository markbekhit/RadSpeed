# RadSpeed agent instructions

RadSpeed is a voice-transcription and structured-reporting application for
radiologists. Protect clinical privacy and verify behaviour with synthetic data.

## Project essentials

- Python application with Tkinter/PyObjC desktop UI, audio pipelines, and
  OpenAI-compatible text and transcription backends.
- `RadSpeed.py` is the entry point; `VoxRad.py` remains a compatibility wrapper.
- Core areas are `audio/`, `ui/`, `llm/`, `config/`, `utils/`, `templates/`,
  `guidelines/`, `web/`, and `docs/`.
- This is a solo project. Work directly on `main`; do not create branches,
  worktrees, or pull requests unless the owner explicitly asks.
- Pull `origin/main` before planning. Read `docs/ROADMAP.md` and verify the code
  before proposing work because many integrations are already shipped.
- Update `docs/ROADMAP.md` when a shipped phase or product strategy changes.

## Safety and working rules

- Never place credentials in URLs, commits, diagnostics branches, artifacts,
  or chat output. Use existing authenticated tools and secret stores.
- Never use patient information in fixtures, screenshots, evaluation cases, or
  external model calls. Use synthetic data only.
- Diagnose GitHub Actions with the authenticated `gh` CLI and Fly.io with
  `flyctl`; do not ask the owner to collect logs or run commands.
- Prefer a purpose-built connector. Use Chrome only when signed-in state is
  required, and an isolated browser for public or repeatable QA.
- Every bug fix needs a regression test.

## Read before release or infrastructure work

For deployment, Fly.io, GitHub Actions, updater signing, release artifacts, or
production secrets, read [docs/agent/deployment.md](docs/agent/deployment.md)
before making changes.

## Verification

- Python suite: `python -m unittest discover -v`
- Browser suite: `pytest e2e --browser chromium` uses an isolated mock server
  and must not call external model providers.
- Clinical evaluation: `python -m evals.clinical_quality`; `--live` may use the
  configured text provider but still requires synthetic cases.
- See `TESTING.md` for detailed layers and conventions.

Where Claude is used, `CLAUDE.md` must remain a relative symlink to this file.
