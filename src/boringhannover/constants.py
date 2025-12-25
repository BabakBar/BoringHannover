from zoneinfo import ZoneInfo


BERLIN_TZ = ZoneInfo("Europe/Berlin")

# How far into the future we include movies in the output.
# Kept separate from the radar cut-off (currently still 7 days).
MOVIES_LOOKAHEAD_DAYS = 10
