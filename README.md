# HCP Clinical Attribute Extraction

A proof of concept for extracting structured clinical attributes from healthcare-professional prompts and linking supported mentions to reference terminology.

The implementation demonstrates the core extraction, validation and reference-matching stages of the **proposed classification engine strategy**. Its scope prioritizes traceability, explicit uncertainty and a reproducible batch workflow within a time-constrained technical assessment.

## Overview

The pipeline processes JSONL records containing a message identifier, country and prompt. For each valid record, it prepares the text, detects its language, extracts clinical entities through a structured language-model response, validates the supporting evidence and attempts reference matching.

The result preserves the original prompt, extracted mentions, assertion attributes, reference identifiers and review flags. Unsupported or ambiguous mappings remain unresolved rather than being assigned inferred terminology codes.

Clinical extraction uses a backend-independent callable interface returning a validated Extraction object and usage metadata. The POC implements an Ollama adapter for local inference. Additional adapters can reuse the same evidence-validation, reference-matching and export stages.

## Relationship to the proposed classification engine strategy

| Pipeline stage | POC implementation | Scope |
|---|---|---|
| Input ingestion | Validates JSONL records and preserves message identifiers, country, original text and physical row numbers. | Each prompt is processed independently. |
| Text preprocessing | Creates a separate view using Unicode NFC normalization and whitespace/control-character cleanup. | Original text remains authoritative for evidence. Casing, accents, punctuation, negation, numbers and units are preserved. |
| Language detection | Uses fastText LID to return a language code and candidate scores; short or ambiguous inputs receive `und`. | Country is independent metadata. Uncertain language does not prevent extraction. |
| Clinical extraction | Makes one schema-constrained model request for six entity types, assertion attributes and explicit context modifiers. | The LLM is the primary extractor in this POC, simplifying the strategy's multi-route architecture. |
| Evidence validation | Checks entity text against the original prompt and derives character offsets. | Fabricated evidence is rejected; repeated occurrences receive review flags and null offsets. |
| Reference matching | Performs normalized exact lookup against versioned reference names and aliases. | Retains unmapped mentions and competing candidates. Generic LOINC component names cannot establish a more specific measurement code. |
| Confidence and review | Applies schema checks, evidence checks and explicit review rules. | Technical validation and detector scores are not calibrated clinical confidence. |
| Persistence and monitoring | Exports structured results, a review table and run metadata. | Includes processing counts, timing, input/reference hashes and available token usage. |

Preprocessing precedes language detection in the execution sequence. The model receives both raw and prepared text, with instructions to copy evidence from the raw prompt.

## Extracted attributes

The supported entity types are:

- `pathology`
- `symptom`
- `active_substance`
- `brand`
- `procedure`
- `diagnostic_test`

Diagnostic examinations are represented as `diagnostic_test`; therapeutic or interventional actions are represented as `procedure`. This is an implementation convention requiring domain validation.

Each entity contains an assertion object:

| Dimension | Supported values |
|---|---|
| Polarity | `affirmed`, `negated`, `uncertain`, `unspecified` |
| Temporality | `current`, `historical`, `future`, `unspecified` |
| Experiencer | `patient`, `family`, `other`, `unspecified` |
| Context | `patient_specific`, `hypothetical`, `general_question`, `unspecified` |

Polarity is one dimension of assertion status. A historical mention may also be negated, and a general question about a condition does not establish a patient diagnosis.

Entity-bound context modifiers cover severity, laterality, body site, duration, therapy line and eligibility. Each modifier includes textual evidence and a normalized value. These attributes use a local schema; they are not automatically mapped to ontology codes. Retained modifier relations are marked for review. Therapy line and eligibility are extracted only when explicit and remain experimental.

## Reference catalogue

The supplied `references.json` contains 3,788 records:

| Source | Included records | Coverage |
|---|---:|---|
| EMA | 3,731 | Product and source-substance records from the 2026-09-12 snapshot |
| ICD-10 | 3 | Demonstration concepts E11, J45 and R50 |
| LOINC 2.83 | 50 | Selected active laboratory terms |
| Local vocabulary | 4 | Appendectomy, biopsy, HbA1c and MRI, with illustrative aliases |

EMA coverage does not replace complete national medicine registers. EMA-derived local substance identifiers represent source spellings rather than authoritative chemical identities. Local vocabulary is explicitly distinguished from official terminology.

LOINC records preserve the original source fields, including identifiers, names, status and defining measurement attributes. Available official Italian, French and Spanish variants are retained. The supplied release contains Brazilian Portuguese rather than European Portuguese; pt-BR terms are not relabelled as pt-PT.

The LOINC subset is selected using the source's common-test ranking, excluding specimen metadata and records with external copyright notices. It is a demonstration subset, not a measure of relevance to the HCP dataset or European ordering frequency.

A complete long or short name may support an exact LOINC match. A component such as `Creatinine` only produces candidates: the pipeline does not infer specimen, property or method from an incomplete mention. Generic `HbA1c` may resolve to the explicitly local concept, not a specific LOINC measurement.

An RF2 Snapshot importer supports a user-selected subset of active SNOMED CT concepts and descriptions. No SNOMED CT dataset is bundled: licensed release access was unavailable during implementation. The importer was verified using synthetic RF2-format fixtures.

## Project files

| File | Purpose |
|---|---|
| `poc.py` | Input handling, language detection, extraction, validation, matching and export |
| `build_references.py` | Builds the LOINC subset and optionally imports selected SNOMED RF2 records |
| `references.json` | Runtime reference catalogue |
| `references_base.json` | EMA, ICD-10 and local records used during catalogue construction |
| `requirements.txt` | Runtime dependencies |
| `test_poc.py`, `test_pipeline_v2.py` | Engineering tests |
| `examples/` | Synthetic prompts, authored extraction responses and demonstration outputs |
| `LoincLicense_5.8.txt` | Licence accompanying the included LOINC content |

## Installation

Python 3.12 is recommended. Run commands from the project directory.

**Windows PowerShell:**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Linux or macOS:**

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Subsequent examples use `python`. Activate the environment, select it as the IDE interpreter, or substitute the environment's Python executable.

## Input format

Provide UTF-8 JSONL with one object per physical line:

```jsonl
{"chat_message_id": "001", "country": "PT", "prompt": "O doente não apresenta febre."}
{"chat_message_id": "002", "country": "IT", "prompt": "Il paziente ha una storia di appendicectomia."}
```

`chat_message_id` accepts a string or integer. `country` and `prompt` must be strings; the prompt must not be blank. Additional fields are ignored. Newlines within a prompt must be JSON-escaped.

Malformed records and duplicate JSON keys are reported without discarding subsequent records. Repeated message identifiers remain distinguishable through `row_id`. Prompts exceeding 20,000 characters are rejected rather than truncated.

## Execution

### Synthetic demonstration

```bash
python poc.py --demo --output demo_output
```

The demonstration uses 19 synthetic prompts with authored extraction responses. It executes language detection, validation, reference matching and export without requiring Ollama. It demonstrates pipeline behavior, not model performance.

### Model inference

Start Ollama and install a multilingual model supporting structured output. For example:

```bash
ollama pull qwen3.5:9b
python poc.py --input data/prompts.jsonl --model qwen3.5:9b --output run_output
```

The model tag is an illustrative configuration, not a clinically validated selection. The default endpoint is `http://localhost:11434`. Use `--endpoint` to supply an alternative supported endpoint and `--references` to select another catalogue.

Each valid record triggers one sequential model request, with temperature set to zero, a 60-second timeout and no automatic retry. Model failures are reported explicitly. Use separate output directories for separate runs; existing output files are overwritten.

Prompts are sent to the configured endpoint and retained in output files. The POC does not perform automated de-identification.

### Reference rebuilding

With the separately obtained LOINC archive:

```bash
python build_references.py --loinc Loinc_2.83.zip
```

Use `--limit` to change the subset size. The builder targets the inspected LOINC 2.83 layout and combines imported records with `references_base.json`.

To include licensed SNOMED data:

```bash
python build_references.py --loinc Loinc_2.83.zip --snomed YOUR_RF2.zip --snomed-types selected_types.json
```

The selection file maps verified concept identifiers to `pathology`, `symptom`, `procedure` or `diagnostic_test`. Missing or inactive selected concepts cause validation failure. National extensions may require the base edition. Importing a release does not confer redistribution rights.

## Outputs

| File | Contents |
|---|---|
| `results.jsonl` | One structured result per input record, including failures, evidence, assertions, matching outcomes and review issues |
| `review.csv` | Entity-level review rows, flattened assertion fields and reviewer notes; includes records with no extracted entities |
| `summary.json` | Processing counts, model/prompt identifiers, reference version, hashes, timing and available token totals |

Processing status is distinct from clinical correctness:

- `processed`: the technical workflow completed without a review flag.
- `needs_review`: an uncertainty or validation condition requires inspection.
- `invalid_input`: the record does not satisfy input requirements.
- `processing_error`: extraction failed.

Offsets refer to Python character positions in the original prompt. Matching outcomes distinguish exact matches, ambiguity, insufficient specificity and missing mappings. Reference provenance remains attached to successful matches.

## Verification

Run the engineering tests with:

```bash
python -m unittest discover -v
```

The supplied implementation passed 27 tests covering input validation, evidence preservation, assertion dimensions, language detection examples, modifier handling, LOINC specificity, translated reference names, RF2 active/inactive handling and the HTTP response contract.

The LOINC import and synthetic demonstration were also executed. Live-model extraction and clinical accuracy were not evaluated. A labelled, clinically reviewed sample is required to measure entity precision/recall, assertion accuracy, mapping quality and per-language performance.

## Scope and limitations

The POC implements a limited end-to-end path through the proposed classification engine strategy. Its principal boundaries are:

- **Business taxonomy:** intent, therapeutic area and consumer-health classification are excluded because controlled labels and annotation rules were not provided.
- **Extraction architecture:** one LLM replaces the proposed combination of deterministic extraction, trained multilingual NER and selective fallback. No comparative cost or throughput benefit is claimed.
- **Language robustness:** the supplied detector uses FastText LIT model. Short-input accuracy and the current abstention thresholds require evaluation on representative prompts; mixed-language segmentation is not implemented.
- **Terminology coverage:** the catalogue is partial. SNOMED availability, European Portuguese aliases and national medicine coverage remain constraints. Semantic retrieval, reranking and hierarchy-based resolution are outside this implementation.
- **Conversation context:** the available fields do not establish ordered conversation history. The extractor can flag missing context but cannot reconstruct it.
- **Clinical validation:** exact evidence confirms that text occurs, not that its type, assertion or modifier relation is correct. No calibrated clinical confidence is reported.
- **Batch scale:** results are accumulated in memory before export. The implementation is intended for sample-sized workloads.

These boundaries keep the first implementation reviewable while preserving the proposed strategy's central principles: original-language evidence, separation of extraction from concept resolution, provenance and explicit uncertainty.
