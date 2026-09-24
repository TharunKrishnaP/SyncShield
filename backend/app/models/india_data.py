"""Pan-India reference data: monitoring zones, river stations, infrastructure.

The monitoring fabric is now built from the complete district registry
(`district_registry.DISTRICTS`, ~763 districts), so *every* district in the
country is a live monitoring zone with:

  * a district-HQ centroid (precise to ~1-5 km),
  * a real-time Open-Meteo weather feed (see `weather_client`),
  * a flood-relevance basin assignment,
  * an approximate population figure (2011 Census shared evenly across a
    state's districts — used only for exposure weighting),
  * a synthetic GeoJSON polygon for the map overlay.

River gauges follow the real CWC flood-forecasting network (level/danger
thresholds from published station bulletins; approximate where private) and
were expanded across the north-east's Teesta/Kosi/Gandak/Bagmati systems and
the east-coast Baitarani/Brahmani/Tungabhadra basins.
"""

import math

from .district_registry import DISTRICTS, STATE_CODES

INDIA_CENTER = [20.5937, 78.9629]
INDIA_BBOX = [68.1, 6.5, 97.4, 35.5]

# Monitored river basins. Primary basins drive each state's default; the
# _DISTRICT_BASIN table re-assigns districts that sit on specific tributaries.
BASINS = [
    {"code": "GANGA", "name": "Ganga", "states": ["Uttarakhand", "Uttar Pradesh", "Bihar", "Jharkhand", "West Bengal"]},
    {"code": "YAMUNA", "name": "Yamuna", "states": ["Uttarakhand", "Himachal Pradesh", "Haryana", "Delhi", "Uttar Pradesh"]},
    {"code": "BRAHMAPUTRA", "name": "Brahmaputra", "states": ["Arunachal Pradesh", "Assam", "Meghalaya", "Nagaland", "West Bengal"]},
    {"code": "BARAK", "name": "Barak (Surma-Meghna)", "states": ["Manipur", "Mizoram", "Assam", "Tripura"]},
    {"code": "GODAVARI", "name": "Godavari", "states": ["Maharashtra", "Telangana", "Andhra Pradesh", "Chhattisgarh", "Odisha"]},
    {"code": "KRISHNA", "name": "Krishna", "states": ["Maharashtra", "Karnataka", "Telangana", "Andhra Pradesh"]},
    {"code": "CAUVERY", "name": "Cauvery", "states": ["Karnataka", "Tamil Nadu", "Kerala", "Puducherry"]},
    {"code": "MAHANADI", "name": "Mahanadi", "states": ["Chhattisgarh", "Odisha"]},
    {"code": "NARMADA", "name": "Narmada", "states": ["Madhya Pradesh", "Maharashtra", "Gujarat"]},
    {"code": "TAPI", "name": "Tapi", "states": ["Madhya Pradesh", "Maharashtra", "Gujarat"]},
    {"code": "SABARMATI", "name": "Sabarmati", "states": ["Rajasthan", "Gujarat"]},
    {"code": "MAHI", "name": "Mahi", "states": ["Madhya Pradesh", "Rajasthan", "Gujarat"]},
    {"code": "PERIYAR", "name": "Periyar", "states": ["Kerala"]},
    {"code": "SUBARNAREKHA", "name": "Subarnarekha", "states": ["Jharkhand", "Odisha", "West Bengal"]},
    {"code": "DAMODAR", "name": "Damodar", "states": ["Jharkhand", "West Bengal"]},
    {"code": "PENNAR", "name": "Pennar", "states": ["Karnataka", "Andhra Pradesh"]},
    {"code": "INDUS", "name": "Indus (Satluj-Beas)", "states": ["Jammu and Kashmir", "Ladakh", "Himachal Pradesh", "Punjab"]},
    {"code": "JHELUM", "name": "Jhelum", "states": ["Jammu and Kashmir"]},
    {"code": "CHENAB", "name": "Chenab", "states": ["Jammu and Kashmir", "Ladakh", "Himachal Pradesh"]},
    {"code": "SATLUJ", "name": "Sutlej", "states": ["Himachal Pradesh", "Punjab"]},
    {"code": "BEAS", "name": "Beas", "states": ["Himachal Pradesh", "Punjab"]},
    {"code": "RAVI", "name": "Ravi", "states": ["Himachal Pradesh", "Punjab", "Jammu and Kashmir"]},
    {"code": "GHAGGAR", "name": "Ghaggar-Hakra", "states": ["Haryana", "Punjab", "Rajasthan", "Chandigarh"]},
    {"code": "LUNI", "name": "Luni", "states": ["Rajasthan"]},
    {"code": "CHAMBAL", "name": "Chambal", "states": ["Rajasthan", "Madhya Pradesh"]},
    {"code": "BANAS", "name": "Banas", "states": ["Rajasthan", "Gujarat"]},
    {"code": "BETWA", "name": "Betwa-Sharda", "states": ["Madhya Pradesh", "Uttar Pradesh"]},
    {"code": "SONE", "name": "Sone", "states": ["Madhya Pradesh", "Jharkhand", "Bihar", "Uttar Pradesh"]},
    {"code": "GHAGHRA", "name": "Ghaghra (Sarayu)", "states": ["Uttar Pradesh", "Bihar"]},
    {"code": "GOMTI", "name": "Gomti", "states": ["Uttar Pradesh"]},
    {"code": "RAMGANGA", "name": "Ramganga", "states": ["Uttarakhand", "Uttar Pradesh"]},
    {"code": "GANDAK", "name": "Gandak", "states": ["Uttar Pradesh", "Bihar"]},
    {"code": "KOSI", "name": "Kosi", "states": ["Bihar"]},
    {"code": "BAGMATI", "name": "Bagmati-Adhwara", "states": ["Bihar"]},
    {"code": "BURHI_GANDAK", "name": "Burhi Gandak", "states": ["Bihar"]},
    {"code": "TEESTA", "name": "Teesta", "states": ["Sikkim", "West Bengal"]},
    {"code": "TORSA", "name": "Torsa", "states": ["West Bengal"]},
    {"code": "MAHANANDA", "name": "Mahananda", "states": ["West Bengal", "Bihar"]},
    {"code": "MANAS", "name": "Manas-Beki", "states": ["Assam"]},
    {"code": "DHANSHIRI", "name": "Dhansiri", "states": ["Assam", "Nagaland"]},
    {"code": "JIA_BHARALI", "name": "Jia Bharali", "states": ["Assam"]},
    {"code": "PUTHIMARI", "name": "Puthimari", "states": ["Assam"]},
    {"code": "PAGLADIA", "name": "Pagladia", "states": ["Assam"]},
    {"code": "TUNGABHADRA", "name": "Tungabhadra", "states": ["Karnataka", "Andhra Pradesh"]},
    {"code": "BRAHMANI", "name": "Brahmani", "states": ["Odisha", "Jharkhand"]},
    {"code": "BAITARANI", "name": "Baitarani", "states": ["Odisha", "Jharkhand"]},
    {"code": "RUSHIKULYA", "name": "Rushikulya", "states": ["Odisha"]},
    {"code": "VAMSADHARA", "name": "Vamsadhara", "states": ["Odisha", "Andhra Pradesh"]},
    {"code": "NAGAVALI", "name": "Nagavali", "states": ["Andhra Pradesh", "Odisha"]},
    {"code": "SWARNAMUKHI", "name": "Swarnamukhi", "states": ["Andhra Pradesh", "Tamil Nadu"]},
    {"code": "PANCHGANGA", "name": "Panchganga", "states": ["Maharashtra"]},
    {"code": "SHETRUNJI", "name": "Shetrunji", "states": ["Gujarat"]},
    {"code": "AAJI", "name": "Aaji", "states": ["Gujarat"]},
    {"code": "BHADAR", "name": "Bhadar", "states": ["Gujarat"]},
    {"code": "OJAT", "name": "Ojat", "states": ["Gujarat"]},
    {"code": "RAN_OF_KACHCHH", "name": "Rann of Kachchh", "states": ["Gujarat"]},
    {"code": "WEST_FLOWING", "name": "West-flowing coastal", "states": ["Gujarat", "Maharashtra", "Goa", "Karnataka", "Kerala"]},
    {"code": "EAST_FLOWING", "name": "East-flowing coastal", "states": ["Andhra Pradesh", "Tamil Nadu"]},
    {"code": "PALAR", "name": "Palar", "states": ["Karnataka", "Andhra Pradesh", "Tamil Nadu"]},
    {"code": "PONNAIYAR", "name": "Ponnaiyar", "states": ["Karnataka", "Tamil Nadu"]},
    {"code": "VAIGAI", "name": "Vaigai", "states": ["Tamil Nadu"]},
    {"code": "COASTAL", "name": "Coastal & islands", "states": ["Tamil Nadu", "Lakshadweep", "Andaman and Nicobar Islands"]},
    {"code": "MUSI", "name": "Musi", "states": ["Telangana", "Andhra Pradesh"]},
]

# Default basin per state (used when a district is not in the override table).
_STATE_BASIN = {
    "Andaman and Nicobar Islands": "COASTAL",
    "Andhra Pradesh": "KRISHNA",
    "Arunachal Pradesh": "BRAHMAPUTRA",
    "Assam": "BRAHMAPUTRA",
    "Bihar": "GANGA",
    "Chandigarh": "GHAGGAR",
    "Chhattisgarh": "MAHANADI",
    "Dadra and Nagar Haveli and Daman and Diu": "TAPI",
    "Delhi": "YAMUNA",
    "Goa": "WEST_FLOWING",
    "Gujarat": "SABARMATI",
    "Haryana": "YAMUNA",
    "Himachal Pradesh": "INDUS",
    "Jammu and Kashmir": "JHELUM",
    "Jharkhand": "SUBARNAREKHA",
    "Karnataka": "KRISHNA",
    "Kerala": "PERIYAR",
    "Ladakh": "INDUS",
    "Lakshadweep": "COASTAL",
    "Madhya Pradesh": "NARMADA",
    "Maharashtra": "GODAVARI",
    "Manipur": "BARAK",
    "Meghalaya": "BRAHMAPUTRA",
    "Mizoram": "BARAK",
    "Nagaland": "BRAHMAPUTRA",
    "Odisha": "MAHANADI",
    "Puducherry": "CAUVERY",
    "Punjab": "INDUS",
    "Rajasthan": "LUNI",
    "Sikkim": "TEESTA",
    "Tamil Nadu": "CAUVERY",
    "Telangana": "KRISHNA",
    "Tripura": "BARAK",
    "Uttar Pradesh": "GANGA",
    "Uttarakhand": "GANGA",
    "West Bengal": "GANGA",
}

# Districts that sit on a specific tributary rather than the state's main
# river — these give each district a *flood-relevant* basin label.
_DISTRICT_BASIN = {
    # ---------------- Bihar (Ganga system) ----------------
    ("Bihar", "Araria"): "KOSI", ("Bihar", "Purnia"): "KOSI", ("Bihar", "Saharsa"): "KOSI",
    ("Bihar", "Supaul"): "KOSI", ("Bihar", "Madhepura"): "KOSI", ("Bihar", "Khagaria"): "KOSI",
    ("Bihar", "Katihar"): "KOSI", ("Bihar", "Darbhanga"): "KOSI", ("Bihar", "Madhubani"): "KOSI",
    ("Bihar", "Sheohar"): "BAGMATI", ("Bihar", "Sitamarhi"): "BAGMATI",
    ("Bihar", "Muzaffarpur"): "BURHI_GANDAK", ("Bihar", "Begusarai"): "BURHI_GANDAK",
    ("Bihar", "Samastipur"): "BURHI_GANDAK", ("Bihar", "Vaishali"): "BURHI_GANDAK",
    ("Bihar", "Gopalganj"): "GANDAK", ("Bihar", "East Champaran"): "GANDAK",
    ("Bihar", "West Champaran"): "GANDAK", ("Bihar", "Pashchim Champaran"): "GANDAK",
    ("Bihar", "Saran"): "GHAGHRA", ("Bihar", "Siwan"): "GHAGHRA",
    ("Bihar", "Bhojpur"): "SONE", ("Bihar", "Arwal"): "SONE", ("Bihar", "Rohtas"): "SONE",
    ("Bihar", "Kaimur"): "SONE", ("Bihar", "Aurangabad"): "SONE", ("Bihar", "Gaya"): "SONE",
    ("Bihar", "Jehanabad"): "SONE", ("Bihar", "Nawada"): "SONE",
    ("Bihar", "Kishanganj"): "MAHANANDA",
    # ---------------- West Bengal ----------------
    ("West Bengal", "Darjeeling"): "TEESTA", ("West Bengal", "Kalimpong"): "TEESTA",
    ("West Bengal", "Jalpaiguri"): "TEESTA", ("West Bengal", "Cooch Behar"): "TEESTA",
    ("West Bengal", "Alipurduar"): "TORSA",
    ("West Bengal", "Malda"): "MAHANANDA", ("West Bengal", "Dakshin Dinajpur"): "MAHANANDA",
    ("West Bengal", "Bankura"): "DAMODAR", ("West Bengal", "Purulia"): "DAMODAR",
    ("West Bengal", "Paschim Bardhaman"): "DAMODAR", ("West Bengal", "Purba Bardhaman"): "DAMODAR",
    ("West Bengal", "Birbhum"): "DAMODAR",
    ("West Bengal", "Paschim Medinipur"): "SUBARNAREKHA", ("West Bengal", "Jhargram"): "SUBARNAREKHA",
    # ---------------- Assam & north-east ----------------
    ("Assam", "Cachar"): "BARAK", ("Assam", "Karimganj"): "BARAK", ("Assam", "Hailakandi"): "BARAK",
    ("Assam", "Dima Hasao"): "BARAK",
    ("Assam", "Barpeta"): "MANAS", ("Assam", "Baksa"): "MANAS", ("Assam", "Chirang"): "MANAS",
    ("Assam", "Bongaigaon"): "MANAS", ("Assam", "Kokrajhar"): "MANAS",
    ("Assam", "Tamulpur"): "MANAS", ("Assam", "Bajali"): "MANAS",
    ("Assam", "Nalbari"): "PAGLADIA",
    ("Assam", "Sonitpur"): "JIA_BHARALI", ("Assam", "Biswanath"): "JIA_BHARALI",
    ("Assam", "Golaghat"): "DHANSHIRI", ("Assam", "Karbi Anglong"): "DHANSHIRI",
    ("Meghalaya", "South Garo Hills"): "BARAK", ("Meghalaya", "South West Garo Hills"): "BARAK",
    # ---------------- Uttar Pradesh ----------------
    ("Uttar Pradesh", "Saharanpur"): "YAMUNA", ("Uttar Pradesh", "Muzaffarnagar"): "YAMUNA",
    ("Uttar Pradesh", "Shamli"): "YAMUNA", ("Uttar Pradesh", "Baghpat"): "YAMUNA",
    ("Uttar Pradesh", "Meerut"): "YAMUNA", ("Uttar Pradesh", "Hapur"): "YAMUNA",
    ("Uttar Pradesh", "Ghaziabad"): "YAMUNA", ("Uttar Pradesh", "Gautam Buddha Nagar"): "YAMUNA",
    ("Uttar Pradesh", "Aligarh"): "YAMUNA", ("Uttar Pradesh", "Hathras"): "YAMUNA",
    ("Uttar Pradesh", "Mathura"): "YAMUNA", ("Uttar Pradesh", "Agra"): "YAMUNA",
    ("Uttar Pradesh", "Firozabad"): "YAMUNA", ("Uttar Pradesh", "Etah"): "YAMUNA",
    ("Uttar Pradesh", "Bijnor"): "RAMGANGA", ("Uttar Pradesh", "Moradabad"): "RAMGANGA",
    ("Uttar Pradesh", "Rampur"): "RAMGANGA", ("Uttar Pradesh", "Bareilly"): "RAMGANGA",
    ("Uttar Pradesh", "Budaun"): "RAMGANGA", ("Uttar Pradesh", "Shahjahanpur"): "RAMGANGA",
    ("Uttar Pradesh", "Kasganj"): "RAMGANGA", ("Uttar Pradesh", "Pilibhit"): "RAMGANGA",
    ("Uttar Pradesh", "Sambhal"): "RAMGANGA",
    ("Uttar Pradesh", "Sitapur"): "GOMTI", ("Uttar Pradesh", "Lucknow"): "GOMTI",
    ("Uttar Pradesh", "Barabanki"): "GOMTI", ("Uttar Pradesh", "Sultanpur"): "GOMTI",
    ("Uttar Pradesh", "Amethi"): "GOMTI", ("Uttar Pradesh", "Raebareli"): "GOMTI",
    ("Uttar Pradesh", "Jaunpur"): "GOMTI",
    ("Uttar Pradesh", "Balrampur"): "GHAGHRA", ("Uttar Pradesh", "Shrawasti"): "GHAGHRA",
    ("Uttar Pradesh", "Bahraich"): "GHAGHRA", ("Uttar Pradesh", "Kheri"): "GHAGHRA",
    ("Uttar Pradesh", "Gonda"): "GHAGHRA", ("Uttar Pradesh", "Ayodhya"): "GHAGHRA",
    ("Uttar Pradesh", "Ambedkar Nagar"): "GHAGHRA", ("Uttar Pradesh", "Azamgarh"): "GHAGHRA",
    ("Uttar Pradesh", "Basti"): "GHAGHRA", ("Uttar Pradesh", "Sant Kabir Nagar"): "GHAGHRA",
    ("Uttar Pradesh", "Mau"): "GHAGHRA", ("Uttar Pradesh", "Ballia"): "GHAGHRA",
    ("Uttar Pradesh", "Deoria"): "GHAGHRA",
    ("Uttar Pradesh", "Siddharthnagar"): "GANDAK", ("Uttar Pradesh", "Gorakhpur"): "GANDAK",
    ("Uttar Pradesh", "Kushinagar"): "GANDAK", ("Uttar Pradesh", "Maharajganj"): "GANDAK",
    ("Uttar Pradesh", "Mirzapur"): "SONE", ("Uttar Pradesh", "Sonbhadra"): "SONE",
    ("Uttar Pradesh", "Jhansi"): "BETWA", ("Uttar Pradesh", "Lalitpur"): "BETWA",
    ("Uttar Pradesh", "Hamirpur"): "BETWA", ("Uttar Pradesh", "Mahoba"): "BETWA",
    ("Uttar Pradesh", "Chitrakoot"): "BETWA", ("Uttar Pradesh", "Banda"): "BETWA",
    # ---------------- Uttarakhand / Himachal ----------------
    ("Uttarakhand", "Dehradun"): "YAMUNA",
    ("Himachal Pradesh", "Kangra"): "BEAS", ("Himachal Pradesh", "Mandi"): "BEAS",
    ("Himachal Pradesh", "Kullu"): "BEAS", ("Himachal Pradesh", "Hamirpur"): "BEAS",
    ("Himachal Pradesh", "Bilaspur"): "SATLUJ", ("Himachal Pradesh", "Kinnaur"): "SATLUJ",
    ("Himachal Pradesh", "Solan"): "SATLUJ", ("Himachal Pradesh", "Shimla"): "SATLUJ",
    ("Himachal Pradesh", "Una"): "SATLUJ",
    ("Himachal Pradesh", "Sirmaur"): "YAMUNA",
    ("Himachal Pradesh", "Chamba"): "RAVI", ("Himachal Pradesh", "Lahaul and Spiti"): "CHENAB",
    ("Jammu and Kashmir", "Doda"): "CHENAB", ("Jammu and Kashmir", "Kishtwar"): "CHENAB",
    ("Jammu and Kashmir", "Ramban"): "CHENAB", ("Jammu and Kashmir", "Udhampur"): "CHENAB",
    ("Jammu and Kashmir", "Rajouri"): "CHENAB", ("Jammu and Kashmir", "Reasi"): "CHENAB",
    ("Jammu and Kashmir", "Jammu"): "CHENAB",
    ("Jammu and Kashmir", "Kathua"): "RAVI", ("Jammu and Kashmir", "Samba"): "RAVI",
    # ---------------- Odisha ----------------
    ("Odisha", "Sundargarh"): "BRAHMANI", ("Odisha", "Kendujhar"): "BRAHMANI",
    ("Odisha", "Deogarh"): "BRAHMANI", ("Odisha", "Angul"): "BRAHMANI",
    ("Odisha", "Dhenkanal"): "BRAHMANI", ("Odisha", "Jajpur"): "BRAHMANI",
    ("Odisha", "Kendrapara"): "BRAHMANI",
    ("Odisha", "Mayurbhanj"): "BAITARANI", ("Odisha", "Balasore"): "BAITARANI",
    ("Odisha", "Bhadrak"): "BAITARANI",
    ("Odisha", "Ganjam"): "RUSHIKULYA", ("Odisha", "Gajapati"): "VAMSADHARA",
    ("Odisha", "Malkangiri"): "GODAVARI", ("Odisha", "Koraput"): "GODAVARI",
    ("Odisha", "Rayagada"): "GODAVARI",
    # ---------------- Andhra Pradesh / Telangana ----------------
    ("Andhra Pradesh", "East Godavari"): "GODAVARI", ("Andhra Pradesh", "West Godavari"): "GODAVARI",
    ("Andhra Pradesh", "Kakinada"): "GODAVARI", ("Andhra Pradesh", "Dr. B.R. Ambedkar Konaseema"): "GODAVARI",
    ("Andhra Pradesh", "Alluri Sitharama Raju"): "GODAVARI", ("Andhra Pradesh", "Anakapalli"): "GODAVARI",
    ("Andhra Pradesh", "YSR Kadapa"): "PENNAR", ("Andhra Pradesh", "Sri Potti Sriramulu Nellore"): "PENNAR",
    ("Andhra Pradesh", "Prakasam"): "PENNAR", ("Andhra Pradesh", "Anantapur"): "PENNAR",
    ("Andhra Pradesh", "Sri Sathya Sai"): "PENNAR", ("Andhra Pradesh", "Annamayya"): "PENNAR",
    ("Andhra Pradesh", "Kurnool"): "TUNGABHADRA", ("Andhra Pradesh", "Nandyal"): "TUNGABHADRA",
    ("Andhra Pradesh", "Srikakulam"): "NAGAVALI", ("Andhra Pradesh", "Vizianagaram"): "NAGAVALI",
    ("Andhra Pradesh", "Parvathipuram Manyam"): "NAGAVALI",
    ("Andhra Pradesh", "Tirupati"): "SWARNAMUKHI", ("Andhra Pradesh", "Chittoor"): "SWARNAMUKHI",
    ("Andhra Pradesh", "Visakhapatnam"): "EAST_FLOWING",
    ("Telangana", "Adilabad"): "GODAVARI", ("Telangana", "Komaram Bheem Asifabad"): "GODAVARI",
    ("Telangana", "Mancherial"): "GODAVARI", ("Telangana", "Nirmal"): "GODAVARI",
    ("Telangana", "Nizamabad"): "GODAVARI", ("Telangana", "Kamareddy"): "GODAVARI",
    ("Telangana", "Jagtial"): "GODAVARI", ("Telangana", "Peddapalli"): "GODAVARI",
    ("Telangana", "Jayashankar Bhupalpally"): "GODAVARI", ("Telangana", "Mulugu"): "GODAVARI",
    ("Telangana", "Bhadradri Kothagudem"): "GODAVARI", ("Telangana", "Mahabubabad"): "GODAVARI",
    ("Telangana", "Warangal"): "GODAVARI", ("Telangana", "Hanumakonda"): "GODAVARI",
    ("Telangana", "Karimnagar"): "GODAVARI", ("Telangana", "Rajanna Sircilla"): "GODAVARI",
    ("Telangana", "Jangaon"): "GODAVARI",
    ("Telangana", "Hyderabad"): "KRISHNA", ("Telangana", "Medchal-Malkajgiri"): "KRISHNA",
    ("Telangana", "Rangareddy"): "KRISHNA", ("Telangana", "Vikarabad"): "KRISHNA",
    ("Telangana", "Sangareddy"): "KRISHNA", ("Telangana", "Medak"): "KRISHNA",
    ("Telangana", "Siddipet"): "KRISHNA", ("Telangana", "Mahabubnagar"): "KRISHNA",
    ("Telangana", "Nagarkurnool"): "KRISHNA", ("Telangana", "Wanaparthy"): "KRISHNA",
    ("Telangana", "Jogulamba Gadwal"): "KRISHNA", ("Telangana", "Narayanpet"): "KRISHNA",
    ("Telangana", "Nalgonda"): "KRISHNA", ("Telangana", "Suryapet"): "KRISHNA",
    ("Telangana", "Yadadri Bhuvanagiri"): "KRISHNA", ("Telangana", "Khammam"): "KRISHNA",
    # ---------------- Karnataka ----------------
    ("Karnataka", "Ballari"): "TUNGABHADRA", ("Karnataka", "Koppal"): "TUNGABHADRA",
    ("Karnataka", "Raichur"): "TUNGABHADRA", ("Karnataka", "Yadgir"): "TUNGABHADRA",
    ("Karnataka", "Chitradurga"): "TUNGABHADRA", ("Karnataka", "Davanagere"): "TUNGABHADRA",
    ("Karnataka", "Chikkamagaluru"): "TUNGABHADRA", ("Karnataka", "Shivamogga"): "TUNGABHADRA",
    ("Karnataka", "Mysuru"): "CAUVERY", ("Karnataka", "Mandya"): "CAUVERY",
    ("Karnataka", "Ramanagara"): "CAUVERY", ("Karnataka", "Chamarajanagar"): "CAUVERY",
    ("Karnataka", "Kodagu"): "CAUVERY", ("Karnataka", "Hassan"): "CAUVERY",
    ("Karnataka", "Dakshina Kannada"): "WEST_FLOWING", ("Karnataka", "Udupi"): "WEST_FLOWING",
    ("Karnataka", "Uttara Kannada"): "WEST_FLOWING",
    ("Karnataka", "Bengaluru Urban"): "PENNAR", ("Karnataka", "Bengaluru Rural"): "PENNAR",
    ("Karnataka", "Kolar"): "PENNAR", ("Karnataka", "Chikkaballapur"): "PENNAR",
    # ---------------- Maharashtra ----------------
    ("Maharashtra", "Satara"): "KRISHNA", ("Maharashtra", "Sangli"): "KRISHNA",
    ("Maharashtra", "Kolhapur"): "PANCHGANGA", ("Maharashtra", "Pune"): "KRISHNA",
    ("Maharashtra", "Solapur"): "KRISHNA", ("Maharashtra", "Osmanabad"): "KRISHNA",
    ("Maharashtra", "Latur"): "KRISHNA", ("Maharashtra", "Panchgani"): "KRISHNA",
    ("Maharashtra", "Jalgaon"): "TAPI", ("Maharashtra", "Dhule"): "TAPI",
    ("Maharashtra", "Nandurbar"): "TAPI",
    ("Maharashtra", "Mumbai City"): "WEST_FLOWING", ("Maharashtra", "Mumbai Suburban"): "WEST_FLOWING",
    ("Maharashtra", "Thane"): "WEST_FLOWING", ("Maharashtra", "Palghar"): "WEST_FLOWING",
    ("Maharashtra", "Raigad"): "WEST_FLOWING", ("Maharashtra", "Ratnagiri"): "WEST_FLOWING",
    ("Maharashtra", "Sindhudurg"): "WEST_FLOWING",
    # ---------------- Rajasthan ----------------
    ("Rajasthan", "Kota"): "CHAMBAL", ("Rajasthan", "Baran"): "CHAMBAL",
    ("Rajasthan", "Bundi"): "CHAMBAL", ("Rajasthan", "Karauli"): "CHAMBAL",
    ("Rajasthan", "Sawai Madhopur"): "CHAMBAL", ("Rajasthan", "Dholpur"): "CHAMBAL",
    ("Rajasthan", "Jaipur"): "BANAS", ("Rajasthan", "Ajmer"): "BANAS",
    ("Rajasthan", "Tonk"): "BANAS", ("Rajasthan", "Bhilwara"): "BANAS",
    ("Rajasthan", "Rajsamand"): "BANAS", ("Rajasthan", "Udaipur"): "BANAS",
    ("Rajasthan", "Devgarh"): "BANAS", ("Rajasthan", "Chittorgarh"): "BANAS",
    ("Rajasthan", "Beawar"): "BANAS", ("Rajasthan", "Salumbar"): "BANAS",
    ("Rajasthan", "Banswara"): "MAHI", ("Rajasthan", "Dungarpur"): "MAHI",
    ("Rajasthan", "Pratapgarh"): "MAHI",
    ("Rajasthan", "Ganganagar"): "GHAGGAR", ("Rajasthan", "Sri Ganganagar"): "GHAGGAR",
    ("Rajasthan", "Hanumangarh"): "GHAGGAR", ("Rajasthan", "Bikaner"): "GHAGGAR",
    ("Rajasthan", "Churu"): "GHAGGAR", ("Rajasthan", "Sikar"): "GHAGGAR",
    ("Rajasthan", "Jhunjhunu"): "GHAGGAR", ("Rajasthan", "Nagaur"): "GHAGGAR",
    ("Rajasthan", "Alwar"): "YAMUNA", ("Rajasthan", "Bharatpur"): "YAMUNA",
    ("Rajasthan", "Bharatpur City"): "YAMUNA", ("Rajasthan", "Dausa"): "YAMUNA",
    # ---------------- Gujarat ----------------
    ("Gujarat", "Mahisagar"): "MAHI", ("Gujarat", "Panchmahal"): "MAHI",
    ("Gujarat", "Dahod"): "MAHI", ("Gujarat", "Vadodara"): "MAHI",
    ("Gujarat", "Kheda"): "MAHI", ("Gujarat", "Anand"): "MAHI",
    ("Gujarat", "Narmada"): "NARMADA", ("Gujarat", "Bharuch"): "NARMADA",
    ("Gujarat", "Chhota Udaipur"): "NARMADA",
    ("Gujarat", "Surat"): "TAPI", ("Gujarat", "Tapi"): "TAPI",
    ("Gujarat", "Navsari"): "WEST_FLOWING", ("Gujarat", "Valsad"): "WEST_FLOWING",
    ("Gujarat", "Dang"): "WEST_FLOWING",
    ("Gujarat", "Bhavnagar"): "SHETRUNJI", ("Gujarat", "Amreli"): "SHETRUNJI",
    ("Gujarat", "Botad"): "SHETRUNJI",
    ("Gujarat", "Rajkot"): "AAJI", ("Gujarat", "Morbi"): "AAJI",
    ("Gujarat", "Jamnagar"): "BHADAR", ("Gujarat", "Devbhoomi Dwarka"): "BHADAR",
    ("Gujarat", "Porbandar"): "OJAT", ("Gujarat", "Junagadh"): "OJAT",
    ("Gujarat", "Gir Somnath"): "OJAT",
    ("Gujarat", "Kutch"): "RAN_OF_KACHCHH", ("Gujarat", "Surendranagar"): "RAN_OF_KACHCHH",
    ("Gujarat", "Banaskantha"): "BANAS", ("Gujarat", "Patan"): "SABARMATI",
    ("Gujarat", "Mehsana"): "SABARMATI",
    # ---------------- Punjab / Haryana ----------------
    ("Punjab", "Ludhiana"): "SATLUJ", ("Punjab", "Rupnagar"): "SATLUJ",
    ("Punjab", "Sangrur"): "SATLUJ", ("Punjab", "Barnala"): "SATLUJ",
    ("Punjab", "Moga"): "SATLUJ", ("Punjab", "Bathinda"): "SATLUJ",
    ("Punjab", "Mansa"): "SATLUJ", ("Punjab", "Fazilka"): "SATLUJ",
    ("Punjab", "Ferozepur"): "SATLUJ", ("Punjab", "Muktsar"): "SATLUJ",
    ("Punjab", "Sri Muktsar Sahib"): "SATLUJ", ("Punjab", "Malerkotla"): "SATLUJ",
    ("Punjab", "Jalandhar"): "BEAS", ("Punjab", "Hoshiarpur"): "BEAS",
    ("Punjab", "Kapurthala"): "BEAS", ("Punjab", "Shahid Bhagat Singh Nagar"): "BEAS",
    ("Punjab", "Gurdaspur"): "BEAS", ("Punjab", "Amritsar"): "BEAS",
    ("Punjab", "Pathankot"): "RAVI", ("Punjab", "Patiala"): "GHAGGAR",
    ("Haryana", "Hisar"): "GHAGGAR", ("Haryana", "Bhiwani"): "GHAGGAR",
    ("Haryana", "Charkhi Dadri"): "GHAGGAR", ("Haryana", "Fatehabad"): "GHAGGAR",
    ("Haryana", "Sirsa"): "GHAGGAR", ("Haryana", "Jind"): "GHAGGAR",
    ("Haryana", "Kaithal"): "GHAGGAR", ("Haryana", "Kurukshetra"): "GHAGGAR",
    ("Haryana", "Panchkula"): "GHAGGAR", ("Haryana", "Ambala"): "GHAGGAR",
    # ---------------- Jharkhand ----------------
    ("Jharkhand", "Dhanbad"): "DAMODAR", ("Jharkhand", "Bokaro"): "DAMODAR",
    ("Jharkhand", "Ramgarh"): "DAMODAR", ("Jharkhand", "Hazaribagh"): "DAMODAR",
    ("Jharkhand", "Giridih"): "DAMODAR", ("Jharkhand", "Koderma"): "DAMODAR",
    ("Jharkhand", "Deoghar"): "GANGA", ("Jharkhand", "Dumka"): "GANGA",
    ("Jharkhand", "Jamtara"): "GANGA", ("Jharkhand", "Godda"): "GANGA",
    ("Jharkhand", "Pakur"): "GANGA", ("Jharkhand", "Sahebganj"): "GANGA",
    ("Jharkhand", "Sahibganj"): "GANGA",
    ("Jharkhand", "Palamu"): "SONE", ("Jharkhand", "Latehar"): "SONE",
    ("Jharkhand", "Garhwa"): "SONE", ("Jharkhand", "Chatra"): "SONE",
    # ---------------- Madhya Pradesh ----------------
    ("Madhya Pradesh", "Morena"): "CHAMBAL", ("Madhya Pradesh", "Sheopur"): "CHAMBAL",
    ("Madhya Pradesh", "Bhind"): "CHAMBAL", ("Madhya Pradesh", "Datia"): "CHAMBAL",
    ("Madhya Pradesh", "Shivpuri"): "CHAMBAL", ("Madhya Pradesh", "Gwalior"): "CHAMBAL",
    ("Madhya Pradesh", "Guna"): "CHAMBAL", ("Madhya Pradesh", "Rajgarh"): "CHAMBAL",
    ("Madhya Pradesh", "Neemuch"): "CHAMBAL", ("Madhya Pradesh", "Mandsaur"): "CHAMBAL",
    ("Madhya Pradesh", "Shajapur"): "CHAMBAL", ("Madhya Pradesh", "Agar Malwa"): "CHAMBAL",
    ("Madhya Pradesh", "Ashoknagar"): "YAMUNA", ("Madhya Pradesh", "Panna"): "YAMUNA",
    ("Madhya Pradesh", "Satna"): "YAMUNA", ("Madhya Pradesh", "Rewa"): "YAMUNA",
    ("Madhya Pradesh", "Vidisha"): "BETWA", ("Madhya Pradesh", "Raisen"): "BETWA",
    ("Madhya Pradesh", "Sagar"): "BETWA", ("Madhya Pradesh", "Damoh"): "BETWA",
    ("Madhya Pradesh", "Tikamgarh"): "BETWA", ("Madhya Pradesh", "Chhatarpur"): "BETWA",
    ("Madhya Pradesh", "Bhopal"): "BETWA", ("Madhya Pradesh", "Sehore"): "BETWA",
    ("Madhya Pradesh", "Sidhi"): "SONE", ("Madhya Pradesh", "Singrauli"): "SONE",
    ("Madhya Pradesh", "Shahdol"): "SONE", ("Madhya Pradesh", "Umaria"): "SONE",
    ("Madhya Pradesh", "Anuppur"): "SONE", ("Madhya Pradesh", "Katni"): "SONE",
    ("Madhya Pradesh", "Balaghat"): "GODAVARI", ("Madhya Pradesh", "Seoni"): "GODAVARI",
    ("Madhya Pradesh", "Chhindwara"): "GODAVARI",
    ("Madhya Pradesh", "Ratlam"): "MAHI", ("Madhya Pradesh", "Jhabua"): "MAHI",
    ("Madhya Pradesh", "Alirajpur"): "MAHI", ("Madhya Pradesh", "Dhar"): "NARMADA",
    # ---------------- Chhattisgarh ----------------
    ("Chhattisgarh", "Bastar"): "GODAVARI", ("Chhattisgarh", "Dantewada"): "GODAVARI",
    ("Chhattisgarh", "Bijapur"): "GODAVARI", ("Chhattisgarh", "Sukma"): "GODAVARI",
    ("Chhattisgarh", "Narayanpur"): "GODAVARI",
    # ---------------- Tamil Nadu ----------------
    ("Tamil Nadu", "Vellore"): "PALAR", ("Tamil Nadu", "Ranipet"): "PALAR",
    ("Tamil Nadu", "Tirupattur"): "PALAR", ("Tamil Nadu", "Kanchipuram"): "PALAR",
    ("Tamil Nadu", "Chengalpattu"): "PALAR", ("Tamil Nadu", "Tiruvallur"): "PALAR",
    ("Tamil Nadu", "Krishnagiri"): "PALAR",
    ("Tamil Nadu", "Tiruvannamalai"): "PONNAIYAR", ("Tamil Nadu", "Viluppuram"): "PONNAIYAR",
    ("Tamil Nadu", "Madurai"): "VAIGAI", ("Tamil Nadu", "Theni"): "VAIGAI",
    ("Tamil Nadu", "Ramanathapuram"): "VAIGAI", ("Tamil Nadu", "Virudhunagar"): "VAIGAI",
    ("Tamil Nadu", "Sivaganga"): "VAIGAI",
    ("Tamil Nadu", "Chennai"): "COASTAL", ("Tamil Nadu", "Kanyakumari"): "COASTAL",
    ("Tamil Nadu", "Thoothukudi"): "COASTAL", ("Tamil Nadu", "Tirunelveli"): "COASTAL",
    ("Tamil Nadu", "Dindigul"): "CAUVERY", ("Tamil Nadu", "Coimbatore"): "CAUVERY",
    ("Tamil Nadu", "Tiruppur"): "CAUVERY", ("Tamil Nadu", "Nilgiris"): "CAUVERY",
}

# Approximate district population: 2011 Census state population shared evenly
# across that state's districts. Only used for exposure weighting.
_STATE_POPULATION = {
    "Andaman and Nicobar Islands": 380_581,
    "Andhra Pradesh": 49_577_103,
    "Arunachal Pradesh": 1_383_727,
    "Assam": 31_205_576,
    "Bihar": 104_099_452,
    "Chandigarh": 1_055_450,
    "Chhattisgarh": 25_545_198,
    "Dadra and Nagar Haveli and Daman and Diu": 586_956,
    "Delhi": 16_787_941,
    "Goa": 1_458_545,
    "Gujarat": 60_439_692,
    "Haryana": 25_351_462,
    "Himachal Pradesh": 6_864_602,
    "Jammu and Kashmir": 12_541_302,
    "Jharkhand": 32_988_134,
    "Karnataka": 61_095_297,
    "Kerala": 33_406_061,
    "Ladakh": 274_289,
    "Lakshadweep": 64_473,
    "Madhya Pradesh": 72_626_809,
    "Maharashtra": 112_374_333,
    "Manipur": 2_855_794,
    "Meghalaya": 2_966_889,
    "Mizoram": 1_097_206,
    "Nagaland": 1_978_502,
    "Odisha": 41_974_218,
    "Puducherry": 1_247_953,
    "Punjab": 27_743_338,
    "Rajasthan": 68_548_437,
    "Sikkim": 610_577,
    "Tamil Nadu": 72_147_030,
    "Telangana": 35_003_674,
    "Tripura": 3_673_917,
    "Uttar Pradesh": 199_812_341,
    "Uttarakhand": 10_086_292,
    "West Bengal": 91_276_115,
}


def build_zone_polygon(lat, lon, half_km):
    """Return GeoJSON polygon ring around a centroid (approx km to deg scale)."""
    deg_per_km_lat = 1.0 / 111.0
    dlat = half_km * deg_per_km_lat
    deg_per_km_lon = 1.0 / (111.0 * abs(math.cos(math.radians(lat))) or 1.0)
    dlon = half_km * deg_per_km_lon
    return [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]


def _basin_for(state: str, district: str) -> str:
    return _DISTRICT_BASIN.get((state, district)) or _STATE_BASIN.get(state, "COASTAL")


def _build_zones():
    from collections import Counter

    per_state = Counter(d["state"] for d in DISTRICTS)
    out = []
    for d in DISTRICTS:
        state = d["state"]
        pop = max(int(_STATE_POPULATION.get(state, 1_000_000) / max(per_state[state], 1)), 10_000)
        vuln = 0.30 if d["flood_prone"] else 0.22
        half_km = 6.0 if pop >= 5_000_000 else 8.0  # tighter polygon for megacities
        hq = d["hq"] or d["district"]
        out.append({
            "id": d["id"],
            "name": hq,
            "state": state,
            "basin": _basin_for(state, d["district"]),
            "district": d["district"],
            "population": pop,
            "vulnerable_population": round(vuln, 3),
            "flood_prone": bool(d["flood_prone"]),
            "coordinates": build_zone_polygon(d["lat"], d["lon"], half_km),
            "centroid": [d["lon"], d["lat"]],
            "area_km2": round(half_km * half_km * 4.0, 1),
        })
    return out


# Every district in India is a monitoring zone (district-HQ precise).
ZONES = _build_zones()
ZONE_INDEX = {z["id"]: z for z in ZONES}

# CWC flood forecasting network stations. WL/DL are published danger/warning
# levels (metres above gauge zero); approximate where private. New stations
# cover the Kosi/Gandak/Bagmati systems, the Teesta/Torsa/Mahananda belt and
# the Baitarani/Brahmani/Tungabhadra basins.
RIVER_STATIONS = [
    # (id, name, river, basin, state, lat, lon, warning_level, danger_level, hfl, type)
    ("CWC-BRP-GHY", "Guwahati PD Ghat", "Brahmaputra", "BRAHMAPUTRA", "Assam", 26.1848, 91.7508, 48.7, 49.6, 50.9, "Level Forecast"),
    ("CWC-BRP-TEZPUR", "Tezpur", "Brahmaputra", "BRAHMAPUTRA", "Assam", 26.6333, 92.8000, 60.5, 61.4, 63.0, "Level Forecast"),
    ("CWC-BRP-DIBRUGARH", "Dibrugarh", "Brahmaputra", "BRAHMAPUTRA", "Assam", 27.4728, 94.9120, 103.4, 104.6, 106.9, "Level Forecast"),
    ("CWC-BRP-DHUBRI", "Dhubri", "Brahmaputra", "BRAHMAPUTRA", "Assam", 26.0225, 90.0000, 27.1, 27.9, 28.9, "Level Forecast"),
    ("CWC-BRP-AMINGAON", "Amingaon", "Brahmaputra", "BRAHMAPUTRA", "Assam", 26.1770, 91.6780, 47.8, 48.9, 50.2, "Level Forecast"),
    ("CWC-MNS-BARPETA", "Beki at Barpeta", "Beki(Manas)", "MANAS", "Assam", 26.3230, 91.0100, 42.5, 43.6, 45.0, "Level Forecast"),
    ("CWC-DNS-NUMALIGARH", "Numaligarh", "Dhansiri", "DHANSHIRI", "Assam", 26.6150, 93.7200, 74.8, 75.9, 77.6, "Level Forecast"),
    ("CWC-JBRH-NTROAD", "Jia Bharali at N.T. Road", "Jia Bharali", "JIA_BHARALI", "Assam", 26.8300, 92.5800, 68.9, 70.1, 71.8, "Level Forecast"),
    ("CWC-BRK-SILCHAR", "Silchar (Annapurna Ghat)", "Barak", "BARAK", "Assam", 24.8280, 92.7970, 20.6, 21.3, 22.2, "Level Forecast"),
    ("CWC-BRK-BADARPUR", "Badarpurghat", "Barak", "BARAK", "Assam", 24.8930, 92.5880, 24.2, 25.1, 26.3, "Level Forecast"),
    ("CWC-GG-PRAYAG", "Prayagraj (Sangam)", "Ganga", "GANGA", "Uttar Pradesh", 25.4358, 81.8463, 83.8, 85.0, 86.6, "Level Forecast"),
    ("CWC-GG-VARANASI", "Varanasi", "Ganga", "GANGA", "Uttar Pradesh", 25.3176, 82.9739, 70.9, 71.8, 73.6, "Level Forecast"),
    ("CWC-GG-KANPUR", "Kanpur", "Ganga", "GANGA", "Uttar Pradesh", 26.4499, 80.3319, 105.8, 107.0, 110.0, "Level Forecast"),
    ("CWC-GG-GHAZIPUR", "Ghazipur", "Ganga", "GANGA", "Uttar Pradesh", 25.5833, 83.5833, 58.4, 59.4, 60.9, "Level Forecast"),
    ("CWC-GG-PATNA", "Patna (Gandhighat)", "Ganga", "GANGA", "Bihar", 25.5941, 85.1376, 46.0, 47.0, 48.7, "Level Forecast"),
    ("CWC-GG-BHAGALPUR", "Bhagalpur", "Ganga", "GANGA", "Bihar", 25.2425, 86.9843, 34.5, 35.5, 36.7, "Level Forecast"),
    ("CWC-GG-FARAKKA", "Farakka", "Ganga", "GANGA", "West Bengal", 24.8033, 87.9000, 22.7, 23.3, 24.5, "Level Forecast"),
    ("CWC-GG-BARH", "Barh", "Ganga", "GANGA", "Bihar", 25.4700, 85.7000, 42.6, 43.7, 45.1, "Level Forecast"),
    ("CWC-GG-BUXAR", "Buxar", "Ganga", "GANGA", "Bihar", 25.5750, 83.9780, 60.2, 61.4, 62.9, "Level Forecast"),
    ("CWC-KS-BIRPUR", "Birpur", "Kosi", "KOSI", "Bihar", 26.5130, 86.9450, 80.2, 81.0, 82.6, "Level Forecast"),
    ("CWC-KS-BALTARA", "Baltara", "Kosi", "KOSI", "Bihar", 25.6000, 86.8200, 34.7, 35.4, 36.8, "Level Forecast"),
    ("CWC-KS-KAMLA", "Kusheshwar Asthan (Kamla)", "Kamla", "KOSI", "Bihar", 26.1400, 86.0700, 47.9, 48.6, 49.9, "Level Forecast"),
    ("CWC-GDK-VALMIKINAGAR", "Chhitauni (Valmikinagar)", "Gandak", "GANDAK", "Bihar", 27.3300, 83.9900, 64.0, 65.1, 66.8, "Level Forecast"),
    ("CWC-GDK-BAGAHA", "Bagaha", "Gandak", "GANDAK", "Bihar", 27.1000, 84.0700, 94.4, 95.5, 97.2, "Level Forecast"),
    ("CWC-BGM-HAYAGHAT", "Hayaghat", "Bagmati", "BAGMATI", "Bihar", 26.0300, 85.9800, 44.6, 45.5, 47.0, "Level Forecast"),
    ("CWC-BGM-ROSERA", "Rosera", "Bagmati", "BAGMATI", "Bihar", 25.8600, 85.9800, 42.3, 43.2, 44.8, "Level Forecast"),
    ("CWC-BG-BAGHA", "Bagha", "Burhi Gandak", "BURHI_GANDAK", "Bihar", 26.4800, 85.3300, 54.7, 55.6, 57.2, "Level Forecast"),
    ("CWC-BG-LALGANJ", "Lalganj", "Burhi Gandak", "BURHI_GANDAK", "Bihar", 25.8900, 85.1800, 48.0, 48.9, 50.4, "Level Forecast"),
    ("CWC-SN-KOELWAR", "Koelwar", "Sone", "SONE", "Bihar", 25.5800, 84.8000, 58.9, 60.0, 61.7, "Level Forecast"),
    ("CWC-SN-MANPUR", "Manpur", "Sone", "SONE", "Bihar", 25.1900, 84.5800, 76.7, 77.8, 79.4, "Level Forecast"),
    ("CWC-GGR-ELGIN", "Elgin Bridge", "Ghaghra", "GHAGHRA", "Uttar Pradesh", 26.6000, 83.9500, 63.0, 64.2, 65.9, "Level Forecast"),
    ("CWC-GGR-AYODHYA", "Ayodhya (Sarayu Ghat)", "Sarayu", "GHAGHRA", "Uttar Pradesh", 26.7915, 82.2001, 92.0, 93.0, 94.6, "Level Forecast"),
    ("CWC-GMT-SULTANPUR", "Sultanpur", "Gomti", "GOMTI", "Uttar Pradesh", 26.2570, 82.0680, 84.3, 85.4, 87.0, "Level Forecast"),
    ("CWC-YM-DELHI", "Delhi Railway Bridge", "Yamuna", "YAMUNA", "Delhi", 28.6448, 77.2167, 204.6, 205.4, 207.1, "Level Forecast"),
    ("CWC-YM-MATHURA", "Mathura", "Yamuna", "YAMUNA", "Uttar Pradesh", 27.4924, 77.6737, 167.1, 168.0, 169.7, "Level Forecast"),
    ("CWC-YM-AGRA", "Agra", "Yamuna", "YAMUNA", "Uttar Pradesh", 27.1767, 78.0081, 158.7, 159.7, 161.4, "Level Forecast"),
    ("CWC-YM-LUCKNOW", "Lucknow (Gomti)", "Gomti", "GANGA", "Uttar Pradesh", 26.8467, 80.9462, 109.0, 110.0, 111.6, "Level Forecast"),
    ("CWC-IS-HARIDWAR", "Haridwar", "Ganga", "GANGA", "Uttarakhand", 29.9457, 78.1642, 295.0, 296.0, 298.0, "Level Forecast"),
    ("CWC-IS-RISHIKESH", "Rishikesh", "Ganga", "GANGA", "Uttarakhand", 30.0869, 78.2676, 337.5, 338.7, 340.5, "Level Forecast"),
    ("CWC-GD-NASIK", "Nashik", "Godavari", "GODAVARI", "Maharashtra", 19.9975, 73.7898, 559.1, 560.3, 562.0, "Level Forecast"),
    ("CWC-GD-BHADRACHALAM", "Bhadrachalam", "Godavari", "GODAVARI", "Andhra Pradesh", 17.6683, 80.8903, 41.0, 42.4, 44.5, "Level Forecast"),
    ("CWC-GD-RAJAHMUNDRY", "Rajahmundry", "Godavari", "GODAVARI", "Andhra Pradesh", 17.0005, 81.8040, 11.9, 12.5, 13.5, "Level Forecast"),
    ("CWC-GD-PAULPALLE", "Paulpalle", "Godavari", "GODAVARI", "Andhra Pradesh", 17.6340, 80.8820, 45.7, 46.4, 48.2, "Level Forecast"),
    ("CWC-KR-VIJAYAWADA", "Vijayawada", "Krishna", "KRISHNA", "Andhra Pradesh", 16.5062, 80.6480, 16.9, 17.6, 18.6, "Level Forecast"),
    ("CWC-KR-BAGALKOT", "Bagalkot (Sangameshwar)", "Krishna", "KRISHNA", "Karnataka", 16.1846, 75.6961, 517.7, 519.1, 521.0, "Level Forecast"),
    ("CWC-KR-PRAKASAM", "Prakasam Barrage", "Krishna", "KRISHNA", "Andhra Pradesh", 16.5050, 80.6490, 15.7, 16.2, 17.4, "Inflow Forecast"),
    ("CWC-KR-SANGLI", "Sangli", "Krishna", "KRISHNA", "Maharashtra", 16.8524, 74.5815, 66.8, 68.0, 69.7, "Level Forecast"),
    ("CWC-TBR-BELLARY", "Tungabhadra Reservoir", "Tungabhadra", "TUNGABHADRA", "Karnataka", 15.2650, 76.3440, 496.8, 497.8, 499.3, "Inflow Forecast"),
    ("CWC-TBR-MANTRALAYAM", "Mantralayam", "Tungabhadra", "TUNGABHADRA", "Andhra Pradesh", 15.9400, 77.4300, 321.4, 322.7, 324.4, "Level Forecast"),
    ("CWC-CV-BHAVANI", "Bhavani", "Cauvery", "CAUVERY", "Tamil Nadu", 11.3660, 77.9400, 185.2, 186.0, 187.6, "Level Forecast"),
    ("CWC-CV-TRICHY", "Tiruchirappalli (Uyyakondan)", "Cauvery", "CAUVERY", "Tamil Nadu", 10.7905, 78.7047, 70.8, 71.7, 73.2, "Level Forecast"),
    ("CWC-CV-MAYILADUTHURAI", "Mayiladuthurai", "Cauvery", "CAUVERY", "Tamil Nadu", 11.1027, 79.6388, 5.6, 6.1, 7.0, "Level Forecast"),
    ("CWC-MH-SAMBALPUR", "Sambalpur", "Mahanadi", "MAHANADI", "Odisha", 21.4669, 83.9797, 185.3, 186.3, 188.0, "Level Forecast"),
    ("CWC-MH-CUTTACK", "Cuttack (Jobra)", "Mahanadi", "MAHANADI", "Odisha", 20.4625, 85.8828, 25.4, 26.1, 27.3, "Level Forecast"),
    ("CWC-MH-NARAJ", "Naraj", "Mahanadi", "MAHANADI", "Odisha", 20.4200, 85.8530, 24.8, 25.5, 26.7, "Level Forecast"),
    ("CWC-MH-TIKARPARA", "Tikarpara", "Mahanadi", "MAHANADI", "Odisha", 20.5400, 85.2500, 88.9, 90.1, 92.0, "Level Forecast"),
    ("CWC-NR-HIRAKUD", "Hirakud Dam", "Mahanadi", "MAHANADI", "Odisha", 21.5764, 83.8722, 630.9, 632.9, 634.9, "Inflow Forecast"),
    ("CWC-NM-JABALPUR", "Jabalpur", "Narmada", "NARMADA", "Madhya Pradesh", 23.1815, 79.9864, 356.7, 358.0, 360.0, "Level Forecast"),
    ("CWC-NM-TILAKWADA", "Garudeshwar", "Narmada", "NARMADA", "Gujarat", 21.8833, 73.6500, 28.3, 29.5, 31.2, "Level Forecast"),
    ("CWC-TP-SURAT", "Surat (Dumas)", "Tapi", "TAPI", "Gujarat", 21.1702, 72.8311, 8.9, 9.5, 10.6, "Level Forecast"),
    ("CWC-TP-KATHOR", "Kathor", "Tapi", "TAPI", "Gujarat", 21.1167, 72.9000, 9.9, 10.6, 11.8, "Level Forecast"),
    ("CWC-SB-SFEGH", "Sabarmati Gandhi Bridge", "Sabarmati", "SABARMATI", "Gujarat", 23.0333, 72.5800, 42.0, 43.0, 44.6, "Level Forecast"),
    ("CWC-SB-DEROL", "Derol", "Sabarmati", "SABARMATI", "Gujarat", 23.2000, 72.8000, 65.5, 66.5, 68.0, "Level Forecast"),
    ("CWC-DM-DURGAPUR", "Durgapur Barrage", "Damodar", "DAMODAR", "West Bengal", 23.4833, 87.3167, 45.3, 46.2, 47.5, "Inflow Forecast"),
    ("CWC-DM-RHONDIA", "Rhondia", "Damodar", "DAMODAR", "West Bengal", 23.6500, 87.4667, 68.2, 69.1, 70.6, "Level Forecast"),
    ("CWC-SR-JAMSHEDPUR", "Jamshedpur (Kharkhai)", "Subarnarekha", "SUBARNAREKHA", "Jharkhand", 22.8046, 86.2029, 110.6, 111.6, 113.2, "Level Forecast"),
    ("CWC-SR-GHATSILA", "Ghatsila", "Subarnarekha", "SUBARNAREKHA", "Jharkhand", 22.5900, 86.4800, 107.8, 108.9, 110.5, "Level Forecast"),
    ("CWC-BRM-TALCHER", "Talcher", "Brahmani", "BRAHMANI", "Odisha", 20.9500, 85.2300, 66.2, 67.4, 69.1, "Level Forecast"),
    ("CWC-BRM-JENAPUR", "Jenapur", "Brahmani", "BRAHMANI", "Odisha", 20.9200, 86.1000, 19.4, 20.2, 21.6, "Level Forecast"),
    ("CWC-BTR-ANANDAPUR", "Anandapur", "Baitarani", "BAITARANI", "Odisha", 21.2100, 86.1200, 24.9, 25.9, 27.4, "Level Forecast"),
    ("CWC-BTR-CHANDBALI", "Chandbali", "Baitarani", "BAITARANI", "Odisha", 20.7780, 86.7430, 4.2, 4.9, 6.0, "Level Forecast"),
    ("CWC-TST-BARRAGE", "Teesta Barrage (Gajoldoba)", "Teesta", "TEESTA", "West Bengal", 26.8530, 88.5400, 100.3, 101.2, 102.8, "Level Forecast"),
    ("CWC-TST-DOMOHANI", "Domohani", "Teesta", "TEESTA", "West Bengal", 26.7500, 88.7000, 78.9, 79.9, 81.5, "Level Forecast"),
    ("CWC-TST-JALPAIGURI", "Jalpaiguri", "Teesta", "TEESTA", "West Bengal", 26.5167, 88.7352, 85.4, 86.5, 88.1, "Level Forecast"),
    ("CWC-TRS-DHALPARA", "Dhalpara", "Torsa", "TORSA", "West Bengal", 26.5400, 89.0600, 71.2, 72.3, 73.9, "Level Forecast"),
    ("CWC-MND-DUMAIL", "Dumail", "Mahananda", "MAHANANDA", "West Bengal", 25.7500, 88.1300, 29.6, 30.6, 32.1, "Level Forecast"),
    ("CWC-MND-DAUKINI", "Daukini", "Mahananda", "MAHANANDA", "West Bengal", 25.2800, 88.6500, 26.4, 27.4, 28.9, "Level Forecast"),
    ("CWC-PN-KOLHAPUR", "Kolhapur", "Panchganga", "PANCHGANGA", "Maharashtra", 16.7050, 74.2433, 16.2, 17.1, 18.6, "Level Forecast"),
    ("CWC-PR-KOCHI", "Kochi (Periyar)", "Periyar", "PERIYAR", "Kerala", 9.9312, 76.2673, 2.8, 3.2, 4.0, "Monitoring"),
    ("CWC-PR-ALUVA", "Aluva Manappuram", "Periyar", "PERIYAR", "Kerala", 10.1078, 76.3516, 3.9, 4.5, 5.5, "Level Forecast"),
]

STATION_INDEX = {s[0]: s for s in RIVER_STATIONS}

# ---------------------------------------------------------------------------
# Rescue & relief infrastructure — generated for EVERY district of India.
#
# * One designated relief shelter and one district (civil) hospital per
#   district, placed at the district-HQ coordinates (the same precision as
#   the monitoring zones). Capacity/beds scale from the 2011 Census
#   population share, so every district has a medical staging point.
# * All 16 NDRF battalions (official locations, parent paramilitary force
#   recorded), one SDRF unit per state (state capital) and major-city
#   fire & rescue services.
# ---------------------------------------------------------------------------

# NDRF battalions — (no., station city, raised-from force, zone id).
_NDRF_BATTALIONS = [
    (1, "Guwahati", "BSF", "AS-Kamrup Metropolitan"),
    (2, "Nadia", "BSF", "WB-Nadia"),
    (3, "Cuttack", "CISF", "OD-Cuttack"),
    (4, "Vellore", "CISF", "TN-Vellore"),
    (5, "Pune", "CRPF", "MH-Pune"),
    (6, "Vadodara", "CRPF", "GJ-Vadodara"),
    (7, "Bhatinda", "ITBP", "PB-Bathinda"),
    (8, "Ghaziabad", "ITBP", "UP-Ghaziabad"),
    (9, "Patna", "BSF", "BR-Patna"),
    (10, "Vijayawada", "CRPF", "AP-NTR"),
    (11, "Varanasi", "SSB", "UP-Varanasi"),
    (12, "Itanagar", "SSB", "AR-Itanagar Capital Complex"),
    (13, "Samba", "Assam Rifles", "JK-Samba"),
    (14, "Mandi", "ITBP", "HP-Mandi"),
    (15, "Haldwani", "ITBP", "UK-Nainital"),
    (16, "Najafgarh", "BSF", "DL-South West Delhi"),
]

# State SDRF headquarters (state capital district; shared where two states
# share a capital). Maps state -> capital district name in the registry.
_STATE_SDRF_HQ = {
    "Andaman and Nicobar Islands": "South Andaman",
    "Andhra Pradesh": "NTR",
    "Arunachal Pradesh": "Itanagar Capital Complex",
    "Assam": "Kamrup Metropolitan",
    "Bihar": "Patna",
    "Chandigarh": "Chandigarh",
    "Chhattisgarh": "Raipur",
    "Dadra and Nagar Haveli and Daman and Diu": "Dadra and Nagar Haveli",
    "Delhi": "New Delhi",
    "Goa": "North Goa",
    "Gujarat": "Ahmedabad",
    "Haryana": "Chandigarh",
    "Himachal Pradesh": "Shimla",
    "Jammu and Kashmir": "Srinagar",
    "Jharkhand": "Ranchi",
    "Karnataka": "Bengaluru Urban",
    "Kerala": "Thiruvananthapuram",
    "Ladakh": "Leh",
    "Lakshadweep": "Lakshadweep",
    "Madhya Pradesh": "Bhopal",
    "Maharashtra": "Mumbai City",
    "Manipur": "Imphal West",
    "Meghalaya": "East Khasi Hills",
    "Mizoram": "Aizawl",
    "Nagaland": "Kohima",
    "Odisha": "Khordha",
    "Puducherry": "Puducherry",
    "Punjab": "Chandigarh",
    "Rajasthan": "Jaipur",
    "Sikkim": "East Sikkim",
    "Tamil Nadu": "Chennai",
    "Telangana": "Hyderabad",
    "Tripura": "West Tripura",
    "Uttar Pradesh": "Lucknow",
    "Uttarakhand": "Dehradun",
    "West Bengal": "Kolkata",
}

# Major-city fire & rescue services (fire-service HQs).
_FIRE_STATIONS = [
    ("Delhi Fire Service HQ", "DL-New Delhi"),
    ("Mumbai Fire Brigade HQ", "MH-Mumbai City"),
    ("Kolkata Fire & Emergency HQ", "WB-Kolkata"),
    ("Chennai Fire & Rescue HQ", "TN-Chennai"),
    ("Hyderabad Fire & Emergency HQ", "TG-Hyderabad"),
    ("Bengaluru Fire & Emergency HQ", "KA-Bengaluru Urban"),
    ("Ahmedabad Fire & Emergency HQ", "GJ-Ahmedabad"),
    ("Pune Fire Brigade HQ", "MH-Pune"),
    ("Ernakulam Fire & Rescue HQ", "KL-Ernakulam"),
]

# Curated tertiary hospitals / named relief camps kept alongside the generated
# per-district sites, so the busiest cities get extra medical depth.
_CURATED_HOSPITALS = [
    {"id": "H-AS-1", "name": "GMCH Guwahati", "zone": "AS-Kamrup Metropolitan", "state": "Assam", "lat": 26.1604, "lon": 91.8642, "beds": 1250, "capacity_status": "OPERATIONAL"},
    {"id": "H-BR-1", "name": "Patna Medical College Hospital", "zone": "BR-Patna", "state": "Bihar", "lat": 25.6090, "lon": 85.1450, "beds": 2100, "capacity_status": "OPERATIONAL"},
    {"id": "H-WB-1", "name": "SSKM Hospital Kolkata", "zone": "WB-Kolkata", "state": "West Bengal", "lat": 22.5429, "lon": 88.3517, "beds": 1850, "capacity_status": "OPERATIONAL"},
    {"id": "H-GJ-1", "name": "Civil Hospital Surat", "zone": "GJ-Surat", "state": "Gujarat", "lat": 21.2035, "lon": 72.8463, "beds": 1300, "capacity_status": "OPERATIONAL"},
    {"id": "H-KL-1", "name": "Rajagiri Hospital Aluva", "zone": "KL-Ernakulam", "state": "Kerala", "lat": 10.1078, "lon": 76.3640, "beds": 500, "capacity_status": "STRESSED"},
    {"id": "H-AP-1", "name": "Vijayawada General Hospital", "zone": "AP-NTR", "state": "Andhra Pradesh", "lat": 16.5112, "lon": 80.6340, "beds": 800, "capacity_status": "STRESSED"},
    {"id": "H-TN-1", "name": "Rajiv Gandhi Govt Hospital Chennai", "zone": "TN-Chennai", "state": "Tamil Nadu", "lat": 13.1264, "lon": 80.2522, "beds": 1200, "capacity_status": "OPERATIONAL"},
    {"id": "H-OD-1", "name": "SCB Medical Cuttack", "zone": "OD-Cuttack", "state": "Odisha", "lat": 20.4625, "lon": 85.8828, "beds": 1500, "capacity_status": "OPERATIONAL"},
    {"id": "H-DL-1", "name": "LNJP Hospital Delhi", "zone": "DL-Central Delhi", "state": "Delhi", "lat": 28.6380, "lon": 77.2330, "beds": 1400, "capacity_status": "OPERATIONAL"},
    {"id": "H-TG-1", "name": "Gandhi Hospital Hyderabad", "zone": "TG-Hyderabad", "state": "Telangana", "lat": 17.4401, "lon": 78.4833, "beds": 1200, "capacity_status": "STRESSED"},
]

_CURATED_SHELTERS = [
    {"id": "S-AS-1", "name": "Pragjyotish College Relief Camp", "zone": "AS-Kamrup Metropolitan", "state": "Assam", "lat": 26.1550, "lon": 91.7780, "capacity": 5000},
    {"id": "S-BR-1", "name": "Patna Collegiate Shelter", "zone": "BR-Patna", "state": "Bihar", "lat": 25.6030, "lon": 85.1390, "capacity": 8000},
    {"id": "S-GJ-1", "name": "SVNIT Surat Shelter", "zone": "GJ-Surat", "state": "Gujarat", "lat": 21.1650, "lon": 72.7900, "capacity": 4000},
    {"id": "S-OD-1", "name": "Ravenshaw College Cuttack Shelter", "zone": "OD-Cuttack", "state": "Odisha", "lat": 20.4700, "lon": 85.8900, "capacity": 6000},
    {"id": "S-KL-1", "name": "Aluva Municipal Shelter", "zone": "KL-Ernakulam", "state": "Kerala", "lat": 10.1078, "lon": 76.3516, "capacity": 2500},
    {"id": "S-WB-1", "name": "Bagdogra Relief Shelter", "zone": "WB-Kolkata", "state": "West Bengal", "lat": 22.5800, "lon": 88.3700, "capacity": 5000},
]


def _enrich_from_zone(rec):
    """Attach the human district name + flood-proneness from the zone registry."""
    z = ZONE_INDEX.get(rec.get("zone")) or {}
    rec.setdefault("district", z.get("district") or rec.get("name"))
    rec.setdefault("flood_prone", bool(z.get("flood_prone")))
    return rec


def _find_district(state, district):
    for d in DISTRICTS:
        if d["state"] == state and d["district"] == district:
            return d
    for d in DISTRICTS:
        if d["district"] == district:
            return d
    return None


def _build_infrastructure():
    from collections import Counter

    per_state = Counter(d["state"] for d in DISTRICTS)
    hospitals = [_enrich_from_zone(dict(h)) for h in _CURATED_HOSPITALS]
    shelters = [_enrich_from_zone(dict(s)) for s in _CURATED_SHELTERS]
    bases = []

    # One relief shelter + one district hospital per district (HQ precise).
    for d in DISTRICTS:
        pop = max(int(_STATE_POPULATION.get(d["state"], 1_000_000) / max(per_state[d["state"]], 1)), 10_000)
        hq = d["hq"] or d["district"]
        shelters.append({
            "id": f"S-{d['id']}",
            "name": f"{hq} Relief Shelter",
            "zone": d["id"],
            "state": d["state"],
            "district": d["district"],
            "lat": d["lat"],
            "lon": d["lon"],
            "capacity": min(max(int(pop * 0.06 / 100) * 100, 400), 150_000),
            "flood_prone": bool(d["flood_prone"]),
        })
        hospitals.append({
            "id": f"H-{d['id']}",
            "name": f"District Hospital, {hq}",
            "zone": d["id"],
            "state": d["state"],
            "district": d["district"],
            "lat": d["lat"],
            "lon": d["lon"],
            "beds": min(max(int(pop * 0.00055 / 10) * 10, 50), 3000),
            "capacity_status": "OPERATIONAL",
            "flood_prone": bool(d["flood_prone"]),
        })

    # All 16 NDRF battalions.
    for num, city, force, zone_id in _NDRF_BATTALIONS:
        z = ZONE_INDEX[zone_id]
        bases.append({
            "id": f"R-NDRF-{num:02d}",
            "name": f"NDRF {num:02d} {city} Battalion",
            "zone": zone_id,
            "state": z["state"],
            "district": z["district"],
            "lat": z["centroid"][1],
            "lon": z["centroid"][0],
            "boats": 40,
            "personnel": 1149,
            "agency": f"NDRF (raised from {force})",
        })

    # One SDRF unit per state, headquartered at the state capital.
    for state, cap_district in _STATE_SDRF_HQ.items():
        cap = _find_district(state, cap_district)
        if not cap:
            continue
        pop = _STATE_POPULATION.get(state, 1_000_000)
        bases.append({
            "id": f"R-SDRF-{STATE_CODES.get(state, 'IN')}",
            "name": f"SDRF {state}",
            "zone": cap["id"],
            "state": state,
            "district": cap["district"],
            "lat": cap["lat"],
            "lon": cap["lon"],
            "boats": min(max(int(8 + pop / 20_000_000), 8), 40),
            "personnel": min(max(int(150 + pop / 500_000), 170), 800),
            "agency": "SDRF",
        })

    # Major-city fire & rescue services.
    for name, zone_id in _FIRE_STATIONS:
        z = ZONE_INDEX[zone_id]
        major = zone_id in {"DL-New Delhi", "MH-Mumbai City", "WB-Kolkata", "TN-Chennai"}
        bases.append({
            "id": f"R-FIRE-{zone_id}",
            "name": name,
            "zone": zone_id,
            "state": z["state"],
            "district": z["district"],
            "lat": z["centroid"][1],
            "lon": z["centroid"][0],
            "boats": 12 if major else 8,
            "personnel": 600 if major else 350,
            "agency": "Fire & Rescue Services",
        })

    bases.sort(key=lambda b: (b["agency"], b["name"]))
    return {"hospitals": hospitals, "rescue_bases": bases, "shelters": shelters}


INFRASTRUCTURE = _build_infrastructure()

# Road corridors historically cut off during floods (NH/State highways).
VULNERABLE_ROADS = [
    {"id": "RD-NH27-AS", "name": "NH-27 Guwahati Bypass", "state": "Assam", "zone": "AS-Kamrup Metropolitan", "lat": 26.1500, "lon": 91.7800, "risk_class": "HIGH"},
    {"id": "RD-NH31-BR", "name": "NH-31 Patna–Barauni", "state": "Bihar", "zone": "BR-Patna", "lat": 25.5500, "lon": 85.2500, "risk_class": "HIGH"},
    {"id": "RD-NH16-AP", "name": "NH-16 Vijayawada–Eluru", "state": "Andhra Pradesh", "zone": "AP-NTR", "lat": 16.5400, "lon": 80.9900, "risk_class": "MEDIUM"},
    {"id": "RD-NH48-KA", "name": "NH-48 Bengaluru–Mysuru", "state": "Karnataka", "zone": "KA-Mandya", "lat": 12.6000, "lon": 76.9000, "risk_class": "MEDIUM"},
    {"id": "RD-NH544-KL", "name": "NH-544 Aluva Underpass", "state": "Kerala", "zone": "KL-Ernakulam", "lat": 10.1078, "lon": 76.3516, "risk_class": "HIGH"},
    {"id": "RD-NH6-OD", "name": "NH-16 Cuttack–Bhubaneswar", "state": "Odisha", "zone": "OD-Cuttack", "lat": 20.4600, "lon": 85.8800, "risk_class": "HIGH"},
    {"id": "RD-NH44-DL", "name": "Ring Road Yamuna Bypass", "state": "Delhi", "zone": "DL-Central Delhi", "lat": 28.6550, "lon": 77.2500, "risk_class": "MEDIUM"},
]


def get_zones_by_state(state: str):
    return [z for z in ZONES if z["state"] == state]


def get_zones_by_basin(basin: str):
    return [z for z in ZONES if z["basin"] == basin]


def get_stations_by_basin(basin: str):
    return [tuple(s) for s in RIVER_STATIONS if s[3] == basin]


def get_districts_by_state(state: str):
    return [d for d in DISTRICTS if d["state"] == state]


def zone_centroid(zone_id: str):
    z = ZONE_INDEX.get(zone_id)
    return z["centroid"] if z else None


def stations_near(lat: float, lon: float, radius_km: float = 50.0):
    def haversine(a_lat, a_lon, b_lat, b_lon):
        R = 6371.0
        p1, p2 = math.radians(a_lat), math.radians(b_lat)
        dp = math.radians(b_lat - a_lat)
        dl = math.radians(b_lon - a_lon)
        h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * R * math.asin(math.sqrt(h))

    return [s for s in RIVER_STATIONS if haversine(lat, lon, s[5], s[6]) <= radius_km]