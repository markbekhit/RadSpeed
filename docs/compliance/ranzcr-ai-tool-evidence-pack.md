# RadSpeed: AI-tool evidence pack for RANZCR Standards of Practice v12

**Version 1.0 draft, 22 September 2026. For the practice's clinical
governance committee and Diagnostic Imaging Accreditation Scheme file.**

The RANZCR *Standards of Practice for Clinical Radiology* v12.0 (7 November
2025) require a provider to govern, assess, audit and document every AI tool
it uses. This pack gives the practice the vendor-side evidence for each
requirement. Where the requirement is the practice's own action, the pack
says what RadSpeed supplies to support it.

## 1. Product description and intended purpose (R3.20)

**What RadSpeed does.** A radiologist dictates; RadSpeed transcribes the
speech (Deepgram Nova-3 Medical) and a language model (Claude Sonnet 5 on
Amazon Bedrock) arranges the transcript into the practice's report template
in the radiologist's style. Deterministic checks flag possible laterality,
sex, anatomy and unit inconsistencies. The radiologist reviews, edits and
signs. The signed report is exported to the RIS or pasted into PowerScribe.

**What RadSpeed does not do.** It does not read images, does not generate
findings, impressions or recommendations the radiologist did not dictate,
and does not make or suggest a diagnosis. The optional research features
that would do so are disabled in the practice profile.

**Scope and limitations.**

- Input: English dictation, radiology vocabulary, streamed at 16 kHz.
- Output: report text in the selected template. Nothing is finalised
  without the radiologist's sign-off.
- Known failure modes: transcription errors in unusual terms (mitigated by
  the practice's spelling lists and per-radiologist learned vocabulary);
  formatting that drops or moves a dictated statement (mitigated by the
  radiologist review, the clinical evaluation set, and the QA checks); an
  unavailable provider (the workflow falls back to direct RIS dictation; no
  report is lost).
- Not validated for: languages other than English; dictation by
  non-radiologists; any image interpretation.

## 2. Development, training data and validation (R3.20, R3.21, R3.22a)

RadSpeed does not train its own models.

| Component | Developer | Training data | RadSpeed's validation |
|---|---|---|---|
| Speech to text | Deepgram Nova-3 Medical, a general-purpose medical model | Deepgram's proprietary corpus; not the practice's data (opt-out enforced) | Radiology keyterm prompting; per-template spelling lists; radiologist-level accuracy review during pilot |
| Language model | Anthropic Claude Sonnet 5 via Amazon Bedrock | Anthropic's general training; not the practice's data | Clinical evaluation set of high-risk synthetic cases (laterality, side-specific pathology, negatives) run on every release; 317 unit tests including template rendering and fact preservation |
| Deterministic QA | RadSpeed | Rules only, no training | Unit tests per rule |

No independent training, validation and test split applies because no model
is trained on practice data. Overfitting is therefore not a risk; drift in a
provider's model is handled under section 6.

## 3. Interoperability and data access (R3.22b, R3.22d)

- RIS and PACS: HL7 v2.4 ORM in / ORU out by file drop; DICOM Basic Text SR
  export; FHIR R4 DiagnosticReport; DICOM Modality Worklist via an
  on-premise bridge. All are standards-based and vendor-neutral.
- Data RadSpeed can access: only the order fields the RIS supplies and the
  radiologist's dictation. RadSpeed has no access to images, the full
  patient record or billing.
- Data leaving the practice: to AWS Sydney (hosting), Deepgram Sydney
  (audio) and Amazon Bedrock Australia (transcript without identifiers).
  Nothing leaves Australia. See the Data Processing Agreement.

## 4. Impact of failure and business continuity (R3.22c, R3.22e, R3.25)

- If RadSpeed is unavailable the radiologist dictates directly into the RIS
  or PowerScribe. No report exists only in RadSpeed until signed, and signed
  reports are exported immediately.
- If a provider returns a wrong transcript or draft, the radiologist's review
  before sign-off is the control; the QA flags add a second check.
- RadSpeed never writes to the RIS without the radiologist's sign-off and
  never overwrites an existing report; amendments are new versions.
- A privacy impact summary is in the Privacy Policy and Security Statement.
  Workflow impact is measured during the pilot (turnaround time, edit rate).

## 5. Generalisability and population (R3.22f)

RadSpeed formats what the radiologist says; it does not apply a model of the
patient population. Age and sex, when supplied, are used only for wording
(for example age-appropriate normal statements) and the dictation always
takes precedence.

## 6. Software updates and monitoring (R3.23, R3.24)

- RadSpeed releases are immutable images that pass 317 unit tests, 50
  browser tests and the clinical evaluation set before deployment. Release
  notes are provided to the practice for any change affecting data handling,
  model provider or clinical output.
- Provider model changes (Deepgram, Anthropic) are pinned by model ID. A
  change of model ID is treated as a release and re-run through the
  evaluation set.
- Monitoring: the practice can see, per accession, every version and every
  event in the audit trail. The recommended practice metrics are the edit
  distance between draft and signed report, QA flags raised per 100
  reports, and turnaround time; RadSpeed can export these on request.

## 7. Clinical responsibility and reporting (S9.3, R9.3, R9.5)

- The reporting radiologist's signed report is the definitive output. The
  radiologist's name is on the report; RadSpeed is not listed as an author.
- Each signed report carries: "AI-assisted draft (RadSpeed). Reviewed and
  signed by [radiologist] on [date]."
- Electronic signature: sign-off locks the text with a hash and timestamp
  attributed to the signed-in radiologist. Amendments are distinguished from
  the original with author, time, date and reason.

## 8. Governance, audit and risk (R1.5, R1.12, R1.13, R1.21, R1.22, S3.7)

For the practice's governance file:

- **Risk classification.** Low: drafting aid with mandatory human sign-off;
  no image analysis; no autonomous output. Suggested initial audit: review
  50 consecutive signed reports against their dictation in the first month,
  then quarterly, with a threshold of zero unresolved clinically significant
  discrepancies.
- **Audit evidence RadSpeed supplies.** Per-accession version history and
  event log; audit-chain verification output; edit-rate export.
- **Regulatory status (S3.7).** Not a medical device under the TGA digital
  scribe guidance; see the TGA scoping statement. Nothing to include on the
  ARTG.
- **Ethical principles (R1.22).** RadSpeed's design follows the RANZCR
  Ethical Principles for AI in Medicine: the radiologist keeps authority and
  accountability; the tool is transparent about its role on every report;
  patient data is minimised and stays in Australia; no practice data trains
  any model; the system is auditable end to end.
- **Conflicts of interest (R1.21).** RadSpeed is developed by Dr Mark
  Bekhit, FRANZCR, who is a practising radiologist. Any use in a practice
  where he reports should be disclosed to that practice's governance
  committee.

## 9. Privacy and information security (R10.13 to R10.17)

- R10.13: encrypted transmission and storage; see Security Statement.
- R10.14: no private health information is transmitted to a publicly
  available generative AI tool. The formatting model is a private, contracted
  service in Australia that receives no identifiers. The practice's patient
  information materials should still mention the use of AI drafting tools,
  consistent with Ahpra and TGA guidance on informing patients.
- R10.15: network, connection, integrity, backup and disaster-recovery
  measures are in the Security Statement and the Data Processing Agreement.
- R10.16: the Data Breach Response Plan covers mandatory notification.
- R10.17: access is removed and data deleted at the end of the agreement, as
  set out in the Data Processing Agreement.

## 10. Staff training (R4.19)

RadSpeed provides a 30-minute onboarding session per radiologist covering
dictation, templates, the QA check, sign-off and amendments, and a one-page
quick reference. The practice records attendance for its training register.
