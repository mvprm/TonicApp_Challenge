# HCP clinical extraction — interview proof of concept v2

A deliberately small implementation accompanying the fuller architecture proposal.
Two runtime dependencies; one extraction script; one reference builder; no database,
training pipeline, vector store or agent framework. Input: UTF-8 JSONL with
`chat_message_id`, `country`, `prompt`. Python 3.11+.

## Run

```text
python -m pip install -r requirements.txt
python poc.py --demo --output demo_output
python -m unittest discover -v
```

The bundled demo replays **19 synthetic prompts with authored responses**. It runs
real language detection, evidence checks, matching and exports; it does not run an LLM.
For real inference, start Ollama with an installed multilingual model, then:

```text
python poc.py --input prompts.jsonl --model YOUR_INSTALLED_MODEL --output run_output
```

One structured `/api/chat` request per valid record, temperature 0, 60-second timeout,
no retries or hidden fallback. The default endpoint is localhost:11434. Optional
`--endpoint` accepts local HTTP or remote HTTPS. Use a separate output directory
for each run: files are overwritten. Prompts go to the configured endpoint and are
retained in outputs. No de-identification is implemented.

## Stages implemented

| Report stage | POC implementation |
|---|---|
| Input validation | JSONL streaming reader; validates fields and each physical line; preserves duplicate IDs with row_id; malformed records do not stop the run |
| Language detection | Lingua over all supported languages, low-accuracy mode; PT/ES/FR/IT and English expected; short/ambiguous text becomes und; country never substitutes for language |
| Text preprocessing | Separate NFC/whitespace/control-character-normalized view; preserves accents, negation, punctuation, numbers and units; original text retained |
| Clinical extraction | One schema-constrained model call; six entity types and assertion/context attributes |
| Evidence validation | Exact original-text spans and token boundaries; rejects fabricated mentions; repeated evidence receives null offsets and review |
| Reference matching | In-memory exact normalized lookup; preserves ambiguity/unmapped entities; no generated ontology codes |
| Quality/review | Flags language uncertainty, missing context, unresolved references, local vocabulary and modifier relations |
| Output | results.jsonl, review.csv and summary.json with hashes, versions, latency and known token usage |

No stemming, stopword removal, automatic spelling correction, HTML stripping or
translation: these can damage clinical evidence. Both raw and prepared text reach
the model; offsets always address the raw prompt using Python character positions.
Lingua thresholds (score >= .70, top-two margin >= .20, >=4 words) are conservative
heuristics, not calibrated accuracy estimates. Short prompts still reach extraction.
Mixed-language segmentation is not implemented.

## Extraction schema

Types: `pathology`, `symptom`, `active_substance`, `brand`, `procedure`,
`diagnostic_test`. Diagnostic examinations belong to diagnostic_test; procedures
are therapeutic/interventional actions. This boundary is a POC convention requiring
clinical review, not a provided business taxonomy.

Each entity contains exact `text`, a required `assertion` object and `modifiers`:

- polarity: affirmed, negated, uncertain, unspecified
- temporality: current, historical, future, unspecified
- experiencer: patient, family, other, unspecified
- context: patient_specific, hypothetical, general_question, unspecified

Polarity is one dimension of assertion status. Historical and negated may coexist.
Questions about a disease do not affirm a patient diagnosis. The schema validates
structure; it cannot verify clinical truth or the correctness of the model's assertion.

Modifiers are attached to their target entity: severity, laterality, body_site,
duration, therapy_line, eligibility. Each has exact evidence and a normalized value.
This is a small local schema, not SNOMED coding. Modifier evidence must occur once;
all retained relations remain `model_asserted_requires_review`. Therapy line and
eligibility are experimental and extracted only when explicit, never inferred.

## References and rebuilding

The bundled `references.json` has **3,788 concepts**:

- 3,731 existing EMA product/source-substance records (snapshot 2026-09-12).
- Three existing ICD-10 examples: E11, J45, R50.
- Four explicitly authored local concepts: appendectomy, biopsy, HbA1c and MRI.
- 50 active LOINC 2.83 laboratory terms selected by source COMMON_TEST_RANK,
  excluding specimen metadata and records with external copyright notices.

The LOINC ranking is not evidence of relevance to the unseen HCP dataset or EU
ordering frequency. The selection keeps the interview sample small. LOINC is
international and suitable for EU interoperability; it is not an EU clinical dataset.
EMA coverage is not a complete national medicines register. EMA local substance IDs
are source spellings, not authoritative chemical identities. Local concept IDs and
translations are demonstrative and never represented as SNOMED mappings.

Original LOINC fields are retained unchanged under `source_record`, including code,
long name, status and the six defining axes. Official available it-IT, fr-FR, es-ES
rows are retained under `linguistic_variants`. This archive has pt-BR, not pt-PT;
pt-BR is not imported or relabelled as European Portuguese. A missing translation
stays missing. No official pt-PT LOINC terminology coverage is claimed.

Full long/short names support exact matching. Component names only generate candidates:
`Creatinine` does not resolve to a particular specimen/property/method, even if the
small reference subset has only one candidate. No fuzzy matching or automatic
translation. Full-name matching is lexical, not semantic disambiguation. Generic
`HbA1c` can match an explicitly LOCAL concept, not a specific LOINC code.

To rebuild with the supplied archive (not duplicated in this package):

```text
python build_references.py --loinc Loinc_2.83.zip
```

`--limit 100` changes subset size. The builder expects the verified 2.83 file layout;
it is not a general release-version migration tool. `references_base.json` preserves
the prior EMA/ICD snapshot plus local vocabulary. Source archive and output hashes
support reproduction.

### SNOMED CT access and adapter

As checked 2026-09-13, full RF2 access requires registration/licensing via
https://www.snomed.org/get-snomed and https://mlds.ihtsdotools.org/ . No release was
available through an authenticated account in this environment. The GPS download
page https://www.snomed.org/gps presents a registration form; no registration was
submitted. GPS is not a replacement for semantic SNOMED processing:
https://docs.snomed.org/implementation-guides/gps-implementation-guide/technical-application .

**No SNOMED CT or GPS dataset is bundled or claimed to have been downloaded.**
Procedures and symptoms remain extractable without codes; a few local terms and the
existing ICD subset demonstrate matching. No equivalent comprehensive open clinical
ontology has been substituted.

The optional RF2 Snapshot adapter accepts active concepts and descriptions from a
licensed ZIP and an explicitly supplied JSON selection/type map:

```text
python build_references.py --loinc Loinc_2.83.zip --snomed YOUR_RF2.zip --snomed-types selected_types.json
```

The map has concept IDs as keys and pathology/symptom/procedure/diagnostic_test as
values. Supply verified IDs from your release; do not use invented example codes.
The adapter fails for missing/inactive selected concepts. It retains description
language and release provenance, without hierarchy inference or preferred-language
refset selection. Extension-only packages may need the base edition. Importing
licensed files does not grant redistribution rights. Adapter verification uses
synthetic RF2-format fixtures, not a genuine SNOMED release.

## Verification and limits

27 automated tests pass, covering language detection for all four countries' main
languages, raw evidence, negation, assertion dimensions, modifier rejection, LOINC
specificity, translated names, RF2 active/inactive handling, malformed JSONL and
HTTP response contract. Actual LOINC import and a 19-record demo were executed.
No local Ollama service was available; real-model inference and clinical accuracy
were **not evaluated**. Synthetic replay is engineering verification, not model evaluation.

The most useful next evaluation is a small manually annotated sample balanced by
language, entity type, question/context and negation. Measure span/type precision
and recall, assertion accuracy, mapping precision/coverage and real-model latency.
No scores are claimed without that data. No training, business label inference,
conversation reconstruction, deployment or production terminology server is included.

## LOINC notice

This material contains content from LOINC (http://loinc.org).
LOINC is copyright © Regenstrief Institute, Inc. and the Logical
Observation Identifiers Names and Codes (LOINC) Committee and is
available at no cost under the license at
http://loinc.org/license. LOINC® is a registered United States
trademark of Regenstrief Institute, Inc.

The complete supplied license is included as `LoincLicense_5.8.txt`.
