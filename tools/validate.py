#!/usr/bin/env python3
"""Validatore della knowledge base di Barbl.

Controlla schemi, riferimenti, copertura dei template, coerenza con il contratto
dell'app, regole su fonti e stato provvisorio, e le proprietà statiche dei casi
d'oro. Con --sources-md cerca anche frasi copiate dai Markdown dei libri.

Uso:
    python3 tools/validate.py
    python3 tools/validate.py --sources-md ~/Progetti/app-palestra/sources/md
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9]*)\}")
NGRAM = 8


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"ERRORE  {where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"AVVISO  {where}: {msg}")


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def load_yaml(p: Path):
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_schema(name: str) -> Draft202012Validator:
    with (ROOT / "schema" / f"{name}.schema.json").open(encoding="utf-8") as f:
        return Draft202012Validator(json.load(f))


def check_schema(r: Report, validator: Draft202012Validator, data, where: str) -> None:
    for e in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = "/".join(str(x) for x in e.path) or "(radice)"
        r.error(where, f"schema, {path}: {e.message}")


def load_dir(r: Report, folder: str, schema: str, id_key: str, recursive: bool = False):
    validator = load_schema(schema)
    items: dict[str, dict] = {}
    files = sorted((ROOT / folder).glob("**/*.yaml" if recursive else "*.yaml"))
    for p in files:
        data = load_yaml(p)
        check_schema(r, validator, data, rel(p))
        if not isinstance(data, dict) or id_key not in data:
            continue
        key = data[id_key]
        if key in items:
            r.error(rel(p), f"identificativo duplicato '{key}'")
        items[key] = data
        data["_file"] = rel(p)
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources-md", type=Path, help="cartella dei Markdown estratti dai PDF (controllo dei testi copiati)")
    args = ap.parse_args()
    r = Report()

    # Vocabolari e contratto
    muscles_doc = load_yaml(ROOT / "vocab/muscles.yaml")
    muscles = {m["id"]: m for m in muscles_doc["muscles"]}
    set_weights = muscles_doc["setWeights"]
    patterns = {p["id"]: p for p in load_yaml(ROOT / "vocab/patterns.yaml")["patterns"]}
    equipment_doc = load_yaml(ROOT / "vocab/equipment.yaml")
    profile_equipment = {e["id"] for e in equipment_doc["profileEquipment"]}
    gym_types = equipment_doc["gymTypes"]
    plan_schema = json.loads((ROOT / "contract/plan.schema.json").read_text(encoding="utf-8"))
    profile_schema = json.loads((ROOT / "contract/profile.schema.json").read_text(encoding="utf-8"))

    defs = plan_schema.get("$defs", {})
    contract_equipment = set(defs["exercise"]["properties"]["equipment"]["enum"])
    plan_equipment = set(equipment_doc["planEquipment"])
    if plan_equipment != contract_equipment:
        r.error("vocab/equipment.yaml", f"planEquipment diverso dal contratto: {sorted(contract_equipment)}")
    contract_splits = set(plan_schema["properties"]["split"]["enum"])
    contract_parameters = defs["parameters"]
    contract_groups = (contract_parameters or {}).get("properties", {})
    profile_gym_types = set(profile_schema["properties"]["gym"]["properties"]["type"]["enum"])
    if set(gym_types) != profile_gym_types:
        r.error("vocab/equipment.yaml", f"gymTypes diversi dal profilo del contratto: {sorted(profile_gym_types)}")
    for gt, items in gym_types.items():
        for e in items:
            if e not in profile_equipment:
                r.error("vocab/equipment.yaml", f"'{e}' in gymTypes.{gt} non è in profileEquipment")

    # File
    sources = load_dir(r, "sources", "source", "id")
    principles = load_dir(r, "principles", "principle", "id", recursive=True)
    exercises = load_dir(r, "exercises", "exercise", "id", recursive=True)
    templates = load_dir(r, "templates", "template", "id")
    prescriptions = load_dir(r, "prescriptions", "prescription", "id")
    parameters = load_dir(r, "parameters", "parameter", "group")
    rationales = load_dir(r, "rationales", "rationale", "ruleId")
    conflicts_doc = load_yaml(ROOT / "conflicts.yaml")
    check_schema(r, load_schema("conflicts"), conflicts_doc, "conflicts.yaml")
    conflicts = {c["id"]: c for c in conflicts_doc.get("conflicts", [])}

    for kind, items, key in (("sources", sources, "id"), ("rationales", rationales, "ruleId")):
        for k, d in items.items():
            if Path(d["_file"]).stem != k:
                r.error(d["_file"], f"il nome del file deve essere '{k}.yaml'")
    for k, d in exercises.items():
        if Path(d["_file"]).stem != k:
            r.error(d["_file"], f"il nome del file deve essere '{k}.yaml'")
        if Path(d["_file"]).parent.name != d["pattern"]:
            r.error(d["_file"], f"l'esercizio sta nella cartella del suo pattern '{d['pattern']}'")
    for k, d in parameters.items():
        if Path(d["_file"]).stem != k:
            r.error(d["_file"], f"il nome del file deve essere '{k}.yaml'")

    # Fonti
    for k, s in sources.items():
        if s["use"] == "public" and "url" not in s and "reference" not in s:
            r.warn(s["_file"], "fonte pubblica senza url né riferimento bibliografico")
        if s["use"] == "internal" and "url" in s:
            r.warn(s["_file"], "fonte interna con url: non va mostrata nell'app")

    # Principi
    for k, p in principles.items():
        where = p["_file"]
        if Path(where).parent.name != p["topic"]:
            r.error(where, f"il principio sta nella cartella del suo tema '{p['topic']}'")
        for s in p["sources"]:
            if s["id"] not in sources:
                r.error(where, f"fonte inesistente '{s['id']}'")
        for c in p.get("conflicts", []):
            ref = c["with"].split("#")[-1]
            if c["with"].startswith("conflicts.yaml") and ref not in conflicts:
                r.error(where, f"conflitto inesistente '{ref}'")
        if p["status"] == "confirmed":
            primary_full = any(
                s["access"] == "full_text" and sources.get(s["id"], {}).get("tier", 5) <= 3 for s in p["sources"]
            )
            if not primary_full:
                r.error(where, "confermato senza una fonte primaria (tier 1-3) letta nel testo completo")
            if not p["reviewedBy"]:
                r.error(where, "confermato senza revisione del coach (reviewedBy)")
        if p["evidence"] == "design" and not any(s["id"] == "barbl-design" for s in p["sources"]):
            r.error(where, "un principio di design deve citare la fonte 'barbl-design'")

    # Esercizi
    for k, e in exercises.items():
        where = e["_file"]
        if e["equipment"] not in plan_equipment:
            r.error(where, f"equipment '{e['equipment']}' non è nel contratto")
        if e["pattern"] not in patterns:
            r.error(where, f"pattern inesistente '{e['pattern']}'")
        elif patterns[e["pattern"]]["mechanics"] != e["mechanics"]:
            r.error(where, "mechanics diverso da quello del pattern")
        for req in e["requires"]:
            if req not in profile_equipment:
                r.error(where, f"attrezzatura '{req}' non è nel vocabolario del profilo")
        for m in [e["muscles"]["primary"], *e["muscles"]["secondary"]]:
            if m not in muscles:
                r.error(where, f"muscolo inesistente '{m}'")
        for s in e["substitutes"]:
            if s not in exercises:
                r.error(where, f"sostituto inesistente '{s}'")
            elif s == k:
                r.error(where, "un esercizio non può sostituire se stesso")
        if e["loading"]["whenLoadUnknown"] == "trial_set" and e["equipment"] != "barbell":
            r.error(where, "la serie di prova vale solo per i bilancieri (decisione A4 dell'app)")

    def available(ex: dict, gym: list[str]) -> bool:
        return set(ex["requires"]) <= set(gym)

    # Prescrizioni e template
    for k, pr in prescriptions.items():
        for role, v in pr["roles"].items():
            if v["reps"]["min"] > v["reps"]["max"]:
                r.error(pr["_file"], f"{role}: reps.min maggiore di reps.max")
    for k, t in templates.items():
        where = t["_file"]
        if t["split"] not in contract_splits:
            r.error(where, f"split '{t['split']}' non è nel contratto")
        session_ids = [s["id"] for s in t["sessions"]]
        if len(set(session_ids)) != len(session_ids):
            r.error(where, "id di seduta duplicati")
        if sorted(t["defaultSchedule"].values()) != sorted(session_ids):
            r.error(where, "defaultSchedule deve avere ogni seduta una volta sola")
        if len(t["defaultSchedule"]) != t["daysPerWeek"]:
            r.error(where, "defaultSchedule non ha daysPerWeek giorni")
        for p in t["principles"]:
            if p not in principles:
                r.error(where, f"principio inesistente '{p}'")
        for s in t.get("structureSources", []):
            if s["id"] not in sources:
                r.error(where, f"fonte inesistente '{s['id']}'")
        for sess in t["sessions"]:
            for bi, block in enumerate(sess["blocks"]):
                if block["type"] == "single" and len(block["slots"]) != 1:
                    r.error(where, f"{sess['id']} blocco {bi + 1}: un blocco single ha un solo slot")
                if block["type"] == "superset" and len(block["slots"]) < 2:
                    r.error(where, f"{sess['id']} blocco {bi + 1}: un superset ha almeno due slot")
                for slot in block["slots"]:
                    if slot["pattern"] not in patterns:
                        r.error(where, f"{sess['id']}: pattern inesistente '{slot['pattern']}'")
                    for c in slot["candidates"]:
                        if c not in exercises:
                            r.error(where, f"{sess['id']}: candidato inesistente '{c}'")
                    if slot["candidates"] and slot["candidates"][0] in exercises:
                        if exercises[slot["candidates"][0]]["pattern"] != slot["pattern"]:
                            r.error(where, f"{sess['id']}: il primo candidato deve avere il pattern dello slot")
                    for gt, gym in gym_types.items():
                        if not any(c in exercises and available(exercises[c], gym) for c in slot["candidates"]):
                            r.error(where, f"{sess['id']}, slot {slot['pattern']}: nessun candidato per la palestra '{gt}'")

    # Parametri e contratto
    for group, spec in contract_groups.items():
        if group not in parameters:
            if group in (contract_parameters or {}).get("required", []):
                r.error("parameters/", f"manca il gruppo obbligatorio del contratto '{group}'")
            continue
        p = parameters[group]
        required = [f for f in spec.get("required", []) if f not in ("provisional", "ruleId", "source")]
        for f in required:
            if f not in p["values"]:
                r.error(p["_file"], f"manca il campo '{f}' richiesto dal contratto")
        allowed = set(spec.get("properties", {}))
        for f in p["values"]:
            if allowed and f not in allowed:
                r.error(p["_file"], f"campo '{f}' sconosciuto al contratto")
        if "ruleId" in spec.get("required", []) and "ruleId" not in p:
            r.error(p["_file"], "il contratto richiede ruleId")
    for k, p in parameters.items():
        where = p["_file"]
        if p["target"] == "parameters" and k not in contract_groups:
            r.error(where, f"gruppo '{k}' sconosciuto al contratto")
        for pid in p["principles"]:
            if pid not in principles:
                r.error(where, f"principio inesistente '{pid}'")
                continue
            pr = principles[pid]
            if not p["provisional"]:
                if pr["status"] != "confirmed":
                    r.error(where, f"non provvisorio ma il principio '{pid}' non è confermato")
                if any(c["status"] == "open" for c in pr.get("conflicts", [])):
                    r.error(where, f"non provvisorio ma il principio '{pid}' ha un conflitto aperto")
    meso = parameters.get("mesocycle")
    if meso:
        weeks = meso["values"].get("weeks", [])
        if [w["number"] for w in weeks] != list(range(1, len(weeks) + 1)):
            r.error(meso["_file"], "settimane non numerate da 1 in ordine")
        deload = parameters.get("deload")
        last = weeks[-1] if weeks else None
        if deload and last and last["type"] == "deload" and last["rirTarget"] != deload["values"]["rirTarget"]:
            r.error(meso["_file"], "il RIR della settimana di scarico è diverso da parameters/deload")

    # Motivazioni
    rule_ids = {p["ruleId"] for p in parameters.values() if "ruleId" in p}
    for rid in sorted(rule_ids):
        if rid not in rationales:
            r.error("rationales/", f"manca la motivazione di '{rid}'")
    for k, ra in rationales.items():
        where = ra["_file"]
        it, en = ra["text"]["it"], ra["text"]["en"]
        if set(PLACEHOLDER.findall(it)) != set(PLACEHOLDER.findall(en)):
            r.error(where, "italiano e inglese usano segnaposto diversi")
        for lang, t in (("it", it), ("en", en)):
            if t.count("**") % 2:
                r.error(where, f"marcatore ** non chiuso ({lang})")
        bold_it = re.findall(r"\*\*(.*?)\*\*", it)
        bold_en = re.findall(r"\*\*(.*?)\*\*", en)
        if sorted(PLACEHOLDER.findall(" ".join(bold_it))) != sorted(PLACEHOLDER.findall(" ".join(bold_en))):
            r.error(where, "italiano e inglese marcano in grassetto segnaposto diversi")
        principle_ids: list[str] = []
        if "sourcesFrom" in ra:
            group = ra["sourcesFrom"].split("/", 1)[1]
            if group not in parameters:
                r.error(where, f"sourcesFrom punta a un gruppo inesistente '{group}'")
            else:
                principle_ids = parameters[group]["principles"]
        else:
            principle_ids = ra["principles"]
        shown = set()
        for pid in principle_ids:
            if pid not in principles:
                r.error(where, f"principio inesistente '{pid}'")
                continue
            for s in principles[pid]["sources"]:
                src = sources.get(s["id"])
                if src and src["use"] == "public" and src.get("url"):
                    shown.add(s["id"])
        if not shown:
            r.warn(where, "nessuna fonte pubblica con url da mostrare nel «Perché?»")

    # Conflitti
    for k, c in conflicts.items():
        for b in c["between"]:
            if b.startswith("P-") and b not in principles:
                r.error("conflicts.yaml", f"{k}: principio inesistente '{b}'")

    # Casi d'oro
    check_golden(r, principles, exercises, templates, prescriptions, parameters, muscles, set_weights, gym_types, patterns)

    # Testi copiati
    if args.sources_md:
        check_copied_text(r, args.sources_md)

    for w in r.warnings:
        print(w)
    for e in r.errors:
        print(e)
    counts = (
        f"{len(sources)} fonti, {len(principles)} principi, {len(exercises)} esercizi, "
        f"{len(templates)} template, {len(parameters)} gruppi di parametri, {len(rationales)} motivazioni"
    )
    if r.errors:
        print(f"\n{len(r.errors)} errori, {len(r.warnings)} avvisi ({counts})")
        return 1
    print(f"\nKB valida: {counts}; {len(r.warnings)} avvisi")
    return 0


def check_golden(r, principles, exercises, templates, prescriptions, parameters, muscles, set_weights, gym_types, patterns):
    golden_validator = load_schema("golden")
    for gp in sorted((ROOT / "golden").glob("*.yaml")):
        g = load_yaml(gp)
        where = rel(gp)
        check_schema(r, golden_validator, g, where)
        profile = json.loads((ROOT / g["profile"]).read_text(encoding="utf-8"))
        gym = profile["gym"]["equipment"]
        matching = [
            t for t in templates.values()
            if t["daysPerWeek"] == profile["daysPerWeek"] and profile["goal"] in t["goals"]
        ]
        if len(matching) != 1:
            r.error(where, f"servono un solo template per il profilo, trovati {len(matching)}")
            continue
        t = matching[0]
        pres = [p for p in prescriptions.values() if profile["goal"] in p["appliesTo"]]
        if len(pres) != 1:
            r.error(where, f"servono una sola prescrizione per l'obiettivo, trovate {len(pres)}")
            continue
        pr = pres[0]
        exp = g["expect"]
        if exp.get("split") and t["split"] != exp["split"]:
            r.error(where, f"split {t['split']} invece di {exp['split']}")
        if exp.get("sessions") and len(t["sessions"]) != exp["sessions"]:
            r.error(where, f"{len(t['sessions'])} sedute invece di {exp['sessions']}")
        if exp.get("scheduleDays") and sorted(t["defaultSchedule"]) != sorted(exp["scheduleDays"]):
            r.error(where, f"giorni {sorted(t['defaultSchedule'])} invece di {sorted(exp['scheduleDays'])}")
        weeks = parameters["mesocycle"]["values"]["weeks"]
        m = exp.get("mesocycle", {})
        if m.get("weeks") and len(weeks) != m["weeks"]:
            r.error(where, f"{len(weeks)} settimane invece di {m['weeks']}")
        if m.get("lastWeekType") and weeks[-1]["type"] != m["lastWeekType"]:
            r.error(where, "l'ultima settimana non è di scarico")
        for wk, rir in m.get("rirTargetByWeek", {}).items():
            if weeks[int(wk) - 1]["rirTarget"] != rir:
                r.error(where, f"RIR della settimana {wk} diverso da {rir}")

        chosen: dict[str, dict] = {}
        weekly: dict[str, float] = {k: 0.0 for k in muscles}
        max_rir = max(w["rirTarget"] for w in weeks if w["rirTarget"] is not None)
        max_minutes = profile["sessionDurationMin"]
        for sess in t["sessions"]:
            sets_in_session = 0
            for block in sess["blocks"]:
                for slot in block["slots"]:
                    pick = next((exercises[c] for c in slot["candidates"] if c in exercises and set(exercises[c]["requires"]) <= set(gym)), None)
                    if not pick:
                        r.error(where, f"{sess['id']}: nessun esercizio disponibile per lo slot {slot['pattern']}")
                        continue
                    role = pr["roles"][slot["role"]]
                    chosen[pick["id"]] = {"role": slot["role"], "reps": slot.get("repsOverride", role["reps"])}
                    sets_in_session += role["sets"]
                    weekly[pick["muscles"]["primary"]] += role["sets"] * set_weights["primary"]
                    for sec in pick["muscles"]["secondary"]:
                        weekly[sec] += role["sets"] * set_weights["secondary"]
            minutes = sets_in_session * pr["timeBudget"]["minutesPerSet"]
            if minutes > max_minutes:
                r.error(where, f"{sess['id']}: circa {minutes} minuti, oltre i {max_minutes} del profilo")
        ws = exp.get("weeklySetsAtLeast", {})
        if ws:
            if ws.get("counting") != "fractional":
                r.error(where, "il controllo statico conta solo le serie frazionarie")
            for mus, minimum in ws["values"].items():
                if weekly.get(mus, 0) < minimum:
                    r.error(where, f"{mus}: {weekly.get(mus, 0):g} serie frazionarie, minimo {minimum}")
        known = {k["exerciseId"]: k for k in profile.get("knownLoads", [])}
        trial = parameters["trialLoad"]
        cap = trial.get("engineConstraints", {}).get("maxRepsPlusRir")
        for ex_id, want in exp.get("initialLoad", {}).items():
            if ex_id not in chosen:
                r.error(where, f"'{ex_id}' non è tra gli esercizi scelti per il profilo")
                continue
            kl = known.get(ex_id)
            if want["source"] == "profile":
                if not kl or kl.get("kg") != want["kg"]:
                    r.error(where, f"'{ex_id}': carico {want['kg']} atteso dal profilo")
            elif want["source"] == "trial_set":
                if exercises[ex_id]["loading"]["whenLoadUnknown"] != "trial_set":
                    r.error(where, f"'{ex_id}': l'esercizio non ammette la serie di prova")
                if cap is not None and chosen[ex_id]["reps"]["min"] + max_rir > cap:
                    r.error(where, f"'{ex_id}': ripetizioni minime + RIR massimo oltre {cap}, niente serie di prova")
        print(f"{where}: " + ", ".join(f"{k} {v:g}" for k, v in weekly.items() if v) + " (serie frazionarie a settimana)")


def check_copied_text(r: Report, md_dir: Path) -> None:
    def words(s: str) -> list[str]:
        return re.findall(r"[a-zà-ù0-9]+", s.lower())

    grams: set[tuple[str, ...]] = set()
    for f in sorted(md_dir.glob("*.md")):
        w = words(f.read_text(encoding="utf-8", errors="ignore"))
        grams.update(tuple(w[i:i + NGRAM]) for i in range(len(w) - NGRAM + 1))

    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for v in node.values():
                yield from strings(v)
        elif isinstance(node, list):
            for v in node:
                yield from strings(v)

    for p in sorted(ROOT.glob("**/*.yaml")):
        # Titoli, autori e url delle fonti compaiono legittimamente nelle bibliografie dei libri.
        if p.relative_to(ROOT).parts[0] in ("golden", "sources"):
            continue
        for s in strings(load_yaml(p)):
            w = words(s)
            for i in range(len(w) - NGRAM + 1):
                if tuple(w[i:i + NGRAM]) in grams:
                    r.error(rel(p), f"sequenza copiata da una fonte: «{' '.join(w[i:i + NGRAM])}»")
                    break


if __name__ == "__main__":
    sys.exit(main())
