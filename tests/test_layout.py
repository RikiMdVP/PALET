"""Repository layout: active prompts exist, obsolete files live in legacy/."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

ACTIVE_PROMPTS = [
    "arq_system_v3.txt",
    "qsp_system_v2.txt",
    "map_system_v2.txt",
    "synthesis_system_v1.txt",
]

# (old location, new location under legacy/)
MOVED_TO_LEGACY = [
    ("palet_legacy.py", "legacy/palet_legacy.py"),
    ("scripts/map_module.py", "legacy/scripts/map_module.py"),
    ("scripts/report_generator.py", "legacy/scripts/report_generator.py"),
    ("scripts/se_module_legacy.py", "legacy/scripts/se_module_legacy.py"),
    ("scripts/test_llm.py", "legacy/scripts/test_llm.py"),
    ("scripts/test_openalex.py", "legacy/scripts/test_openalex.py"),
    ("scripts/test_scopus.py", "legacy/scripts/test_scopus.py"),
    ("scripts/test_scopus_simple.py", "legacy/scripts/test_scopus_simple.py"),
    ("scripts/configure_pybliometrics.py", "legacy/scripts/configure_pybliometrics.py"),
    ("prompts/arq_system.txt", "legacy/prompts/arq_system.txt"),
    ("prompts/arq_system_v2.txt", "legacy/prompts/arq_system_v2.txt"),
    ("prompts/map_system.txt", "legacy/prompts/map_system.txt"),
    ("prompts/qsp_system.txt", "legacy/prompts/qsp_system.txt"),
    ("prompts/synthesis_system.txt", None),  # renamed to synthesis_system_v1.txt
]


@pytest.mark.parametrize("prompt", ACTIVE_PROMPTS)
def test_active_prompt_exists(prompt):
    assert (ROOT / "prompts" / prompt).is_file()


@pytest.mark.parametrize("old,new", MOVED_TO_LEGACY)
def test_obsolete_file_moved_to_legacy(old, new):
    assert not (ROOT / old).exists(), f"{old} should no longer be at its old location"
    if new is not None:
        assert (ROOT / new).is_file(), f"{new} missing: files are moved, never deleted"


def test_modules_point_to_existing_prompts():
    import arq_module
    import map_module_v2
    import qsp_module
    import synthesis_module

    paths = [
        arq_module.prompt_system_path,
        qsp_module.QSP_SYSTEM_PATH,
        map_module_v2.MAP_SYSTEM_PATH,
        synthesis_module.SYNTHESIS_SYSTEM_PATH,
    ]
    for path in paths:
        assert Path(path).is_file(), path
        assert Path(path).name in ACTIVE_PROMPTS
