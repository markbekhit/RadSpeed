"""Public radiology report template library.

This module powers the free, indexable "report templates" discovery aid at
`/report-templates`. It is a marketing/SEO surface, so it must NEVER expose the
proprietary prompt engineering, ASR spelling lexicons, or per-section
`**Instructions:**` blocks that live inside the bundled template files.

Two fields are parsed live from the real bundled templates so the catalogue
always matches the product: the exam name (`### Exam:`) and the one-line
technique (`### Technique:`). Both are plain, human-facing, non-proprietary
strings. Everything else shown on the page (typical indications, the report
section checklist, and a synthetic sample impression) is authored here as
standard, publishable radiology reference content. No patient data is used.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Optional

_BUNDLED_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "templates"
)

# Modality groups, in display order. Each stem is mapped to exactly one group.
GROUPS: list[dict] = [
    {
        "id": "mri",
        "label": "MRI",
        "blurb": "Structured MRI reporting scaffolds for neuro, body and musculoskeletal studies.",
        "stems": [
            "MRI_Brain", "MRI_Spine_Cervical", "MRI_Spine_Thoracic", "MRI_Spine_Lumbar",
            "MRI_Shoulder", "MRI_Knee", "MRI_Hip", "MRI_Ankle", "MRI_Wrist",
            "MRI_Abdomen_Liver", "MRCP", "MRI_Pelvis", "MRI_Prostate", "MRI_Breast",
        ],
    },
    {
        "id": "ct",
        "label": "CT",
        "blurb": "Section-by-section CT report structures from head to spine and angiography.",
        "stems": [
            "CT_Head_Brain", "CT_Sinuses", "CT_Neck", "CT_Chest", "HRCT_Thorax",
            "CT_Pulmonary_Angiogram", "CT_Angiography_Thoracic", "CT_Abdomen_Pelvis",
            "CT_KUB", "CT_Spine_Cervical", "CT_Spine_Thoracic", "CT_Spine_Lumbar",
        ],
    },
    {
        "id": "ultrasound",
        "label": "Ultrasound",
        "blurb": "Ultrasound and Doppler report templates for body, small parts and vascular work.",
        "stems": [
            "Ultrasound_Abdomen", "Ultrasound_Pelvis", "Ultrasound_Thyroid",
            "Ultrasound_Breast", "Ultrasound_Scrotum", "Ultrasound_Carotid_Doppler",
            "Ultrasound_Doppler_Venous",
        ],
    },
    {
        "id": "xray",
        "label": "X-ray & mammography",
        "blurb": "Plain-film and mammography report structures with concise impressions.",
        "stems": ["CXR", "Abdominal_Xray", "Mammography"],
    },
    {
        "id": "nuclear",
        "label": "Nuclear medicine & PET",
        "blurb": "Whole-body scintigraphy and PET-CT report scaffolds.",
        "stems": ["Bone_Scan", "PET_CT"],
    },
    {
        "id": "cardiac",
        "label": "Cardiac",
        "blurb": "Echocardiography reporting structure with a chamber-by-chamber checklist.",
        "stems": ["Echocardiography"],
    },
]

# The source template exam line remains visible on the page. These shorter,
# query-specific names keep unusually long source labels readable in search.
SEO_TITLES = {
    "Bone_Scan": "Whole-Body Bone Scan",
    "CT_Angiography_Thoracic": "CT Thoracic Angiography",
    "CT_KUB": "CT KUB",
    "Echocardiography": "Echocardiography",
    "Mammography": "Mammography",
    "MRCP": "MRCP",
    "PET_CT": "PET-CT",
    "Ultrasound_Carotid_Doppler": "Carotid Doppler Ultrasound",
    "Ultrasound_Doppler_Venous": "Lower Limb Venous Doppler",
}

# Curated, publishable reference layer. Keyed by template file stem.
# `indications`: one plain line of typical clinical indications.
# `sections`: the report checklist a radiologist works through — anatomy only.
# `impression`: a short, entirely synthetic sample impression.
LIBRARY: dict[str, dict] = {
    # ---- MRI ----------------------------------------------------------------
    "MRI_Brain": {
        "indications": "Headache, focal neurology, seizures, suspected stroke, tumour or demyelination.",
        "sections": [
            "Cerebral hemispheres and grey–white differentiation",
            "Ventricles, sulci and extra-axial spaces",
            "Basal ganglia, thalami and deep white matter",
            "Posterior fossa, brainstem and cerebellum",
            "Sella, pituitary and cavernous sinuses",
            "Orbits, paranasal sinuses and mastoids",
            "Vascular flow voids and, if performed, diffusion",
        ],
        "impression": [
            "No acute intracranial abnormality.",
            "Scattered non-specific white-matter foci, likely microvascular.",
            "No mass, midline shift or restricted diffusion.",
        ],
    },
    "MRI_Spine_Cervical": {
        "indications": "Neck pain, radiculopathy, myelopathy, trauma or suspected cord compression.",
        "sections": [
            "Vertebral alignment and marrow signal",
            "Intervertebral discs, level by level",
            "Spinal canal and cord signal",
            "Neural exit foramina",
            "Facet joints and posterior elements",
            "Craniocervical junction and paraspinal soft tissues",
        ],
        "impression": [
            "C5–C6 disc–osteophyte complex with mild canal narrowing.",
            "No cord signal abnormality.",
            "Mild bilateral foraminal narrowing at C5–C6.",
        ],
    },
    "MRI_Spine_Thoracic": {
        "indications": "Thoracic back pain, myelopathy, suspected lesion or cord compression.",
        "sections": [
            "Vertebral alignment and marrow signal",
            "Intervertebral discs, level by level",
            "Spinal canal and cord signal",
            "Neural exit foramina",
            "Costovertebral and facet joints",
            "Paraspinal soft tissues",
        ],
        "impression": [
            "Minor multilevel degenerative change.",
            "Normal cord calibre and signal.",
            "No focal disc protrusion or canal compromise.",
        ],
    },
    "MRI_Spine_Lumbar": {
        "indications": "Low back pain, sciatica, radiculopathy or suspected canal stenosis.",
        "sections": [
            "Vertebral alignment and marrow signal",
            "Intervertebral discs, level by level",
            "Central canal and thecal sac",
            "Lateral recesses and neural foramina",
            "Facet joints and ligamentum flavum",
            "Conus, cauda equina and paraspinal soft tissues",
        ],
        "impression": [
            "L4–L5 disc protrusion with mild central canal narrowing.",
            "Bilateral L5 lateral recess narrowing.",
            "Conus terminates normally.",
        ],
    },
    "MRI_Shoulder": {
        "indications": "Shoulder pain, suspected rotator cuff tear, instability or labral injury.",
        "sections": [
            "Rotator cuff tendons (supraspinatus, infraspinatus, subscapularis, teres minor)",
            "Long head of biceps tendon",
            "Glenoid labrum",
            "Acromioclavicular and glenohumeral joints",
            "Acromion, coracoacromial arch and subacromial space",
            "Bones, marrow and muscle bulk",
        ],
        "impression": [
            "Full-thickness supraspinatus tendon tear with mild retraction.",
            "No labral tear.",
            "Mild acromioclavicular joint osteoarthritis.",
        ],
    },
    "MRI_Knee": {
        "indications": "Knee pain, locking, instability or suspected meniscal or ligament injury.",
        "sections": [
            "Menisci (medial and lateral)",
            "Cruciate ligaments (ACL and PCL)",
            "Collateral ligaments and posterolateral corner",
            "Articular cartilage (medial, lateral, patellofemoral)",
            "Extensor mechanism and tendons",
            "Bones, marrow and joint effusion",
            "Soft tissues and popliteal fossa",
        ],
        "impression": [
            "Posterior horn medial meniscal tear.",
            "Cruciate and collateral ligaments intact.",
            "No significant joint effusion.",
        ],
    },
    "MRI_Hip": {
        "indications": "Hip or groin pain, suspected labral tear, impingement or occult fracture.",
        "sections": [
            "Acetabular labrum",
            "Articular cartilage and joint space",
            "Femoral head and neck marrow",
            "Capsule and surrounding tendons",
            "Muscles and bursae",
            "Sacroiliac joints and visualised pelvis",
        ],
        "impression": [
            "Anterosuperior acetabular labral tear.",
            "Cam-type morphology at the femoral head–neck junction.",
            "No marrow oedema to suggest fracture.",
        ],
    },
    "MRI_Ankle": {
        "indications": "Ankle pain, sprain, suspected tendon injury or osteochondral lesion.",
        "sections": [
            "Lateral, medial and syndesmotic ligaments",
            "Tendons (peroneal, tibialis posterior, flexor and extensor groups)",
            "Achilles tendon and plantar fascia",
            "Articular cartilage and osteochondral surfaces",
            "Bones, marrow and sinus tarsi",
            "Soft tissues",
        ],
        "impression": [
            "Anterior talofibular ligament sprain without full-thickness tear.",
            "Intact tendons.",
            "No osteochondral lesion.",
        ],
    },
    "MRI_Wrist": {
        "indications": "Wrist pain, suspected TFCC or ligament tear, occult fracture or ganglion.",
        "sections": [
            "Triangular fibrocartilage complex",
            "Scapholunate and lunotriquetral ligaments",
            "Carpal bones and marrow",
            "Flexor and extensor tendon compartments",
            "Median nerve and carpal tunnel",
            "Distal radioulnar and radiocarpal joints",
        ],
        "impression": [
            "Central TFCC perforation.",
            "Intact scapholunate ligament.",
            "No marrow oedema or occult fracture.",
        ],
    },
    "MRI_Abdomen_Liver": {
        "indications": "Characterisation of a liver lesion, cirrhosis surveillance or suspected metastases.",
        "sections": [
            "Liver size, contour and parenchymal signal",
            "Focal lesions with dynamic enhancement pattern",
            "Biliary tree and gallbladder",
            "Portal and hepatic veins",
            "Spleen, pancreas, adrenals and kidneys",
            "Nodes, ascites and visualised structures",
        ],
        "impression": [
            "Arterial-phase hyperenhancing lesion in segment VIII with washout.",
            "Features are consistent with hepatocellular carcinoma in this setting.",
            "Patent portal vein.",
        ],
    },
    "MRCP": {
        "indications": "Suspected choledocholithiasis, biliary obstruction or pancreatic ductal disease.",
        "sections": [
            "Intrahepatic and extrahepatic bile ducts",
            "Common bile duct calibre and filling defects",
            "Gallbladder and cystic duct",
            "Pancreatic duct",
            "Liver, pancreas and adjacent structures",
        ],
        "impression": [
            "Distal common bile duct calculus with upstream ductal dilatation.",
            "No pancreatic ductal abnormality.",
            "Gallbladder contains further calculi.",
        ],
    },
    "MRI_Pelvis": {
        "indications": "Pelvic pain, suspected gynaecological or soft-tissue pathology, or staging.",
        "sections": [
            "Uterus, endometrium and cervix (or prostate and seminal vesicles)",
            "Adnexa and ovaries",
            "Bladder and pelvic floor",
            "Rectum and sigmoid",
            "Pelvic nodes and bones",
            "Free fluid and soft tissues",
        ],
        "impression": [
            "Well-defined intramural uterine fibroid.",
            "Normal ovaries.",
            "No suspicious pelvic node or free fluid.",
        ],
    },
    "MRI_Prostate": {
        "indications": "Raised PSA, suspected prostate cancer, or active surveillance.",
        "sections": [
            "Prostate size and zonal anatomy",
            "Peripheral zone (T2, diffusion and dynamic enhancement)",
            "Transition zone",
            "PI-RADS assessment category",
            "Seminal vesicles and neurovascular bundles",
            "Pelvic nodes and bones",
        ],
        "impression": [
            "PI-RADS 4 lesion in the left peripheral zone at mid-gland.",
            "No extraprostatic extension.",
            "No suspicious pelvic lymphadenopathy.",
        ],
    },
    "MRI_Breast": {
        "indications": "High-risk screening, extent of disease, or problem-solving after other imaging.",
        "sections": [
            "Background parenchymal enhancement and fibroglandular tissue",
            "Focal masses with morphology and kinetics",
            "Non-mass enhancement",
            "Skin, nipple and chest wall",
            "Axillary and internal mammary nodes",
            "Overall MRI BI-RADS assessment",
        ],
        "impression": [
            "Irregular enhancing mass in the right upper outer quadrant with washout kinetics.",
            "MRI BI-RADS 4 — biopsy recommended.",
            "No abnormal axillary node.",
        ],
    },
    # ---- CT -----------------------------------------------------------------
    "CT_Head_Brain": {
        "indications": "Trauma, acute headache, suspected haemorrhage, stroke or raised pressure.",
        "sections": [
            "Extra-axial spaces for haemorrhage or collection",
            "Brain parenchyma and grey–white differentiation",
            "Ventricles and basal cisterns",
            "Midline and mass effect",
            "Skull, skull base and calvarium",
            "Paranasal sinuses and mastoids",
        ],
        "impression": [
            "No acute intracranial haemorrhage.",
            "No territorial infarct or mass effect.",
            "Age-appropriate involutional change.",
        ],
    },
    "CT_Sinuses": {
        "indications": "Chronic rhinosinusitis, pre-operative planning or suspected complication.",
        "sections": [
            "Maxillary, ethmoid, frontal and sphenoid sinuses",
            "Ostiomeatal complexes",
            "Nasal septum and turbinates",
            "Bony walls and skull base",
            "Orbits and adjacent structures",
        ],
        "impression": [
            "Mucosal thickening of the maxillary and ethmoid sinuses.",
            "Patent ostiomeatal complexes.",
            "Mild nasal septal deviation.",
        ],
    },
    "CT_Neck": {
        "indications": "Neck mass, suspected infection or abscess, or staging of a known malignancy.",
        "sections": [
            "Mucosal spaces and airway",
            "Salivary glands and thyroid",
            "Cervical lymph node levels",
            "Vessels and carotid spaces",
            "Bones and soft tissues",
            "Lung apices",
        ],
        "impression": [
            "Enlarged left level II lymph node with central necrosis.",
            "No airway compromise.",
            "Recommend correlation with the primary site.",
        ],
    },
    "CT_Chest": {
        "indications": "Suspected malignancy, infection, interstitial disease or nodule follow-up.",
        "sections": [
            "Lungs and airways",
            "Pleura and pleural spaces",
            "Mediastinum and hila",
            "Heart, pericardium and great vessels",
            "Nodal stations",
            "Chest wall and visualised upper abdomen",
        ],
        "impression": [
            "Solitary solid right upper lobe nodule.",
            "No mediastinal or hilar lymphadenopathy.",
            "Recommend interval follow-up per guidelines.",
        ],
    },
    "HRCT_Thorax": {
        "indications": "Suspected interstitial lung disease, bronchiectasis or small-airways disease.",
        "sections": [
            "Distribution and pattern of parenchymal disease",
            "Reticulation, ground-glass and honeycombing",
            "Traction bronchiectasis",
            "Airways and air trapping",
            "Pleura and mediastinum",
            "Bones and visualised structures",
        ],
        "impression": [
            "Basal, subpleural reticulation with honeycombing.",
            "Pattern is consistent with usual interstitial pneumonia.",
            "No pleural effusion.",
        ],
    },
    "CT_Pulmonary_Angiogram": {
        "indications": "Suspected pulmonary embolism.",
        "sections": [
            "Main, lobar, segmental and subsegmental pulmonary arteries",
            "Right heart size and interventricular septum",
            "Lung parenchyma for infarction or alternative cause",
            "Pleura and mediastinum",
            "Bones and visualised upper abdomen",
        ],
        "impression": [
            "Filling defect in the right lower lobe segmental artery, consistent with pulmonary embolism.",
            "No right heart strain.",
            "No pleural effusion.",
        ],
    },
    "CT_Angiography_Thoracic": {
        "indications": "Suspected aortic dissection, aneurysm or acute aortic syndrome.",
        "sections": [
            "Ascending aorta, arch and descending aorta calibre",
            "Intimal flap, dissection or intramural haematoma",
            "Great vessel origins",
            "Pulmonary arteries, if opacified",
            "Heart, pericardium and mediastinum",
            "Lungs, pleura and bones",
        ],
        "impression": [
            "No intimal flap to suggest dissection.",
            "Aortic calibre within normal limits.",
            "No pericardial effusion.",
        ],
    },
    "CT_Abdomen_Pelvis": {
        "indications": "Abdominal pain, suspected malignancy, infection, obstruction or staging.",
        "sections": [
            "Liver, gallbladder and biliary tree",
            "Pancreas, spleen and adrenals",
            "Kidneys, ureters and bladder",
            "Bowel and appendix",
            "Peritoneum, nodes and vessels",
            "Pelvic organs and bones",
        ],
        "impression": [
            "Uncomplicated acute appendicitis.",
            "No free intraperitoneal gas.",
            "No obstructing lesion.",
        ],
    },
    "CT_KUB": {
        "indications": "Renal colic or suspected urinary tract calculus.",
        "sections": [
            "Kidneys and collecting systems",
            "Calculi — site, size and density",
            "Ureters along their course",
            "Bladder",
            "Perinephric and periureteric stranding",
            "Visualised bowel and bones",
        ],
        "impression": [
            "Obstructing 5 mm calculus at the left vesicoureteric junction.",
            "Mild left hydroureteronephrosis.",
            "No other calculus.",
        ],
    },
    "CT_Spine_Cervical": {
        "indications": "Trauma, suspected fracture, or degenerative bony assessment.",
        "sections": [
            "Vertebral alignment and craniocervical junction",
            "Vertebral bodies and posterior elements",
            "Discs and osteophytes",
            "Central canal and neural foramina",
            "Facet joints",
            "Prevertebral and paraspinal soft tissues",
        ],
        "impression": [
            "No acute fracture or malalignment.",
            "Multilevel uncovertebral and facet degenerative change.",
            "Mild C5–C6 foraminal narrowing.",
        ],
    },
    "CT_Spine_Thoracic": {
        "indications": "Trauma, suspected fracture or degenerative bony assessment.",
        "sections": [
            "Vertebral alignment",
            "Vertebral bodies and posterior elements",
            "Discs and osteophytes",
            "Central canal and neural foramina",
            "Costovertebral and facet joints",
            "Paraspinal soft tissues",
        ],
        "impression": [
            "No acute fracture.",
            "Minor multilevel degenerative change.",
            "Normal vertebral alignment.",
        ],
    },
    "CT_Spine_Lumbar": {
        "indications": "Trauma, suspected fracture, or degenerative bony assessment.",
        "sections": [
            "Vertebral alignment",
            "Vertebral bodies and posterior elements",
            "Discs and osteophytes",
            "Central canal and lateral recesses",
            "Neural foramina and facet joints",
            "Paraspinal soft tissues",
        ],
        "impression": [
            "No acute fracture.",
            "L4–L5 facet arthropathy with mild canal narrowing.",
            "Normal alignment.",
        ],
    },
    # ---- Ultrasound ---------------------------------------------------------
    "Ultrasound_Abdomen": {
        "indications": "Right upper quadrant pain, deranged liver function or abnormal screening.",
        "sections": [
            "Liver size, echotexture and focal lesions",
            "Gallbladder and biliary tree",
            "Pancreas",
            "Spleen",
            "Kidneys",
            "Aorta and free fluid",
        ],
        "impression": [
            "Multiple mobile gallstones without wall thickening.",
            "No biliary dilatation.",
            "Normal liver echotexture.",
        ],
    },
    "Ultrasound_Pelvis": {
        "indications": "Pelvic pain, abnormal bleeding, or assessment of the ovaries and uterus.",
        "sections": [
            "Uterus size, myometrium and endometrial thickness",
            "Ovaries and adnexa",
            "Cervix",
            "Bladder",
            "Free fluid in the pouch of Douglas",
        ],
        "impression": [
            "Simple left ovarian cyst.",
            "Normal endometrial thickness.",
            "No free fluid.",
        ],
    },
    "Ultrasound_Thyroid": {
        "indications": "Palpable nodule, goitre, or abnormal thyroid function.",
        "sections": [
            "Right and left thyroid lobes",
            "Isthmus",
            "Nodules with ACR TI-RADS features",
            "Overall gland volume and vascularity",
            "Cervical lymph node levels",
        ],
        "impression": [
            "Solid hypoechoic right lobe nodule — ACR TI-RADS 4.",
            "Fine-needle aspiration recommended per guidelines.",
            "No cervical lymphadenopathy.",
        ],
    },
    "Ultrasound_Breast": {
        "indications": "Palpable lump, focal pain, or targeted assessment after mammography.",
        "sections": [
            "Focal masses with morphology and orientation",
            "Cysts and ductal changes",
            "Skin and subcutaneous tissues",
            "Axilla for lymph nodes",
            "Overall ultrasound BI-RADS assessment",
        ],
        "impression": [
            "Well-defined oval hypoechoic mass, likely fibroadenoma — BI-RADS 3.",
            "No suspicious axillary node.",
            "Short-interval follow-up recommended.",
        ],
    },
    "Ultrasound_Scrotum": {
        "indications": "Scrotal pain, palpable lump, or suspected torsion or varicocele.",
        "sections": [
            "Both testes — size, echotexture and vascularity",
            "Epididymes",
            "Focal lesions",
            "Hydrocele or other fluid",
            "Varicocele on Valsalva",
        ],
        "impression": [
            "Normal testicular size, echotexture and vascularity bilaterally.",
            "Small left varicocele.",
            "No focal testicular lesion.",
        ],
    },
    "Ultrasound_Carotid_Doppler": {
        "indications": "TIA or stroke, carotid bruit, or surveillance of known stenosis.",
        "sections": [
            "Common, internal and external carotid arteries",
            "Plaque burden and characteristics",
            "Peak systolic and end-diastolic velocities",
            "Degree of stenosis",
            "Vertebral artery flow direction",
        ],
        "impression": [
            "Mixed plaque at the right carotid bulb with 50–69% stenosis by velocity criteria.",
            "Left carotid system without significant stenosis.",
            "Antegrade vertebral flow bilaterally.",
        ],
    },
    "Ultrasound_Doppler_Venous": {
        "page_title": "Lower Limb Venous Doppler Ultrasound",
        "meta_description": (
            "Lower limb venous Doppler ultrasound report template for suspected DVT: "
            "copyable report format, required sections and synthetic sample impression."
        ),
        "lead": (
            "Use this DVT ultrasound scaffold to review the examination scope, document "
            "venous compressibility and flow, and produce a clear impression. RadSpeed can "
            "structure the same headings from natural dictation."
        ),
        "scope_note": (
            "This page covers lower limb venous Doppler for suspected DVT. It does not cover "
            "lower limb arterial Doppler."
        ),
        "indications": "Suspected deep vein thrombosis of the lower limb.",
        "sections": [
            "Common femoral vein compressibility and flow",
            "Femoral and popliteal veins",
            "Calf veins",
            "Augmentation and phasicity",
            "Superficial venous system",
        ],
        "impression": [
            "No evidence of deep vein thrombosis in the imaged left lower limb.",
            "Normal compressibility and phasic flow.",
            "Patent superficial veins.",
        ],
        "report_format": [
            "EXAM: LOWER LIMB VENOUS DOPPLER ULTRASOUND",
            "CLINICAL DETAILS: [Indication and side]",
            "TECHNIQUE: [Veins assessed and examination limitations]",
            "",
            "FINDINGS:",
            "Common femoral vein: [Compressibility and flow]",
            "Femoral vein: [Compressibility and flow]",
            "Popliteal vein: [Compressibility and flow]",
            "Calf veins: [Veins assessed and patency]",
            "Superficial veins: [If assessed]",
            "Other findings: [If present]",
            "",
            "IMPRESSION:",
            "[Presence or absence of DVT, side, site and extent]",
        ],
    },
    # ---- X-ray & mammography ------------------------------------------------
    "CXR": {
        "indications": "Cough, breathlessness, chest pain, sepsis, or line and tube position.",
        "sections": [
            "Lungs and pleural spaces",
            "Heart size and mediastinal contour",
            "Hila",
            "Bones and soft tissues",
            "Lines, tubes and review areas",
        ],
        "impression": [
            "Right basal consolidation, consistent with pneumonia.",
            "No pleural effusion or pneumothorax.",
            "Normal cardiomediastinal contour.",
        ],
    },
    "Abdominal_Xray": {
        "indications": "Suspected obstruction, perforation, constipation, or foreign body.",
        "sections": [
            "Bowel gas pattern and calibre",
            "Free intraperitoneal gas",
            "Soft-tissue outlines and organomegaly",
            "Calcification and calculi",
            "Bones and lung bases",
        ],
        "impression": [
            "Dilated small bowel loops, suggesting obstruction.",
            "No free intraperitoneal gas.",
            "Correlation with CT recommended.",
        ],
    },
    "Mammography": {
        "indications": "Screening or diagnostic assessment of the breast.",
        "sections": [
            "Breast composition and density",
            "Masses with shape, margin and density",
            "Calcifications with morphology and distribution",
            "Architectural distortion and asymmetry",
            "Skin, nipple and axilla",
            "Overall BI-RADS assessment for each breast",
        ],
        "impression": [
            "Grouped pleomorphic microcalcifications in the right breast.",
            "BI-RADS 4 — stereotactic biopsy recommended.",
            "Left breast BI-RADS 1.",
        ],
    },
    # ---- Nuclear medicine & PET ---------------------------------------------
    "Bone_Scan": {
        "indications": "Suspected metastases, occult fracture, infection or metabolic bone disease.",
        "sections": [
            "Whole-body tracer distribution",
            "Axial skeleton",
            "Appendicular skeleton",
            "Focal areas of increased or decreased uptake",
            "Soft-tissue and renal tract activity",
        ],
        "impression": [
            "Multiple foci of increased uptake in the axial skeleton, consistent with metastases.",
            "No matching benign explanation on correlation.",
            "Recommend correlation with cross-sectional imaging.",
        ],
    },
    "PET_CT": {
        "indications": "Staging, restaging or treatment response assessment of malignancy.",
        "sections": [
            "Primary site and metabolic activity (SUVmax)",
            "Regional and distant nodes",
            "Distant metastatic sites",
            "Physiological versus pathological uptake",
            "CT correlate for each focus",
            "Comparison with prior studies",
        ],
        "impression": [
            "FDG-avid right upper lobe primary with ipsilateral hilar nodal uptake.",
            "No distant metastatic disease.",
            "Findings are consistent with locally advanced disease.",
        ],
    },
    # ---- Cardiac ------------------------------------------------------------
    "Echocardiography": {
        "indications": "Breathlessness, murmur, suspected heart failure or valvular disease.",
        "sections": [
            "Left ventricular size and systolic function",
            "Right ventricle",
            "Atria",
            "Aortic, mitral, tricuspid and pulmonary valves",
            "Pericardium and effusion",
            "Great vessels and estimated pressures",
        ],
        "impression": [
            "Mildly impaired left ventricular systolic function.",
            "Moderate mitral regurgitation.",
            "No pericardial effusion.",
        ],
    },
}


def _slug_from_stem(stem: str) -> str:
    return stem.lower().replace("_", "-")


def _parse_field(text: str, name: str) -> str:
    """Return the first plain content line under a `### <name>:` heading.

    Only the exam name and technique are read this way; both are non-proprietary
    single lines. Anything that looks like an instruction block is skipped.
    """
    m = re.search(r"^###\s*" + re.escape(name) + r":?\s*$", text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^###\s", rest, re.M)
    seg = rest[: nxt.start()] if nxt else rest
    for line in seg.splitlines():
        s = line.strip()
        if not s or s.startswith("**"):
            continue
        return s
    return ""


@lru_cache(maxsize=1)
def _parsed_fields() -> dict[str, dict]:
    """Parse exam + technique from bundled templates. Cached for the process."""
    out: dict[str, dict] = {}
    for stem in LIBRARY:
        path = os.path.join(_BUNDLED_TEMPLATES_DIR, f"{stem}.txt")
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        out[stem] = {
            "exam": _parse_field(text, "Exam"),
            "technique": _parse_field(text, "Technique"),
        }
    return out


@lru_cache(maxsize=1)
def _entries() -> dict[str, dict]:
    """Assemble the full, publishable entry for every curated template."""
    parsed = _parsed_fields()
    group_of: dict[str, dict] = {}
    for g in GROUPS:
        for stem in g["stems"]:
            group_of[stem] = g
    entries: dict[str, dict] = {}
    for stem, curated in LIBRARY.items():
        p = parsed.get(stem, {})
        exam = p.get("exam") or stem.replace("_", " ")
        g = group_of.get(stem)
        entries[_slug_from_stem(stem)] = {
            "stem": stem,
            "slug": _slug_from_stem(stem),
            "exam": exam,
            "seo_title": SEO_TITLES.get(stem, exam),
            "page_title": curated.get("page_title", SEO_TITLES.get(stem, exam)),
            "meta_description": curated.get("meta_description"),
            "lead": curated.get("lead"),
            "scope_note": curated.get("scope_note"),
            "report_format": curated.get("report_format"),
            "technique": p.get("technique", ""),
            "group_id": g["id"] if g else "other",
            "group_label": g["label"] if g else "Other",
            "indications": curated["indications"],
            "sections": curated["sections"],
            "impression": curated["impression"],
        }
    return entries


def library_groups() -> list[dict]:
    """Return modality groups, each with its ordered list of catalogue entries."""
    entries = _entries()
    result = []
    for g in GROUPS:
        items = []
        for stem in g["stems"]:
            slug = _slug_from_stem(stem)
            if slug in entries:
                items.append(entries[slug])
        if items:
            result.append({**g, "entries": items})
    return result


def all_slugs() -> list[str]:
    return list(_entries().keys())


def get_entry(slug: str) -> Optional[dict]:
    return _entries().get(slug)


_RELATED_OVERRIDES: dict[str, list[str]] = {
    # Body and pelvic studies otherwise fall outside the first-six default.
    "mri-pelvis": ["mri-prostate", "ultrasound-pelvis", "ct-abdomen-pelvis"],
    "mri-prostate": ["mri-pelvis"],
    "ultrasound-pelvis": ["mri-pelvis", "ct-abdomen-pelvis"],
    "ct-kub": ["ct-abdomen-pelvis", "ultrasound-abdomen"],
    "ct-abdomen-pelvis": ["ct-kub", "ultrasound-abdomen", "mri-abdomen-liver", "mri-pelvis"],
    "ultrasound-abdomen": ["ct-abdomen-pelvis", "ct-kub", "mri-abdomen-liver"],
    # Search Console shows demand for these pages. Put the closest clinical
    # companion first instead of giving every page the first six templates in
    # its modality group.
    "mrcp": ["mri-abdomen-liver", "ct-abdomen-pelvis"],
    "mri-abdomen-liver": ["mrcp", "ct-abdomen-pelvis"],
    "mri-breast": ["ultrasound-breast", "mammography"],
    "ultrasound-breast": ["mri-breast", "mammography"],
    "mammography": ["mri-breast", "ultrasound-breast"],
    "mri-spine-cervical": [
        "ct-spine-cervical",
        "mri-spine-thoracic",
        "mri-spine-lumbar",
    ],
    "ct-spine-cervical": [
        "mri-spine-cervical",
        "ct-spine-thoracic",
        "ct-spine-lumbar",
    ],
}


def related_entries(slug: str, limit: int = 6) -> list[dict]:
    """Return useful related templates, with curated clinical links first."""
    entry = get_entry(slug)
    if not entry:
        return []

    candidates = list(_RELATED_OVERRIDES.get(slug, []))
    candidates.extend(
        item["slug"]
        for group in library_groups()
        if group["id"] == entry["group_id"]
        for item in group["entries"]
        if item["slug"] != slug
    )

    related: list[dict] = []
    seen = {slug}
    for candidate_slug in candidates:
        if candidate_slug in seen:
            continue
        seen.add(candidate_slug)
        candidate = get_entry(candidate_slug)
        if candidate:
            related.append(candidate)
        if len(related) == limit:
            break
    return related


def library_count() -> int:
    return len(_entries())
