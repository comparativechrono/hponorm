"""The tests never go online: any attempt to open a URL fails at once.

EBI's Ontology Lookup Service is replaced by a fake that answers with JSON
written for these tests (see test_ols.py)."""
import urllib.request

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a URL: {}".format(args[0] if args else kwargs))

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
