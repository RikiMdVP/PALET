"""Exceptions raised by PALET library code.

Library modules never call ``sys.exit``: they raise one of these, and the
entry points (command line, web GUI) decide how to report it.
"""


class PaletError(Exception):
    """Base class for every error PALET raises on purpose."""


class PaletConfigError(PaletError):
    """Missing or invalid configuration (API keys, prompt files, settings)."""


class SearchError(PaletError):
    """A database search failed. Never to be confused with 'no results'."""


class NoResultsError(PaletError):
    """The searches ran correctly but returned no records."""
