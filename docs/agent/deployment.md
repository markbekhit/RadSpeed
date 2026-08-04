# Deployment, release, and updater rules

Read this file before changing AWS, GitHub Actions, release artifacts,
updater configuration, signing, or production secrets.

## Operating model

- Pushing `main` automatically deploys `radspeed.com.au` through
  `.github/workflows/aws-deploy.yml`. Pull and inspect `main` first.
- Use authenticated `gh` and AWS sessions directly. Never print, move, commit,
  or expose credentials.
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

## AWS production details

- Production is one AWS Lightsail server in Sydney, fronted by Caddy. ECR holds
  immutable images and Lightsail snapshots provide rollback copies.
- Persistent application data lives below `/opt/radspeed/data` on the server.
- CloudFormation in `deploy/aws/cloudformation.yml` owns the server, static IP,
  ECR repository, GitHub OIDC deployment role, and budget warning.
- GitHub Actions receives short-lived AWS credentials through OIDC. It opens
  SSH only to the current runner and closes access after deployment.
- Treat `docs/deploy-aws.md` as the detailed source of truth. Use synthetic or
  explicitly de-identified public cases for deployment checks.

## GitHub Actions deployment

- The deployment runs all quality gates, publishes an immutable image to ECR,
  deploys it to Lightsail, and verifies `/health` before succeeding.
- Preserve the temporary SSH allow-list and cleanup steps. Do not introduce
  long-lived AWS access keys into GitHub.
- Push a normal commit to deploy. Use an empty redeploy commit only when a
  code-free redeployment is genuinely required.
