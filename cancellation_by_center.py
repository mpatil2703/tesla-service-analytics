import pandas as pd

# Load the CSV back into a DataFrame (pandas' table object).
df = pd.read_csv("service_appointments.csv")

# groupby("service_center") splits the whole table into smaller groups --
# one group per unique service center -- without changing any data, just
# organizing it so we can summarize each group separately.
#
# ["outcome_status"] then narrows each group down to just that one column,
# since that's the only column we need for this calculation.
#
# .apply(...) runs our own custom function on each group's outcome_status
# column. The function we pass in is:
#   lambda s: (s == "Cancelled").mean()
# Here's what that does, step by step:
#   - "s" is one center's list of outcome values, e.g. ["Completed", "Cancelled", ...]
#   - (s == "Cancelled") compares every value to the word "Cancelled" and
#     produces a list of True/False values (True where it was Cancelled).
#   - .mean() treats True as 1 and False as 0, so averaging them gives the
#     fraction that were Cancelled -- e.g. 0.25 means 25% were cancelled.
cancellation_rate = (
    df.groupby("service_center")["outcome_status"]
    .apply(lambda s: (s == "Cancelled").mean())
)

# Multiply by 100 and round so it reads as a clean percentage instead of
# a decimal fraction.
cancellation_rate = (cancellation_rate * 100).round(1)

# sort_values(ascending=False) reorders the result from highest to lowest,
# so the busiest/most problematic centers show up first.
cancellation_rate = cancellation_rate.sort_values(ascending=False)

print("Cancellation rate by service center (%):")
print(cancellation_rate)
