"""
Streamlit dashboard for the synthetic Tesla-style service appointments data.

What Streamlit IS, in one idea: this whole file is a normal Python script
that Streamlit re-runs from TOP TO BOTTOM every single time something on
the page changes -- like when you click a filter in the sidebar. There's
no manual "wire this button to that function" step; you just write plain
Python, and any `st.` command in the script becomes something visible on
the page (a chart, a table, a header) in the order it appears in the file.
Run this with:  streamlit run app.py
"""

import os
import textwrap

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# --- Design tokens (colors) -------------------------------------------------
# One blue hue carries every "just a measurement" bar/line in this dashboard
# (categorical slot 1 from the project's data-viz palette). Status colors
# (good/warning/critical) are a SEPARATE, reserved set -- used only to signal
# severity (a KPI card, the worst bar, the worst table cell), never recycled
# as "just another series color". Keeping the two systems separate is what
# makes the red pop mean something instead of becoming visual noise.
BLUE = "#2a78d6"
GOOD = "#0ca30c"
WARNING = "#fab219"
CRITICAL = "#d03b3b"

SURFACE = "#fcfcfb"
GRID = "#e1e0d9"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"

MIN_CELL_N = 30  # minimum appointments before we trust a (type, bucket) cell
MIN_BUCKET_N = 100  # minimum appointments before we trust an overall bucket rate

# --- Page setup -----------------------------------------------------------
# st.set_page_config must be the first Streamlit command in the script.
# It sets the browser tab title and switches the page to a wide layout
# (instead of a narrow centered column), which gives charts more room.
st.set_page_config(page_title="Tesla Service Operations Dashboard", layout="wide")

# --- Global styling ----------------------------------------------------
# Streamlit renders st.title as an <h1> and st.subheader as an <h3> under
# the hood. Since those are just ordinary HTML tags, one block of CSS
# injected via st.markdown can restyle every one of them consistently --
# a bigger, bolder main title; medium-weight section headers with more
# space above them so sections don't feel jammed together; plus the
# classes the custom KPI cards and callout box below use.
st.markdown(
    textwrap.dedent(f"""
    <style>
    h1 {{
        font-weight: 800 !important;
        font-size: 2.5rem !important;
        letter-spacing: -0.02em;
        margin-bottom: 0.1rem !important;
    }}
    h3 {{
        font-weight: 600 !important;
        margin-top: 2.2rem !important;
        margin-bottom: 0.2rem !important;
    }}
    hr {{ margin: 1.6rem 0 !important; }}

    .callout-box {{
        background: rgba(42, 120, 214, 0.06);
        border: 1px solid rgba(42, 120, 214, 0.18);
        border-left: 4px solid {BLUE};
        border-radius: 8px;
        padding: 14px 18px;
        margin: 0.3rem 0 1.6rem 0;
        font-size: 15px;
        color: {INK};
    }}
    .callout-label {{
        font-weight: 700;
        color: {BLUE};
        margin-right: 8px;
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: 0.05em;
    }}

    .kpi-row {{
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
        margin: 0.4rem 0 1rem 0;
    }}
    .kpi-card {{
        flex: 1;
        min-width: 200px;
        background: {SURFACE};
        border: 1px solid rgba(11, 11, 11, 0.08);
        border-left: 4px solid {BLUE};
        border-radius: 10px;
        padding: 16px 18px;
        box-shadow: 0 1px 4px rgba(11, 11, 11, 0.07);
    }}
    .kpi-good {{ border-left-color: {GOOD}; background: rgba(12, 163, 12, 0.05); }}
    .kpi-warning {{ border-left-color: {WARNING}; background: rgba(250, 178, 25, 0.08); }}
    .kpi-critical {{ border-left-color: {CRITICAL}; background: rgba(208, 59, 59, 0.05); }}

    .kpi-icon {{ font-size: 22px; margin-bottom: 6px; }}
    .kpi-label {{ font-size: 13px; font-weight: 600; color: {INK_SECONDARY}; margin-bottom: 2px; }}
    .kpi-value {{ font-size: 28px; font-weight: 700; color: {INK}; line-height: 1.25; }}
    .kpi-sub {{ font-size: 12.5px; color: {INK_SECONDARY}; margin-top: 2px; }}
    .kpi-badge {{
        display: inline-flex; align-items: center; gap: 6px;
        font-size: 12px; font-weight: 600; color: {INK_SECONDARY};
        margin-top: 8px;
    }}
    .kpi-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}

    .chart-caption {{ color: {INK_MUTED}; font-size: 13px; }}
    </style>
    """).strip(),
    unsafe_allow_html=True,
)


# --- Loading the data -------------------------------------------------------
# @st.cache_data is a "decorator" -- a wrapper Streamlit provides that
# remembers the result of this function the first time it runs, keyed off
# the function's own code plus whatever arguments are passed in. Since
# Streamlit re-runs the whole script on every click, without this the app
# would re-read the CSV from disk on every single interaction.
#
# The catch: st.cache_data has NO idea that "service_appointments.csv" is a
# file on disk that can change -- it only looks at load_data()'s code and
# arguments to decide whether it's already seen this call before. If we
# update the CSV's contents (new columns, new rows) without changing this
# function's code, a cache entry warmed up on the OLD file can get served
# right back out, even after deploying the new code and new CSV -- which is
# exactly what caused a deployed KeyError: 'channel' after we added that
# column. Passing the file's last-modified time in as an argument fixes
# this: every time the CSV's contents change, its mtime changes too, which
# changes the cache key, which forces a fresh read.
@st.cache_data
def load_data(csv_mtime):
    df = pd.read_csv("service_appointments.csv")
    df["utilization_bucket"] = pd.cut(
        df["technician_utilization_pct"],
        bins=[0, 40, 60, 80, 100],
        labels=["0-40", "40-60", "60-80", "80-100"],
    )
    return df


df = load_data(os.path.getmtime("service_appointments.csv"))

st.title("Tesla Service Operations Dashboard")

# --- Sidebar filters ---------------------------------------------------
# st.sidebar puts a widget in the collapsible left-hand panel instead of
# the main page body. Anything placed there is available on every part
# of the dashboard below, since it's set once at the top of the script.
st.sidebar.header("Filters")

all_centers = sorted(df["service_center"].unique())
all_types = sorted(df["appointment_type"].unique())
all_channels = sorted(df["channel"].unique())

selected_centers = st.sidebar.multiselect(
    "Service center", options=all_centers, default=all_centers
)
selected_types = st.sidebar.multiselect(
    "Appointment type", options=all_types, default=all_types
)
selected_channels = st.sidebar.multiselect(
    "Channel", options=all_channels, default=all_channels
)

# Every time a filter changes, Streamlit re-runs the script and this line
# re-computes the filtered table from scratch using the CURRENT checkbox
# selections -- that's the whole "interactivity" model in one line.
filtered = df[
    df["service_center"].isin(selected_centers)
    & df["appointment_type"].isin(selected_types)
    & df["channel"].isin(selected_channels)
].copy()

if filtered.empty:
    st.warning("No appointments match the selected filters. Adjust the sidebar options.")
    st.stop()  # halts the script here so nothing below tries to chart empty data

filtered["is_cancelled"] = filtered["outcome_status"] == "Cancelled"


# ============================================================================
# Compute every headline number ONCE, up front. The KPI cards, the "Key
# Insight" banner, and the heatmap's highlighted cell all need to agree on
# "what's the worst combination in the data" -- so we work it out a single
# time here and hand the same numbers to all three, rather than recomputing
# (and risking three slightly different answers) further down the page.
# ============================================================================
total_appointments = len(filtered)
cancellation_rate = filtered["is_cancelled"].mean() * 100
avg_utilization = filtered["technician_utilization_pct"].mean()

# --- Highest-risk (appointment_type, utilization_bucket) combination -------
pivot = pd.pivot_table(
    filtered, index="appointment_type", columns="utilization_bucket",
    values="is_cancelled", aggfunc="mean", observed=True,
) * 100
pivot = pivot.round(1)

cell_counts = pd.pivot_table(
    filtered, index="appointment_type", columns="utilization_bucket",
    values="is_cancelled", aggfunc="count", observed=True,
)

# Guard: a handful of the 0-40% cells only have a few appointments (that
# bucket is rare overall), so a cell can hit an extreme rate by pure chance.
# We only let a cell be crowned "highest risk" if it has at least
# MIN_CELL_N appointments behind it -- everything still shows its real
# number in the table either way, this guard only affects what gets
# highlighted as THE headline finding.
reliable_cells = pivot.where(cell_counts >= MIN_CELL_N)
stacked_reliable = reliable_cells.stack()
if stacked_reliable.empty:
    max_type, max_bucket = pivot.stack().idxmax()
else:
    max_type, max_bucket = stacked_reliable.idxmax()
max_rate = pivot.loc[max_type, max_bucket]

# --- Overall trend across utilization buckets (same reliability guard) ----
bucket_order = list(pivot.columns)
bucket_totals = filtered.groupby("utilization_bucket", observed=True).size()
overall_by_bucket = filtered.groupby("utilization_bucket", observed=True)["is_cancelled"].mean() * 100

reliable_buckets = [b for b in bucket_order if bucket_totals.get(b, 0) >= MIN_BUCKET_N]
if len(reliable_buckets) >= 2:
    low_bucket, high_bucket = reliable_buckets[0], reliable_buckets[-1]
else:
    low_bucket, high_bucket = bucket_order[0], bucket_order[-1]
low_rate = overall_by_bucket[low_bucket]
high_rate = overall_by_bucket[high_bucket]
rises_with_workload = high_rate > low_rate


# --- "Key Insight" callout -------------------------------------------------
# One sentence, built from the numbers above rather than typed out by hand,
# so it can never drift out of sync with the data or the sidebar filters.
if rises_with_workload:
    insight = (
        f"Cancellations rise from {low_rate:.0f}% to {high_rate:.0f}% as technician "
        f"workload increases, with {max_type} appointments most affected."
    )
else:
    insight = (
        f"Cancellation rate varies by technician workload — {max_type} at "
        f"{max_bucket}% workload is the single highest-risk combination "
        f"({max_rate:.1f}%)."
    )

st.markdown(
    f'<div class="callout-box"><span class="callout-label">Key Insight</span>{insight}</div>',
    unsafe_allow_html=True,
)


# --- KPI cards ---------------------------------------------------------
# Streamlit's built-in st.metric doesn't support custom icons, colored
# borders, or badges, so these four cards are built as one block of plain
# HTML instead and dropped in with a single st.markdown call -- the same
# trick used for the heatmap table further down.
def kpi_card(icon, label, value, sub=None, variant="", badge_text=None, badge_color=None):
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    badge_html = (
        f'<div class="kpi-badge"><span class="kpi-dot" style="background:{badge_color}"></span>{badge_text}</div>'
        if badge_text else ""
    )
    html = textwrap.dedent(f"""
    <div class="kpi-card {variant}">
        <div class="kpi-icon">{icon}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {sub_html}
        {badge_html}
    </div>
    """)
    # When a card has no sub-line or badge, sub_html/badge_html are empty
    # strings, which leaves a whitespace-only line in their place. A blank
    # line in the middle of an HTML <div> block ends the block early in
    # Markdown's eyes, dumping the rest of the tags back out as visible
    # text -- so blank lines are dropped entirely, not just dedented.
    return "\n".join(line for line in html.splitlines() if line.strip())


# Cancellation rate is color-coded by severity: green under 20%, amber
# 20-25%, red above 25%. The number itself stays in high-contrast dark ink
# (amber text on a light card fails accessible contrast) -- the color
# signal instead lives in the card's background wash, left-border stripe,
# and a small colored dot + text badge, so the severity is never carried
# by color alone.
if cancellation_rate < 20:
    cr_variant, cr_badge, cr_color = "kpi-good", "Low risk", GOOD
elif cancellation_rate <= 25:
    cr_variant, cr_badge, cr_color = "kpi-warning", "Watch", WARNING
else:
    cr_variant, cr_badge, cr_color = "kpi-critical", "High risk", CRITICAL

kpi_html = (
    '<div class="kpi-row">'
    + kpi_card("📅", "Total Appointments", f"{total_appointments:,}")
    + kpi_card(
        "⚠️", "Overall Cancellation Rate", f"{cancellation_rate:.1f}%",
        variant=cr_variant, badge_text=cr_badge, badge_color=cr_color,
    )
    + kpi_card("⚙️", "Avg Technician Utilization", f"{avg_utilization:.1f}%")
    + kpi_card(
        "🎯", "Highest Risk Combo", f"{max_rate:.1f}%",
        sub=f"{max_type} @ {max_bucket}% util", variant="kpi-critical",
    )
    + "</div>"
)
st.markdown(kpi_html, unsafe_allow_html=True)

st.divider()


# --- Shared chart styling ---------------------------------------------
# A small helper so every chart shares the same clean look (light
# background, thin hairline gridlines, no border around the marks, no
# legend box) instead of repeating the same styling code several times.
def style_chart(fig, y_title):
    fig.update_layout(
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font_color=INK,
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        yaxis=dict(title=y_title, gridcolor=GRID, zeroline=False),
        xaxis=dict(title=None, showgrid=False),
        hoverlabel=dict(bgcolor=SURFACE, font_color=INK, bordercolor=GRID),
    )
    return fig


# --- Chart 1: cancellation rate by service center --------------------------
by_center = (
    filtered.groupby("service_center")
    .agg(cancellation_rate_pct=("is_cancelled", "mean"), n=("is_cancelled", "size"))
    .reset_index()
)
by_center["cancellation_rate_pct"] = (by_center["cancellation_rate_pct"] * 100).round(1)
by_center = by_center.sort_values("cancellation_rate_pct", ascending=False)

# Emphasis coloring: every bar stays the base blue EXCEPT the single worst
# one, which is drawn in the same critical red used everywhere else in the
# dashboard to mean "this is the outlier" -- so the reader's eye lands on
# the one bar that matters instead of scanning six similar-looking bars.
worst_idx = by_center["cancellation_rate_pct"].idxmax()
center_colors = [
    CRITICAL if i == worst_idx else BLUE for i in by_center.index
]

fig_center = px.bar(
    by_center, x="service_center", y="cancellation_rate_pct", text="cancellation_rate_pct",
)
fig_center.update_traces(
    marker_color=center_colors,
    marker_line_width=0,
    texttemplate="%{text:.1f}%",
    textposition="outside",
    customdata=by_center[["n"]],
    hovertemplate="<b>%{x}</b><br>Cancellation rate: %{y:.1f}%<br>Appointments: %{customdata[0]:,}<extra></extra>",
)
fig_center.update_layout(bargap=0.4)
fig_center = style_chart(fig_center, "Cancellation rate (%)")

st.subheader("Cancellation Rate by Service Center")
st.plotly_chart(fig_center, use_container_width=True)
st.markdown(
    '<span class="chart-caption">Red bar marks the highest cancellation rate. Hover any bar for the exact rate and appointment count.</span>',
    unsafe_allow_html=True,
)


# --- Chart 2: cancellation rate by utilization bucket -----------------------
by_bucket = (
    filtered.groupby("utilization_bucket", observed=True)
    .agg(cancellation_rate_pct=("is_cancelled", "mean"), n=("is_cancelled", "size"))
    .reset_index()
)
by_bucket["cancellation_rate_pct"] = (by_bucket["cancellation_rate_pct"] * 100).round(1)

worst_bucket_idx = by_bucket["cancellation_rate_pct"].idxmax()
bucket_colors = [CRITICAL if i == worst_bucket_idx else BLUE for i in by_bucket.index]

fig_bucket = px.bar(
    by_bucket, x="utilization_bucket", y="cancellation_rate_pct", text="cancellation_rate_pct",
)
fig_bucket.update_traces(
    marker_color=bucket_colors,
    marker_line_width=0,
    texttemplate="%{text:.1f}%",
    textposition="outside",
    customdata=by_bucket[["n"]],
    hovertemplate="<b>Utilization %{x}%</b><br>Cancellation rate: %{y:.1f}%<br>Appointments: %{customdata[0]:,}<extra></extra>",
)
fig_bucket.update_layout(bargap=0.4)
fig_bucket = style_chart(fig_bucket, "Cancellation rate (%)")

st.subheader("Cancellation Rate by Technician Utilization Bucket")
st.plotly_chart(fig_bucket, use_container_width=True)
st.markdown(
    '<span class="chart-caption">Red bar marks the highest cancellation rate. Hover any bar for the exact rate and appointment count.</span>',
    unsafe_allow_html=True,
)


# --- Chart 3: cancellation rate trend as utilization rises ------------------
# A finer-grained view than the 4-bucket bar chart above: utilization split
# into 10-point bands so the upward trend reads as a genuine line rather
# than 4 chunky steps. Bands below 30% are dropped -- they have almost no
# appointments (as few as 1), so plotting them would draw a "trend" that's
# really just noise from a handful of rows.
trend = filtered.copy()
trend["decile"] = pd.cut(
    trend["technician_utilization_pct"], bins=list(range(0, 101, 10)), include_lowest=True
)
trend_agg = (
    trend.groupby("decile", observed=True)
    .agg(rate=("is_cancelled", "mean"), n=("is_cancelled", "size"))
    .reset_index()
)
trend_agg["rate"] = (trend_agg["rate"] * 100).round(1)
# .apply() on a categorical column returns a categorical result by default
# (pandas maps the function over the unique categories, then reconstructs
# a Categorical) -- .astype(float) unwraps that back to plain numbers so
# the arithmetic below (midpoint = (low + high) / 2) actually works.
trend_agg["low"] = trend_agg["decile"].apply(lambda i: i.left).astype(float)
trend_agg["high"] = trend_agg["decile"].apply(lambda i: i.right).astype(float)
trend_agg["midpoint"] = (trend_agg["low"] + trend_agg["high"]) / 2
trend_agg["label"] = trend_agg["low"].astype(int).astype(str) + "-" + trend_agg["high"].astype(int).astype(str) + "%"

MIN_DECILE_N = 30
trend_agg = trend_agg[trend_agg["n"] >= MIN_DECILE_N].sort_values("midpoint").reset_index(drop=True)

if len(trend_agg) >= 2:
    fig_trend = go.Figure()

    # The shaded "danger zone" behind the line -- drawn first so the line
    # and markers sit on top of it, not the other way around.
    fig_trend.add_vrect(
        x0=80, x1=100,
        fillcolor="rgba(208, 59, 59, 0.08)", line_width=0, layer="below",
        annotation_text="High-risk zone (80-100%)", annotation_position="top left",
        annotation_font_size=11, annotation_font_color=INK_MUTED,
    )

    # Text label only on the final point (the endpoint) -- labeling every
    # point would be clutter; the axis and hover tooltip carry the rest.
    end_labels = [""] * (len(trend_agg) - 1) + [f"{trend_agg['rate'].iloc[-1]:.1f}%"]

    fig_trend.add_trace(go.Scatter(
        x=trend_agg["midpoint"], y=trend_agg["rate"],
        mode="lines+markers+text",
        text=end_labels, textposition="top center",
        line=dict(color=BLUE, width=2),
        marker=dict(size=9, color=BLUE, line=dict(width=2, color=SURFACE)),
        fill="tozeroy", fillcolor="rgba(42, 120, 214, 0.10)",
        customdata=trend_agg[["n", "label"]].values,
        hovertemplate="<b>Utilization %{customdata[1]}</b><br>Cancellation rate: %{y:.1f}%<br>Appointments: %{customdata[0]:,}<extra></extra>",
    ))

    fig_trend.update_layout(
        xaxis=dict(
            title=None, showgrid=False,
            tickvals=trend_agg["midpoint"], ticktext=trend_agg["label"],
        ),
    )
    fig_trend = style_chart(fig_trend, "Cancellation rate (%)")

    st.subheader("Cancellation Rate Trend as Technician Workload Rises")
    st.plotly_chart(fig_trend, use_container_width=True)
    st.markdown(
        f'<span class="chart-caption">Chart starts at 30% utilization — bands below that have too few '
        f'appointments (fewer than {MIN_DECILE_N}) to plot reliably. Hover any point for the exact rate and count.</span>',
        unsafe_allow_html=True,
    )
else:
    st.subheader("Cancellation Rate Trend as Technician Workload Rises")
    st.caption("Not enough appointments in the current filter selection to plot a reliable trend.")

st.divider()


# --- Table: cancellation rate by appointment type x utilization bucket -----
st.subheader("Cancellation Rate by Appointment Type × Utilization Bucket")

if rises_with_workload:
    st.caption(f"Cancellation rate rises as technician workload increases — most sharply for **{max_type}**.")
else:
    st.caption(f"Cancellation rate varies by technician workload — highest for **{max_type}** at **{max_bucket}%** workload.")

# --- Every cell gets a hover tooltip with its exact rate + sample size -----
tooltip_text = pd.DataFrame(index=pivot.index, columns=pivot.columns, dtype=object)
for r in pivot.index:
    for c in pivot.columns:
        n = int(cell_counts.loc[r, c])
        note = f"{pivot.loc[r, c]:.1f}% cancelled ({n} appointments)"
        if r == max_type and c == max_bucket:
            note += " — highest in the dataset"
        tooltip_text.loc[r, c] = note

# --- Rename columns to a two-row header ---------------------------------
# A pandas MultiIndex lets a column have TWO header labels stacked on top
# of each other. Every column gets the SAME top label, which pandas merges
# into one wide spanning cell when rendered -- giving the units/label AND
# the low-to-high axis cue without repeating "Technician Workload" four
# times (clutter the earlier version of this table had).
workload_label = "Technician Workload (Low → High)"
new_columns = pd.MultiIndex.from_product([[workload_label], [f"{b}%" for b in bucket_order]])
pivot.columns = new_columns
tooltip_text.columns = new_columns
max_bucket_col = (workload_label, f"{max_bucket}%")

styled_pivot = (
    pivot.style.background_gradient(cmap="Blues", vmin=0, vmax=max(pivot.values.max(), 1))
    .format("{:.1f}%")
    # Overwrite just the single highest-risk cell's text with a small
    # warning-star prefix, so that cell's meaning never depends on color
    # alone (useful for colorblind readers or a black-and-white printout).
    .format("⚠ {:.1f}%", subset=pd.IndexSlice[[max_type], [max_bucket_col]])
    .set_properties(
        subset=pd.IndexSlice[[max_type], [max_bucket_col]],
        **{"border": f"3px solid {CRITICAL}"},
    )
    .set_tooltips(
        tooltip_text,
        props="visibility: hidden; position: absolute; z-index: 1; background-color: #0b0b0b; "
              "color: white; padding: 5px 9px; border-radius: 5px; font-size: 12px; white-space: nowrap;",
    )
    .set_table_styles([
        {"selector": "th, td", "props": "padding: 6px 10px; text-align: center; font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;"},
        {"selector": "th", "props": "background-color: #f9f9f7; color: #52514e; font-weight: 600;"},
        {"selector": "table", "props": "border-collapse: collapse;"},
    ])
)

# st.dataframe's Styler support doesn't reliably render custom CSS like
# borders or tooltips, so we render the Styler's own HTML directly instead
# -- this keeps the highlight border and hover tooltips intact.
st.markdown(styled_pivot.to_html(), unsafe_allow_html=True)

st.markdown(
    '<span class="chart-caption">Darker blue = higher cancellation rate. The red-bordered ⚠ cell marks the '
    'single highest-risk combination. Hover any cell for its exact rate and appointment count.</span>',
    unsafe_allow_html=True,
)
