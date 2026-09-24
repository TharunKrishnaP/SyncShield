"""Verified national emergency contacts and evacuation guidance for India.

All numbers below are national, publicly published Government of India
helplines. State Emergency Operations Centres are reached through the common
state disaster helpline 1070, which every State/UT operates, so we never
publish a district number that may be stale.
"""

NATIONAL_HELPLINES = [
    {
        "number": "112",
        "label": "All emergencies (ERSS)",
        "plain": "One number for police, fire and ambulance anywhere in India",
        "category": "emergency",
        "priority": 1,
    },
    {
        "number": "1078",
        "label": "National disaster helpline (NDMA)",
        "plain": "Disaster management help from the National Disaster Management Authority",
        "category": "disaster",
        "priority": 2,
    },
    {
        "number": "1070",
        "label": "State disaster helpline",
        "plain": "Connects you to your State Emergency Operations Centre",
        "category": "disaster",
        "priority": 3,
    },
    {
        "number": "108",
        "label": "Ambulance",
        "plain": "Free emergency ambulance service",
        "category": "medical",
        "priority": 4,
    },
    {
        "number": "101",
        "label": "Fire and rescue",
        "plain": "Fire brigade and rescue services",
        "category": "emergency",
        "priority": 5,
    },
    {
        "number": "100",
        "label": "Police",
        "plain": "Police control room",
        "category": "emergency",
        "priority": 6,
    },
    {
        "number": "102",
        "label": "Medical / pregnancy help",
        "plain": "Ambulance and medical assistance for mothers and children",
        "category": "medical",
        "priority": 7,
    },
    {
        "number": "104",
        "label": "Health advice",
        "plain": "Free health advice helpline, useful for water-borne illness",
        "category": "medical",
        "priority": 8,
    },
    {
        "number": "1033",
        "label": "Highway / road assistance",
        "plain": "Help on national highways if a road is blocked or flooded",
        "category": "travel",
        "priority": 9,
    },
    {
        "number": "139",
        "label": "Railway helpline",
        "plain": "Railway emergencies and enquiry",
        "category": "travel",
        "priority": 10,
    },
    {
        "number": "1098",
        "label": "Child helpline",
        "plain": "Help for children in danger, including separated children",
        "category": "welfare",
        "priority": 11,
    },
    {
        "number": "1091",
        "label": "Women helpline",
        "plain": "Help and support for women in distress",
        "category": "welfare",
        "priority": 12,
    },
]

AGENCY_CONTACTS = [
    {
        "name": "National Disaster Management Authority (NDMA)",
        "role": "National disaster coordination",
        "phone": ["011-26701728", "011-26701700"],
        "email": "controlroom@ndma.gov.in",
        "website": "https://ndma.gov.in/",
        "plain": "The national body that coordinates flood response across states",
    },
    {
        "name": "National Disaster Response Force (NDRF)",
        "role": "Flood rescue and relief",
        "phone": ["09711077372", "011-23438091", "011-23438136"],
        "email": "hq.ndrf@nic.in",
        "website": "https://www.ndrf.gov.in/",
        "plain": "The specialised central force that carries out flood rescues",
    },
    {
        "name": "Ministry of Home Affairs - National Emergency Response Centre",
        "role": "National emergency coordination",
        "phone": ["011-23438252", "011-23438253"],
        "email": "",
        "website": "https://www.mha.gov.in/",
        "plain": "Central control room that runs the national emergency helpline 1070",
    },
    {
        "name": "Central Water Commission - Central Flood Control Room",
        "role": "River levels and flood forecasts",
        "phone": ["011-26102112", "011-26182836"],
        "email": "fmdte@nic.in",
        "website": "https://ffs.india-water.gov.in/",
        "plain": "The agency that measures river levels and issues India's flood forecasts",
    },
    {
        "name": "India Meteorological Department (IMD)",
        "role": "Weather and rainfall warnings",
        "phone": [],
        "email": "",
        "website": "https://mausam.imd.gov.in/",
        "plain": "The national weather service that issues rainfall and cyclone warnings",
    },
    {
        "name": "Indian Red Cross Society",
        "role": "Relief and first aid support",
        "phone": ["011-23716441"],
        "email": "redcross@indianredcross.org",
        "website": "https://www.indianredcross.org/",
        "plain": "Provides relief material, shelters and first aid during floods",
    },
]

EVACUATION_GUIDANCE = [
    {
        "title": "Before you leave home",
        "steps": [
            "Switch off electricity and gas at the mains.",
            "Carry your phone, charger, ID papers in a waterproof bag.",
            "Take drinking water, dry food and any medicines for 3 days.",
            "Lock doors and move valuables to a high shelf or upper floor.",
        ],
    },
    {
        "title": "While moving out",
        "steps": [
            "Use only the route announced by the district administration.",
            "Never walk or drive through moving water — 15 cm can knock you down.",
            "Stay away from electric poles, wires and open drains.",
            "Help elderly, pregnant and disabled neighbours first.",
        ],
    },
    {
        "title": "At the relief shelter",
        "steps": [
            "Register your name so your family can find you.",
            "Drink only boiled, filtered or bottled water.",
            "Follow shelter volunteers and do not return home until told it is safe.",
        ],
    },
]

SAFETY_RULES = [
    "Move to higher ground as soon as water starts entering your home.",
    "Never touch electrical wires or appliances that are in water.",
    "Do not believe rumours on social media — follow NDMA, IMD and district alerts.",
    "Keep children away from flood water; even shallow water can be dangerous.",
    "Boil drinking water to avoid cholera, typhoid and diarrhoea.",
    "If trapped, move to the highest floor and signal for help from a window or terrace.",
]


def contacts_payload() -> dict:
    return {
        "helplines": sorted(NATIONAL_HELPLINES, key=lambda h: h["priority"]),
        "agencies": AGENCY_CONTACTS,
        "evacuation": EVACUATION_GUIDANCE,
        "safety_rules": SAFETY_RULES,
    }
