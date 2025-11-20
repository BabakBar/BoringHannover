"""
Configuration settings for KinoWeek scrapers.

All URLs and settings are centralized here for easy updates.
"""

# Astor Grand Cinema API
ASTOR_API_URL = "https://backend.premiumkino.de/v1/de/hannover/program"

# Staatstheater Hannover
# Note: The iCal feed URL may not be publicly available.
# Alternative: Could scrape the HTML calendar at https://staatstheater-hannover.de/de_DE/kalender
STAATSTHEATER_ICAL_URL = "https://www.staatstheater-hannover.de/de_DE/kalender.ics"
STAATSTHEATER_CALENDAR_URL = "https://www.staatstheater-hannover.de/de_DE/kalender"

# Concert venues to scrape
# Note: Hannover-Concerts.de may not exist. Alternative sources:
# - ZAG Arena: https://www.zagarena.de/events/
# - Swiss Life Hall: https://www.swisslifehall.de/events
# - Capitol Hannover: https://www.capitol-hannover.de/programm
CONCERT_SOURCES = [
    {
        "name": "ZAG Arena",
        "url": "https://www.zagarena.de/events/",
        "enabled": False,  # Enable after testing
    },
    {
        "name": "Swiss Life Hall",
        "url": "https://www.swisslifehall.de/events",
        "enabled": False,  # Enable after testing
    },
    {
        "name": "Capitol Hannover",
        "url": "https://www.capitol-hannover.de/programm",
        "enabled": False,  # Enable after testing
    },
]

# Keywords to filter out (noise reduction)
IGNORE_KEYWORDS = [
    "Führung",
    "Einführung",
    "Kindertheater",
    "Kindertanz",
    "Workshop",
    "Probe",
    "Geschlossene Veranstaltung",
]

# HTTP request settings
REQUEST_TIMEOUT = 30.0  # seconds
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
