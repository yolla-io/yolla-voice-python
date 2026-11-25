import importlib.metadata

import yolla_voice


def test_initial_version():
    assert yolla_voice.__version__ == "0.1.0"
    assert importlib.metadata.version("yolla-voice-python") == yolla_voice.__version__
