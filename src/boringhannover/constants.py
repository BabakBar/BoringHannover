from zoneinfo import ZoneInfo


BERLIN_TZ = ZoneInfo("Europe/Berlin")

# How far into the future we include events in the output (movies and concerts).
# Unified 2-week window keeps the UI focused and prevents overwhelming users.
EVENT_LOOKAHEAD_DAYS = 14

# City Occasions need more lead time for planning festivals and seasonal visits.
OCCASION_LOOKAHEAD_DAYS = 30

# End is inclusive; retain useful detail pages for the next seven Berlin dates.
OCCASION_RETENTION_DAYS = 7
