import logging
from openai import OpenAI
from ui.utils import update_status
from config.config import config
import os
import json
import re
from typing import Tuple, Optional, List
import configparser
from json.decoder import JSONDecodeError

logger = logging.getLogger(__name__)


def _get_save_directory():
    """Returns the config directory as save_directory, creating it if needed."""
    config_dir = None

    if os.name == "nt":  # Windows
        config_dir = os.path.join(os.environ["APPDATA"], "VOXRAD")
    else:  # Assuming macOS or Linux
        config_dir = os.path.join(os.path.expanduser("~"), ".voxrad")

    # Ensure config directory exists (consistent with get_default_config_path)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    config_path = os.path.join(config_dir, "settings.ini") # Path to settings.ini (for consistency)


    if os.path.exists(config_path): # Check if settings.ini exists
        config_parser = configparser.ConfigParser()
        config_parser.read(config_path)
        if "DEFAULT" in config_parser and "WorkingDirectory" in config_parser["DEFAULT"]:
            return config_parser["DEFAULT"]["WorkingDirectory"]
        else: # If WorkingDirectory is missing in existing ini, return config_dir as default
            return config_dir
    else: # If settings.ini is missing, return config_dir as default.
        return config_dir # Return the config directory itself as save_directory


SAVE_DIRECTORY = _get_save_directory()
TEMPLATES_DIR = os.path.join(SAVE_DIRECTORY, "templates")
GUIDELINES_DIR = os.path.join(SAVE_DIRECTORY, "guidelines")

# Bundled templates/guidelines shipped with the app (fallback for web/Docker)
_BUNDLED_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
_BUNDLED_GUIDELINES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "guidelines")

def _get_file_list(directory: str, ext: str) -> List[str]:
    """Get files with given extension in directory."""
    if not os.path.exists(directory):
        return []
    return [f for f in os.listdir(directory) if f.endswith(ext)]


def _get_templates() -> List[str]:
    """Return template list, preferring user directory then bundled."""
    for d in [TEMPLATES_DIR, _BUNDLED_TEMPLATES_DIR]:
        files = _get_file_list(d, ".txt") + _get_file_list(d, ".md")
        if files:
            return files
    return []


def _get_guidelines() -> List[str]:
    """Return guideline list, preferring user directory then bundled."""
    for d in [GUIDELINES_DIR, _BUNDLED_GUIDELINES_DIR]:
        files = _get_file_list(d, ".md")
        if files:
            return files
    return []

# ---------------------------------------------------------------------------
# Keyword-based template pre-selection (no LLM call)
# ---------------------------------------------------------------------------
_KEYWORD_MAP = [
    # (template_filename, [keywords — checked against lowercase transcript])
    # Order matters: more specific entries first
    ("CT_Angiography_Thoracic.txt", ["cta thorax", "ct angio thorax", "thoracic aorta", "ct pulmonary angiogram", "ctpa"]),
    ("HRCT_Thorax.txt",             ["hrct", "high resolution ct", "high-resolution ct", "hrct thorax"]),
    ("CT_Chest.txt",                ["ct chest", "chest ct", "ct thorax", "thorax ct"]),
    ("CT_Abdomen_Pelvis.txt",       ["ct abdomen pelvis", "ct ap", "abdomen and pelvis ct", "ct of the abdomen and pelvis"]),
    ("CT_KUB.txt",                  ["ct kub", "kub ct", "ct urogram", "ct kidney ureter"]),
    ("CT_Head_Brain.txt",           ["ct head", "ct brain", "head ct", "brain ct"]),
    ("CT_Spine_Cervical.txt",       ["ct cervical spine", "ct c-spine", "cervical spine ct"]),
    ("CT_Spine_Lumbar.txt",         ["ct lumbar spine", "ct l-spine", "lumbar spine ct"]),
    ("CT_Spine_Thoracic.txt",       ["ct thoracic spine", "ct t-spine", "thoracic spine ct"]),
    ("MRI_Knee.txt",                ["mri knee", "knee mri", "mri of the knee", "mri right knee", "mri left knee"]),
    ("MRI_Shoulder.txt",            ["mri shoulder", "shoulder mri", "mri of the shoulder"]),
    ("MRI_Hip.txt",                 ["mri hip", "hip mri", "mri of the hip"]),
    ("MRI_Brain.txt",               ["mri brain", "brain mri", "mri head", "mri of the brain"]),
    ("MRI_Spine_Cervical.txt",      ["mri cervical spine", "mri c-spine", "cervical spine mri"]),
    ("MRI_Spine_Lumbar.txt",        ["mri lumbar spine", "mri l-spine", "lumbar spine mri"]),
    ("MRI_Abdomen_Liver.txt",       ["mri liver", "mri abdomen", "liver mri", "mri of the liver"]),
    ("MRI_Pelvis.txt",              ["mri pelvis", "pelvis mri", "mri of the pelvis"]),
    ("MRI_Prostate.txt",            ["mri prostate", "prostate mri", "mri of the prostate"]),
    ("MRI_Breast.txt",              ["mri breast", "breast mri"]),
    ("CXR.txt",                     ["chest x-ray", "chest xray", "cxr", "plain film chest", "pa chest"]),
    ("Abdominal_Xray.txt",          ["abdominal x-ray", "abdominal xray", "axa", "plain film abdomen", "kub x-ray"]),
