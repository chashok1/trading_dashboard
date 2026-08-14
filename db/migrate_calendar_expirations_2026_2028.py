"""
Migration: correct ref_calendar_event's 'Monthly Exp'/'Qtly Exp' rows for
2026-2028 against published OCC/OIC options-expiration dates.

Run once from the project root:
    python -m db.migrate_calendar_expirations_2026_2028

Background (2026-08-14): ref_calendar_event is workbook-sourced (Data tab,
etl/load_raw.py::load_data_tab_calendar_events) -- purely manual entry, no
formula or external feed behind it. Two problems were found by cross-
checking against published expiration calendars (Macroption's 2026
calendar, options-expiration search results for 2027, both consistent with
each other and with OCC's own rules):

1. Monthly Exp (3rd Friday of the month, shifted to Thursday when that
   Friday is a market holiday) had 2 rows that missed the Juneteenth (June
   19) holiday shift: 2026-06-19 (should be 06-18) and 2027-06-18 (should
   be 06-17, since June 19 2027 falls on a Saturday and is observed the
   preceding Friday). Verified no other month in 2026/2027/2028 collides
   with Juneteenth or Good Friday (2026: Apr 3, 2027: Mar 26, 2028: Apr 14
   -- none land on that year's 3rd Friday of any month).
2. Qtly Exp had been storing "last Friday of the quarter" -- a rule that
   matches neither OCC's real Quarterly Options convention (last BUSINESS
   day of the quarter) nor quad-witching (3rd Friday, same date as that
   month's Monthly Exp). Replaced with the correct last-business-day-of-
   quarter values; Sep/Dec 2028 shift to the preceding Friday since the
   calendar quarter-end itself falls on a weekend that year.

2028 was also added for both categories (previously missing entirely).

Idempotent: the Monthly Exp UPDATEs only touch rows still at their old
(wrong) value; every INSERT is ON CONFLICT DO NOTHING; the Qtly Exp DELETE
only targets the specific 2026-2027 date range being replaced. Safe to
re-run.

Caveat: this fixes the live database only. The source Excel workbook's
Data tab (whichever columns feed 'Monthly Exp'/'Qtly Exp') still has the
old values -- a future full re-import (db.init_db --reset-audit +
tickers_initial_load) would reintroduce them unless the workbook itself is
also corrected.
"""
from etl.db import session_scope
from sqlalchemy import text

# (old, new) -- Juneteenth holiday-shift misses.
MONTHLY_FIXES = [
    ("2026-06-19", "2026-06-18"),
    ("2027-06-18", "2027-06-17"),
]

# 2028 Monthly Exp -- plain 3rd-Friday-of-month, no holiday collisions that year.
MONTHLY_2028 = [
    "2028-01-21", "2028-02-18", "2028-03-17", "2028-04-21", "2028-05-19", "2028-06-16",
    "2028-07-21", "2028-08-18", "2028-09-15", "2028-10-20", "2028-11-17", "2028-12-15",
]

# Qtly Exp -- OCC Quarterly Options expire on the last business day of the
# calendar quarter (Mar/Jun/Sep/Dec).
QTLY_CORRECT = [
    "2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31",
    "2027-03-31", "2027-06-30", "2027-09-30", "2027-12-31",
    "2028-03-31", "2028-06-30", "2028-09-29", "2028-12-29",
]


def main():
    with session_scope() as s:
        for old, new in MONTHLY_FIXES:
            r = s.execute(text(
                "UPDATE ref_calendar_event SET event_date = :new "
                "WHERE category = 'Monthly Exp' AND event_date = :old"
            ), {"old": old, "new": new})
            print(f"Monthly Exp {old} -> {new}: {r.rowcount} row(s)")

        for d in MONTHLY_2028:
            r = s.execute(text(
                "INSERT INTO ref_calendar_event (category, event_date) VALUES ('Monthly Exp', :d) "
                "ON CONFLICT (category, event_date) DO NOTHING"
            ), {"d": d})
            print(f"Monthly Exp add {d}: {r.rowcount} row(s)")

        r = s.execute(text(
            "DELETE FROM ref_calendar_event WHERE category = 'Qtly Exp' "
            "AND event_date >= '2026-01-01' AND event_date < '2028-01-01'"
        ))
        print(f"Qtly Exp deleted (2026-2027 wrong rows): {r.rowcount}")

        for d in QTLY_CORRECT:
            r = s.execute(text(
                "INSERT INTO ref_calendar_event (category, event_date) VALUES ('Qtly Exp', :d) "
                "ON CONFLICT (category, event_date) DO NOTHING"
            ), {"d": d})
            print(f"Qtly Exp add {d}: {r.rowcount} row(s)")

        s.commit()
    print("done")


if __name__ == "__main__":
    main()
