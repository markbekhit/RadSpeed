# Deployment, release, and updater rules

Read this file before changing Fly.io, GitHub Actions, release artifacts,
updater configuration, signing, or production secrets.

## Operating model

- Pushing `main` automatically deploys `radspeed.com.au` through
  `.github/workflows/fly-deploy.yml`. Pull and inspect `main` first.
- Use authenticated `gh` and `flyctl` sessions directly. Never print, move,
  commit, or expose credentials.
- GitHub issues are disabled. Do not use issues as diagnostics transport.
- Workflows should upload useful build logs with `actions/upload-artifact@v4`
  and `if: always()` so failures remain inspectable.

## Tauri 2 updater format

- `createUpdaterArtifacts: true` is v2 mode. On Windows, the NSIS `.exe` is the
  signed updater artifact; there is no `.nsis.zip` wrapper. `update.json` must
  reference `RadSpeed_X.Y.Z_x64-setup.exe` and its `.sig`.
- `createUpdaterArtifacts: "v1Compatible"` is legacy mode and produces the
  `.nsis.zip` plus `.nsis.zip.sig` wrapper.
- Generate the signing key in rsign/scrypt format with
  `cargo tauri signer generate --ci -p ""`. Minisign `--no-password` keys with
  an `RWQ...` prefix are rejected by Tauri.
- `TAURI_SIGNING_PRIVATE_KEY` contains the base64-encoded contents of the whole
  `.key` file, not a path or a single key line.

## Fly.io production details

- App: `voxrad-v-hkvq`; primary region: `syd`.
- Resolve `flyctl` from `PATH` and pass `-a voxrad-v-hkvq` explicitly.
- Persistent volume `voxrad_data` is mounted at `/data`. Persistent paths are
  `/data/users.db`, `/data/working`, `/data/hl7_inbox`, `/data/hl7_outbox`, and
  `/data/sr_outbox`.
- `/data/session_secret.key` is generated once and retained so sessions survive
  deployments.
- Set required secrets with `flyctl secrets set` without echoing values.

## GitHub Actions deployment

- `FLY_API_TOKEN` is stored as a repository secret.
- The deployment builds and pushes the image, ensures `voxrad_data` exists,
  removes legacy machines that lack the required volume mount, then deploys.
  Preserve that migration safeguard unless the infrastructure model changes.
- `fly.toml` uses `strategy = "immediate"` because the app has one persistent
  volume and cannot use a two-machine rolling deployment.
- Push a normal commit to deploy. Use an empty redeploy commit only when a
  code-free redeployment is genuinely required.
