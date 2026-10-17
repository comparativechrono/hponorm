"""The command line, run on a small family with the bundled sample of the HPO."""
import json
import os
import socket
import subprocess
import sys
import urllib.error

import pytest

import hponorm
from hponorm import SAMPLE_OBO, cli
from hponorm import phenopackets as pp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAMILY = {
    "id": "FAM1",
    "proband": {
        "id": "FAM1-II-1",
        "subject": {"id": "II-1", "sex": "MALE"},
        "phenotypicFeatures": [
            {"type": {"id": "", "label": "Diabetes"}},
            {"type": {"id": "", "label": "long qt interval"}},
            {"type": {"id": "", "label": "Seizures"}, "excluded": True},
        ],
    },
    "relatives": [{
        "id": "FAM1-I-2",
        "subject": {"id": "I-2", "sex": "FEMALE"},
        "phenotypicFeatures": [{"type": {"id": "", "label": "diabetes"}}],
    }],
}


@pytest.fixture
def family(tmp_path):
    path = tmp_path / "family.json"
    path.write_text(json.dumps(FAMILY), encoding="utf-8")
    return path


def answers(monkeypatch, *replies):
    """Answer the questions in turn; after the last, stop (as at the end of input)."""
    queue = list(replies)

    def reply(prompt=""):
        if not queue:
            raise EOFError
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", reply)


def run(*argv, cache):
    return cli.main([*map(str, argv), "--no-color", "--cache-dir", str(cache)])


def features(path):
    return [(r.label, r.id, r.excluded) for r in pp.find_phenotypic_features(pp.load(path))]


def test_a_mapping_file_matches_names_in_any_case(family, tmp_path, monkeypatch):
    mapping = tmp_path / "terms.json"
    mapping.write_text(json.dumps({
        "DIABETES": "HP:0000819",                                            # a bare id, as studio2ga4gh reads
        "Long QT Interval": {"id": "HP:0001657", "label": "Prolonged QT interval"},
        "Breast cancer": {"id": "MONDO:0007254", "label": "breast cancer", "kind": "disease"},
    }), encoding="utf-8")
    answers(monkeypatch)                                                    # "Seizures" is asked about: stop
    out = tmp_path / "out.json"
    assert run(family, "--backend", "local", "--hpo-file", SAMPLE_OBO, "--mapping", mapping,
               "--auto-remembered", "-o", out, cache=tmp_path / "cache") == 0
    got = features(out)
    assert ("Diabetes mellitus", "HP:0000819", False) in got               # the label looked up for the bare id
    assert ("Prolonged QT interval", "HP:0001657", False) in got
    assert ("Seizures", "", True) in got                                     # left as it was
    saved = json.loads(mapping.read_text(encoding="utf-8"))
    # the other ontology's entry, and the entries' own forms, are kept
    assert saved["Breast cancer"]["id"] == "MONDO:0007254"
    assert saved["DIABETES"] == "HP:0000819"
    assert saved["Long QT Interval"] == {"id": "HP:0001657", "label": "Prolonged QT interval"}


def test_a_choice_is_remembered(family, tmp_path, monkeypatch, capsys):
    mapping = tmp_path / "terms.json"
    # Diabetes: the first suggestion; long qt interval: skip; Seizures: the first suggestion;
    # diabetes (another spelling, so asked about again): the decision remembered for it
    answers(monkeypatch, "1", "x", "1", "r")
    assert run(family, "--backend", "local", "--hpo-file", SAMPLE_OBO, "--mapping", mapping,
               cache=tmp_path / "cache") == 0
    got = features(tmp_path / "family.normalized.json")
    assert ("Diabetes mellitus", "HP:0000819", False) in got and ("diabetes", "", False) not in got
    assert ("Seizure", "HP:0001250", True) in got                          # still excluded
    assert ("long qt interval", "", False) in got
    saved = json.loads(mapping.read_text(encoding="utf-8"))
    assert saved == {"diabetes": {"id": "HP:0000819", "label": "Diabetes mellitus"},
                     "seizures": {"id": "HP:0001250", "label": "Seizure"}}
    log = json.loads((tmp_path / "family.normalized.json.mapping.json").read_text(encoding="utf-8"))
    assert [d["action"] for d in log["decisions"]] == ["map", "skip", "map", "map"]


def test_ols_not_answering_is_said(family, tmp_path, monkeypatch, capsys):
    class Unreachable(hponorm.OlsClient):
        def _get_json(self, url):
            raise urllib.error.URLError(socket.timeout("timed out"))

    monkeypatch.setattr(cli, "OlsClient", Unreachable)
    answers(monkeypatch, "x", "x", "x")
    assert run(family, "--backend", "ols", cache=tmp_path / "cache") == 0
    out = capsys.readouterr().out
    assert "did not answer in time, so there are no suggestions" in out
    assert "No suggestions found" not in out


def test_an_unreadable_mapping_file_is_not_overwritten(family, tmp_path, monkeypatch, capsys):
    mapping = tmp_path / "terms.json"
    mapping.write_text("[1, 2, 3]", encoding="utf-8")
    answers(monkeypatch, "1")
    assert run(family, "--backend", "local", "--hpo-file", SAMPLE_OBO, "--mapping", mapping,
               cache=tmp_path / "cache") == 0
    assert mapping.read_text(encoding="utf-8") == "[1, 2, 3]"
    assert "will not be overwritten" in capsys.readouterr().out


def test_mapping_helpers():
    remembered, others = cli.read_mapping({"resolved": {"Deafness": "HP:0000365", "X": "MONDO:0000001"},
                                           "unresolved": []})
    assert remembered == {"deafness": {"id": "HP:0000365", "label": ""}} and others == 1
    data, notes = cli.update_mapping({"Breast cancer": "MONDO:0007254"},
                                     {"breast cancer": {"id": "HP:0003002", "label": "Breast carcinoma"},
                                      "new name": {"id": "HP:0000365", "label": "Hearing impairment"}})
    assert data == {"Breast cancer": "MONDO:0007254",
                    "new name": {"id": "HP:0000365", "label": "Hearing impairment"}}
    assert len(notes) == 1 and "MONDO:0007254" in notes[0]


def test_the_package_is_importable_as_the_readme_says():
    from hponorm import HpoIndex, OlsClient, Suggester  # noqa: F401
    from hponorm import phenopackets  # noqa: F401
    assert hponorm.__version__ == "1.1.0"


def test_python_dash_m(tmp_path):
    env = dict(os.environ, PYTHONPATH=ROOT)
    done = subprocess.run([sys.executable, "-m", "hponorm", "--version"], capture_output=True, text=True,
                          env=env, cwd=str(tmp_path))
    assert done.returncode == 0 and done.stdout.strip() == "hponorm " + hponorm.__version__
