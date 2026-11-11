"""Safety net: every active module must be importable without side effects."""

import importlib

import pytest

ACTIVE_MODULES = [
    "arq_module",
    "qsp_module",
    "se_module",
    "map_module_v2",
    "synthesis_module",
    "report_generator_v2",
    "export_bibtex",
    "prisma_validator",
    "app",
]


@pytest.mark.parametrize("module_name", ACTIVE_MODULES)
def test_active_module_imports(module_name):
    module = importlib.import_module(module_name)
    assert module is not None
