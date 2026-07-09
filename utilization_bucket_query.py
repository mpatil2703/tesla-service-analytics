import sqlite3
import pandas as pd

conn = sqlite3.connect("service_ops.db")

# --- CASE WHEN bucketing, explained ---
# CASE WHEN is SQL's if/elif/else. It's evaluated once per row, checking
# each condition top to bottom, and stops at the first one that's true --
# just like Python's if/elif/elif/else chain.
#
# For every row, this looks at that row's technician_utilization_pct and
# decides which labeled range it falls into:
#   WHEN technician_utilization_pct < 40  THEN '0-40'
#     -> if utilization is under 40, label it '0-40'
#   WHEN technician_utilization_pct < 60  THEN '40-60'
#     -> otherwise (so we already know it's >= 40), if it's under 60,
#        label it '40-60'
#   WHEN technician_utilization_pct < 80  THEN '60-80'
#     -> otherwise, if under 80, label it '60-80'
#   ELSE '80-100'
#     -> anything left over (80 and up) gets this final label
#
# Because each WHEN only has to rule out the lower boundary already
# eliminated by the checks above it, we don't need to write "BETWEEN 40
# AND 60" -- the ordering of the conditions does that work for us.
#
# "AS utilization_bucket" names this calculated column so we can
# GROUP BY it and refer to it later, just like a normal column name.
query = """
SELECT
    CASE
        WHEN technician_utilization_pct < 40 THEN '0-40'
        WHEN technician_utilization_pct < 60 THEN '40-60'
        WHEN technician_utilization_pct < 80 THEN '60-80'
        ELSE '80-100'
    END AS utilization_bucket,
    ROUND(AVG(CASE WHEN outcome_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0, 1)
        AS cancellation_rate_pct,
    COUNT(*) AS num_appointments
FROM appointments
GROUP BY utilization_bucket
ORDER BY utilization_bucket ASC;
"""

result = pd.read_sql_query(query, conn)
print("Cancellation rate by utilization bucket (lowest to highest utilization):")
print(result)

conn.close()
