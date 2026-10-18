"""The local index: exact names first, then the closest names, scored the same
with or without rapidfuzz."""
import os

import pytest

from hponorm import SAMPLE_OBO, HpoIndex, hpo
from hponorm.hpo import HpoTerm

EXCERPT = os.path.join(os.path.dirname(__file__), "data", "hp_excerpt.obo")


@pytest.fixture(params=[False, True], ids=["difflib", "rapidfuzz"])
def matcher(request, monkeypatch):
    """Run a test once with the standard library's matching and once with rapidfuzz (if installed)."""
    if request.param:
        pytest.importorskip("rapidfuzz")
    monkeypatch.setattr(hpo, "_HAVE_RAPIDFUZZ", request.param)
    if request.param:
        from rapidfuzz import fuzz, process
        monkeypatch.setattr(hpo, "fuzz", fuzz, raising=False)
        monkeypatch.setattr(hpo, "process", process, raising=False)
    return request.param


@pytest.fixture
def sample(tmp_path):
    return HpoIndex.load(SAMPLE_OBO, cache_dir=tmp_path)


@pytest.fixture
def excerpt(tmp_path):
    return HpoIndex.load(EXCERPT, cache_dir=tmp_path)


def test_the_sample_ships_with_the_package(sample):
    assert SAMPLE_OBO.exists() and SAMPLE_OBO.parent.name == "data"
    assert len(sample) == 8
    assert sample.get("HP:0001657").label == "Prolonged QT interval"
    assert sample.get("hp_0001657").id == "HP:0001657"


def test_a_label_scores_100_and_a_synonym_98(sample, matcher):
    top = sample.search("Diabetes mellitus")[0]
    assert (top.id, top.score, top.matched_on) == ("HP:0000819", 100.0, "label")
    top = sample.search("diabetes")[0]
    assert (top.id, top.score, top.matched_on) == ("HP:0000819", 98.0, "synonym: Diabetes")
    # case, hyphens and spacing do not count
    top = sample.search("  LONG-QT   interval ")[0]
    assert (top.id, top.score) == ("HP:0001657", 98.0)


def test_a_misspelt_name_is_found(sample, excerpt, matcher):
    top = sample.search("diabetis mellitus")[0]
    assert top.id == "HP:0000819" and 90 <= top.score <= 96
    assert excerpt.search("dyslexya")[0].id == "HP:0010522"


def test_shared_words_count_for_more_than_shared_letters(excerpt, matcher):
    # "Reading disability" (Dyslexia) has more letters in common with the name, but
    # "Specific learning disability" has both of its words
    ids = [c.id for c in excerpt.search("learning disability")]
    assert ids[0] == "HP:0001328"
    assert ids.index("HP:0001328") < ids.index("HP:0010522")


def test_a_name_inside_a_longer_one_is_not_taken_for_it(excerpt, matcher):
    top = excerpt.search("hearing loss from birth")[0]
    assert top.id == "HP:0000365" and top.matched_on == "synonym: Hearing loss"
    assert top.score < 90           # phenotk's default threshold: not accepted without a person


def test_scores_do_not_depend_on_rapidfuzz(excerpt, monkeypatch):
    """rapidfuzz may find more names, but a term found both ways has the same score."""
    pytest.importorskip("rapidfuzz")
    for q in ["learning disability", "deafness", "hearing loss sensorineural", "mental retardaton"]:
        found = {}
        for flag in (False, True):
            monkeypatch.setattr(hpo, "_HAVE_RAPIDFUZZ", flag)
            found[flag] = [(c.id, c.score) for c in excerpt.search(q, limit=5)]
        assert found[False][0] == found[True][0], q
        both = dict(found[False]).keys() & dict(found[True]).keys()
        assert all(dict(found[False])[t] == dict(found[True])[t] for t in both), q


def test_obsolete_terms_are_never_suggested():
    idx = HpoIndex({"HP:0000001": HpoTerm("HP:0000001", "Seizure", ["Fits"], obsolete=True),
                    "HP:0001250": HpoTerm("HP:0001250", "Seizure", ["Seizures"])}, source="test")
    assert [c.id for c in idx.search("seizure")] == ["HP:0001250"]
    assert "HP:0000001" not in [c.id for c in idx.search("fits")]


def test_candidates_carry_the_terms_synonyms(sample):
    top = sample.search("prolonged qt interval")[0]
    assert "QT prolongation" in top.synonyms


def test_nothing_is_downloaded_unless_allowed(tmp_path):
    with pytest.raises(FileNotFoundError):
        HpoIndex.load(None, allow_download=False, cache_dir=tmp_path)
    assert hpo.HPO_OBO_URL.startswith("https://") and hpo.HPO_JSON_URL.startswith("https://")


def test_the_parsed_index_is_cached(tmp_path):
    first = HpoIndex.load(SAMPLE_OBO, cache_dir=tmp_path)
    assert list(tmp_path.glob("*.idx.pkl"))
    again = HpoIndex.load(SAMPLE_OBO, cache_dir=tmp_path)
    assert len(again) == len(first) and again.search("seizures")[0].id == "HP:0001250"


def test_names_are_compared_without_case_accents_or_possessives():
    from hponorm.suggest import normalise_text, similarity
    assert normalise_text("  Long-QT   interval ") == "long qt interval"
    assert normalise_text("Ménière’s disease") == "meniere disease"
    assert similarity("Down's syndrome", "down syndrome") == 100.0
    # the figures the README gives
    assert round(similarity("learning disability", "Specific learning disability")) == 80
    assert round(similarity("learning disability", "Reading disability")) == 68
    assert round(similarity("hearing loss from birth", "Hearing loss")) == 74
    assert similarity("QT interval prolonged", "Prolonged QT interval") == 97.0
    assert similarity("abnormal ear", "Abnormal fear") < 80          # short words must be the same
