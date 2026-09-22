# RadSpeed Cybersecurity Review

## Current security position and practice pilot readiness

| | |
|---|---|
| **Report date** | 22 September 2026 |
| **Application** | RadSpeed production service at radspeed.com.au, practice profile |
| **Technical owner** | Dr Mark Bekhit |
| **Practice pilot** | Dedicated instance per practice, Australian practice profile, HL7 or MWL integration |

**Current position.** We believe RadSpeed in its practice profile is safe and
secure for a radiology-practice pilot. Final approval rests with the
practice, and any further cybersecurity review is welcome. This report
outlines the controls and checks completed so far and the items to agree
before go-live.

## Executive summary

RadSpeed transcribes a radiologist's dictation, drafts a report in the
practice's template, and delivers the signed report to the practice's RIS or
PACS. Security controls are in place across staff access, data handling,
model providers, external connections, infrastructure and software
dependencies. This assessment included a full source review, a run of the
automated test suites, and non-destructive checks of the production service.

- All patient information is processed in Australia: hosting in AWS Sydney,
  speech to text on Deepgram's Sydney endpoint with model-improvement
  opt-out, and report formatting on Claude through Amazon Bedrock's
  Australian inference profile. The service refuses to start if any
  configured endpoint is outside Australia.
- Staff sign in through the practice's own single sign-on, so the practice's
  multi-factor policy applies. There is no shared password in this profile.
  Sessions expire after 12 hours and after 30 minutes of inactivity.
- The language model never receives the patient's name, date of birth,
  record number, accession or referrer. Those are replaced by placeholders
  before the request and restored afterwards.
- Every login, transcription, draft, edit, sign-off, amendment, export and
  purge is written to a hash-chained audit log with a verification endpoint.
  Signed reports are immutable; amendments are new versions with a mandatory
  reason.
- Stored report copies are scrubbed after 30 days and export files deleted
  after 14 days, automatically and with an audit entry.

**Recommended practice position.** Subject to practice review and approval,
begin with a small group of radiologists on a dedicated RadSpeed instance,
with reports pasted into the RIS or delivered by the HL7 file drop. Add the
DICOM worklist bridge once the practice's integration team is ready.

## 1. System, data and current controls

| Layer | Current production implementation |
|---|---|
| Radiologist web app | Browser workstation (FastAPI, Jinja2, vanilla JavaScript). Streaming dictation over a signed WebSocket token valid for 12 hours. |
| Application service | Single container behind a Caddy reverse proxy with automatic TLS, HSTS, nosniff, referrer policy and frame denial. Plain HTTP is redirected. |
| Data store | SQLite on the instance's persistent volume in AWS Sydney (users, reports, audit log, follow-ups). Export files in a working directory on the same volume. |
| Speech to text | Deepgram Nova-3 Medical, `api.au.deepgram.com`, `mip_opt_out=true`. AssemblyAI and Groq are refused under the Australian residency setting. |
| Report formatting | Claude Sonnet 5 via Amazon Bedrock, `au.anthropic.claude-sonnet-5`, processed only in Sydney and Melbourne. Bedrock does not store or train on prompts. |
| Integration | HL7 v2.4 file drop (inbound orders, outbound results), DICOM Basic Text SR, FHIR R4 DiagnosticReport, and an on-premise DICOM worklist bridge that pushes orders over HTTPS with a constant-time-checked shared token. |

### Information handled

- Patient demographics supplied by the RIS: name, date of birth, patient
  identifier, accession, modality, body part, referrer.
- Dictated audio (streamed, not written to disk), transcript (in memory for
  up to 30 minutes), draft and signed report text, and a prior report the
  radiologist explicitly selects for comparison.
- Staff identity from the practice's SSO: name and email.
- No medical images are stored. The optional research features that accept
  images are disabled in the practice profile.

### Current cybersecurity controls

| Control area | Current protection |
|---|---|
| Identity and access | Google or Microsoft SSO only; no shared password; per-user accounts with ownership checks on every report query; admin allow-list for server settings; 12-hour session limit, 30-minute idle timeout, Secure and HttpOnly cookies; cross-site POSTs rejected; brute-force lockout on any fallback login. |
| Data minimisation | Identifier placeholders in every model prompt (format, stream, voice-refinement and prior-comparison paths); age derived from date of birth; no patient text in application logs. |
| Data residency | Start-up validation of every configured endpoint against an Australian allow-list; refusal to start on a violation. |
| Application and network | HTTPS redirect, HSTS, nosniff, strict referrer policy, frame denial, `Cache-Control: no-store` on every authenticated page and API response, signed WebSocket tokens, rate limiting on public tools. |
| Report integrity | Explicit sign-off locks the report with a SHA-256 hash and server timestamp; amendments create a new version with a mandatory reason; exports run only against signed text; deterministic laterality, sex, anatomy and unit checks flag but never rewrite. |
| Audit | Seventeen event types in a SHA-256 hash chain; `verify_chain` detects any edited, removed or reordered row; append lock prevents forks under concurrent writes. |
| Retention | Scheduled scrub of report text and identifiers after 30 days, deletion of export files after 14 days, both audited; admin endpoint to run on demand. |
| Integration security | Constant-time bearer-token check on the worklist push endpoint, which is disabled when no token is set; field allow-list and filename sanitisation on inbound orders; oversized or malformed HL7 files quarantined. |
| Build and deploy | GitHub Actions with OpenID Connect to AWS (no long-lived keys); SSH opened only to the runner for the duration of a deploy; immutable container images; 317 unit tests, 50 browser tests and a clinical evaluation set must pass before deployment. |

## 2. Security review and practice workflow

This review used OWASP ASVS and OAIC APP 11 as its reference points. Checks
used synthetic identifiers; no real patient records were accessed.

| Review area | What was checked | Status |
|---|---|---|
| Application review | Every route, authentication boundary, data flow to external providers, storage location, export path and log statement was read and documented (22 September 2026). | Completed |
| Remediation | Findings from the review were fixed the same day: offshore provider paths, shared-password fallback, session lifetime, cache headers, plain-HTTP proxy, transcript logging, absence of retention, absence of an AI disclosure line. | Completed |
| Automated verification | 317 unit tests, 50 browser workflow tests and the clinical evaluation set pass; they run on every deployment. | Pass |
| Live service | HTTPS enforcement, HSTS, no-store on private responses, HTTP-to-HTTPS redirect and SSO sign-in observed on production. | Pass |
| Secrets and dependencies | Secrets are held outside the repository; direct dependencies reviewed against the deployed architecture. | Reviewed |
| Practice SSO | Microsoft Entra or Google Workspace tenant configuration and end-to-end validation are required before live use. | Pending |

### Practice pilot workflow

1. The practice's RIS sends orders to RadSpeed by HL7 file drop or the
   worklist bridge; radiologists select the case from the worklist.
2. The radiologist dictates; the transcript streams back and the draft report
   is generated in the practice's template.
3. The radiologist reviews, edits, runs the QA check and signs off. The
   disclosure line is added and the signed report is exported to the RIS or
   pasted into PowerScribe.
4. Amendments create a new version. The audit trail for any accession is
   available in the app and by API.

## 3. Items to agree before the pilot

| Item | Before go-live |
|---|---|
| Practice SSO | Microsoft Entra or Google Workspace application registered for the practice's tenant; admin emails nominated; revocation tested. |
| Hosting | Dedicated instance for the practice in AWS Sydney, data directory on an encrypted attached disk, snapshot schedule and retention agreed. |
| Data handling | Written acceptance of the sub-processor list (AWS, Deepgram Australia, Amazon Bedrock), the 30-day and 14-day retention values, and the breach-notification responsibilities in the Data Processing Agreement. |
| Integration | Agreed HL7 sending and receiving facility codes, outbox path, and whether DICOM SR or FHIR export is also required. |
| Operational readiness | Named support contacts, monitoring, incident process, a documented recovery exercise and practice security approval for the live pilot. |

## Ongoing security

- Maintain the automated tests, dependency review and audit-chain
  verification as release and operational controls.
- Conduct an independent external penetration test before expansion beyond
  the small pilot and after any material integration or hosting change.
- Move deployment secrets from the instance environment file to AWS Systems
  Manager Parameter Store.
- Review the access register and rotate the Bedrock, Deepgram and worklist
  tokens when personnel change.

## Residual items and planned hardening

None of the items below is exploitable in normal use. They are recorded so
the practice can weigh them.

- **Audit log is tamper-evident, not tamper-proof.** An attacker with write
  access to the database file could recompute the chain. Planned: periodic
  export of the chain head hash to write-once storage.
- **Secrets on the instance.** API keys live in a root-owned environment
  file readable by the container. Planned: Parameter Store as above.
- **System disk.** Lightsail's system disk is not encrypted; the practice
  deployment places all data on an attached disk, which is encrypted by
  default.
- **Single instance.** No high availability. Radiologists dictate into the
  RIS directly if RadSpeed is unavailable; no report is lost because none is
  finalised outside the practice's systems.
- **No external penetration test yet.** Scheduled before expansion beyond the
  pilot.

## Assessment scope

This is an internal current-state application review, not a formal
certification, legal opinion or external penetration test. AWS, Deepgram,
Amazon Bedrock, Google, Microsoft and the practice's own RIS and integration
engine were not independently audited.

## Key references

- OAIC, APP 11 Security of personal information; APP 8 Cross-border disclosure
- OWASP Application Security Verification Standard
- RANZCR Standards of Practice for Clinical Radiology v12.0 (November 2025)
- TGA, Digital scribes (updated 30 January 2026)
- Deepgram, Australia endpoint and Model Improvement Program opt-out
- AWS, Amazon Bedrock geographic cross-Region inference and data handling

Version 1.0, 22 September 2026. Reassess after material identity,
integration or hosting changes.
