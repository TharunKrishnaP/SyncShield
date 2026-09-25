"""Build the REAL-WORLD incident corpus for the FDR text classifier (Phase 1, v2).

ALL text and labels come from real-world sources — no templates, no synthetic
phrasings, no fabricated rows:

  PRIMARY   HumAID (QCRI, Alam et al. ICWSM 2021) — 43,409 human-annotated
            tweets from 13 major disaster events (2016-2019), including real
            flood events. Each event ships official train/dev/test splits.
            https://crisisnlp.qcri.org/humaid_dataset

  SECONDARY CrisisNLP (QCRI, Imran et al. LREC 2016) — human-annotated
            disaster tweets:
              - CrowdFlower (paid-worker) labeled data (12 events, 3-col TSV)
              - Volunteers (AIDR) labeled data (readable-label CSVs)
            Includes real 2014 India floods + 2014 Pakistan floods tweets.

  SYSTEM    Real citizen reports + NDMA alerts already stored in this
            project's datalake (ml/../data_lake/index.json). Test-only rows —
            the system's own real operational data, never used for training.

SPLIT (event-disjoint, zero leakage):
  Every row of a held-out TEST event is used for testing; none of its tweets
  ever appear in training. HumAID's own dev/train rows for held-out events
  are ALSO used as test rows (maximising real test coverage).

TEST_EVENTS (real disasters held out entirely):
  - srilanka_floods_2017      (real South-Asia flood event)
  - maryland_floods_2018      (real US flood event)
  - 2015_Cyclone_Pam_en       (real cyclone/flood, CrisisNLP)
  - 2014_Philippines_Typhoon_Hagupit_en  (real typhoon/flood)
  - 2014_Hurricane_Odile_Mexico_en       (real hurricane)
  Plus all rows from the datalake live system reports.

LABEL MAPPING (documented, deterministic):
  HumAID/CrisisNLP humanitarian labels are COARSE categories. Each coarse
  label is (a) mapped to an FDR category directly when unambiguous,
  (b) refined to a specific FDR category ONLY when the tweet text carries
  keyword evidence (signal dictionary below mirrors the project's rule
  engine), or (c) assigned OTHER (real text, honestly coarse) — a label is
  never invented. Non-incident classes (sympathy, not_humanitarian, etc.)
  are dropped.

Produces ``ml/data/text_corpus.jsonl``:
  {"text", "label", "split": "train"|"test", "origin": "<provenance>",
   "source_id": "...", "coarse_label": "...", "dataset": "...", "event": "..."}
"""
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRISIS_DIR = ROOT / "data" / "crisisnlp"
HUMAID_DIR = ROOT / "data" / "humaid"
OUT = ROOT / "data" / "text_corpus.jsonl"
DATALAKE = ROOT.parent / "data_lake" / "index.json"

FDR_CATEGORIES = [
    "FLOODED_ROAD", "TRAPPED_RESIDENTS", "POWER_OUTAGE", "HOSPITAL_ACCESS_BLOCKED",
    "BRIDGE_COLLAPSE", "LANDSLIDE", "EVACUATION_NEEDED", "RELIEF_SHELTER_FULL",
    "WATER_CONTAMINATION", "COMMUNICATION_DOWN", "OTHER",
]

# ---------------------------------------------------------------------------
# Keyword evidence used to refine coarse labels (mirrors nlp_extractor signals,
# widened for casual social-media phrasing).
# ---------------------------------------------------------------------------
_SIGNALS = {
    "FLOODED_ROAD": [
        r"road\s+(submerg|under\s*water|block|flood)", r"water\s+(on|logged)\s+road",
        r"flood(ed|ing)\s+(the\s+)?(road|street|highway|nh|street)", r"traffic\s+(jam|stop|disrupt|blocked)",
        r"vehicles?\s+(stuck|submerged|stranded)", r"underpass\s+(flood|water|closed)",
        r"nh-?\d+", r"street\s+(flood|under\s+water|blocked)", r"cars?\s+(stuck|stranded|flooded)",
        r"roads?\s+(closed|blocked|flooded|washed)", r"motorway\s+(closed|flooded|block)",
        r"commute|transport\s+disrupt",
    ],
    "TRAPPED_RESIDENTS": [
        r"(people|person|men|women|child|children|family|families|residents|villagers|students|workers|tourists)\s+(trapped|stranded|maroon|stuck|buried)",
        r"trapped\s+(in|on|under)", r"stranded\s+(in|at|on)", r"stuck\s+(in|on)",
        r"(on|under)\s+(roof|rubble|debris|building|floor|rubble)", r"missing\s+(people|child|children|persons|families)",
        r"rescue\s+(team|workers|operation|efforts?|boats?)", r"rescuers?", r"pull(ed|ing)?\s+out",
        r"caught\s+(in|under)", r"buried\s+alive", r"survivors?\s+(trapped|dug|pulled)",
    ],
    "POWER_OUTAGE": [
        r"power\s+(outage|cut|fail|loss|gone|shutdown|off|restored|restoration)", r"electric(?:ity)?\s+(cut|fail|gone|down|loss|off)",
        r"no\s+(power|electricity|light|lights)", r"transformer\s+(blast|blow|burst|explod|fire|fail)",
        r"electrical?\s+(line|wire|grid)\s+(down|cut|fail|snapp|damag)", r"blackout",
        r"powerless", r"power\s+grip", r"load[- ]?shedding", r"electric\s+(shock|poles?\s+down|wires?\s+down)",
        r"power\s+(plant|station|supply|line)\s+(shut|down|fail|disrupt)",
    ],
    "HOSPITAL_ACCESS_BLOCKED": [
        r"hospital\s+(access|block|close|road|gate|flood|overwhelm)", r"ambulance\s+(stuck|delay|cannot|block|unable)",
        r"medical\s+(emergency|block|access|help)", r"can'?t\s+(reach|get to|make it to)\s+(the\s+)?hospital",
        r"clinics?\s+(flood|close|damag)", r"medical\s+supplies", r"(doctors?|nurses?)\s+cannot",
        r"(patients?|injured)\s+cannot\s+(reach|get)\s+(the\s+)?hospital", r"maternity|delivery\s+blocked",
    ],
    "BRIDGE_COLLAPSE": [
        r"bridge\s+(collaps|fail|damag|wash|broken|bent|closed|crack|part|down|gone|swept|destroy)",
        r"bridge\s+(was|is|got)\s+(washed|destroyed|damaged|swept)", r"fell\s+into\s+(the\s+)?river",
        r"bridges?\s+(down|out|cut off)", r"bridge\s+(over|across)\s+(the\s+)?(river|creek)\s+(gave|collapsed|washed)",
    ],
    "LANDSLIDE": [
        r"landslide", r"mudslide", r"rock\s+slide", r"land\s+slide", r"hillslope",
        r"slope\s+(fail|crack|slip)", r"debris\s+flow", r"boulder", r"mud\s+slide",
        r"avalanche", r"earth\s+slide", r"landslip",
    ],
    "EVACUATION_NEEDED": [
        r"evacuat", r"relocat", r"shift\s+(people|residents|family|families|villagers)",
        r"move\s+(them|people|residents|families|everyone)", r"need(?:s|ed)?\s+(boats?|help|rescue|assistance)",
        r"boats?\s+(needed|required)", r"displaced", r"take\s+(them|people)\s+to", r"higher\s+ground",
        r"left\s+homeless", r"homeless", r"stranded\s+(need|families)|evacuation\s+(order|center|centre|camp)",
        r"get\s+(them|people|everyone)\s+out", r"flee(ing)?", r"ordered\s+to\s+leave",
    ],
    "RELIEF_SHELTER_FULL": [
        r"shelter\s+(full|overflow|crowd|pack)", r"relief\s+camp", r"no\s+(food|water|medicine|supplies)",
        r"shortage\s+of\s+(food|water|medicine|supplies)", r"need\s+(food|shelter|supplies|medicine|aid|help)",
        r"(food|water|supplies|donations?)\s+(needed|required|urgently|running out)", r"ration",
        r"homeless\s+(need|families)", r"camp\s+(full|crowded|overflow)", r"aid\s+(needed|required|urgent)",
        r"supplies?\s+(running|running out|needed|short)", r"donat(e|ions)?\s+(needed|required)",
    ],
    "WATER_CONTAMINATION": [
        r"water\s+(contaminat|pollut|dirty|unsafe|unfit)", r"sewage\s+(mix|overflow|enter)",
        r"drinking\s+water\s+(shortage|contamin|unsafe|pollut|not)", r"contaminat(ed|ion)",
        r"stagnant\s+water", r"diarrhoe?a", r"cholera", r"disease", r"water-borne", r"waterborne",
        r"purif(y|ied|ication)|boil\s+water|water\s+supply\s+(contamin|pollut)",
    ],
    "COMMUNICATION_DOWN": [
        r"(phone|mobile|network|internet|telecom|telephone|wifi|broadband|cell)\s+(down|fail|cut|off|disrupt|out|dead)",
        r"no\s+(signal|network|service|coverage|reception)", r"communication\s+(down|cut|failed|lost)",
        r"can'?t\s+(call|reach)\s+(anyone|family)", r"lost\s+contact", r"no\s+reception",
        r"cell\s+service\s+(down|out|dead)", r"coverage\s+(down|gone|lost)",
    ],
}

# Token co-occurrence refinement for casual phrasing: strong token(s) AND
# context token(s) both appear (e.g., "power" + "gone").
_TOKEN_RULES = {
    "POWER_OUTAGE": (("power", "electricity", "electric", "light"), ("gone", "cut", "out", "fail", "off", "lost", "shutdown", "blackout")),
    "FLOODED_ROAD": (("road", "street", "highway", "nh", "motorway", "traffic"), ("flood", "water", "submerged", "under water", "blocked", "stuck", "closed")),
    "COMMUNICATION_DOWN": (("phone", "mobile", "network", "internet", "signal", "cell", "telecom"), ("down", "dead", "no", "lost", "cut", "out", "gone")),
    "TRAPPED_RESIDENTS": (("people", "family", "families", "children", "child", "residents", "villagers", "workers"), ("trapped", "stranded", "stuck", "buried", "missing")),
    "HOSPITAL_ACCESS_BLOCKED": (("hospital", "clinic", "ambulance", "medical", "patients", "injured"), ("blocked", "cannot", "can't", "can not", "flooded", "cut off", "access", "reach")),
    "EVACUATION_NEEDED": (("people", "residents", "families", "villagers", "everyone", "them"), ("evacuate", "evacuation", "move", "shift", "relocate", "higher ground")),
}


def _refine_fdr(text: str) -> str:
    """Refine a coarse humanitarian label to an FDR category using keyword
    evidence. Returns the FIRST category with a signal match, else OTHER."""
    low = text.lower()
    for cat in ("TRAPPED_RESIDENTS", "BRIDGE_COLLAPSE", "LANDSLIDE",
                "HOSPITAL_ACCESS_BLOCKED", "POWER_OUTAGE", "COMMUNICATION_DOWN",
                "WATER_CONTAMINATION", "EVACUATION_NEEDED", "RELIEF_SHELTER_FULL",
                "FLOODED_ROAD"):
        for pat in _SIGNALS[cat]:
            if re.search(pat, low):
                return cat
    for cat, (strong, ctx) in _TOKEN_RULES.items():
        if any(f" {t} " in f" {low} " for t in strong) and any(f" {t} " in f" {low} " for t in ctx):
            return cat
    return "OTHER"


# ---------------------------------------------------------------------------
# Coarse-label -> handling.
#   ("drop",)                     non-incident rows are excluded
#   ("map", FDR_CATEGORY)         unambiguous direct mapping
#   ("refine",)                   keyword refinement over real tweet text
# ---------------------------------------------------------------------------
_CF_MAP = {
    # CrisisNLP CrowdFlower
    "not_related_or_irrelevant": ("drop",),
    "sympathy_and_emotional_support": ("drop",),
    "personal_updates": ("drop",),
    "donation_needs_or_offers_or_volunteering_services": ("refine",),
    "caution_and_advice": ("refine",),
    "other_useful_information": ("refine",),
    "infrastructure_and_utilities_damage": ("refine",),
    "injured_or_dead_people": ("refine",),
    "missing_trapped_or_found_people": ("refine",),
    "displaced_people_and_evacuations": ("map", "EVACUATION_NEEDED"),
    # CrisisNLP volunteers (human-readable)
    "not relevant": ("drop",),
    "not related or irrelevant": ("drop",),
    "sympathy and emotional support": ("drop",),
    "personal updates": ("drop",),
    "money": ("drop",),
    "response efforts": ("refine",),
    "other relevant information": ("refine",),
    "other": ("refine",),
    "infrastructure damage": ("refine",),
    "infrastructure and utilities": ("refine",),
    "injured or dead people": ("refine",),
    "missing, trapped, or found people": ("refine",),
    "displaced people": ("map", "EVACUATION_NEEDED"),
    "displaced people and evacuations": ("map", "EVACUATION_NEEDED"),
    "urgent needs": ("refine",),
    "caution and advice": ("refine",),
    "shelter and supplies": ("map", "RELIEF_SHELTER_FULL"),
    "physical landslide": ("map", "LANDSLIDE"),
    "not physical landslide": ("drop",),
    "traditional media": ("drop",),
    "volunteer or professional services": ("drop",),
    "unknown": ("drop",),
    # HumAID
    "not_humanitarian": ("drop",),
    "sympathy_and_support": ("drop",),
    "caution_and_advice": ("refine",),
    "other_relevant_information": ("refine",),
    "infrastructure_and_utility_damage": ("refine",),
    "injured_or_dead_people": ("refine",),
    "missing_or_found_people": ("refine",),
    "displaced_people_and_evacuations": ("map", "EVACUATION_NEEDED"),
    "requests_or_urgent_needs": ("refine",),
    "rescue_volunteering_or_donation_effort": ("refine",),
}

# Events held out ENTIRELY for testing — no tweet from these disasters is ever
# seen during training (honest cross-event generalization test).
TEST_EVENTS = {
    # real flood/cyclone disasters
    "srilanka_floods_2017",
    "maryland_floods_2018",
    # CrisisNLP flood-adjacent events
    "2015_Cyclone_Pam_en",
    "2014_Philippines_Typhoon_Hagupit_en",
    "2014_Hurricane_Odile_Mexico_en",
}


def _resolve(label: str, text: str) -> str:
    key = label.strip().lower()
    action = _CF_MAP.get(key)
    if action is None:
        return None  # unknown coarse label: honest fallback (dropped)
    kind = action[0]
    if kind == "drop":
        return None
    if kind == "map":
        return action[1]
    return _refine_fdr(text)


def _load_humaid(root: Path):
    """HumAID set1: per-event train/dev/test TSVs (tweet_id, text, class_label)."""
    rows = []
    base = root / "extracted" / "events_set1"
    for tsv in base.rglob("*_train.tsv"):
        pass  # iterate all splits below
    for tsv in base.rglob("*.tsv"):
        event = tsv.parent.name
        split = tsv.stem.split("_")[-1].strip()
        if split not in ("train", "dev", "test"):
            continue
        with open(tsv, encoding="utf-8", errors="replace") as fh:
            rd = csv.reader(fh, delimiter="\t")
            header = next(rd)
            li = header.index("class_label") if "class_label" in header else 2
            for r in rd:
                if len(r) <= li:
                    continue
                tid, text, label = r[0], r[1] if len(r) > 1 else "", r[li].strip()
                if not text.strip():
                    continue
                rows.append({"event": event, "tweet_id": tid,
                             "text": text, "coarse": label,
                             "origin": f"humaid:{event}:{split}"})
    return rows


def _load_cf(root: Path):
    """CrisisNLP CrowdFlower (paid-worker) TSVs."""
    rows = []
    base = root / "CrisisNLP_labeled_data_crowdflower"
    for tsv in base.rglob("*_CF_labeled_data.tsv"):
        event = tsv.parent.name
        with open(tsv, encoding="utf-8", errors="replace") as fh:
            rd = csv.reader(fh, delimiter="\t")
            header = next(rd)
            li = header.index("label") if "label" in header else 2
            for r in rd:
                if len(r) <= li:
                    continue
                tid, text, label = r[0], r[1] if len(r) > 1 else "", r[li].strip()
                if not text.strip():
                    continue
                rows.append({"event": event, "tweet_id": tid,
                             "text": text, "coarse": label,
                             "origin": f"crisisnlp-crowdflower:{event}"})
    return rows


def _load_vol(root: Path):
    """CrisisNLP volunteers (AIDR) CSVs: wider schema, label is the last column."""
    rows = []
    base = root / "CrisisNLP_volunteers_labeled_data"
    for csvf in base.rglob("*.csv"):
        event = csvf.parent.name
        with open(csvf, encoding="utf-8", errors="replace") as fh:
            rd = csv.reader(fh)
            header = next(rd)
            names = [h.strip().lower() for h in header]
            ti_text = names.index("tweet_text") if "tweet_text" in names else 1
            li = names.index("label") if "label" in names else len(header) - 1
            for r in rd:
                if len(r) <= li:
                    continue
                text = r[ti_text] if ti_text < len(r) else ""
                if not text or not text.strip():
                    continue
                label = r[li].strip()
                rows.append({"event": event,
                             "tweet_id": r[0] if len(r) > 0 else "",
                             "text": text, "coarse": label,
                             "origin": f"crisisnlp-volunteers:{event}"})
    return rows


def _load_datalake_real():
    """Secondary signal: real citizen reports + NDMA alerts from the datalake.
    Test-only rows (the system's own real data, never trained on)."""
    rows = []
    try:
        idx = json.loads(DATALAKE.read_text(encoding="utf-8"))
    except Exception:
        return rows, 0
    seen = set()
    n_real = 0
    for i in idx.get("incidents", []):
        src = i.get("source", "")
        if src not in ("CITIZEN_REPORT", "NDMA_SACHET"):
            continue
        text = str(i.get("description", "")).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        n_real += 1
        rows.append({
            "event": "datalake-live", "tweet_id": i.get("id", ""),
            "text": text, "coarse": i.get("category", "OTHER"),
            "origin": f"system:{src.lower()}",
        })
    return rows, n_real


def main():
    humaid = _load_humaid(HUMAID_DIR)
    cf = _load_cf(CRISIS_DIR)
    vol = _load_vol(CRISIS_DIR)
    live, n_real = _load_datalake_real()
    print(f"raw rows: humaid={len(humaid)} cf={len(cf)} volunteers={len(vol)} live={n_real}")

    emitted = []
    dropped = Counter()
    by_event = Counter()
    by_coarse = Counter()

    for row in humaid + cf + vol:
        label = _resolve(row["coarse"], row["text"])
        if label is None:
            dropped[row["coarse"]] += 1
            continue
        split = "test" if row["event"] in TEST_EVENTS else "train"
        by_event[row["event"]] += 1
        by_coarse[row["coarse"]] += 1
        emitted.append({
            "text": row["text"].strip(),
            "label": label,
            "split": split,
            "origin": row["origin"],
            "source_id": row["tweet_id"],
            "coarse_label": row["coarse"],
            "dataset": row["origin"].split(":")[0],
            "event": row["event"],
        })

    for row in live:
        label = row["coarse"] if row["coarse"] in FDR_CATEGORIES else "OTHER"
        by_event["datalake-live"] += 1
        emitted.append({
            "text": row["text"].strip(),
            "label": label,
            "split": "test",
            "origin": row["origin"],
            "source_id": row["tweet_id"],
            "coarse_label": row["coarse"],
            "dataset": "system",
            "event": "datalake-live",
        })

    # De-duplicate exact tweet text (an event may repeat a message).
    seen_text = set()
    dedup = []
    for r in emitted:
        if r["text"] in seen_text:
            continue
        seen_text.add(r["text"])
        dedup.append(r)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in dedup:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    train = [r for r in dedup if r["split"] == "train"]
    test = [r for r in dedup if r["split"] == "test"]
    print(f"\nemitted: {len(dedup)} (train={len(train)} test={len(test)})")
    print("dropped (non-incident):", dict(dropped.most_common(8)))
    print("\nper-class TRAIN:", dict(Counter(r['label'] for r in train).most_common()))
    print("per-class TEST: ", dict(Counter(r['label'] for r in test).most_common()))
    print("\nper-event (train/test):")
    for ev, c in sorted(by_event.items(), key=lambda kv: -kv[1]):
        tag = "test" if ev in TEST_EVENTS or ev == "datalake-live" else "train"
        print(f"  [{tag:5}] {ev:45s} {c}")
    print(f"\ncorpus -> {OUT}")


if __name__ == "__main__":
    main()