# tests/test_v4_setup.py

def test_governor_v4_package_importable():
    from governor_v4 import __version__
    assert __version__ is not None
