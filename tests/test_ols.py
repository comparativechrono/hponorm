"""The OLS backend, with EBI's Ontology Lookup Service replaced by a fake: OLS is
never asked. The fake's answers have the shape of OLS4's /api/search and
/api/ontologies/hp/terms responses; the terms in them are the HPO's."""
import socket
import urllib.error
import urllib.parse

import pytest

from hponorm import SAMPLE_OBO, HpoIndex, OlsClient, Suggester

SEARCH = {
    "response": {
        "numFound": 5,
        "start": 0,
        "docs": [
            {"iri": "http://purl.obolibrary.org/obo/HP_0000407", "obo_id": "HP:0000407",
             "short_form": "HP_0000407", "label": "Sensorineural hearing impairment",
             "description": ["A type of hearing impairment in one or both ears related to an abnormal "
                             "functionality of the cochlear nerve."],
             "synonym": ["Hearing loss, sensorineural", "Sensorineural deafness", "Sensorineural hearing loss"],
             "ontology_name": "hp", "type": "class"},
            {"iri": "http://purl.obolibrary.org/obo/HP_0000365", "obo_id": "HP:0000365",
             "short_form": "HP_0000365", "label": "Hearing impairment",
             "description": ["A decreased magnitude of the sensory perception of sound."],
             "synonym": ["Deafness", "Hearing defect", "Hearing impairment", "Hearing loss", "Hypacusis",
                         "Hypoacusis"],
             "ontology_name": "hp", "type": "class"},
            {"iri": "http://purl.obolibrary.org/obo/HP_0000365", "obo_id": "HP:0000365",
             "label": "Hearing impairment", "ontology_name": "hp", "type": "class"},
            {"iri": "http://purl.obolibrary.org/obo/MONDO_0005365", "obo_id": "MONDO:0005365",
             "label": "hearing loss disorder", "ontology_name": "mondo", "type": "class"},
            {"iri": "http://purl.obolibrary.org/obo/HP_0000366", "obo_id": "HP:0000366",
             "label": "obsolete Deafness", "is_obsolete": True, "ontology_name": "hp", "type": "class"},
        ],
    }
}

TERM = {"_embedded": {"terms": [{
    "iri": "http://purl.obolibrary.org/obo/HP_0000365", "label": "Hearing impairment",
    "description": ["A decreased magnitude of the sensory perception of sound."],
    "synonyms": ["Deafness", "Hearing defect", "Hearing impairment", "Hearing loss", "Hypacusis", "Hypoacusis"],
    "obo_id": "HP:0000365"}]}}


class FakeOls(OlsClient):
    """OlsClient with the requests answered here."""

    def __init__(self, answers=None, error=None):
        super().__init__()
        self.answers = answers or {}
        self.error = error
        self.urls = []

    def _get_json(self, url):
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        path = urllib.parse.urlparse(url).path
        for key, answer in self.answers.items():
            if path.endswith(key):
                return answer
        return {}


def test_results_are_scored_by_how_well_they_match():
    ols = FakeOls({"/search": SEARCH})
    found = ols.search("deafness", limit=5)
    # OLS put Sensorineural hearing impairment first; the synonym match comes first here
    assert [c.id for c in found] == ["HP:0000365", "HP:0000407"]
    best = found[0]
    assert (best.score, best.matched_on, best.source) == (98.0, "synonym: Deafness", "ols")
    assert found[1].score < 90
    assert "Hypoacusis" in best.synonyms


def test_the_first_result_is_not_taken_for_a_match():
    """hponorm 1.0 scored OLS's results by rank (100, 96, 92 ...), so the first looked exact."""
    found = FakeOls({"/search": SEARCH}).search("hearing loss from birth")
    assert found[0].score < 90 and found[0].matched_on == "synonym: Hearing loss"
    assert all(c.matched_on != "OLS relevance" for c in found)


def test_other_ontologies_obsolete_terms_and_repeats_are_left_out():
    found = FakeOls({"/search": SEARCH}).search("hearing", limit=10)
    assert sorted(c.id for c in found) == ["HP:0000365", "HP:0000407"]


def test_the_request_asks_for_synonyms_and_enough_results():
    ols = FakeOls({"/search": SEARCH})
    ols.search("deafness", limit=8)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(ols.urls[0]).query)
    assert query["q"] == ["deafness"] and query["ontology"] == ["hp"]
    assert "synonym" in query["fieldList"][0].split(",")
    assert int(query["rows"][0]) >= 24


def test_a_term_is_looked_up_by_its_id():
    ols = FakeOls({"/terms": TERM})
    term = ols.get("HP:0000365")
    assert (term.id, term.label, term.matched_on) == ("HP:0000365", "Hearing impairment", "exact id")
    assert "iri=http%3A%2F%2Fpurl.obolibrary.org%2Fobo%2FHP_0000365" in ols.urls[0]
    assert ols.last_error is None
    assert FakeOls({"/terms": {"_embedded": {"terms": []}}}).get("HP:9999999") is None


@pytest.mark.parametrize("error, words", [
    (urllib.error.URLError(socket.timeout("timed out")), "did not answer in time"),
    (urllib.error.URLError(ConnectionRefusedError(111, "Connection refused")), "did not answer"),
    (urllib.error.HTTPError("https://www.ebi.ac.uk/ols4/api/search", 429, "Too Many Requests", {}, None),
     "answered with an error (HTTP 429 Too Many Requests)"),
    (ValueError("Expecting value"), "could not be read"),
], ids=["timeout", "refused", "http-429", "not-json"])
def test_a_failure_is_explained(error, words):
    assert words in OlsClient.failure_message(error)
    ols = FakeOls(error=error)
    assert ols.get("HP:0000365") is None
    assert words in ols.last_error


def test_a_term_ols_does_not_have_is_not_a_failure():
    ols = FakeOls(error=urllib.error.HTTPError("u", 404, "Not Found", {}, None))
    assert ols.get("HP:9999999") is None and ols.last_error is None


def test_the_suggester_says_when_ols_did_not_answer():
    sug = Suggester(FakeOls(error=urllib.error.URLError(socket.timeout("timed out"))), name="ols")
    assert sug.suggest("deafness") == []
    assert "did not answer in time" in sug.last_error
    # the next search that works clears it
    sug.backend = FakeOls({"/search": SEARCH})
    assert sug.suggest("deafness") and sug.last_error is None


def test_the_fallback_answers_and_the_failure_is_still_reported(tmp_path):
    local = HpoIndex.load(SAMPLE_OBO, cache_dir=tmp_path)
    sug = Suggester(FakeOls(error=urllib.error.URLError("no route to host")), fallback=local, name="ols")
    found = sug.suggest("seizures")
    assert found[0].id == "HP:0001250" and found[0].source == "hpo-local"
    assert "did not answer" in sug.last_error
    assert sug.resolve("HP:0001250").label == "Seizure"
    assert "did not answer" in sug.last_error


def test_resolve_without_an_answer():
    sug = Suggester(FakeOls(error=urllib.error.URLError("no route to host")), name="ols")
    assert sug.resolve("HP:0000365") is None and "did not answer" in sug.last_error
    sug = Suggester(FakeOls({"/terms": {"_embedded": {"terms": []}}}), name="ols")
    assert sug.resolve("HP:9999999") is None and sug.last_error is None


def test_an_opposite_term_from_ols_is_not_a_match():
    """OLS may offer Maternal hyperthyroidism first for "Maternal hypothyroidism", the HPO having no such term."""
    answer = {"response": {"numFound": 1, "start": 0, "docs": [
        {"iri": "http://purl.obolibrary.org/obo/HP_0034778", "obo_id": "HP:0034778", "short_form": "HP_0034778",
         "label": "Maternal hyperthyroidism", "ontology_name": "hp", "type": "class"}]}}
    found = FakeOls({"/search": answer}).search("Maternal hypothyroidism", limit=5)
    assert [c.id for c in found] == ["HP:0034778"] and found[0].score < 50
