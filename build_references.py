"""Build a small reference JSON from LOINC Complete and optional licensed RF2 Snapshot."""
import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VARIANTS = {"it-IT": "itIT16", "fr-FR": "frFR18", "es-ES": "esES12"}


def rows(archive, name):
    with archive.open(name) as stream:
        yield from csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))


def loinc_concepts(path, limit=50):
    with zipfile.ZipFile(path) as z:
        # Rank is source data, not a claim about the unseen HCP dataset distribution.
        selected = sorted((r for r in rows(z, "LoincTable/Loinc.csv")
                           if r["STATUS"] == "ACTIVE" and r["CLASSTYPE"] == "1"
                           and r["CLASS"] != "SPEC" and not r["EXTERNAL_COPYRIGHT_NOTICE"]
                           and r["COMMON_TEST_RANK"].isdigit() and 0 < int(r["COMMON_TEST_RANK"]) < 20000),
                          key=lambda r: (int(r["COMMON_TEST_RANK"]), r["LOINC_NUM"]))[:limit]
        concepts = {}
        for r in selected:
            exact = [r[k] for k in ("LONG_COMMON_NAME", "SHORTNAME") if r[k]]
            concepts[r["LOINC_NUM"]] = {
                "id": "LOINC:" + r["LOINC_NUM"], "source": "LOINC", "release": "2.83",
                "label": r["LONG_COMMON_NAME"], "type": "diagnostic_test",
                "source_url": "https://loinc.org/" + r["LOINC_NUM"] + "/",
                "aliases": sorted(set(exact + [r["COMPONENT"]])), "exact_aliases": exact,
                "source_record": r, "linguistic_variants": {},
                "alias_policy": "Full long/short names can match; components are candidates only."}
        for locale, prefix in VARIANTS.items():
            name = "AccessoryFiles/LinguisticVariants/" + prefix + "LinguisticVariant.csv"
            for r in rows(z, name):
                if r["LOINC_NUM"] not in concepts:
                    continue
                c = concepts[r["LOINC_NUM"]]
                c["linguistic_variants"][locale] = r
                names = [r[k] for k in ("LONG_COMMON_NAME", "SHORTNAME") if r[k]]
                c["exact_aliases"] += names
                c["aliases"] += names + ([r["COMPONENT"]] if r["COMPONENT"] else [])
        for c in concepts.values():
            c["aliases"] = sorted(set(c["aliases"]))
            c["exact_aliases"] = sorted(set(c["exact_aliases"]))
        return list(concepts.values()), z.read("LoincLicense_5.8.txt")


def snomed_concepts(path, type_map):
    """Read a selected subset; selection/type assignment is explicitly user supplied.

    No hierarchy inference. Only active concepts and active descriptions; no GPS
    masquerading as a full RF2 release. National extensions may require base files.
    """
    result = {}
    allowed = {"pathology", "symptom", "procedure", "diagnostic_test"}
    if any(t not in allowed for t in type_map.values()):
        raise ValueError("Unsupported SNOMED type mapping")
    with zipfile.ZipFile(path) as z:
        concept_files = [n for n in z.namelist() if "/Snapshot/Terminology/" in "/" + n and Path(n).name.startswith("sct2_Concept_Snapshot")]
        description_files = [n for n in z.namelist() if "/Snapshot/Terminology/" in "/" + n and Path(n).name.startswith("sct2_Description_Snapshot")]
        if not concept_files or not description_files:
            raise ValueError("Expected RF2 Snapshot concept and description files")
        for name in concept_files:
            with z.open(name) as f:
                for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter="\t"):
                    if r["id"] in type_map and r["active"] == "1":
                        result[r["id"]] = {"id": "SNOMEDCT:" + r["id"], "source": "SNOMEDCT",
                            "release": Path(path).name, "effective_time": r["effectiveTime"],
                            "type": type_map[r["id"]], "label": "", "aliases": [], "descriptions": [],
                            "source_url": "http://snomed.info/id/" + r["id"]}
        for name in description_files:
            with z.open(name) as f:
                for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter="\t"):
                    c = result.get(r["conceptId"])
                    if c is not None and r["active"] == "1":
                        c["descriptions"].append(r)
                        c["aliases"].append(r["term"])
                        if not c["label"] or r["typeId"] == "900000000000003001":
                            c["label"] = r["term"]
        missing = set(type_map) - {k for k, v in result.items() if v["aliases"]}
        if missing:
            raise ValueError("Selected SNOMED concepts inactive/missing descriptions: " + ", ".join(sorted(missing)))
    return list(result.values())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--loinc", type=Path, required=True)
    p.add_argument("--base", type=Path, default=ROOT / "references_base.json")
    p.add_argument("--output", type=Path, default=ROOT / "references.json")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--snomed", type=Path)
    p.add_argument("--snomed-types", type=Path, help='JSON object: {"conceptId": "symptom", ...}')
    args = p.parse_args()
    if args.limit < 1 or bool(args.snomed) != bool(args.snomed_types):
        p.error("Positive limit required; provide both --snomed and --snomed-types")
    base = json.loads(args.base.read_text(encoding="utf-8"))
    loinc, license_bytes = loinc_concepts(args.loinc, args.limit)
    base["concepts"].extend(loinc)
    base["version"] += "+LOINC-2.83-poc-v2"
    base["scope"] = "EMA + tiny ICD subset + authored local concepts + selected LOINC lab terms; not comprehensive"
    base["imports"] = [{"source": "LOINC", "version": "2.83", "archive_sha256": hashlib.sha256(args.loinc.read_bytes()).hexdigest(),
                        "records": len(loinc), "selection": "Top active laboratory COMMON_TEST_RANK excluding SPEC and external copyright notices",
                        "locales": list(VARIANTS), "pt_PT_available": False}]
    if args.snomed:
        concepts = snomed_concepts(args.snomed, json.loads(args.snomed_types.read_text()))
        base["concepts"].extend(concepts)
        base["imports"].append({"source": "SNOMEDCT", "records": len(concepts),
                                "archive_sha256": hashlib.sha256(args.snomed.read_bytes()).hexdigest()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output.parent / "LoincLicense_5.8.txt").write_bytes(license_bytes)
    print(json.dumps({"records": len(base["concepts"]), "imports": base["imports"]}, indent=2))


if __name__ == "__main__":
    main()
