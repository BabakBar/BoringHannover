from zoneinfo import ZoneInfo


BERLIN_TZ = ZoneInfo("Europe/Berlin")

# How far into the future we include events in the output (movies and concerts).
# Unified 2-week window keeps the UI focused and prevents overwhelming users.
EVENT_LOOKAHEAD_DAYS = 14
