import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ORG_ROOT_DIR = Path(os.environ.get("ORG_ROOT") or REPO_ROOT / "org")

DOCS_DIR = REPO_ROOT / "docs"
PROJECTS_DIR = REPO_ROOT / "projects"
CONFIG_DIR = REPO_ROOT / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"
RENDERERS_DIR = CONFIG_DIR / "renderers"
RUBRICS_DIR = REPO_ROOT / "rubrics"
GLOBAL_PRIMITIVES_DIR = REPO_ROOT / "global_primitives"
PAPERS_DIR = REPO_ROOT / "papers"
PAPER1_DIR = PAPERS_DIR / "paper1"
PAPER2_DIR = PAPERS_DIR / "paper2"
WORKSPACE_DIR = Path(
    os.environ.get("COGNITIVE_FIRM_WORKSPACE")
    or REPO_ROOT / "cognitive_firm_workspace"
)
