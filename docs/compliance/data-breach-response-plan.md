# RadSpeed Data Breach Response Plan and Retention Schedule

**Version 1.0 draft, 22 September 2026. Owner: Dr Mark Bekhit.**

## Part A: Data breach response

### 1. Purpose

To meet the Notifiable Data Breaches (NDB) scheme in Part IIIC of the
*Privacy Act 1988* and the 24-hour notification commitment in the Data
Processing Agreement, and to limit harm to patients and practices.

### 2. What counts as a breach

Unauthorised access to, unauthorised disclosure of, or loss of personal
information RadSpeed holds. Examples: a compromised administrator account, a
misdirected export file, an exposed backup, a provider incident, a lost
laptop with a signed-in session, or a report shown to the wrong user.

### 3. Roles

| Role | Person | Backup |
|---|---|---|
| Incident lead | Dr Mark Bekhit | [to nominate] |
| Technical response | Dr Mark Bekhit with AI-assisted engineering tooling | [to nominate] |
| Practice liaison | Dr Mark Bekhit | |
| Legal and regulator contact | [privacy lawyer to nominate] | |

### 4. Steps and time limits

| Step | Time limit | Actions |
|---|---|---|
| **Contain** | Immediately | Revoke the affected session, token or key; rotate the Bedrock, Deepgram, worklist and session secrets if in doubt; isolate or snapshot the instance for evidence before changing it; block the source. |
| **Record** | Within 4 hours | Open an incident log: what happened, when detected, systems and data involved, who is working on it. Preserve audit-log output, server logs and provider notices. |
| **Notify the practice** | Within 24 hours of awareness | Tell each affected practice's nominated contact what is known, the containment steps, and what RadSpeed needs from them. Update at least daily until closed. |
| **Assess** | Within 30 days at most; target 7 days | With the practice, decide whether the breach is likely to result in serious harm (an eligible data breach). Consider the kind of information, who may have it, whether it was encrypted, and remedial action. Record the reasoning. |
| **Notify the Commissioner and individuals** | As soon as practicable after the assessment | The practice, as the entity accountable to patients, prepares the OAIC statement (Notifiable Data Breach form) and notifies individuals; RadSpeed drafts the technical content and supplies contact lists from its records. Where RadSpeed's own account holders (radiologists, staff) are affected, RadSpeed notifies them and the OAIC itself. |
| **Remediate** | Before closing | Fix the cause, add a regression test where possible, and update this plan and the Security Statement. |
| **Review** | Within 14 days of closure | Post-incident review with the practice: timeline, what worked, what to change. |

### 5. Where the evidence is

- Audit chain: `GET /api/audit-log?accession=...` and
  `GET /api/audit-log/verify` on the affected instance.
- Container logs: `docker compose logs app` on the instance.
- Caddy access logs on the instance.
- AWS CloudTrail for account activity; Lightsail snapshots for point-in-time
  copies.
- Provider status and incident pages: Deepgram, AWS, Google, Microsoft.

### 6. Contacts

- OAIC: 1300 363 992, oaic.gov.au, NDB form.
- Australian Cyber Security Centre: 1300 292 371 (24 hours), report at
  cyber.gov.au.
- Cyber insurance: [insurer and policy number to confirm].
- Practice contacts: per Data Processing Agreement schedule.

### 7. Testing

Walk through this plan with a tabletop scenario once a year and after any
material change to hosting or integrations. Record the date and outcome here.

| Date | Scenario | Outcome |
|---|---|---|
| | | |

## Part B: Retention schedule

Retention is enforced by the service where marked "automatic". Values are
the practice-profile defaults and are adjustable per practice.

| Record | Retention | Enforcement | Basis |
|---|---|---|---|
| Streamed dictation audio | Not stored | Design | APP 11.2 data minimisation |
| Transcript awaiting formatting | 30 minutes in memory | Automatic | Operational need only |
| Draft report before sign-off | Until sign-off or next case; not persisted server-side beyond the session | Design | Draft is the radiologist's working text |
| Signed report copy, patient identifiers | 30 days, then text and identifiers replaced by a purge marker | Automatic (`RADSPEED_RETENTION_DAYS`) | Supports amendments and audit review; the RIS is the record of record, retained by the practice for the statutory period (typically 7 years for adults, longer for minors; RANZCR notes reports may be retained 20 years) |
| HL7, DICOM SR, FHIR export files | 14 days | Automatic (`RADSPEED_OUTBOX_RETENTION_DAYS`) | Integration engine has consumed them |
| Inbound HL7 orders (archive and quarantine) | 14 days | Automatic | Same |
| Audit log | Life of agreement plus 7 years, or as the practice directs | Manual export on termination | Medico-legal; contains accession keys and hashes, not report text after purge |
| Follow-up register entries | Open items kept; closed items scrubbed after 30 days | Automatic | Clinical safety while open |
| Staff accounts, preferences, vocabulary | Life of agreement; deleted within 30 days of termination | Manual | Contractual |
| Server snapshots | 7 days rolling | Automatic (Lightsail) | Recovery only; contains data as at snapshot time |
| Application logs | 14 days | Docker log rotation [to configure] | Operational; no patient text by design |
| Incident records | 7 years | Manual | NDB scheme evidence |
