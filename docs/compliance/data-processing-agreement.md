# Data Processing Agreement

**RadSpeed practice deployment. Version 1.0 draft, 22 September 2026**

**Between:** Clarity Insights Imaging Pty Ltd (ABN 92 696 493 740) ("RadSpeed")
**and:** [Practice legal name, ABN] ("Practice")

This agreement forms part of the RadSpeed order form or pilot agreement. It
sets out how RadSpeed handles the Practice's personal and health information
under the *Privacy Act 1988* (Cth), the *Health Records and Information
Privacy Act 2002* (NSW), the *Health Records Act 2001* (Vic) and equivalent
state laws where they apply to the Practice.

## 1. Roles

1. The Practice collects health information from patients and referrers and
   remains the entity accountable to patients for it.
2. RadSpeed processes that information on the Practice's behalf, only to
   provide the service described in the Terms of Use, and is itself an APP
   entity bound by the Australian Privacy Principles in respect of that
   processing.
3. RadSpeed acts on the Practice's documented instructions, which are the
   Terms of Use, this agreement and the configuration the Practice approves.

## 2. Information processed

| Category | Items | Source |
|---|---|---|
| Patient demographics | Name, date of birth, patient identifier, accession number | Practice RIS via HL7, DICOM worklist or FHIR |
| Study context | Modality, body part, referrer, reporting radiologist | Practice RIS |
| Clinical content | Dictated audio (streamed, not stored), transcript, draft and signed report text, prior report selected for comparison | Radiologist |
| Staff data | Name, email, identity-provider ID, style preferences, audit events | Practice SSO and use of the service |

## 3. Processing locations and sub-processors

RadSpeed will process the Practice's information only in Australia and only
with the sub-processors below. RadSpeed will give 30 days' written notice
before adding or replacing a sub-processor and the Practice may object on
reasonable grounds.

| Sub-processor | Service | Location | Safeguards |
|---|---|---|---|
| Amazon Web Services Australia Pty Ltd | Compute, storage, snapshots (Lightsail or EC2) | Sydney, ap-southeast-2 | Encrypted storage; ISO 27001, SOC 2, IRAP-assessed region |
| Deepgram Inc. | Streaming speech to text (Nova-3 Medical), Australian endpoint | Sydney (AWS ap-southeast-2) | `mip_opt_out` on every request: audio and transcripts retained only for the request; no model training; SOC 2 Type II |
| Amazon Bedrock (Anthropic Claude models supplied through AWS) | Report formatting, `au.` inference profile | Sydney and Melbourne regions only | No storage of prompts or outputs; no training on customer content; AWS terms |
| Google LLC or Microsoft Corporation | Single sign-on identity | Provider infrastructure | Receives staff name and email only; no patient data |

RadSpeed's own hosting is dedicated to the Practice: one dedicated instance per practice, so no other practice's data shares the database, storage or audit log.

## 4. Security measures

RadSpeed maintains the measures in its Security Statement, including:

- HTTPS with HSTS for all traffic; plain HTTP redirected.
- Practice single sign-on with the Practice's multi-factor policy; no shared
  passwords; 12-hour session limit and 30-minute idle timeout; Secure
  cookies; cross-site request rejection.
- Identifier minimisation: the language model never receives patient name,
  date of birth, patient identifier, accession or referrer.
- Start-up validation that refuses any endpoint outside Australia.
- Tamper-evident (hash-chained) audit log of every login, transcription,
  draft, edit, sign-off, amendment, export and purge, with a verification
  endpoint.
- Immutable signed reports with versioned amendments and mandatory reasons.
- Encrypted storage at rest in Sydney; secrets held outside the code
  repository; no long-lived cloud credentials in the deployment pipeline.
- Automated tests (317 unit, 50 browser, clinical evaluation set) run on
  every deployment; deployments are immutable images.

## 5. Personnel

Only Dr Mark Bekhit has administrative access
to the Practice's deployment. Access is logged. RadSpeed will remove access
within one business day when a person's role ends.

## 6. Retention and deletion

| Item | Retention | Method |
|---|---|---|
| Streamed audio | Not stored | Processed in memory only |
| Transcript awaiting formatting | Up to 30 minutes | In-memory cache, then discarded |
| Signed report copy and patient identifiers | 30 days (configurable) | Text and identifiers replaced by a purge marker; row, version chain and audit events retained |
| HL7 / DICOM SR / FHIR export files | 14 days (configurable) | Deleted by scheduled job |
| Audit log | Life of the agreement plus 7 years, or as the Practice directs | Retained without patient free text; contains identifiers only where the Practice's accession is the key |
| Server snapshots | 7 days rolling | Automatic expiry |
| Staff accounts and preferences | Life of the agreement | Deleted within 30 days of termination |

On termination RadSpeed exports any unpurged signed reports to the Practice on
request, then deletes the Practice's data and snapshots within 30 days and
confirms deletion in writing.

## 7. Data breach notification

1. RadSpeed will notify the Practice's nominated contact within **24 hours**
   of becoming aware of unauthorised access to, disclosure of, or loss of the
   Practice's information, and will provide what is known about the
   information involved, the cause, the individuals affected and the
   containment steps.
2. RadSpeed will assist the Practice to assess whether the breach is an
   eligible data breach under the Notifiable Data Breaches scheme and to
   prepare any statement to the Office of the Australian Information
   Commissioner and any notification to individuals. The Practice, as the
   entity accountable to patients, makes those notifications unless the
   parties agree otherwise in writing.
3. RadSpeed will not notify a regulator or individuals about the Practice's
   information without first consulting the Practice, except where the law
   requires RadSpeed to do so within a fixed time.

## 8. Assistance and audit

1. RadSpeed will help the Practice respond to patient access and correction
   requests that involve RadSpeed-held data within 10 business days.
2. Once a year, or after a security incident, the Practice may request
   RadSpeed's current Security Statement, test results and audit-chain
   verification output, and may commission an independent penetration test
   at its own cost with 14 days' notice.

## 9. Changes in law or service

If a change in law or in a sub-processor's service would prevent RadSpeed
from meeting this agreement, RadSpeed will notify the Practice within 10
business days and the parties will agree a remedy, failing which the Practice
may terminate without penalty.

**Signed for RadSpeed:** ______________________  Date: __________
**Signed for the Practice:** ___________________  Date: __________
