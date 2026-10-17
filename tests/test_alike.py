"""Names that are spelt nearly alike but are not the same thing.

"Hypertension" and "hypotension" share all but two letters and mean the
opposite; "type 1" and "type 2" differ by one character. Such names must never
score like close spellings of each other, or a tool that accepts a match above
a threshold (phenotk normalise) would fill a name with the wrong term. British
and American spellings of a name are the same name, and still match."""
import os

import pytest

from hponorm import HpoIndex
from hponorm.suggest import best_match, different_words, similarity

EXCERPT = os.path.join(os.path.dirname(__file__), "data", "hp_excerpt.obo")

# pairs that are not the same thing: none may score 50 or more
DIFFERENT = [
    ("Maternal hypothyroidism", "Maternal hyperthyroidism"),   # hyper- and hypo-
    ("Essential hypotension", "essential hypertension"),
    ("Hypertension", "Hypotension"),
    ("Hypertelorism", "Hypotelorism"),
    ("Hypoaesthesia", "Hyperesthesia"),                        # and in British spelling
    ("Microcephaly", "Macrocephaly"),                          # micro- and macro-
    ("Microcephaly", "Acrocephaly"),
    ("Bradycardia", "Tachycardia"),                            # brady- and tachy-
    ("Polyhydramnios", "Oligohydramnios"),                     # poly- and oligo-
    ("Polyuria", "Oliguria"),
    ("Esotropia", "Exotropia"),
    ("Limited hip abduction", "Limited hip adduction"),
    ("Congenital hypothyroidism", "Congenital hypoparathyroidism"),   # a prefix added
    ("Hypoparathyroidism", "Pseudohypoparathyroidism"),
    ("Symptomatic", "Asymptomatic"),                           # negated
    ("Syndromic hearing loss", "Nonsyndromic hearing loss"),
    ("Normal pulse", "Abnormal pulse"),
    ("Complete penetrance", "Incomplete penetrance"),
    ("Type 1 diabetes mellitus", "Type 2 diabetes mellitus"),  # numbers and letters
    ("Long QT syndrome 1", "long QT syndrome 2"),
    ("Mucopolysaccharidosis type I", "Mucopolysaccharidosis type II"),
    ("Hepatitis A", "Hepatitis B"),
    ("Vitamin B12 deficiency", "Vitamin B6 deficiency"),
    ("Niemann-Pick disease type A", "Niemann-Pick disease type B"),
    ("46,XX disorder of sex development", "46,XY disorder of sex development"),
]

# pairs that are the same name, spelt differently: all must still score 90 or more
SAME = [
    ("Anaemia", "Anemia"),
    ("Haemophilia A", "Hemophilia A"),
    ("Oedema", "Edema"),
    ("Oesophageal atresia", "Esophageal atresia"),
    ("Foetal growth restriction", "Fetal growth restriction"),
    ("Paediatric onset", "Pediatric onset"),
    ("Aetiology unknown", "Etiology unknown"),     # the "a" of a British spelling is not "a-" meaning "not"
    ("Hypoaesthesia", "Hypoesthesia"),
    ("Coeliac disease", "Celiac disease"),
    ("Dysfunction", "Disfunction"),
    ("Mucopolysaccharidosis type I", "Mucopolysaccharidosis type 1"),   # a Roman numeral and its number
    ("Seizure", "Seizures"),
]


@pytest.mark.parametrize("a,b", DIFFERENT, ids=["{} / {}".format(a, b) for a, b in DIFFERENT])
def test_names_that_are_not_the_same_thing_score_low(a, b):
    assert similarity(a, b) < 50
    assert best_match(a, "Another term", [b])[0] < 50


@pytest.mark.parametrize("a,b", SAME, ids=["{} / {}".format(a, b) for a, b in SAME])
def test_spellings_of_the_same_name_still_match(a, b):
    assert similarity(a, b) >= 90


def test_different_words():
    assert different_words("hypertension", "hypotension")
    assert different_words("hypertelorism", "hypotelorism")
    assert different_words("pseudohypoparathyroidism", "pseudohyperparathyroidism")   # inside a word
    assert different_words("atypical", "typical") and different_words("anencephaly", "encephaly")
    assert different_words("1", "2") and different_words("ii", "iii") and not different_words("ii", "2")
    for a, b in (("aetiology", "etiology"), ("anaemia", "anemia"), ("oedema", "edema"), ("seizure", "seizures")):
        assert not different_words(a, b), (a, b)


@pytest.fixture
def excerpt(tmp_path):
    return HpoIndex.load(EXCERPT, cache_dir=tmp_path)


def test_the_opposite_term_is_not_suggested_as_a_match(excerpt):
    """phenotk 0.3 filled "Maternal hypothyroidism" with Maternal hyperthyroidism (hponorm 1.0 scored it 93.6)."""
    for name, wrong in (("Maternal hypothyroidism", "HP:0034778"), ("Hypotension", "HP:0000822"),
                        ("Hypertension", "HP:0002615"), ("Hypotelorism", "HP:0000316")):
        found = {c.id: c.score for c in excerpt.search(name, limit=12)}
        assert found.get(wrong, 0) < 50, (name, found)
    top = excerpt.search("Maternal hypothyroidism")[0]
    assert top.id == "HP:0000821" and top.score < 90       # Hypothyroidism: close, but for a person to choose


def test_the_figures_the_readme_gives():
    assert similarity("Maternal hypothyroidism", "Maternal hyperthyroidism") == 25
    assert similarity("Hypotension", "Hypertension") == 0
    assert similarity("Oesophageal atresia", "Esophageal atresia") == 96
