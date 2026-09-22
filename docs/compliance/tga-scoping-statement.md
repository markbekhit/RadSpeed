# RadSpeed: TGA regulatory scoping statement

**Version 1.0 draft, 22 September 2026. Manufacturer: [Clarity Insights
Imaging Pty Ltd, ABN to confirm]. Prepared by Dr Mark Bekhit.**

## 1. Conclusion

RadSpeed, as supplied to Australian radiology practices in its practice
profile, is **not a medical device** under section 41BD of the *Therapeutic
Goods Act 1989* and is not required to be included in the Australian Register
of Therapeutic Goods. This statement records the reasoning, the features
that are excluded from the practice product to keep that position, and the
process for reassessing it.

## 2. Intended purpose

RadSpeed is intended to transcribe a radiologist's dictated report and format
the transcript into the practice's report template, applying the
radiologist's style preferences, for the radiologist to review, edit and
sign. It is a documentation tool. It is not intended for the diagnosis,
monitoring, prediction, prognosis, treatment or alleviation of disease, and
it does not investigate anatomy or a physiological process.

## 3. Basis

The TGA's guidance *Digital scribes* (updated 30 January 2026) states that
digital scribes intended only to transcribe and translate clinical
conversations into written records, without performing analysis or
interpretation, are not considered medical devices, because they have no
therapeutic use under the Act. It states that a scribe becomes a medical
device if it analyses or interprets clinical content, for example by
generating a diagnosis, differential diagnosis or treatment recommendation
not explicitly stated by the practitioner.

RadSpeed's practice product performs only transcription and formatting. Its
outputs contain only what the radiologist dictated, arranged in the template.
The deterministic checks (laterality, sex, anatomy, units) compare the
report against the order data and the report's own content; they do not
interpret images or generate clinical content, and they only flag.

## 4. Features excluded from the practice product

Three features in the RadSpeed code base could generate clinical content not
explicitly stated by the radiologist. They are disabled by configuration in
the practice profile (`RADSPEED_RESEARCH_FEATURES=false`), their routes
return "not found", and the interface control is removed. They are labelled
research features.

| Feature | Why excluded |
|---|---|
| Impression generator | Produces an impression from the findings text, optionally citing published guidelines (Fleischner, BI-RADS, LI-RADS, PI-RADS, TI-RADS). This is analysis of clinical content. |
| Fracture Lab | Accepts radiograph images and returns fracture probability estimates and locations. This is image analysis for diagnosis, a Class IIa or higher software medical device if supplied for clinical use. |
| Public Impressions tool on radspeed.com.au | Same function as the impression generator, offered publicly. It is not part of the practice product and carries a notice that it is not for clinical use and must not receive patient identifiers. |

The structured-assessment calculators (TI-RADS, Fleischner, adrenal washout)
implement published clinical rules the radiologist selects and populates
manually and display the published category or interval. The TGA's
*calculator software* and *digitisation of published clinical rules*
exclusions cover software of this kind. They remain available; the practice
may disable them.

## 5. Change control

Any change to RadSpeed that would cause it to generate findings,
impressions, recommendations or diagnoses not dictated by the radiologist,
or to analyse images, changes its intended purpose. Before such a change is
supplied to a practice, RadSpeed will reassess this statement and, if the
product would be a medical device, either withhold the feature from the
practice product, notify the TGA under the clinical decision support
exemption where the criteria are met, or seek ARTG inclusion. This
reassessment is recorded in the release notes.

## 6. Other obligations acknowledged

Not being a medical device does not remove other obligations. RadSpeed
complies with the *Privacy Act 1988* (see Privacy Policy and Data Processing
Agreement), supports practices' obligations under the RANZCR Standards of
Practice (see the AI-tool evidence pack), and supports radiologists'
obligations under Ahpra's guidance on AI in healthcare, including informed
patient communication and verification of every output before it enters the
record.
