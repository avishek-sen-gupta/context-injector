"""Test Governor v3 package setup."""
import pytest


def test_governor_v3_package_importable():
    from governor_v3 import __version__
    assert __version__ is not None


def test_langgraph_installed():
    import langgraph
    assert langgraph is not None
