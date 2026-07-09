import pandas as pd

df = pd.read_csv("service_appointments.csv")

# pd.cut() takes a numeric column and slices it into labeled ranges
# ("buckets"), the same way we did earlier for the sanity check. Every
# row's utilization number gets replaced by which bucket it falls into.
df["utilization_bucket"] = pd.cut(
    df["technician_utilization_pct"],
    bins=[0, 40, 60, 80, 100],
    labels=["0-40%", "40-60%", "60-80%", "80-100%"],
)

# We need a plain 0/1 number to average, so make a new column that's
# True (1) when the appointment was Cancelled, False (0) otherwise.
df["is_cancelled"] = df["outcome_status"] == "Cancelled"

# --- Pivot table, explained ---
# A pivot table reshapes long data (one row per appointment) into a
# summary grid: one category down the side (rows), another category
# across the top (columns), and a calculated value filling each cell
# where they intersect. It's the same idea as a pivot table in Excel.
#
# Here:
#   index="appointment_type"       -> one row per appointment type
#   columns="utilization_bucket"   -> one column per utilization bucket
#   values="is_cancelled"          -> the number we're summarizing
#   aggfunc="mean"                 -> for every (type, bucket) combination,
#                                      average the is_cancelled column.
#                                      Averaging a column of True/False
#                                      values gives the fraction that were
#                                      True -- i.e. the cancellation rate
#                                      for that specific combination.
pivot = pd.pivot_table(
    df,
    index="appointment_type",
    columns="utilization_bucket",
    values="is_cancelled",
    aggfunc="mean",
    observed=True,
)

# Turn the 0-1 fractions into readable percentages.
pivot = (pivot * 100).round(1)

print("Cancellation rate (%) by appointment type and utilization bucket:\n")
print(pivot)
