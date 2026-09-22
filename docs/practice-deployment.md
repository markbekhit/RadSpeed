# Practice deployment (Australian radiology practices)

This guide sets up RadSpeed for a radiology practice that must meet the
Privacy Act 1988 (APP 8 and APP 11), the NSW and Victorian health records
laws, and the RANZCR Standards of Practice v12 requirements for AI tools.
It uses the **practice profile**, a single switch that changes RadSpeed's
defaults so that:

- audio, transcripts and report text are processed only in Australia;
- every user signs in through the practice's own single sign-on (Microsoft
  Entra or Google Workspace), so the practice's multi-factor policy applies;
- sessions expire after 12 hours and after 30 minutes without activity;
- the language model never sees the patient's name, date of birth, record
  number, accession or referrer;
- every signed report carries an "AI-assisted draft" line;
- features that generate clinical content the radiologist did not dictate
  (Impression generator, Fracture Lab) are switched off;
- stored report copies are scrubbed after 30 days and export files deleted
  after 14 days, with each purge written to the audit trail.

The default (`personal`) profile is unchanged. Nothing in this guide affects
an existing personal deployment unless `RADSPEED_PROFILE=practice` is set.

## 1. Data flow in the practice profile

| Step | Service | Where the data is processed |
|---|---|---|
| Hosting, database, exports | AWS Lightsail or EC2, Sydney | Australia |
| Live speech to text | Deepgram Nova-3 Medical, `api.au.deepgram.com` | Australia (AWS Sydney), with model-improvement opt-out |
| Report formatting | Claude on Amazon Bedrock, `au.` inference profile | Australia (Sydney and Melbourne regions only) |
| RIS / PACS integration | HL7 file drop, DICOM SR, FHIR, MWL bridge | Inside the practice network |

OpenAI's Australian data residency only stores data at rest in Australia and
still runs inference in the United States, so it is not accepted under
`RADSPEED_DATA_RESIDENCY=au`. AssemblyAI and Groq have no Australian region.
RadSpeed refuses to start in the practice profile if any configured endpoint
is outside Australia, rather than falling back silently.

## 2. Environment

Start from [`deploy/practice.env.example`](../deploy/practice.env.example).
The variables that matter:

| Variable | Purpose |
|---|---|
| `RADSPEED_PROFILE=practice` | Turns on every control below with the defaults shown. |
| `RADSPEED_DATA_RESIDENCY=au` | Only Australian endpoints may receive patient data. Add a clinic-local Whisper host with `RADSPEED_RESIDENCY_ALLOWED_HOSTS`. |
| `RADSPEED_REQUIRE_SSO=true` | The shared-password fallback is disabled. Configure `MICROSOFT_CLIENT_ID/SECRET` or `GOOGLE_CLIENT_ID/SECRET` and `OAUTH_REDIRECT_BASE_URL`. |
| `RADSPEED_ADMIN_EMAILS` | Who may change server settings and run the retention purge. |
| `RADSPEED_SESSION_MAX_AGE_SECONDS=43200` / `RADSPEED_SESSION_IDLE_TIMEOUT_SECONDS=1800` | Session limits. |
| `RADSPEED_STRICT_ORIGIN=true` | Rejects cross-site POSTs to the API. |
| `RADSPEED_MINIMISE_LLM_IDENTIFIERS=true` | Identifiers are replaced by placeholders in the model prompt and restored in the result. Age is derived from the date of birth. |
| `RADSPEED_AI_DISCLOSURE_FOOTER=true` | Adds the disclosure line at sign-off. Wording is set with `RADSPEED_AI_DISCLOSURE_TEXT`. |
| `RADSPEED_RESEARCH_FEATURES=false` | Impression generator and Fracture Lab routes answer 404 and the button is hidden. |
| `RADSPEED_RETENTION_DAYS=30` / `RADSPEED_OUTBOX_RETENTION_DAYS=14` | Retention. `0` keeps data forever. |
| `DEEPGRAM_REGION=au`, `DEEPGRAM_MIP_OPT_OUT=true` | Sydney endpoint and opt-out. |
| `RADSPEED_TEXT_PROVIDER=bedrock-anthropic`, `BEDROCK_REGION=ap-southeast-2`, `VOXRAD_TEXT_MODEL=au.anthropic.claude-sonnet-5`, `VOXRAD_TEXT_API_KEY=<Bedrock API key>` | Claude via Bedrock's Australian profile. |

## 3. AWS setup for the language model

1. In the Bedrock console (Sydney), request access to Anthropic Claude
   Sonnet 5 (or Opus 4.6) if the account has not used it before.
2. Create a long-term Bedrock API key (Bedrock console, API keys). Store it
   as `VOXRAD_TEXT_API_KEY`. Do not put it in the repository.
3. The IAM principal behind the key needs `bedrock:InvokeModel` and
   `bedrock:InvokeModelWithResponseStream` on the `au.` inference profile
   and on the foundation model in `ap-southeast-2` and `ap-southeast-4`.
   These two regions are the whole Australian geography, so requests never
   leave Australia.
4. Amazon Bedrock does not store prompts or completions and does not use
   customer content to train models. Abuse-detection storage, where it
   applies, stays in the destination region.

## 4. Server hardening checklist

These are infrastructure steps outside the application. Do them once per
practice server.

- **Encrypt data at rest.** Lightsail's attached block-storage disks are
  encrypted by default; the system disk is not. Attach a disk, mount it at
  `/opt/radspeed/data`, and keep the database and working directory there.
  On EC2 use an encrypted EBS volume.
- **Secrets.** Keep `/opt/radspeed/.env` readable only by root and the
  `docker` group, or load it from AWS Systems Manager Parameter Store at
  deploy time. Rotate the Bedrock, Deepgram and MWL tokens when staff with
  server access leave.
- **Transport.** The shipped Caddyfile serves HTTPS with HSTS and redirects
  plain HTTP (except the `/health` probe). Do not open port 8765 to the
  internet.
- **Backups.** Enable automatic snapshots and record a tested restore. Note
  that snapshots contain patient data and inherit the retention period of
  the snapshot schedule, not `RADSPEED_RETENTION_DAYS`.
- **Access register.** Keep a list of who holds the AWS account, the SSH
  key, the GitHub deploy role and the practice admin emails, and review it
  when staff change.

## 5. What the practice receives for its AI-tool file

RANZCR Standards R3.20 to R3.25 and R1.12/R1.13 require the practice to
document the scope, limitations and audit of any AI tool. RadSpeed provides:

- **Intended purpose.** RadSpeed transcribes a radiologist's dictation and
  formats it into the practice's report template. It does not interpret
  images and does not generate findings, impressions or recommendations the
  radiologist did not dictate. The radiologist reviews and signs every
  report (RANZCR S9.3, R9.3), and the disclosure line records that.
- **Regulatory status.** Transcription and formatting software without
  analysis or interpretation is not a medical device under the TGA's digital
  scribe guidance. Research features that would change that status are
  disabled in this profile.
- **Audit.** Every login, transcription, format, edit, sign-off, amendment,
  export and retention purge is written to a hash-chained audit log.
  `GET /api/audit-log/verify` confirms the chain is intact.
- **Quality checks.** Deterministic laterality, sex, anatomy and unit checks
  flag inconsistencies and never rewrite text.
- **Failure mode.** If Deepgram or Bedrock is unavailable, dictation falls
  back to nothing rather than to an offshore service; the radiologist
  dictates into the RIS as before. No report is exported without sign-off.

## 6. Retention

The purge runs hourly. Reports older than `RADSPEED_RETENTION_DAYS` have
their text and identifiers replaced by `[purged under retention policy]`;
the row, version chain and audit events remain so the audit trail still
verifies. Export files older than `RADSPEED_OUTBOX_RETENTION_DAYS` are
deleted. Admins can trigger a run with `POST /api/retention/run` and see the
policy with `GET /api/retention`. The report of record is the copy in the
practice's RIS.

## 7. Verifying a deployment

```bash
curl -s https://<host>/api/capabilities
```

should show `"profile": "practice"`, `"data_residency": "au"` and
`"research_features": false`. The server log at start-up prints the profile
summary, and refuses to start with a clear message if an endpoint is outside
Australia or SSO is not configured.
