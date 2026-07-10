"""
Generates a synthetic Tesla-style service appointment dataset.

The core "story" we're simulating: on days/centers where technicians are
running at higher utilization (busier), appointments are more likely to be
Cancelled or Rescheduled instead of Completed.
"""

import numpy as np
import pandas as pd

# A "seed" locks the random number generator to a fixed starting point.
# Without it, you'd get different random values every time you run the
# script. With it, running this script twice produces the exact same
# dataset -- useful for a portfolio project so your numbers don't change
# every time you re-run it.
np.random.seed(42)

# How many appointment records to simulate.
N = 5000

# --- 1. Static reference lists -------------------------------------------
# These are the categories we'll randomly assign to each appointment.
# These 6 cities were chosen because they correspond to real Tesla service
# center markets -- the city names are realistic, but which specific
# appointments happen there and when is entirely simulated.
service_centers = [
    "Fremont, CA",
    "Austin, TX",
    "Chicago, IL",
    "Seattle, WA",
    "Denver, CO",
    "Toronto, ON",
]

# Real Tesla customer-facing service categories. Two categories that might
# seem like an obvious fit were deliberately left OUT:
#   - "Software Update" -- Tesla ships software updates over-the-air (OTA)
#     directly to the car, not as something a customer books an appointment
#     for, so it doesn't belong in a list of bookable appointment types.
#   - "Diagnostic Check" -- diagnostics happen as an internal backend
#     pre-triage step (deciding what a car actually needs) rather than a
#     category a customer selects when booking, so it isn't customer-facing.
appointment_types = [
    "Tire Rotation",
    "Brake Fluid/Caliper Service",
    "Cabin/HEPA Filter Replacement",
    "12V Battery Service",
    "Warranty Repair",
    "Collision Repair",
    "Alignment",
]

# A Tesla appointment is booked through one of three channels. These
# weights (roughly 58% / 37% / 5%) are an ESTIMATE for this portfolio
# project based on general knowledge of how Tesla's service network is
# structured (most work funnels through fixed service centers, mobile vans
# handle a large minority of lighter jobs, and body-shop-style collision
# work is comparatively rare) -- they are not a published Tesla statistic.
channels = ["Service Center", "Mobile Service", "Collision Center"]
channel_weights = [0.58, 0.37, 0.05]

# --- 2. Random categorical columns ----------------------------------------
# np.random.choice picks randomly (with replacement) from a list, N times.
# This gives us one service center, appointment type, and channel per row.
# Passing p= gives channel its weighted (not equal-chance) probabilities.
service_center = np.random.choice(service_centers, size=N)
appointment_type = np.random.choice(appointment_types, size=N)
channel = np.random.choice(channels, size=N, p=channel_weights)

# --- 3. Random dates --------------------------------------------------------
# pd.Timestamp.today() is "right now" as a pandas date object.
# We build a pool of the last 90 days, then randomly pick N of them (with
# replacement, since many appointments can share a date). 90 days is an
# ASSUMED window for this portfolio project -- not a real Tesla reporting
# period -- chosen to look like a plausible "last quarter" service log.
today = pd.Timestamp.today().normalize()  # normalize() strips the time-of-day
date_pool = pd.date_range(end=today, periods=90, freq="D")
scheduled_date = np.random.choice(date_pool, size=N)

# --- 4. Technician utilization ----------------------------------------------
# We simulate utilization as a percentage (0-100) using a normal
# ("bell curve") distribution centered at 75% with a spread of 15.
# Real service centers cluster around a "typically busy" rate, with some
# days quieter and some busier -- a normal distribution mimics that.
technician_utilization = np.random.normal(loc=75, scale=15, size=N)

# Utilization can't go below 0% or above 100%, so we clip (cap) any values
# that randomly landed outside that range.
technician_utilization = np.clip(technician_utilization, 0, 100)

# Round to 1 decimal place so it reads like a real percentage metric.
technician_utilization = np.round(technician_utilization, 1)

# --- 5. Outcome status, correlated with utilization -------------------------
# This is the key relationship for the whole dataset: the busier the
# technicians are, the more likely an appointment is to be Cancelled or
# Rescheduled instead of Completed.
#
# We express utilization as a fraction from 0.0 to 1.0 to make the math
# below easier to read.
u = technician_utilization / 100.0

# Cancellation probability rises from ~3% (when utilization is low) up to
# ~35% (when utilization is maxed out at 100%). Linear interpolation:
# prob = start + (end - start) * u
p_cancel = 0.03 + (0.35 - 0.03) * u

# Reschedule probability rises more mildly, from ~5% up to ~20%. Rescheduling
# is a "softer" version of a cancellation -- still more likely when busy,
# but not as steep.
p_reschedule = 0.05 + (0.20 - 0.05) * u

# Whatever probability is left over goes to "Completed".
p_complete = 1.0 - p_cancel - p_reschedule

# --- 6. Sampling one outcome per row using row-specific probabilities -------
# np.random.choice only accepts ONE probability list for ALL rows at once,
# but here every row has its OWN probabilities (since they depend on that
# row's utilization). So instead we roll a single "dice" value per row
# (a random number between 0 and 1) and check which probability bucket it
# falls into. This is a standard trick for vectorized (fast, loop-free)
# random sampling with per-row probabilities.
roll = np.random.uniform(0, 1, size=N)

# np.select checks a list of conditions in order and assigns the matching
# choice. Here: if the roll lands in the "cancel" slice -> Cancelled,
# else if it lands in the next slice -> Rescheduled, else -> Completed.
conditions = [
    roll < p_cancel,
    roll < (p_cancel + p_reschedule),
]
choices = ["Cancelled", "Rescheduled"]
outcome_status = np.select(conditions, choices, default="Completed")

# --- 7. Assemble into a DataFrame -------------------------------------------
# A DataFrame is pandas' main table object -- think of it like an Excel
# sheet or a database table living in memory. We build it from a
# dictionary where each key becomes a column name and each value is the
# column's data (all the same length, N).
df = pd.DataFrame({
    "service_center": service_center,
    "appointment_type": appointment_type,
    "channel": channel,
    "scheduled_date": pd.to_datetime(scheduled_date).date,
    "technician_utilization_pct": technician_utilization,
    "outcome_status": outcome_status,
})

# Sort by date so the CSV reads chronologically rather than in random order.
df = df.sort_values("scheduled_date").reset_index(drop=True)

# --- 8. Save to CSV ----------------------------------------------------------
# index=False means "don't write pandas' internal row-number index as a
# column" -- we only want the 5 real columns in the file.
output_path = "service_appointments.csv"
df.to_csv(output_path, index=False)

print(f"Saved {len(df):,} rows to {output_path}")

# --- 9. Quick sanity check that the correlation actually shows up ----------
# We bucket utilization into ranges and check the cancellation rate in each
# bucket -- this should climb as utilization climbs, confirming our
# simulated relationship worked as intended.
df["utilization_bucket"] = pd.cut(
    df["technician_utilization_pct"],
    bins=[0, 40, 60, 80, 100],
    labels=["0-40%", "40-60%", "60-80%", "80-100%"],
)
summary = (
    df.groupby("utilization_bucket", observed=True)["outcome_status"]
    .apply(lambda s: (s == "Cancelled").mean())
    .round(3)
)
print("\nCancellation rate by utilization bucket:")
print(summary)
