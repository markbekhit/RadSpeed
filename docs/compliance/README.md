# RadSpeed compliance pack (Australia)

Draft documents a radiology practice's privacy officer, IT team and clinical
governance committee will ask for before a RadSpeed pilot. Prepared 22
September 2026 from the compliance review and the practice profile shipped
the same day. All documents are **drafts for Dr Mark Bekhit's review**; items
in square brackets must be confirmed before any document is sent.

| Document | Audience | Purpose |
|---|---|---|
| [privacy-policy.md](privacy-policy.md) | Public (APP 1) | How RadSpeed handles personal and health information, including the automated decision-making disclosure due by 10 December 2026. |
| [terms-of-use.md](terms-of-use.md) | Practices and radiologists | Service terms, clinical responsibility, acceptable use. |
| [data-processing-agreement.md](data-processing-agreement.md) | Practice privacy officer / legal | Contract schedule covering roles, sub-processors, security, breach notification, retention and deletion. |
| [security-statement.md](security-statement.md) | Practice IT / security | Current-state security review in the format Qscan accepted for PainTrack. |
| [data-breach-response-plan.md](data-breach-response-plan.md) | Internal, shared on request | Notifiable Data Breaches scheme procedure and the retention schedule. |
| [ranzcr-ai-tool-evidence-pack.md](ranzcr-ai-tool-evidence-pack.md) | Clinical governance / DIAS accreditation | Evidence against RANZCR Standards of Practice v12 R1.12, R1.13, R1.21, R1.22, S3.7, R3.20 to R3.25, S9.3, R9.3, R10.13 to R10.17. |
| [tga-scoping-statement.md](tga-scoping-statement.md) | Practice and regulator on request | Why the dictation and formatting product is not a medical device, and how the boundary is kept. |

Rendered PDFs are built with `python tools/build_compliance_pack.py` into
`docs/compliance/build/`.

## Facts to confirm before sending

- Legal entity and ABN that supplies RadSpeed (existing material names
  **Clarity Insights Imaging Pty Ltd** for Imaging Finder; confirm the same
  entity supplies RadSpeed).
- A monitored privacy and security contact address on the radspeed.com.au
  domain.
- Cyber insurance status.
- Whether each practice gets a dedicated instance (recommended) or shares one.
