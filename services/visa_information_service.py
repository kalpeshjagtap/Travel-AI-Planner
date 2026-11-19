"""Official-source discovery links; does not make visa eligibility claims."""
from urllib.parse import quote_plus

def official_entry_information_link(destination: str, traveler_nationality: str = "") -> str:
    query="official government visa entry requirements " + destination + (" for " + traveler_nationality if traveler_nationality else "")
    return "https://www.google.com/search?q="+quote_plus(query)
