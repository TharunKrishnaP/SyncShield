"""Build the weakly-supervised bilingual incident corpus for the FDR classifier.

Produces ``ml/data/text_corpus.jsonl`` with fields
``{text, label, split, origin}`` where ``origin`` is:
  - ``template`` — generated from curated phrasings per category (train)
  - ``curated``  — hand-written realistic reports (train)
  - ``gold``     — hand-written realistic reports (test, NEVER seen in training)

Classes (10 incident categories from the rule engine + OTHER):
  FLOODED_ROAD, TRAPPED_RESIDENTS, POWER_OUTAGE, HOSPITAL_ACCESS_BLOCKED,
  BRIDGE_COLLAPSE, LANDSLIDE, EVACUATION_NEEDED, RELIEF_SHELTER_FULL,
  WATER_CONTAMINATION, COMMUNICATION_DOWN, OTHER
"""
import itertools
import json
import random
from collections import Counter
from pathlib import Path

SEED = 42
OUT = Path(__file__).resolve().parent.parent / "data" / "text_corpus.jsonl"

CATEGORIES = [
    "FLOODED_ROAD", "TRAPPED_RESIDENTS", "POWER_OUTAGE", "HOSPITAL_ACCESS_BLOCKED",
    "BRIDGE_COLLAPSE", "LANDSLIDE", "EVACUATION_NEEDED", "RELIEF_SHELTER_FULL",
    "WATER_CONTAMINATION", "COMMUNICATION_DOWN", "OTHER",
]

PLACES = [
    "Guwahati", "Patna", "Vijayawada", "Varanasi", "Chennai", "Kolkata",
    "Darbhanga", "Aluva", "Bhagalpur", "Cuttack", "Sangli", "Hyderabad",
    "Tezpur", "Muzaffarpur", "Silchar", "Prayagraj", "Nellore", "Thrissur",
    "Jalpaiguri", "Malda", "Kanpur", "Lucknow", "Srinagar", "Jorhat",
]
SPOTS = [
    "Gandhi Ghat", "the railway station", "Besant Nagar", "the old bus stand",
    "NH-31", "the Ring Road", "Assi Ghat", "the market lane", "the temple tank",
    "the colony entrance", "the river bund", "the pump house", "the main bazaar",
    "behind the school", "the vegetable market", "the underpass", "the flyover",
    "the embankment road", "Lalbagh", "the high school gate", "the petrol pump",
]
TIMES = [
    "last night", "this morning", "two hours", "the evening", "yesterday",
    "just now", "around 10 am", "the past day", "noon", "the early hours",
]
CONFIRMS = [
    "confirmed", "verified", "I saw", "locals say", "per reports",
    "as per officials", "witnesses say", "residents confirm",
]
PEOPLE = [
    "families", "residents", "elderly people", "students", "villagers",
    "people", "commuters", "workers", "children", "women",
]
NUMS = ["2", "3", "5", "6", "8", "10", "12", "15", "18", "20", "25", "30",
        "40", "45", "50", "60", "70", "100"]
DEPTHS = ["knee deep", "waist deep", "chest deep", "ankle deep", "neck deep", "half a metre deep"]
REGIONS = ["locality", "colony", "village", "ward", "mohalla", "area", "neighbourhood", "basti"]

COMMON_SLOTS = {
    "place": PLACES, "spot": SPOTS, "time": TIMES, "confirm": CONFIRMS,
    "people": PEOPLE, "n": NUMS, "depth": DEPTHS, "region": REGIONS,
}


def _expand(base: str, **slots) -> list:
    keys = sorted(set(slots))
    combos = list(itertools.product(*(slots[k] for k in keys)))
    out = []
    for combo in combos:
        s = base
        for k, v in zip(keys, combo):
            s = s.replace("{" + k + "}", v)
        out.append(s)
    return out


def _slot_plan(base: str) -> dict:
    return {k: v for k, v in COMMON_SLOTS.items() if "{" + k + "}" in base}


TEMPLATES: dict = {
    "FLOODED_ROAD": [
        "Waterlogging on {spot}, {place}: vehicles stuck and traffic moving at a crawl",
        "{place}: the road to {spot} is submerged and completely blocked",
        "Heavy water on the {spot} stretch, {place}, cars cannot pass",
        "Road under water at {spot}, {place}, {n} vehicles stuck",
        "Traffic jam due to flooding on {spot} in {place} since {time}",
        "Water level rising on the highway near {spot}, {place}, diversions needed",
        "The underpass at {spot} {place} is flooded, drivers are turning back",
        "Street completely flooded on {spot}, {place}, bike riders stranded",
        "Bridge approach road waterlogged at {spot}, {place}, {n} cars reported stuck",
        "Commuters stranded on {spot} road, {place}, water is {depth}",
        "gali me paani bhar gaya hai, {place} me raste par gaadiyaan atki hui hain",
        "{place} ke {spot} ke paas sadak paani me doobi hui hai, traffic ruk gaya",
        "NH par paani a gaya hai {place} ke paas, vehicles nahi nikal pa rahe",
        "Bus stand road under water in {place}, public transport affected for {n} hours",
    ],
    "TRAPPED_RESIDENTS": [
        "{n} {people} trapped on the rooftop after water entered their homes in {place}",
        "Residents stranded on upper floors at {spot}, {place}, need rescue",
        "A family is stuck on the terrace in {place}, water all around their house",
        "Elderly couple trapped in their ground-floor house in {place}, water rising",
        "Rescue needed urgently: {n} {people} marooned in {spot}, {place}",
        "People on rooftops waving for help at {spot}, {place}, since {time}",
        "Water entered houses in {spot}, {place}; {n} {people} trapped inside",
        "Students stranded in the hostel at {place}, {spot}, no way out",
        "Villagers stuck on an island of high ground near {spot}, {place}, boats required",
        "chhat par log phans gaye hain {place} me, paani ghar me ghus gaya hai",
        "{n} gharon ke log imarat ki uparli manzil par atke hain, bachao chahiye",
        "Ghar me paani bhar gaya, log andar phanse hue hain {place} ke {spot} me",
    ],
    "POWER_OUTAGE": [
        "Power cut in the whole {region} of {place} since {time}; transformers tripped after rain",
        "No electricity in {place}: electric lines down at {spot}, repair crew needed",
        "Transformer blast near {spot}, {place} — power off for {n} hours",
        "Electric poles fallen on {spot} road, {place}, wires live on the ground",
        "Widespread power failure in {place} after the storm, hospitals on backup",
        "Power lines snapped at {spot}, {place}, risk of electric shock reported",
        "Bijli chali gayi hai {place} me, transformer kharab ho gaya",
        "Bichale wire gir gayi hai {place} ke {spot} ke paas, khatra hai",
        "Electricity restored in parts but {spot}, {place} still dark for {n} hours",
    ],
    "HOSPITAL_ACCESS_BLOCKED": [
        "Road to the district hospital at {place} is flooded, ambulances cannot reach",
        "Hospital access blocked at {spot}, {place} — a patient heart case waiting",
        "Ambulance stuck in water near {spot}, {place}, {n} minutes delay",
        "Emergency ward cut off: hospital in {place} surrounded by water since {time}",
        "Blood bank vehicles unable to cross {spot}, {place}, urgent supply needed",
        "Medical emergency in {place}: the approach road to the clinic is under water",
        "aspatal ka rasta paani se band hai {place} me, ambulance nahi pahunch pa rahi",
    ],
    "BRIDGE_COLLAPSE": [
        "Bridge collapsed at {spot}, {place}, villagers cut off from the main road",
        "The old bridge over the river near {place} gave way this morning",
        "Bridge partially damaged at {spot}, {place} — heavy vehicles advised to avoid",
        "Cracks seen in the bridge at {spot}, {place} after flooding, unsafe to cross",
        "Bridge washed away at {spot}, {place}; schools closed on the other bank",
        "pul gir gaya hai {place} ke {spot} ke paas, log pareshan hain",
        "Bridge approach eroded near {place}, vehicles diverted to {n} km detour",
    ],
    "LANDSLIDE": [
        "Landslide blocked the hill road near {place}, vehicles stranded for {n} hours",
        "Mudslide came down at {spot}, {place}, houses at the foothills at risk",
        "Rockfall on the {spot} stretch near {place} after heavy rain",
        "Hillside slipped above {spot}, {place}; the road is buried under debris",
        "Soil erosion and landslide threats reported in {place} hills after the rains",
        "pahadi se mitti gir gayi hai {place} ke paas, rasta band hai",
        "Landslide debris cleared from {spot} road, {place}, but more rain expected",
    ],
    "EVACUATION_NEEDED": [
        "Water entering low-lying homes in {spot}, {place} — evacuation needed now",
        "Boats needed: {n} {people} to shift from {spot}, {place}",
        "Villages flooded around {place}, families need to be relocated to shelters",
        "Send boats and help evacuate {spot}, {place} before the waters rise further",
        "Evacuation ordered for the {region} of {place} as the river crosses danger level",
        "Boats requested for {n} {people} marooned at {spot}, {place}",
        "Embankment breach at {spot}, {place} — evacuation of the {region} ordered",
        "River overtopping the bund near {place}, low-lying {region} to be cleared",
        "nauka chahiye {place} me, log bahut pani me ghire hue hain",
        "Logon ko khali karvana zaroori hai {place} ke {spot} se, paani badh raha hai",
    ],
    "RELIEF_SHELTER_FULL": [
        "Relief camp at {spot}, {place} is full, {n} more families waiting outside",
        "Shelter overcrowded in {place} — no beds left for the newly arrived",
        "Relief materials running out at {spot}, {place}; no food packets since {time}",
        "Evacuees at the {place} shelter need drinking water and medicine",
        "Shelter capacity exceeded at {spot}, {place}, additional tents required",
        "School shelter in {place} packed, people sleeping on the floor",
        "Ration shortage at the relief camp in {place}, children without milk",
        "sharan sthal me jagah nahi hai {place} me, aur log aa rahe hain",
    ],
    "WATER_CONTAMINATION": [
        "Drinking water contaminated in {spot}, {place} — sewage mixing in the lines",
        "Tap water dirty and smelly in {place}; households reporting stomach illness",
        "Flood water mixed with the supply at {spot}, {place}, unsafe to drink",
        "Water tanker in {place} carrying polluted water, residents demand testing",
        "Chemical smell in the water at {spot}, {place}, supply stopped temporarily",
        "Borewell water suspected contaminated in {place} after the floods",
        "paani ganda aur badbu wala hai {place} me, peene ke laayak nahi",
        "Sewage backflow into homes in {spot}, {place} — contamination risk high",
    ],
    "COMMUNICATION_DOWN": [
        "Mobile network down in the {region} of {place} since {time}, families unreachable",
        "No internet or phone signal in {place}; people cannot contact relatives",
        "Telecom towers down at {spot}, {place} after the storm",
        "Landline and broadband cut off in {place} for {n} hours",
        "Network completely dead in {spot}, {place} — relief teams working blind",
        "Can't reach my family in {place}, phone lines are down since {time}",
        "network kharab hai {place} me, kisi ko call nahi ho raha",
        "Mobile tower damage at {spot}, {place} leaving the area without coverage",
    ],
    "OTHER": [
        "School reopening dates announced for {n} districts after the holidays",
        "Onion prices rose again at the {place} vegetable market this week",
        "Marriage ceremony planned at {spot}, {place} on Sunday evening",
        "Cricket tournament starts in {place} next week, entry free",
        "Job interviews scheduled at the {place} branch office from Monday",
        "Festival shopping crowds expected in {spot}, {place} this weekend",
        "The bus stand at {place} is getting new lights and benches",
        "Exam date sheet released for board classes in {place}",
        "Light rain expected in {place} tomorrow, carry an umbrella if outdoors",
        "City council meeting at {place} to discuss road repairs",
        "My neighbour got a new puppy, it keeps barking at night",
        "Pharmacy near {spot}, {place} offering discount on medicines",
        "Salon offers in {spot}, {place} this month, walk-ins welcome",
        "Weekly market at {spot}, {place} stocked with fresh vegetables today",
        "New bus route approved connecting {place} to the district headquarters",
        "Temple fair begins at {place} from Friday, traffic expected all day",
    ],
}

TEMPLATE_PER_CAT = {
    "FLOODED_ROAD": 1400,
    "TRAPPED_RESIDENTS": 1200,
    "POWER_OUTAGE": 1100,
    "HOSPITAL_ACCESS_BLOCKED": 1200,
    "BRIDGE_COLLAPSE": 850,
    "LANDSLIDE": 850,
    "EVACUATION_NEEDED": 1200,
    "RELIEF_SHELTER_FULL": 900,
    "WATER_CONTAMINATION": 1000,
    "COMMUNICATION_DOWN": 1000,
    "OTHER": 700,
}

# Hand-written realistic reports used as TRAINING data (keeps the model on real
# phrasing, which templates alone cannot provide).
CURATED_TRAIN: dict = {
    "FLOODED_ROAD": [
        "Went to drop my son at school, the road near the park is under water, cars are turning back",
        "The market road has turned into a stream, shopkeepers closed early",
        "Can't reach the office, water on the NH near the toll plaza is knee deep",
        "Auto driver says the ghat road is blocked by water since the early hours",
        "Our lane is flooded up to the gate, delivery vans can't enter",
        "Bus diverted because the main road is washed out near the bazaar",
        "The flyover approach is waterlogged, bikes are skidding",
        "Rickshaw pulled over, the whole crossing is submerged",
        "School bus can't pass the underpass, water is too high today",
        "Street near the temple flooded again, vehicles stuck this morning",
        "Ghat steps and the walkway are under water, boats running where buses were",
        "River is above the promenade, cars parked on the ghats are being moved",
        "The river is at warning level and water has reached the colony gate",
        "Yamuna creeping to warning level in Delhi, riverside walkways closed",
    ],
    "TRAPPED_RESIDENTS": [
        "My aunt and two kids are on the first floor, water entered the shop below, need help",
        "People waving white cloth from a rooftop in the market area",
        "The nurse is stuck in her apartment, ground floor flooded",
        "Colony residents on the terrace since 4 am, water all around",
        "Father-in-law trapped in the garage, water rose suddenly",
        "A pregnant woman is stranded on the upper floor of the clinic building",
        "The landlord family is on the roof, house half submerged",
        "Students in the hostel top floor, the stairs are under water",
        "Residents of the red building asking for a boat, water at first floor",
        "Grandparents alone on the terrace, neighbours left by boat",
        "Heavy waterlogging near Gandhi Ghat, six people stranded on the rooftop",
        "Waterlogging in the old town left four families up on the roofs",
        "Two shopkeepers stuck on the mezzanine, water rushed in from the lane",
    ],
    "POWER_OUTAGE": [
        "Everything dark in our street, transformer died with a loud sound",
        "No electricity at home since midnight, inverter also dead",
        "Electricity flickering then gone, wires hissing near the post",
        "Market shops running on generators, grid down since the rain",
        "Hospital backup for emergency only, the whole area is without power",
        "Neighbourhood pitch dark, streetlights also out",
        "Power went off during the storm, electric stove useless",
        "The colony has had no light for a day, complaints not attended",
        "Electric pole leaning after the storm, power cut for safety",
        "Office UPS beeping, no mains power since morning",
    ],
    "HOSPITAL_ACCESS_BLOCKED": [
        "Ambulance can't carry the patient to the district hospital, the road is flooded at the gate",
        "Doctor stranded on the far side, the hospital approach is under water",
        "Dialysis patient inside the hospital, family can't cross the flooded bridge to visit",
        "The clinic near the bus stand is cut off, medicines locked inside",
        "Blood bank appeal: donors can't reach because the street is flooded",
        "Maternity home compound waterlogged, expecting mothers inside need transfer",
        "Primary health centre staff stuck, relief needed at the hospital itself",
        "Hospital generator works but the supply route is blocked by water",
        "Sick child needs the city hospital, road half submerged",
        "Paramedic boat needed to ferry patients to the flooded hospital block entrance",
    ],
    "BRIDGE_COLLAPSE": [
        "The kutcha bridge to the village fell in last night, cracked in the middle",
        "Bridge over the canal tilted after the surge, villagers walking on planks",
        "Old iron bridge declared unsafe, school children cross on foot",
        "Two spans of the bridge sank into the river",
        "The minor bridge near the sugar factory gave way under a tractor",
        "Grandparents say the bridge is swaying, buses won't cross",
        "Bridge partially collapsed, police barricaded both ends",
        "The bridge pillars cracked after the flood, repairs will take months",
        "Villagers complain the newly built bridge is already breaking",
        "Bridge between the two markets collapsed, detour adds 12 km",
    ],
    "LANDSLIDE": [
        "Hill above the tea estate slid, workers seen running",
        "The ghat road buried under mud and rocks, buses stranded",
        "A boulder crushed the shop at the hill road bend",
        "Soil came down over the railway track near the tunnel",
        "Villagers report the hill slope has been cracking since the rains",
        "Debris blocked the trek route, trekkers safely evacuated",
        "Landslide cut off the mountain villages, food stocks low",
        "The hillside behind the school gave way, playground covered",
        "Rockfall on the highway, two vehicles damaged",
        "Slope failure near the reservoir, engineers inspecting",
    ],
    "EVACUATION_NEEDED": [
        "Township under risk, order to move to higher ground before night",
        "Boat teams requested for the island settlement, water rising every hour",
        "Families on the river bank told to pack and shift",
        "The ward committee is arranging transport to the relief camp",
        "People from the low-lying basti heading to the school building",
        "Need more boats, half the village still to be moved",
        "Police asked residents to evacuate, many refusing to leave cattle",
        "The camp opposite the river needs boats for the elderly",
        "Families with infants shifted last, others still waiting",
        "Relief officials say evacuation must complete by midnight",
        "Embankment breached near the village, water entering the fields, families moving out",
        "The river has overtopped the bund, everyone in the low quarter is being moved",
        "Sandbags are being filled and the administration ordered the ward to clear",
        "Paddy fields inundated after the breach, households packing to leave",
        "Breach reported in the river bank near the town, people heading for safer ground",
        "The river crossed warning level, low-lying localities alerted to move",
    ],
    "RELIEF_SHELTER_FULL": [
        "The high school shelter has no space, mats finish fast",
        "Kitchen at the camp ran out of dal, rice for one more meal",
        "Evacuees sleeping in the open beside the packed shelter",
        "No mosquito nets left at the relief point, children bitten badly",
        "Shelter medicine box empty, fever cases rising",
        "Camp toilets overflowing, hygiene a worry",
        "Donation truck didn't arrive, the shelter is hungry tonight",
        "People turned away from the full camp, directed to the church",
        "The shelter needs more blankets before night",
        "Volunteers exhausted, camp overcrowded, supplies falling short",
    ],
    "WATER_CONTAMINATION": [
        "Tap water smells like a drain, we boil everything now",
        "The well near the flooded fields is unsafe, villagers warned",
        "Handpump water turned brown after the floods",
        "Stomach illness in the colony since the water changed taste",
        "The tanker that supplies our street has murky water",
        "Sewage overflowing into the drinking water line, officials informed",
        "Kids got rashes after bathing in the stored water",
        "RO plants closed, water in the overhead tank is dirty",
        "The supply line was submerged during the flood, water still smells",
        "Market ice made from contaminated water, avoid cold drinks",
    ],
    "COMMUNICATION_DOWN": [
        "Can't call home from the flood shelter, network dead",
        "The tower near the river is silent, the whole belt has no signal",
        "Messages not going through since the storm",
        "Village cut off digitally, news reaches by bicycle courier",
        "Relatives overseas panicking, no internet since night",
        "The taluk office phone lines are dead, coordination via HAM radio",
        "My sim shows no service even at the rooftop",
        "Broadband down for a day, office work affected",
        "The cable tower battery drained, no coverage since morning",
        "Student can't attend the online class, no network in the village",
    ],
    "OTHER": [
        "Anyone selling a second hand fridge near the market?",
        "Ration card camps at the panchayat office from Tuesday",
        "The new bridge inauguration next month, CM expected",
        "Vaccination camp at the community hall on Friday",
        "School fee payment deadline extended to the 15th",
        "Temple festival procession route announced, lanes notified",
        "The vegetable cooperative opened a new outlet at the bus stand",
        "Neighbourhood watch meeting on Sunday, all apartment owners invited",
        "Trains between these stations resumed normal schedule",
        "Diwali shopping mela at the ground from evening",
    ],
}

# Hand-written realistic reports — held out as the TEST split (never trained on).
GOLD: dict = {
    "FLOODED_ROAD": [
        "The entire stretch from the clock tower to the market is under three feet of water and no vehicle can cross",
        "Our office is cut off, the road in front is a river since the storm",
        "Driving into the city impossible this morning, water across the flyover approach",
        "Auto drivers refusing trips beyond the temple, road completely flooded",
        "School buses all turned back at the lake road, water too deep",
        "The flyover itself has standing water, two wheelers skidded twice",
    ],
    "TRAPPED_RESIDENTS": [
        "Please send help, three families are on their terrace in the red building near the church, water is up to the first floor",
        "My grandmother is alone on the rooftop, house flooded since early morning",
        "We are stuck in the godown, water entered suddenly, two children with us",
        "The constable on duty is marooned in the check post, water on all sides",
        "Temple priest and his family have been on the rooftop since evening",
        "A newborn and its mother are stranded on the top floor of the maternity home",
    ],
    "POWER_OUTAGE": [
        "Whole block has been without power for six hours, several transformers drowned",
        "There is no light in the hospital corridor, generator also failed",
        "A pole snapped near the bakery and the wire is hanging low, everyone is scared",
        "Our colony has been dark since the transformer caught fire",
        "The flour mill is idle, no electricity for two days",
    ],
    "HOSPITAL_ACCESS_BLOCKED": [
        "The maternity hospital road is flooded and a woman in labour cannot be brought in",
        "Ambulance from the health centre could not reach the highway junction",
        "Doctor unable to reach the primary health centre due to water on the bridge road",
        "The private clinic in the lane is cut off, patients inside since morning",
        "Physio van stuck, day-care patients cannot leave the centre",
    ],
    "BRIDGE_COLLAPSE": [
        "The small bridge over the canal gave way, a milk tanker fell in",
        "People are crossing the cracked bridge on foot, buses stopped",
        "Bridge supports washed out between the two villages, diversions in place",
        "The old wooden bridge broke under a cart this afternoon",
        "Concrete span of the feeder bridge dropped into the water",
    ],
    "LANDSLIDE": [
        "Boulders came down on the ghat road again, buses waiting since morning",
        "The hill above our school slipped and mud covered the playground",
        "Two houses at the hill base damaged by the slide last night",
        "A tractor buried on the estate road, driver rescued",
        "Debris over the culvert, tankers detouring via the valley",
    ],
    "EVACUATION_NEEDED": [
        "Water is entering the low lying basti fast, people need to move to the school building tonight",
        "We need boats at the canal colony, about forty people with cattle are stuck",
        "The entire village near the river needs shifting before midnight",
        "Ration and vessels are being loaded, families to leave within two hours",
        "Fishermen asked to ferry people from the island by dawn",
    ],
    "RELIEF_SHELTER_FULL": [
        "Camp is overflowing, we are turning people away with children",
        "No medicine left at the relief point, diabetics are suffering",
        "Shelter kitchen has run out of rice, supplies stuck on the other side",
        "Every room of the college shelter is occupied, refugees on the corridors",
        "The camp school is full, new arrivals asked to wait at the temple",
    ],
    "WATER_CONTAMINATION": [
        "The tanker water tastes of diesel, half the lane is sick",
        "Sewage is bubbling up from the drains and mixing with stored drinking water",
        "Our borewell water turned black this morning, babies have rashes",
        "Diesel smell in the municipal supply, residents stopped using it",
        "The village pond is the only source and it is polluted by flood debris",
    ],
    "COMMUNICATION_DOWN": [
        "No signal from the tower since the cyclone, our rescue volunteers cannot coordinate",
        "Every phone in the village shows no service, worried relatives keep calling",
        "Both internet and mobile are dead at the taluk office",
        "The new tower promised last month still silent, area blacked out",
        "Even the wired phone at the school is not working",
    ],
    "OTHER": [
        "Looking for a tiffin service near the office, any recommendations",
        "Second hand study table for sale, pickup from the colony gate",
        "Temple annadanam on the first of next month, volunteers welcome",
        "Does anyone know the new ration card office timings",
        "Morning walkers group forming at the park, join before seven",
        "Free yoga class at the community hall twice a week",
        "The jeweller's shop has announced a gold scheme for the festival",
    ],
}


def build_corpus(rng: random.Random) -> list:
    records = []
    for cat, bases in TEMPLATES.items():
        expanded = []
        for base in bases:
            expanded.extend(_expand(base, **_slot_plan(base)))
        seen, picked = set(), []
        rng.shuffle(expanded)
        for s in expanded:
            if s not in seen:
                seen.add(s)
                picked.append(s)
        cap = TEMPLATE_PER_CAT.get(cat, 1000)
        for s in picked[:cap]:
            records.append({"text": s, "label": cat, "split": "train", "origin": "template"})

    for cat, texts in CURATED_TRAIN.items():
        for t in texts:
            records.append({"text": t, "label": cat, "split": "train", "origin": "curated"})

    for cat, texts in GOLD.items():
        for t in texts:
            records.append({"text": t, "label": cat, "split": "test", "origin": "gold"})
    return records


def main():
    rng = random.Random(SEED)
    records = build_corpus(rng)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    counts = Counter(r["label"] for r in records)
    train = sum(1 for r in records if r["split"] == "train")
    gold = sum(1 for r in records if r["split"] == "test")
    curated = sum(1 for r in records if r["origin"] == "curated")
    print(f"corpus -> {OUT}  total={len(records)}  train={train} (curated={curated})  gold_test={gold}")
    for cat in CATEGORIES:
        print(f"  {cat:26s} {counts[cat]:5d}")


if __name__ == "__main__":
    main()