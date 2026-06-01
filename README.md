# hponorm

Interactively **validate and normalise the phenotypic-feature terms** in GA4GH
phenopacket / family JSON files against the **HPO** (Human Phenotype Ontology).

It's the sibling of `mondonorm` (which does disease terms → MONDO) and shares the
same look and feel. This one targets `phenotypicFeatures[].type` and HPO.

If your pedigree conversion currently emits phenotype terms with an empty `id` and a
free-text label:

```json
"phenotypicFeatures": [ { "type": { "id": "", "label": "long qt interval" } } ]
```

`hponorm` walks the file, finds every phenotypic feature, suggests the most
likely HPO terms for each label, lets you pick one (or type an HP id yourself),
and writes a normalised copy:

```json
"phenotypicFeatures": [ { "type": { "id": "HP:0001657", "label": "Prolonged QT interval" } } ]
```

## How suggestions are sourced

Two interchangeable backends; pick with `--backend`:

| Backend | What it uses | Network |
|---------|--------------|---------|
| `ols`   | EBI Ontology Lookup Service v4 (live HPO) | required |
| `local` | A local `hp.obo` / `hp.json`, downloaded + cached on first use | only for the one-time download |
| `auto`  | OLS if reachable, otherwise local (the default) | preferred |

The official ontology file can be fetched automatically (from
`purl.obolibrary.org/obo/hp.obo`) or supplied with `--hpo-file`.
A tiny **illustrative** offline sample (`hponorm/data/hpo-sample.obo`, 8 terms)
ships with the package so you can try the tool with no network — it is **not** a
substitute for the real ontology.

## Install

```bash
pip install -e .                 # installs the `hponorm` command
pip install -e ".[recommended]"  # + rapidfuzz (better matching) and rich (nicer UI)
```

Both extras are optional: without `rapidfuzz` it falls back to stdlib `difflib`;
without `rich` it prints plain text.

## Quick start

```bash
# Online (auto-detects OLS):
hponorm test3_phenopackets.json

# Fully offline against a downloaded ontology:
hponorm myfile.json --backend local --hpo-file /path/to/hp.obo

# Try it offline with the bundled sample (diabetes / long QT / a few others):
hponorm myfile.json --backend local --hpo-file hponorm/data/hpo-sample.obo

# Equivalent without installing:
python -m hponorm myfile.json
```

## The interactive review

Each **distinct** label is reviewed once and the decision is applied to every
occurrence (so "diabetes" appearing 8 times is one question, not eight). For
each label you see a ranked table and a prompt:

```
Select [#, s words, h HP:id, r, k, x, ?, q]:
  <number>     select that suggestion
  s <words>    search again with different words
  h HP:id      enter an HPO id manually (validated, canonical label fetched)
  r            reuse a decision remembered from earlier in this session
  k            keep the current term unchanged
  x            skip this label (leave it unmapped)
  ?            help
  q            finish now: apply decisions made so far and save
```

If a feature already has an `id`, it is validated: the tool reports whether the
id resolves in HPO and whether its canonical label matches the existing label.
A feature's `excluded` flag (a negated phenotype) is preserved untouched — only
`type.id` / `type.label` are changed.

## Output

For `input.json` (unless you pass `--out` or `--in-place`):

* `input.normalized.json` — the normalised phenopacket (only `type.id` /
  `type.label` are changed; everything else, including the pedigree and any
  `diseases` terms, is left exactly as-is).
* `input.normalized.json.mapping.json` — a decision log (label → HP id, count).

Because `hponorm` only touches `phenotypicFeatures`, you can run it alongside
`mondonorm` (which only touches `diseases`) on the same file without conflict.

## Useful options

```
--out PATH            output path (single input file only)
--in-place            overwrite the input file(s)
--backend {auto,ols,local}
--hpo-file PATH       local hp.obo or hp.json
--cache-dir DIR       where the downloaded HPO + parsed index are cached
--update              re-download / re-parse HPO
--no-download         never download (local backend must find a file)
--no-online           never use OLS, even in auto mode
--limit N             suggestions shown per label (default 8)
--mapping FILE        load/save remembered label->term decisions across runs
--auto-remembered     auto-apply remembered labels without prompting
--no-color            plain text output
```

Process several files in one go; remembered decisions carry across them:

```bash
hponorm *.json --mapping team-hpo-map.json
# next time, reuse without re-typing:
hponorm new/*.json --mapping team-hpo-map.json --auto-remembered
```

## Use as a library

```python
from hponorm import HpoIndex, OlsClient, Suggester
from hponorm import phenopackets as pp

sug = Suggester(OlsClient(), name="ols")          # or Suggester(HpoIndex.load(...))
for c in sug.suggest("long qt interval", limit=5):
    print(c.id, c.label, c.score)

data = pp.load("myfile.json")
for ref in pp.find_phenotypic_features(data):
    print(ref.path, ref.label, ref.id, "excluded" if ref.excluded else "")
```

## Getting the full HPO ontology

* Browser / search: https://hpo.jax.org
* Direct files: `http://purl.obolibrary.org/obo/hp.obo` or `.../hp.json`
* Releases: https://github.com/obophenotype/human-phenotype-ontology/releases

Phenopackets reference: https://phenopacket-schema.readthedocs.io
(phenotypic features use HPO `OntologyClass` values in `PhenotypicFeature.type`).

## A note on the bundled sample's ids

The HP ids in `hpo-sample.obo` were checked against HPO browsers (e.g. Diabetes
mellitus HP:0000819, Prolonged QT interval HP:0001657, Seizure HP:0001250,
Microcephaly HP:0000252, Short stature HP:0004322, Global developmental delay
HP:0001263). It is still only a tiny demo fixture — verify against the live HPO
for real curation work.
