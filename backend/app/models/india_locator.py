"""India-wide location registry for citizen area-checks.

Coverage now spans *every* district in the country by combining:
  * DISTRICTS          → every district headquarters (precise to ~1-5 km)
  * RIVER_STATIONS     → precise gauge points on all monitored rivers
  * EXTRA_TOWNS        → additional flood-prone towns/municipalities

`LOCATOR_POINTS` is a flat, homogeneous key-value table built once at import;
`locate()` returns the nearest points with distances so the API can blend the
scores of the K nearest zones into one continuous estimate for *any* place in
India, with an honest confidence based on how far the location is from a
monitored district/town/station.
"""
import math
from typing import Any, Dict, List, Optional, Tuple

from .india_data import ZONES, RIVER_STATIONS, _basin_for
from .district_registry import DISTRICTS

# ---------------------------------------------------------------------------
# Additional monitored places — flood-prone towns/municipalities across all
# states, with approximate real coordinates (decimal degrees, WGS84).
# ---------------------------------------------------------------------------
EXTRA_TOWNS: List[Dict[str, Any]] = [
    {"name": "Srinagar", "state": "Jammu and Kashmir", "district": "Srinagar", "basin": "JHELUM", "lat": 34.0837, "lon": 74.7973},
    {"name": "Anantnag", "state": "Jammu and Kashmir", "district": "Anantnag", "basin": "JHELUM", "lat": 33.7311, "lon": 75.1494},
    {"name": "Jammu", "state": "Jammu and Kashmir", "district": "Jammu", "basin": "CHENAB", "lat": 32.7266, "lon": 74.8570},
    {"name": "Shimla", "state": "Himachal Pradesh", "district": "Shimla", "basin": "SATLUJ", "lat": 31.1048, "lon": 77.1734},
    {"name": "Mandi", "state": "Himachal Pradesh", "district": "Mandi", "basin": "BEAS", "lat": 31.7089, "lon": 76.9322},
    {"name": "Rohtak", "state": "Haryana", "district": "Rohtak", "basin": "GHAGGAR", "lat": 28.8955, "lon": 76.6066},
    {"name": "Hisar", "state": "Haryana", "district": "Hisar", "basin": "GHAGGAR", "lat": 29.1492, "lon": 75.7217},
    {"name": "Chandigarh", "state": "Punjab", "district": "Chandigarh", "basin": "GHAGGAR", "lat": 30.7333, "lon": 76.7794},
    {"name": "Ludhiana", "state": "Punjab", "district": "Ludhiana", "basin": "SATLUJ", "lat": 30.9010, "lon": 75.8573},
    {"name": "Amritsar", "state": "Punjab", "district": "Amritsar", "basin": "Ravi", "lat": 31.6340, "lon": 74.8723},
    {"name": "Jalandhar", "state": "Punjab", "district": "Jalandhar", "basin": "BEAS", "lat": 31.3260, "lon": 75.5762},
    {"name": "Dehradun", "state": "Uttarakhand", "district": "Dehradun", "basin": "Ganga", "lat": 30.3165, "lon": 78.0322},
    {"name": "Haridwar", "state": "Uttarakhand", "district": "Haridwar", "basin": "Ganga", "lat": 29.9457, "lon": 78.1642},
    {"name": "Rishikesh", "state": "Uttarakhand", "district": "Dehradun", "basin": "Ganga", "lat": 30.0869, "lon": 78.2676},
    {"name": "Nainital", "state": "Uttarakhand", "district": "Nainital", "basin": "KOSI", "lat": 29.3803, "lon": 79.4636},
    {"name": "Agra", "state": "Uttar Pradesh", "district": "Agra", "basin": "Ganga", "lat": 27.1767, "lon": 78.0081},
    {"name": "Kanpur", "state": "Uttar Pradesh", "district": "Kanpur", "basin": "Ganga", "lat": 26.4499, "lon": 80.3319},
    {"name": "Lucknow", "state": "Uttar Pradesh", "district": "Lucknow", "basin": "GOMTI", "lat": 26.8467, "lon": 80.9462},
    {"name": "Bareilly", "state": "Uttar Pradesh", "district": "Bareilly", "basin": "Ganga", "lat": 28.3670, "lon": 79.4304},
    {"name": "Gorakhpur", "state": "Uttar Pradesh", "district": "Gorakhpur", "basin": "GHAGHRA", "lat": 26.7606, "lon": 83.3732},
    {"name": "Varanasi", "state": "Uttar Pradesh", "district": "Varanasi", "basin": "Ganga", "lat": 25.3176, "lon": 82.9739},
    {"name": "Allahabad", "state": "Uttar Pradesh", "district": "Prayagraj", "basin": "Ganga", "lat": 25.4358, "lon": 81.8463},
    {"name": "Mathura", "state": "Uttar Pradesh", "district": "Mathura", "basin": "YAMUNA", "lat": 27.4924, "lon": 77.6737},
    {"name": "Mirzapur", "state": "Uttar Pradesh", "district": "Mirzapur", "basin": "Ganga", "lat": 25.1480, "lon": 82.5650},
    {"name": "Ayodhya", "state": "Uttar Pradesh", "district": "Ayodhya", "basin": "GHAGHRA", "lat": 26.7921, "lon": 82.1996},
    {"name": "Jaunpur", "state": "Uttar Pradesh", "district": "Jaunpur", "basin": "GOMTI", "lat": 25.7535, "lon": 82.6868},
    {"name": "Saharanpur", "state": "Uttar Pradesh", "district": "Saharanpur", "basin": "YAMUNA", "lat": 29.9640, "lon": 77.5460},
    {"name": "Moradabad", "state": "Uttar Pradesh", "district": "Moradabad", "basin": "RAMGANGA", "lat": 28.8386, "lon": 78.7733},
    {"name": "Rae Bareli", "state": "Uttar Pradesh", "district": "Rae Bareli", "basin": "SAI", "lat": 26.2309, "lon": 81.2420},
    {"name": "Noida", "state": "Uttar Pradesh", "district": "Gautam Budh Nagar", "basin": "YAMUNA", "lat": 28.5355, "lon": 77.3910},
    {"name": "Gwalior", "state": "Madhya Pradesh", "district": "Gwalior", "basin": "SINDH", "lat": 26.2183, "lon": 78.1828},
    {"name": "Jabalpur", "state": "Madhya Pradesh", "district": "Jabalpur", "basin": "NARMADA", "lat": 23.1815, "lon": 79.9864},
    {"name": "Rewa", "state": "Madhya Pradesh", "district": "Rewa", "basin": "SON", "lat": 24.5329, "lon": 81.2962},
    {"name": "Ujjain", "state": "Madhya Pradesh", "district": "Ujjain", "basin": "SHIPRA", "lat": 23.1765, "lon": 75.7885},
    {"name": "Khandwa", "state": "Madhya Pradesh", "district": "Khandwa", "basin": "NARMADA", "lat": 21.8260, "lon": 76.3510},
    {"name": "Bhimbetka", "state": "Madhya Pradesh", "district": "Raisen", "basin": "BETWA", "lat": 22.9400, "lon": 77.6110},
    {"name": "Bhopal", "state": "Madhya Pradesh", "district": "Bhopal", "basin": "BETWA", "lat": 23.2599, "lon": 77.4126},
    {"name": "Chhatarpur", "state": "Madhya Pradesh", "district": "Chhatarpur", "basin": "KANE", "lat": 24.9170, "lon": 79.5660},
    {"name": "Khajuraho", "state": "Madhya Pradesh", "district": "Chhatarpur", "basin": "KANE", "lat": 24.8318, "lon": 79.9199},
    {"name": "Ajmer", "state": "Rajasthan", "district": "Ajmer", "basin": "LUNI", "lat": 26.4499, "lon": 74.6399},
    {"name": "Jodhpur", "state": "Rajasthan", "district": "Jodhpur", "basin": "LUNI", "lat": 26.2389, "lon": 73.0243},
    {"name": "Udaipur", "state": "Rajasthan", "district": "Udaipur", "basin": "BANAS", "lat": 24.5854, "lon": 73.7125},
    {"name": "Kota", "state": "Rajasthan", "district": "Kota", "basin": "CHAMBAL", "lat": 25.2138, "lon": 75.8648},
    {"name": "Bikaner", "state": "Rajasthan", "district": "Bikaner", "basin": "GHAGGAR", "lat": 28.0229, "lon": 73.3119},
    {"name": "Jaipur", "state": "Rajasthan", "district": "Jaipur", "basin": "BANAS", "lat": 26.9124, "lon": 75.7873},
    {"name": "Kota City", "state": "Rajasthan", "district": "Kota", "basin": "CHAMBAL", "lat": 25.2020, "lon": 75.8470},
    {"name": "Pali", "state": "Rajasthan", "district": "Pali", "basin": "LUNI", "lat": 25.7725, "lon": 73.3233},
    {"name": "Ahmedabad", "state": "Gujarat", "district": "Ahmedabad", "basin": "SABARMATI", "lat": 23.0225, "lon": 72.5714},
    {"name": "Surat", "state": "Gujarat", "district": "Surat", "basin": "TAPI", "lat": 21.1702, "lon": 72.8311},
    {"name": "Vadodara", "state": "Gujarat", "district": "Vadodara", "basin": "VISHWAMITRI", "lat": 22.3072, "lon": 73.1812},
    {"name": "Rajkot", "state": "Gujarat", "district": "Rajkot", "basin": "AAJI", "lat": 22.3039, "lon": 70.8022},
    {"name": "Jamnagar", "state": "Gujarat", "district": "Jamnagar", "basin": "RAN OF KACHCHH", "lat": 22.4707, "lon": 70.0577},
    {"name": "Bhavnagar", "state": "Gujarat", "district": "Bhavnagar", "basin": "SHETRUNJI", "lat": 21.7645, "lon": 72.1519},
    {"name": "Gandhinagar", "state": "Gujarat", "district": "Gandhinagar", "basin": "SABARMATI", "lat": 23.2156, "lon": 72.6369},
    {"name": "Mumbai", "state": "Maharashtra", "district": "Mumbai", "basin": "ULHAS", "lat": 19.0760, "lon": 72.8777},
    {"name": "Pune", "state": "Maharashtra", "district": "Pune", "basin": "MULA-MUTHA", "lat": 18.5204, "lon": 73.8567},
    {"name": "Nagpur", "state": "Maharashtra", "district": "Nagpur", "basin": "KANHAN", "lat": 21.1458, "lon": 79.0882},
    {"name": "Nashik", "state": "Maharashtra", "district": "Nashik", "basin": "GODAVARI", "lat": 19.9975, "lon": 73.7898},
    {"name": "Aurangabad", "state": "Maharashtra", "district": "Aurangabad", "basin": "GODAVARI", "lat": 19.8762, "lon": 75.3433},
    {"name": "Kolhapur", "state": "Maharashtra", "district": "Kolhapur", "basin": "PANCHGANGA", "lat": 16.7050, "lon": 74.2433},
    {"name": "Sangli", "state": "Maharashtra", "district": "Sangli", "basin": "KRISHNA", "lat": 16.8524, "lon": 74.5815},
    {"name": "Satara", "state": "Maharashtra", "district": "Satara", "basin": "KRISHNA", "lat": 17.6805, "lon": 74.0183},
    {"name": "Jalgaon", "state": "Maharashtra", "district": "Jalgaon", "basin": "TAPI", "lat": 21.0078, "lon": 75.5626},
    {"name": "Ratnagiri", "state": "Maharashtra", "district": "Ratnagiri", "basin": "KALINADI", "lat": 16.9960, "lon": 73.2950},
    {"name": "Chennai", "state": "Tamil Nadu", "district": "Chennai", "basin": "COUVEM", "lat": 13.0827, "lon": 80.2707},
    {"name": "Coimbatore", "state": "Tamil Nadu", "district": "Coimbatore", "basin": "BHARATHAPPUZHA", "lat": 11.0168, "lon": 76.9558},
    {"name": "Madurai", "state": "Tamil Nadu", "district": "Madurai", "basin": "VAIGAI", "lat": 9.9252, "lon": 78.1198},
    {"name": "Tiruchirappalli", "state": "Tamil Nadu", "district": "Tiruchirappalli", "basin": "CAUVERY", "lat": 10.7905, "lon": 78.7047},
    {"name": "Tanjore", "state": "Tamil Nadu", "district": "Thanjavur", "basin": "CAUVERY", "lat": 10.7870, "lon": 79.1390},
    {"name": "Vellore", "state": "Tamil Nadu", "district": "Vellore", "basin": "PALAR", "lat": 12.9165, "lon": 79.1325},
    {"name": "Salem", "state": "Tamil Nadu", "district": "Salem", "basin": "CAUVERY", "lat": 11.6643, "lon": 78.1460},
    {"name": "Erode", "state": "Tamil Nadu", "district": "Erode", "basin": "CAUVERY", "lat": 11.3410, "lon": 77.7172},
    {"name": "Bengaluru", "state": "Karnataka", "district": "Bengaluru", "basin": "ARAKAVATI", "lat": 12.9716, "lon": 77.5946},
    {"name": "Mysuru", "state": "Karnataka", "district": "Mysuru", "basin": "CAUVERY", "lat": 12.2958, "lon": 76.6394},
    {"name": "Belagavi", "state": "Karnataka", "district": "Belagavi", "basin": "GHATAPRABHA", "lat": 15.8497, "lon": 74.4977},
    {"name": "Hubballi", "state": "Karnataka", "district": "Dharwad", "basin": "WEST FLOWING", "lat": 15.3647, "lon": 75.1240},
    {"name": "Mangaluru", "state": "Karnataka", "district": "Dakshina Kannada", "basin": "NETRAVATI", "lat": 12.9141, "lon": 74.8560},
    {"name": "Thiruvananthapuram", "state": "Kerala", "district": "Thiruvananthapuram", "basin": "KARAMANA", "lat": 8.5241, "lon": 76.9366},
    {"name": "Kochi", "state": "Kerala", "district": "Ernakulam", "basin": "PERIYAR", "lat": 9.9312, "lon": 76.2673},
    {"name": "Kozhikode", "state": "Kerala", "district": "Kozhikode", "basin": "CHALIYAR", "lat": 11.2588, "lon": 75.7804},
    {"name": "Kottayam", "state": "Kerala", "district": "Kottayam", "basin": "MEENACHIL", "lat": 9.5916, "lon": 76.5211},
    {"name": "Alappuzha", "state": "Kerala", "district": "Alappuzha", "basin": "PAMBA", "lat": 9.4931, "lon": 76.3315},
    {"name": "Thrissur", "state": "Kerala", "district": "Thrissur", "basin": "PEYO", "lat": 10.5276, "lon": 76.2144},
    {"name": "Hyderabad", "state": "Telangana", "district": "Hyderabad", "basin": "MUSI", "lat": 17.3850, "lon": 78.4867},
    {"name": "Warangal", "state": "Telangana", "district": "Warangal", "basin": "GODAVARI", "lat": 17.9689, "lon": 79.5941},
    {"name": "Nizamabad", "state": "Telangana", "district": "Nizamabad", "basin": "GODAVARI", "lat": 18.6725, "lon": 78.0940},
    {"name": "Visakhapatnam", "state": "Andhra Pradesh", "district": "Visakhapatnam", "basin": "EAST FLOWING", "lat": 17.6868, "lon": 83.2185},
    {"name": "Vijayawada", "state": "Andhra Pradesh", "district": "Krishna", "basin": "KRISHNA", "lat": 16.5062, "lon": 80.6480},
    {"name": "Guntur", "state": "Andhra Pradesh", "district": "Guntur", "basin": "KRISHNA", "lat": 16.3067, "lon": 80.4365},
    {"name": "Nellore", "state": "Andhra Pradesh", "district": "Nellore", "basin": "PENNAR", "lat": 14.4426, "lon": 79.9865},
    {"name": "Kurnool", "state": "Andhra Pradesh", "district": "Kurnool", "basin": "TUNGABHADRA", "lat": 15.8281, "lon": 78.0373},
    {"name": "Tirupati", "state": "Andhra Pradesh", "district": "Chittoor", "basin": "SWARNAMUKHI", "lat": 13.6288, "lon": 79.4192},
    {"name": "Bhubaneswar", "state": "Odisha", "district": "Khordha", "basin": "MAHANADI", "lat": 20.2961, "lon": 85.8245},
    {"name": "Puri", "state": "Odisha", "district": "Puri", "basin": "DAYA", "lat": 19.8135, "lon": 85.8312},
    {"name": "Sambalpur", "state": "Odisha", "district": "Sambalpur", "basin": "MAHANADI", "lat": 21.4690, "lon": 83.9798},
    {"name": "Balasore", "state": "Odisha", "district": "Balasore", "basin": "BURHABALANG", "lat": 21.4936, "lon": 86.9321},
    {"name": "Berhampur", "state": "Odisha", "district": "Ganjam", "basin": "RUSHIKULYA", "lat": 19.3136, "lon": 84.7906},
    {"name": "Jharsuguda", "state": "Odisha", "district": "Jharsuguda", "basin": "IB", "lat": 21.8564, "lon": 84.0061},
    {"name": "Jamshedpur", "state": "Jharkhand", "district": "East Singhbhum", "basin": "SUBARNAREKHA", "lat": 22.8046, "lon": 86.2029},
    {"name": "Ranchi", "state": "Jharkhand", "district": "Ranchi", "basin": "SUBARNAREKHA", "lat": 23.3441, "lon": 85.3096},
    {"name": "Dhanbad", "state": "Jharkhand", "district": "Dhanbad", "basin": "DAMODAR", "lat": 23.7957, "lon": 86.4304},
    {"name": "Bokaro", "state": "Jharkhand", "district": "Bokaro", "basin": "DAMODAR", "lat": 23.6693, "lon": 86.1511},
    {"name": "Durgapur", "state": "West Bengal", "district": "Paschim Bardhaman", "basin": "DAMODAR", "lat": 23.5204, "lon": 87.3119},
    {"name": "Siliguri", "state": "West Bengal", "district": "Darjeeling", "basin": "MAHANANDA", "lat": 26.7271, "lon": 88.3953},
    {"name": "Kolkata", "state": "West Bengal", "district": "Kolkata", "basin": "HOOGHLY", "lat": 22.5726, "lon": 88.3639},
    {"name": "Howrah", "state": "West Bengal", "district": "Howrah", "basin": "HOOGHLY", "lat": 22.5960, "lon": 88.2635},
    {"name": "Asansol", "state": "West Bengal", "district": "Paschim Bardhaman", "basin": "DAMODAR", "lat": 23.6742, "lon": 86.9522},
    {"name": "Malda", "state": "West Bengal", "district": "Malda", "basin": "GANGA", "lat": 25.0108, "lon": 88.1411},
    {"name": "Jalpaiguri", "state": "West Bengal", "district": "Jalpaiguri", "basin": "TEESTA", "lat": 26.5167, "lon": 88.7352},
    {"name": "Dumka", "state": "Jharkhand", "district": "Dumka", "basin": "AJAY", "lat": 24.2675, "lon": 87.2407},
    {"name": "Guwahati", "state": "Assam", "district": "Kamrup Metropolitan", "basin": "BRAHMAPUTRA", "lat": 26.1445, "lon": 91.7362},
    {"name": "Dibrugarh", "state": "Assam", "district": "Dibrugarh", "basin": "BRAHMAPUTRA", "lat": 27.4728, "lon": 94.9120},
    {"name": "Silchar", "state": "Assam", "district": "Cachar", "basin": "BARAK", "lat": 24.8333, "lon": 92.7789},
    {"name": "Jorhat", "state": "Assam", "district": "Jorhat", "basin": "BRAHMAPUTRA", "lat": 26.7509, "lon": 94.2037},
    {"name": "Nalbari", "state": "Assam", "district": "Nalbari", "basin": "BRAHMAPUTRA", "lat": 26.4417, "lon": 91.4404},
    {"name": "BongaiGaon", "state": "Assam", "district": "Bongaigaon", "basin": "BRAHMAPUTRA", "lat": 26.4833, "lon": 90.5583},
    {"name": "Karimganj", "state": "Assam", "district": "Karimganj", "basin": "KUSIARA", "lat": 24.8690, "lon": 92.3610},
    {"name": "Hailakandi", "state": "Assam", "district": "Hailakandi", "basin": "BARAK", "lat": 24.6833, "lon": 92.5333},
    {"name": "Murshidabad", "state": "West Bengal", "district": "Murshidabad", "basin": "GANGA", "lat": 24.1910, "lon": 88.2680},
    {"name": "Purnia", "state": "Bihar", "district": "Purnia", "basin": "KOSI", "lat": 25.7779, "lon": 87.4753},
    {"name": "Araria", "state": "Bihar", "district": "Araria", "basin": "KOSI", "lat": 26.1477, "lon": 87.5147},
    {"name": "Kishanganj", "state": "Bihar", "district": "Kishanganj", "basin": "MAHANANDA", "lat": 26.1077, "lon": 87.9496},
    {"name": "Katihar", "state": "Bihar", "district": "Katihar", "basin": "GANGA", "lat": 25.5361, "lon": 87.5708},
    {"name": "Supaul", "state": "Bihar", "district": "Supaul", "basin": "KOSI", "lat": 26.1158, "lon": 86.6051},
    {"name": "Saharsa", "state": "Bihar", "district": "Saharsa", "basin": "KOSI", "lat": 25.8749, "lon": 86.5956},
    {"name": "Muzaffarpur", "state": "Bihar", "district": "Muzaffarpur", "basin": "BURHI GANDAK", "lat": 26.1209, "lon": 85.3647},
    {"name": "Begusarai", "state": "Bihar", "district": "Begusarai", "basin": "BURHI GANDAK", "lat": 25.4180, "lon": 86.1330},
    {"name": "Siwan", "state": "Bihar", "district": "Siwan", "basin": "GHAGHRA", "lat": 26.2196, "lon": 84.3567},
    {"name": "Gopalganj", "state": "Bihar", "district": "Gopalganj", "basin": "GHAGHRA", "lat": 26.4700, "lon": 84.4270},
    {"name": "Gaya", "state": "Bihar", "district": "Gaya", "basin": "SON", "lat": 24.7914, "lon": 85.0002},
    {"name": "Aurangabad Bihar", "state": "Bihar", "district": "Aurangabad", "basin": "SON", "lat": 24.7545, "lon": 84.3706},
    {"name": "Palamu", "state": "Jharkhand", "district": "Palamu", "basin": "KOEL", "lat": 24.0040, "lon": 84.0900},
    {"name": "Agartala", "state": "Tripura", "district": "West Tripura", "basin": "HAORA", "lat": 23.8315, "lon": 91.2868},
    {"name": "Udaipur Tripura", "state": "Tripura", "district": "Gomati", "basin": "GOMATI", "lat": 23.5455, "lon": 91.4797},
    {"name": "Aizawl", "state": "Mizoram", "district": "Aizawl", "basin": "TLAWNG", "lat": 23.7271, "lon": 92.7176},
    {"name": "Shillong", "state": "Meghalaya", "district": "East Khasi Hills", "basin": "UMSHIANG", "lat": 25.5788, "lon": 91.8933},
    {"name": "Imphal", "state": "Manipur", "district": "Imphal West", "basin": "IMPHAL", "lat": 24.8170, "lon": 93.9368},
    {"name": "Kohima", "state": "Nagaland", "district": "Kohima", "basin": "DZULIA", "lat": 25.6751, "lon": 94.1086},
    {"name": "Itanagar", "state": "Arunachal Pradesh", "district": "Papum Pare", "basin": "SIKKIM", "lat": 27.0844, "lon": 93.6053},
    {"name": "Gangtok", "state": "Sikkim", "district": "East Sikkim", "basin": "TEESTA", "lat": 27.3389, "lon": 88.6065},
    {"name": "Port Blair", "state": "Andaman and Nicobar Islands", "district": "South Andaman", "basin": "COASTAL", "lat": 11.6234, "lon": 92.7265},
    {"name": "Pondicherry", "state": "Puducherry", "district": "Puducherry", "basin": "GINGEE", "lat": 11.9139, "lon": 79.8145},
    {"name": "Panaji", "state": "Goa", "district": "North Goa", "basin": "MANDOVI", "lat": 15.4909, "lon": 73.8278},
    {"name": "Margao", "state": "Goa", "district": "South Goa", "basin": "SAL", "lat": 15.2833, "lon": 73.9884},
    {"name": "Kavaratti", "state": "Lakshadweep", "district": "Lakshadweep", "basin": "COASTAL", "lat": 10.5593, "lon": 72.6358},
    {"name": "Sirsa", "state": "Haryana", "district": "Sirsa", "basin": "GHAGGAR", "lat": 29.5341, "lon": 75.0011},
    {"name": "Fatehabad", "state": "Haryana", "district": "Fatehabad", "basin": "GHAGGAR", "lat": 29.5124, "lon": 75.4552},
    {"name": "Bhiwani", "state": "Haryana", "district": "Bhiwani", "basin": "GHAGGAR", "lat": 28.8018, "lon": 76.1342},
    {"name": "Karauli", "state": "Rajasthan", "district": "Karauli", "basin": "CHAMBAL", "lat": 26.4940, "lon": 77.0270},
    {"name": "Sawai Madhopur", "state": "Rajasthan", "district": "Sawai Madhopur", "basin": "BANAS", "lat": 26.0030, "lon": 76.3510},
    {"name": "Dhar", "state": "Madhya Pradesh", "district": "Dhar", "basin": "NARMADA", "lat": 22.5950, "lon": 75.3100},
    {"name": "Burhanpur", "state": "Madhya Pradesh", "district": "Burhanpur", "basin": "TAPI", "lat": 21.3090, "lon": 76.2300},
    {"name": "Indore", "state": "Madhya Pradesh", "district": "Indore", "basin": "NARMADA", "lat": 22.7196, "lon": 75.8577},
    {"name": "Sagar", "state": "Madhya Pradesh", "district": "Sagar", "basin": "SONAR", "lat": 23.8388, "lon": 78.7378},
    {"name": "Guna", "state": "Madhya Pradesh", "district": "Guna", "basin": "PARVATI", "lat": 24.6500, "lon": 77.3100},
    {"name": "Chhindwara", "state": "Madhya Pradesh", "district": "Chhindwara", "basin": "PENCH", "lat": 22.0600, "lon": 78.9400},
    {"name": "Narsinghpur", "state": "Madhya Pradesh", "district": "Narsinghpur", "basin": "NARMADA", "lat": 22.9100, "lon": 79.1900},
    {"name": "Chhatarpur MP", "state": "Madhya Pradesh", "district": "Chhatarpur", "basin": "KANE", "lat": 24.9170, "lon": 79.5660},
    {"name": "Churu", "state": "Rajasthan", "district": "Churu", "basin": "GHAGGAR", "lat": 28.3060, "lon": 74.9560},
    {"name": "Barmer", "state": "Rajasthan", "district": "Barmer", "basin": "LUNI", "lat": 25.7460, "lon": 71.3790},
    {"name": "Jaisalmer", "state": "Rajasthan", "district": "Jaisalmer", "basin": "LUNI", "lat": 26.9157, "lon": 70.9083},
    {"name": "Bundi", "state": "Rajasthan", "district": "Bundi", "basin": "CHAMBAL", "lat": 25.4400, "lon": 75.6400},
    {"name": "Bharatpur", "state": "Rajasthan", "district": "Bharatpur", "basin": "MOREKHARO", "lat": 27.2173, "lon": 77.4901},
    {"name": "Alwar", "state": "Rajasthan", "district": "Alwar", "basin": "YAMUNA", "lat": 27.5530, "lon": 76.6340},
    {"name": "Jaunpur", "state": "Uttar Pradesh", "district": "Jaunpur", "basin": "GOMTI", "lat": 25.7535, "lon": 82.6868},
    {"name": "Purulia", "state": "West Bengal", "district": "Purulia", "basin": "DAMODAR", "lat": 23.3327, "lon": 86.3650},
    {"name": "Krishnanagar", "state": "West Bengal", "district": "Nadia", "basin": "HOOGHLY", "lat": 23.4020, "lon": 88.5160},
    {"name": "Barasat", "state": "West Bengal", "district": "North 24 Parganas", "basin": "HOOGHLY", "lat": 22.7200, "lon": 88.4820},
    {"name": "Bardhaman", "state": "West Bengal", "district": "Paschim Bardhaman", "basin": "DAMODAR", "lat": 23.2400, "lon": 87.8610},
    {"name": "Chandannagar", "state": "West Bengal", "district": "Hooghly", "basin": "HOOGHLY", "lat": 22.8570, "lon": 88.3790},
    {"name": "Baharampur", "state": "West Bengal", "district": "Murshidabad", "basin": "BHAGIRATHI", "lat": 24.1000, "lon": 88.2540},
    {"name": "Katwa", "state": "West Bengal", "district": "Purba Bardhaman", "basin": "BHAGIRATHI", "lat": 23.6410, "lon": 88.1290},
    {"name": "Nabadwip", "state": "West Bengal", "district": "Nadia", "basin": "BHAGIRATHI", "lat": 23.4030, "lon": 88.3750},
    {"name": "Berhampore", "state": "West Bengal", "district": "Murshidabad", "basin": "BHAGIRATHI", "lat": 24.2040, "lon": 88.5990},
    {"name": "Dhupguri", "state": "West Bengal", "district": "Jalpaiguri", "basin": "TEESTA", "lat": 26.5890, "lon": 88.9970},
    {"name": "Cooch Behar", "state": "West Bengal", "district": "Cooch Behar", "basin": "TEESTA", "lat": 26.3240, "lon": 89.4500},
    {"name": "Falakata", "state": "West Bengal", "district": "Alipurduar", "basin": "TORSHA", "lat": 26.5260, "lon": 89.1960},
    {"name": "Alipurduar", "state": "West Bengal", "district": "Alipurduar", "basin": "TORSHA", "lat": 26.4860, "lon": 89.5270},
    {"name": "Raiganj", "state": "West Bengal", "district": "Uttar Dinajpur", "basin": "TANGAON", "lat": 25.6160, "lon": 88.1300},
    {"name": "Islampur", "state": "West Bengal", "district": "Uttar Dinajpur", "basin": "PURNIA WEST", "lat": 26.2640, "lon": 88.1890},
    {"name": "Balughat", "state": "West Bengal", "district": "Malda", "basin": "GANGA", "lat": 25.2220, "lon": 88.1440},
    {"name": "English Bazar", "state": "West Bengal", "district": "Malda", "basin": "GANGA", "lat": 25.0100, "lon": 88.1410},
    {"name": "Gazole", "state": "West Bengal", "district": "Malda", "basin": "GANGA", "lat": 25.2200, "lon": 87.9100},
    {"name": "Pakur", "state": "Jharkhand", "district": "Pakur", "basin": "GANGA", "lat": 24.6400, "lon": 87.8400},
    {"name": "Sahebganj", "state": "Jharkhand", "district": "Sahebganj", "basin": "GANGA", "lat": 25.2500, "lon": 87.6200},
    {"name": "Godda", "state": "Jharkhand", "district": "Godda", "basin": "GANGA", "lat": 24.8300, "lon": 87.1500},
    {"name": "Barsoi", "state": "Bihar", "district": "Katihar", "basin": "GANGA", "lat": 25.4600, "lon": 87.9800},
    {"name": "Bansi", "state": "Bihar", "district": "Siwan", "basin": "GHAGHRA", "lat": 26.3600, "lon": 84.4000},
    {"name": "Nabinagar", "state": "Bihar", "district": "Aurangabad", "basin": "SON", "lat": 24.6100, "lon": 84.1200},
    {"name": "Sherpur", "state": "Bihar", "district": "Munger", "basin": "BAGMATI", "lat": 25.6800, "lon": 86.2900},
    {"name": "Munger", "state": "Bihar", "district": "Munger", "basin": "GANGA", "lat": 25.3808, "lon": 86.4648},
    {"name": "Jamalpur", "state": "Bihar", "district": "Munger", "basin": "GANGA", "lat": 25.3108, "lon": 86.4913},
    {"name": "Bhagalpur", "state": "Bihar", "district": "Bhagalpur", "basin": "GANGA", "lat": 25.2425, "lon": 86.9842},
    {"name": "Patna", "state": "Bihar", "district": "Patna", "basin": "GANGA", "lat": 25.5941, "lon": 85.1376},
    {"name": "Arrah", "state": "Bihar", "district": "Bhojpur", "basin": "SON", "lat": 25.5560, "lon": 84.6640},
    {"name": "Buxar", "state": "Bihar", "district": "Buxar", "basin": "GANGA", "lat": 25.5750, "lon": 83.9780},
    {"name": "Chhapra", "state": "Bihar", "district": "Saran", "basin": "GHAGHRA", "lat": 25.7790, "lon": 84.7310},
    {"name": "Motihari", "state": "Bihar", "district": "East Champaran", "basin": "BAGMATI", "lat": 26.6570, "lon": 84.9190},
    {"name": "Sitamarhi", "state": "Bihar", "district": "Sitamarhi", "basin": "BAGMATI", "lat": 26.5920, "lon": 85.4810},
    {"name": "Darbhanga", "state": "Bihar", "district": "Darbhanga", "basin": "KOSI", "lat": 26.1542, "lon": 85.8918},
    {"name": "Madhubani", "state": "Bihar", "district": "Madhubani", "basin": "KAMALA", "lat": 26.3530, "lon": 86.0710},
    {"name": "Samastipur", "state": "Bihar", "district": "Samastipur", "basin": "BURHI GANDAK", "lat": 25.8560, "lon": 85.7820},
    {"name": "Bettiah", "state": "Bihar", "district": "West Champaran", "basin": "GANDAK", "lat": 26.8040, "lon": 84.4980},
    {"name": "Raxaul", "state": "Bihar", "district": "East Champaran", "basin": "GANDAK", "lat": 26.9780, "lon": 84.8350},
    {"name": "Forbesganj", "state": "Bihar", "district": "Araria", "basin": "KOSI", "lat": 26.2940, "lon": 87.2430},
    {"name": "Tezpur", "state": "Assam", "district": "Sonitpur", "basin": "BRAHMAPUTRA", "lat": 26.6334, "lon": 92.7920},
    {"name": "Majuli", "state": "Assam", "district": "Majuli", "basin": "BRAHMAPUTRA", "lat": 26.9500, "lon": 94.1660},
    {"name": "Barpeta", "state": "Assam", "district": "Barpeta", "basin": "BRAHMAPUTRA", "lat": 26.3230, "lon": 91.0100},
    {"name": "Duliajan", "state": "Assam", "district": "Dibrugarh", "basin": "BRAHMAPUTRA", "lat": 27.3680, "lon": 95.3000},
    {"name": "Tinsukia", "state": "Assam", "district": "Tinsukia", "basin": "DIGBOI", "lat": 27.4890, "lon": 95.3540},
    {"name": "Margherita", "state": "Assam", "district": "Tinsukia", "basin": "BURHI DOLING", "lat": 27.2840, "lon": 95.6760},
    {"name": "Sivasagar", "state": "Assam", "district": "Sivasagar", "basin": "BRAHMAPUTRA", "lat": 26.9850, "lon": 94.6280},
    {"name": "Morigaon", "state": "Assam", "district": "Morigaon", "basin": "KOLONG", "lat": 26.2520, "lon": 92.3320},
    {"name": "Goalpara", "state": "Assam", "district": "Goalpara", "basin": "BRAHMAPUTRA", "lat": 26.1760, "lon": 90.6260},
    {"name": "Dhubri", "state": "Assam", "district": "Dhubri", "basin": "BRAHMAPUTRA", "lat": 26.0240, "lon": 89.9730},
    {"name": "Kokrajhar", "state": "Assam", "district": "Kokrajhar", "basin": "BRAHMAPUTRA", "lat": 26.4010, "lon": 90.2740},
    {"name": "Bilashipara", "state": "Assam", "district": "Dhubri", "basin": "BRAHMAPUTRA", "lat": 26.3090, "lon": 89.9900},
    {"name": "Kalimpong", "state": "West Bengal", "district": "Kalimpong", "basin": "TEESTA", "lat": 27.0600, "lon": 88.4750},
    {"name": "Balurghat", "state": "West Bengal", "district": "Dakshin Dinajpur", "basin": "ATRAYEE", "lat": 25.2230, "lon": 88.7710},
    {"name": "Jangipur", "state": "West Bengal", "district": "Murshidabad", "basin": "BHAGIRATHI", "lat": 24.4680, "lon": 88.0730},
    {"name": "Regent Square", "state": "West Bengal", "district": "Kolkata", "basin": "HOOGHLY", "lat": 22.5480, "lon": 88.3720},
    {"name": "Barrackpore", "state": "West Bengal", "district": "North 24 Parganas", "basin": "HOOGHLY", "lat": 22.7660, "lon": 88.3620},
    {"name": "Bally", "state": "West Bengal", "district": "Howrah", "basin": "HOOGHLY", "lat": 22.6490, "lon": 88.3380},
    {"name": "Basirhat", "state": "West Bengal", "district": "North 24 Parganas", "basin": "HOOGHLY", "lat": 22.6540, "lon": 88.8730},
    {"name": "Canning", "state": "West Bengal", "district": "South 24 Parganas", "basin": "MOTIARI", "lat": 22.3140, "lon": 88.6690},
    {"name": "Baruipur", "state": "West Bengal", "district": "South 24 Parganas", "basin": "HOOGHLY", "lat": 22.3590, "lon": 88.4400},
    {"name": "Gopalpur", "state": "Odisha", "district": "Ganjam", "basin": "RUSHIKULYA", "lat": 19.2560, "lon": 84.8950},
    {"name": "Chandbali", "state": "Odisha", "district": "Bhadrak", "basin": "BHADRAK", "lat": 20.7780, "lon": 86.7430},
    {"name": "Dhamra", "state": "Odisha", "district": "Bhadrak", "basin": "BANSADHARA", "lat": 20.8050, "lon": 86.9630},
    {"name": "Paradeep", "state": "Odisha", "district": "Jagatsinghpur", "basin": "MAHANADI", "lat": 20.2880, "lon": 86.6620},
    {"name": "Patamundai", "state": "Odisha", "district": "Kendrapara", "basin": "KARANDIA", "lat": 20.5450, "lon": 86.5460},
    {"name": "Annavaram", "state": "Andhra Pradesh", "district": "East Godavari", "basin": "GODAVARI", "lat": 17.2880, "lon": 82.3710},
    {"name": "Rajahmundry", "state": "Andhra Pradesh", "district": "East Godavari", "basin": "GODAVARI", "lat": 17.0005, "lon": 81.8040},
    {"name": "Kakinada", "state": "Andhra Pradesh", "district": "East Godavari", "basin": "GODAVARI", "lat": 16.9891, "lon": 82.2475},
    {"name": "Bhavanipeta", "state": "Andhra Pradesh", "district": "Srikakulam", "basin": "NAGAVALI", "lat": 18.2830, "lon": 83.8640},
    {"name": "Kandukur", "state": "Andhra Pradesh", "district": "Prakasam", "basin": "MUSI", "lat": 15.2150, "lon": 79.9010},
    {"name": "Ongole", "state": "Andhra Pradesh", "district": "Prakasam", "basin": "GUNDLAKAMMA", "lat": 15.5057, "lon": 80.0500},
    {"name": "Machilipatnam", "state": "Andhra Pradesh", "district": "Krishna", "basin": "KRISHNA", "lat": 16.1870, "lon": 81.1400},
    {"name": "Tenali", "state": "Andhra Pradesh", "district": "Guntur", "basin": "KRISHNA", "lat": 16.2440, "lon": 80.6470},
    {"name": "Kovvur", "state": "Andhra Pradesh", "district": "West Godavari", "basin": "GODAVARI", "lat": 16.9870, "lon": 81.7450},
    {"name": "Tuni", "state": "Andhra Pradesh", "district": "East Godavari", "basin": "VAKAPNADAM", "lat": 17.3500, "lon": 82.5600},
    {"name": "Bhimavaram", "state": "Andhra Pradesh", "district": "West Godavari", "basin": "GODAVARI", "lat": 16.5510, "lon": 81.5190},
    {"name": "Narasaraopet", "state": "Andhra Pradesh", "district": "Guntur", "basin": "KRISHNA", "lat": 16.2300, "lon": 80.0460},
    {"name": "Karimnagar", "state": "Telangana", "district": "Karimnagar", "basin": "GODAVARI", "lat": 18.4386, "lon": 79.1328},
    {"name": "Sangareddy", "state": "Telangana", "district": "Sangareddy", "basin": "MANJIRA", "lat": 17.6340, "lon": 78.0860},
    {"name": "Khammam", "state": "Telangana", "district": "Khammam", "basin": "GODAVARI", "lat": 17.2470, "lon": 80.1510},
    {"name": "Mahbubnagar", "state": "Telangana", "district": "Mahbubnagar", "basin": "KRISHNA", "lat": 16.7430, "lon": 77.9850},
    {"name": "Adilabad", "state": "Telangana", "district": "Adilabad", "basin": "GODAVARI", "lat": 19.6730, "lon": 78.5410},
    {"name": "Nalgonda", "state": "Telangana", "district": "Nalgonda", "basin": "KRISHNA", "lat": 17.0550, "lon": 79.2670},
    {"name": "Suryapet", "state": "Telangana", "district": "Suryapet", "basin": "KRISHNA", "lat": 17.1380, "lon": 79.6220},
    {"name": "Miryalaguda", "state": "Telangana", "district": "Nalgonda", "basin": "MUSI", "lat": 16.8660, "lon": 79.5600},
    {"name": "Vikarabad", "state": "Telangana", "district": "Vikarabad", "basin": "KRISHNA", "lat": 17.3370, "lon": 77.9030},
    {"name": "Warangal Tri", "state": "Telangana", "district": "Warangal", "basin": "GODAVARI", "lat": 17.9689, "lon": 79.5941},
    {"name": "Anantapur", "state": "Andhra Pradesh", "district": "Anantapur", "basin": "EAST FLOWING", "lat": 14.6810, "lon": 77.6000},
    {"name": "Chittoor", "state": "Andhra Pradesh", "district": "Chittoor", "basin": "SWARNAMUKHI", "lat": 13.2120, "lon": 79.1000},
    {"name": "Sri City", "state": "Andhra Pradesh", "district": "Chittoor", "basin": "SWARNAMUKHI", "lat": 13.5400, "lon": 79.9500},
    {"name": "Hosur", "state": "Tamil Nadu", "district": "Krishnagiri", "basin": "PALAR", "lat": 12.7360, "lon": 77.8300},
    {"name": "Kanchipuram", "state": "Tamil Nadu", "district": "Kanchipuram", "basin": "PALAR", "lat": 12.8340, "lon": 79.7030},
    {"name": "Cuddalore", "state": "Tamil Nadu", "district": "Cuddalore", "basin": "PARVASINAR", "lat": 11.7440, "lon": 79.7720},
    {"name": "Nagapattinam", "state": "Tamil Nadu", "district": "Nagapattinam", "basin": "VELLAR", "lat": 10.7650, "lon": 79.8460},
    {"name": "Thanjavur", "state": "Tamil Nadu", "district": "Thanjavur", "basin": "CAUVERY", "lat": 10.7870, "lon": 79.1390},
    {"name": "Kumbakonam", "state": "Tamil Nadu", "district": "Thanjavur", "basin": "CAUVERY", "lat": 10.9600, "lon": 79.3850},
    {"name": "Mannargudi", "state": "Tamil Nadu", "district": "Tiruvarur", "basin": "VELLAR", "lat": 10.6590, "lon": 79.4500},
    {"name": "Thiruvarur", "state": "Tamil Nadu", "district": "Tiruvarur", "basin": "CAUVERY", "lat": 10.7740, "lon": 79.6540},
    {"name": "Mayiladuthurai", "state": "Tamil Nadu", "district": "Mayiladuthurai", "basin": "CAUVERY", "lat": 11.1040, "lon": 79.6490},
    {"name": "Thanjavur", "state": "Tamil Nadu", "district": "Thanjavur", "basin": "CAUVERY", "lat": 10.7870, "lon": 79.1390},
    {"name": "Adirampattinam", "state": "Tamil Nadu", "district": "Thanjavur", "basin": "VELLAR", "lat": 10.3420, "lon": 79.3820},
    {"name": "Vedaranyam", "state": "Tamil Nadu", "district": "Nagapattinam", "basin": "VELLAR", "lat": 10.3750, "lon": 79.8500},
    {"name": "Karaikal", "state": "Puducherry", "district": "Karaikal", "basin": "ARASALAR", "lat": 10.9180, "lon": 79.8310},
    {"name": "Marakkanam", "state": "Tamil Nadu", "district": "Villupuram", "basin": "COASTAL", "lat": 12.1980, "lon": 79.9430},
    {"name": "Arni", "state": "Tamil Nadu", "district": "Tiruvannamalai", "basin": "PONNAIYAR", "lat": 12.6720, "lon": 79.2920},
    {"name": "Tiruvannamalai", "state": "Tamil Nadu", "district": "Tiruvannamalai", "basin": "PALAR", "lat": 12.2250, "lon": 79.0750},
]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _build_locator() -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    # Every district headquarters is a locator point (nationwide precision).
    for d in DISTRICTS:
        points.append({
            "type": "district",
            "id": d["id"],
            "name": d["hq"] or d["district"],
            "district": d["district"],
            "state": d["state"],
            "basin": _basin_for(d["state"], d["district"]),
            "lat": d["lat"],
            "lon": d["lon"],
            "flood_prone": bool(d["flood_prone"]),
        })
    for z in ZONES:
        lon, lat = z["centroid"]
        points.append({
            "type": "priority_zone",
            "id": z["id"],
            "name": z["name"],
            "district": z.get("district") or z["name"],
            "state": z["state"],
            "basin": z["basin"],
            "lat": lat,
            "lon": lon,
            "area_km2": z.get("area_km2"),
            "population": z.get("population"),
        })
    for st in RIVER_STATIONS:
        sid, name, river, basin, state, lat, lon = st[:7]
        points.append({
            "type": "river_gauge",
            "id": sid,
            "name": name,
            "district": state,
            "state": state,
            "basin": basin,
            "river": river,
            "lat": float(lat),
            "lon": float(lon),
        })
    for t in EXTRA_TOWNS:
        points.append({
            "type": "town",
            "id": t["name"].lower().replace(" ", "-"),
            "name": t["name"],
            "district": t.get("district") or t["name"],
            "state": t["state"],
            "basin": t.get("basin", ""),
            "lat": float(t["lat"]),
            "lon": float(t["lon"]),
        })
    return points


LOCATOR_POINTS: List[Dict[str, Any]] = _build_locator()


def locate(lat: float, lon: float, k: int = 3) -> List[Dict[str, Any]]:
    """Return the k nearest locator points with straight-line distance (km)."""
    scored = []
    for p in LOCATOR_POINTS:
        d = _haversine(lat, lon, p["lat"], p["lon"])
        row = dict(p)
        row["distance_km"] = round(d, 1)
        scored.append(row)
    scored.sort(key=lambda x: x["distance_km"])
    return scored[:k]


def zone_score_fields() -> Any:
    """Import shim so orchestrator/citizen modules do not hard-code imports."""
    from .india_data import ZONES as _z, RIVER_STATIONS as _rs

    return _z, _rs