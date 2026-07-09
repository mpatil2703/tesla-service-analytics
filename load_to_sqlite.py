import sqlite3
import pandas as pd

df = pd.read_csv("service_appointments.csv")

# sqlite3.connect() opens a connection to a database file. If the file
# doesn't exist yet, SQLite creates it on the spot -- so this line both
# creates and connects to service_ops.db in one step.
conn = sqlite3.connect("service_ops.db")

# df.to_sql() takes a DataFrame and writes it into the database as a
# real SQL table, translating pandas' columns/rows into SQL rows for you
# (no manual CREATE TABLE or INSERT statements needed).
#   "appointments"       -> the table name to create
#   conn                 -> which database connection to write through
#   if_exists="replace"  -> if a table with this name already exists
#                            (e.g. from a previous run), drop it and
#                            rebuild it fresh, instead of erroring out
#   index=False          -> don't add pandas' internal row-number index
#                            as its own column in the table
df.to_sql("appointments", conn, if_exists="replace", index=False)

print("Loaded", len(df), "rows into service_ops.db -> table 'appointments'")

# --- The SQL query ---
# SELECT service_center, ...   -> pick which columns show up in the result.
#                                  Here: the center's name, plus a
#                                  calculated cancellation rate column.
#
# AVG(CASE WHEN outcome_status = 'Cancelled' THEN 1 ELSE 0 END)
#   This is the "AVG(CASE WHEN...)" trick for turning a category into a
#   percentage, entirely in SQL:
#     - CASE WHEN outcome_status = 'Cancelled' THEN 1 ELSE 0 END looks at
#       EVERY row and outputs 1 if that row was Cancelled, 0 otherwise --
#       it's an inline if/else that runs per row.
#     - AVG(...) then averages that column of 1s and 0s. Averaging a
#       0/1 column gives the fraction of rows that were 1 -- i.e. exactly
#       the cancellation rate, without needing a separate COUNT of
#       cancelled rows divided by a COUNT of all rows.
#   Multiplying by 100.0 converts that fraction into a percentage.
#
# GROUP BY service_center
#   This tells SQL "don't average across the WHOLE table -- instead,
#   split all rows into buckets by service_center first, then compute
#   the AVG(...) separately within each bucket." It's the SQL equivalent
#   of pandas' groupby(): one result row comes out per unique center.
#
# ORDER BY cancellation_rate_pct DESC
#   Sorts the final result rows from highest cancellation rate to lowest.
#   DESC means descending (high to low); ASC (the default) would mean
#   low to high.
query = """
SELECT
    service_center,
    ROUND(AVG(CASE WHEN outcome_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0, 1)
        AS cancellation_rate_pct
FROM appointments
GROUP BY service_center
ORDER BY cancellation_rate_pct DESC;
"""

result = pd.read_sql_query(query, conn)
print("\nCancellation rate by service center:")
print(result)

conn.close()
