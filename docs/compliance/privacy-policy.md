# RadSpeed Privacy Policy

**Version 1.0, 22 September 2026**
**Operator:** Clarity Insights Imaging Pty Ltd (ABN 92 696 493 740) ("RadSpeed", "we")
**Contact:** Dr Mark Bekhit, hello@radspeed.com.au

RadSpeed is an AI-assisted dictation and report-formatting service for
radiologists. This policy explains what information we handle, why, where it
is processed, and your rights. It is written to meet the Australian Privacy
Principles (APPs) in the *Privacy Act 1988* (Cth). We are a health service
provider under that Act, so it applies to us regardless of our size.

## 1. Who this policy covers

- **Radiologists and practice staff** who sign in to RadSpeed.
- **Patients** whose imaging reports are drafted through RadSpeed. Patients
  do not use RadSpeed directly. Their information reaches us only from the
  radiology practice that has engaged us and only to draft that practice's
  report.
- **Visitors** to radspeed.com.au and users of the free public tools.

## 2. What we collect

**From radiologists and staff:** name, email address and identity-provider
account identifier (Google or Microsoft), reporting style preferences, learned
vocabulary, templates, and an audit record of actions taken in the service.

**From practices, about patients (practice deployments):** the dictated audio
and transcript, the formatted report, and the patient details the practice's
radiology information system supplies with the order: name, date of birth,
patient identifier, accession number, modality, body part and referrer. This
is health information and sensitive information under the Act.

**From website visitors:** standard server logs (IP address, browser, pages
requested). The free Impressions tool processes the findings text you paste
and does not store it. Do not paste patient identifiers into public tools.

We do not collect payment card details directly; we invoice practices directly.

## 3. Why we collect it

- To transcribe dictation and draft a formatted report for the reporting
  radiologist to review, edit and sign.
- To deliver the signed report to the practice's own systems (HL7, DICOM SR
  or FHIR export).
- To keep a medico-legal audit trail of who drafted, edited, signed and
  amended each report.
- To operate, secure and support the service.

We do not use patient information to train or improve AI models, and our
providers are contractually or technically prevented from doing so (see
section 5).

## 4. How we use AI, and automated decisions

RadSpeed uses two kinds of artificial intelligence:

1. **Speech to text** converts dictation into a transcript.
2. **A language model** arranges the transcript into the practice's report
   template and applies the radiologist's style preferences.

Neither makes a clinical decision. Every report is a draft until the
reporting radiologist reviews and signs it. Signed reports carry the line
"AI-assisted draft (RadSpeed). Reviewed and signed by [radiologist] on
[date]". Deterministic checks flag possible laterality, sex, anatomy and
unit inconsistencies for the radiologist; they never change the text.

*Automated decision-making disclosure (APP 1.7, in force from 10 December
2026):* RadSpeed does not use computer programs to make decisions that could
reasonably be expected to significantly affect an individual's rights or
interests. The only decisions with such an effect are clinical decisions made
by the reporting radiologist. Practice deployments can disable optional
research features (an impression generator and a fracture-analysis
workbench) that generate content the radiologist did not dictate, and those
features are off by default for practices.

## 5. Where information is processed and who receives it

**Practice deployments (Australian practice profile).** All processing of
patient information occurs in Australia:

| Processor | Role | Location |
|---|---|---|
| Amazon Web Services | Hosting, storage, backups | Sydney (ap-southeast-2) |
| Deepgram | Speech to text, Australian endpoint, model-improvement opt-out | Sydney |
| Amazon Bedrock (Anthropic Claude models) | Report formatting, Australian inference profile | Sydney and Melbourne only |
| Google or Microsoft | Sign-in identity only; receives no patient data | Provider's infrastructure |

Amazon Bedrock does not store prompts or outputs and does not use them to
train models. Deepgram retains audio only for the duration of the request.
No patient information is disclosed to an overseas recipient in a practice
deployment. Before the practice profile existed, or where a practice
explicitly chooses other providers, processing may occur in the United States;
that choice is the practice's and is recorded in its agreement with us.

**Personal (single-radiologist) deployments** may use providers the
radiologist configures, including providers outside Australia. Radiologists
using such a configuration must not enter patient identifiers.

We do not sell personal information and do not share it with advertisers.

## 6. Security

Sign-in is through the practice's own single sign-on with its multi-factor
policy. Sessions expire after 12 hours and after 30 minutes of inactivity.
All traffic is encrypted in transit (HTTPS with HSTS). Data at rest is held on
encrypted storage in Sydney. The language model does not receive the
patient's name, date of birth, record number, accession or referrer; those
are replaced by placeholders and restored after formatting. Every login,
transcription, draft, edit, sign-off, amendment, export and purge is written
to a tamper-evident audit log. Details are in our Security Statement,
available to practices on request.

## 7. Retention and deletion

The practice's radiology information system holds the report of record.
RadSpeed keeps its own copy of a signed report for 30 days to support
amendments and audit review, then replaces the report text and patient
identifiers with a purge marker while keeping the audit entries. Export files
handed to the practice's integration engine are deleted after 14 days.
Transcripts are held in memory for at most 30 minutes. Audio is not stored.
Server backups are retained for 7 days. A practice can request earlier
deletion at any time.

Account information for radiologists is kept while the account is active and
deleted within 30 days of a closure request, except audit entries that must be
retained for medico-legal reasons.

## 8. Access and correction

Patients should direct requests to see or correct their imaging report to the
radiology practice, which holds the record of record and can amend it through
the practice's normal process. Radiologists and staff can see the information
we hold about them in the service settings or by contacting us. We respond to
access and correction requests within 30 days.

## 9. Data breaches

We maintain a data breach response plan aligned with the Notifiable Data
Breaches scheme. If a breach is likely to result in serious harm, we notify
the affected practice without delay so that it can notify patients and the
Office of the Australian Information Commissioner, and we assist with that
notification. Where we are the responsible entity, we notify the Commissioner
and affected individuals ourselves.

## 10. Complaints

Contact us first at hello@radspeed.com.au. We acknowledge complaints
within 7 days and aim to resolve them within 30 days. If you are not
satisfied, you may complain to the Office of the Australian Information
Commissioner (oaic.gov.au, 1300 363 992). Patients may also contact their
state health complaints body.

## 11. Changes

We will publish changes to this policy at radspeed.com.au/privacy and notify
practices of material changes in writing at least 30 days before they take
effect.
