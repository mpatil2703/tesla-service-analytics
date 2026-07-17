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

# --- Page setup -----------------------------------------------------------
# st.set_page_config must be the first Streamlit command in the script.
# It sets the browser tab title and switches the page to a wide layout
# (instead of a narrow centered column), which gives charts more room.
st.set_page_config(page_title="Tesla Service Operations Dashboard", layout="wide")

MIN_CELL_N = 30  # minimum appointments before we trust a (type, bucket) cell
MIN_BUCKET_N = 100  # minimum appointments before we trust an overall bucket rate

# --- Design tokens (colors) -------------------------------------------------
# Every custom-styled element in this dashboard (KPI cards, hero metric,
# charts, footer, ...) is built from these tokens instead of one-off hex
# codes, so the whole page can flip between Streamlit's light and dark
# themes by changing values in ONE place rather than hunting through CSS.
#
# st.context.theme.type reports which theme is ACTUALLY active for this
# viewer right now ("light" or "dark") -- this is the real, current
# Streamlit theme, not just the OS/browser's prefers-color-scheme, so it
# stays correct even if someone picks a theme from Streamlit's own settings
# menu that differs from their system setting. Per Streamlit's docs it can
# briefly be None on the very first render of a session; we default to
# "light" in that split second, and it corrects itself on the next rerun
# (e.g. the moment someone touches a sidebar filter).
DARK_MODE = st.context.theme.type == "dark"


def _rgba(hex_color, alpha):
    """Turn a '#rrggbb' token into an 'rgba(r, g, b, alpha)' string, so every
    translucent wash/border below is derived from the SAME hex tokens used
    for solid fills -- no separate, easy-to-forget rgba literals that could
    drift out of sync with the token they're supposed to be a tint of."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


# Tesla brand palette: a neutral carries every "just a measurement" bar/line
# in this dashboard (categorical slot 1 from the project's data-viz palette),
# and Tesla's own brand red is reserved for emphasis/brand chrome (the hero
# metric, the worst bar, the worst table cell).
# Status colors (good/warning/critical) are a SEPARATE, reserved set -- used
# only to signal severity, never recycled as "just another series color".
# Keeping the two systems separate is what makes the red pop mean something
# instead of becoming visual noise. Each token has a light- and dark-theme
# value -- e.g. ACCENT is near-black on a light page but flips to a light
# neutral in dark mode, because near-black bars on a near-black dark-mode
# chart background would simply disappear.
if DARK_MODE:
    ACCENT = "#c9cbd1"
    GOOD = "#3ddc84"
    WARNING = "#ffc247"
    CRITICAL = "#ff4b4f"  # brighter than the light-mode red for AA contrast on a dark card
    SURFACE = "#262730"  # Streamlit's own dark-theme "card" background
    GRID = "#41424c"
    INK = "#fafafa"
    INK_SECONDARY = "#c7c8cc"
    INK_MUTED = "#93959c"
else:
    ACCENT = "#171a20"
    GOOD = "#0ca30c"
    WARNING = "#fab219"
    CRITICAL = "#e82127"
    SURFACE = "#fcfcfb"
    GRID = "#e1e0d9"
    INK = "#0b0b0b"
    INK_SECONDARY = "#52514e"
    INK_MUTED = "#898781"

# Derived tokens -- translucent washes/borders computed FROM the base
# palette above (via _rgba) so they automatically stay correct for whichever
# theme is active, plus a couple of standalone light/dark pairs for the one
# element (the disclaimer) that intentionally keeps its own amber identity
# in both themes rather than adopting the red/black brand accent.
CARD_BORDER = _rgba(INK, 0.08)
CARD_SHADOW = _rgba(INK, 0.08)
GOOD_WASH = _rgba(GOOD, 0.05)
WARNING_WASH = _rgba(WARNING, 0.08)
CRITICAL_WASH = _rgba(CRITICAL, 0.05)
HERO_TINT_STRONG = _rgba(CRITICAL, 0.12 if DARK_MODE else 0.07)
HERO_TINT_FAINT = _rgba(CRITICAL, 0.02)
HERO_BORDER = _rgba(CRITICAL, 0.3 if DARK_MODE else 0.25)
TREND_FILL = _rgba(ACCENT, 0.10)
DANGER_ZONE_FILL = _rgba(CRITICAL, 0.08)
DISCLAIMER_BG = "#3a2f10" if DARK_MODE else "#fff8e1"
DISCLAIMER_BORDER = "#6b5518" if DARK_MODE else "#f0d078"
DISCLAIMER_TEXT = "#f5d67b" if DARK_MODE else "#6b5900"

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
        border: 1px solid {CARD_BORDER};
        border-left: 4px solid {ACCENT};
        border-radius: 10px;
        padding: 16px 18px;
        box-shadow: 0 1px 4px {CARD_SHADOW};
    }}
    /* The wash below is layered OVER {SURFACE} (not just the translucent
       wash alone) -- a status card's background rule replaces .kpi-card's
       background rather than adding to it (same CSS specificity, later
       rule wins), so without an opaque base here a status card would show
       the PAGE's background through the tint instead of the card surface,
       looking inconsistent with the plain (non-status) cards next to it. */
    .kpi-good {{ border-left-color: {GOOD}; background: linear-gradient({GOOD_WASH}, {GOOD_WASH}), {SURFACE}; }}
    .kpi-warning {{ border-left-color: {WARNING}; background: linear-gradient({WARNING_WASH}, {WARNING_WASH}), {SURFACE}; }}
    .kpi-critical {{ border-left-color: {CRITICAL}; background: linear-gradient({CRITICAL_WASH}, {CRITICAL_WASH}), {SURFACE}; }}

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

    .disclaimer-banner {{
        background: {DISCLAIMER_BG};
        border: 1px solid {DISCLAIMER_BORDER};
        border-radius: 8px;
        padding: 10px 16px;
        margin: 0 0 1.1rem 0;
        font-size: 13.5px;
        color: {DISCLAIMER_TEXT};
        text-align: center;
    }}

    .project-summary {{
        font-size: 15.5px;
        line-height: 1.5;
        color: {INK_SECONDARY};
        max-width: 900px;
        margin: 0.2rem 0 1.3rem 0;
    }}

    .hero-metric {{
        background: linear-gradient(135deg, {HERO_TINT_STRONG}, {HERO_TINT_FAINT}), {SURFACE};
        border: 1px solid {HERO_BORDER};
        border-left: 6px solid {CRITICAL};
        border-radius: 12px;
        padding: 22px 26px;
        margin: 0.3rem 0 1.4rem 0;
    }}
    .hero-metric-label {{
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: {CRITICAL};
        margin-bottom: 8px;
    }}
    .hero-metric-value {{
        font-size: clamp(1.35rem, 3.6vw, 2.1rem);
        font-weight: 800;
        color: {INK};
        line-height: 1.3;
    }}
    .hero-metric-sub {{
        font-size: 14px;
        color: {INK_SECONDARY};
        margin-top: 10px;
    }}

    .insights-box {{
        font-size: 15px;
        line-height: 1.9;
        color: {INK};
    }}
    .insights-box b {{ color: {INK}; }}

    .site-footer {{
        margin-top: 2.5rem;
        padding-top: 1.2rem;
        border-top: 1px solid {GRID};
        color: {INK_MUTED};
        font-size: 13px;
        text-align: center;
    }}
    .site-footer a {{ color: {CRITICAL}; font-weight: 600; text-decoration: none; }}
    .site-footer a:hover {{ text-decoration: underline; }}

    .section-box {{
        background: {SURFACE};
        border: 1px solid {CARD_BORDER};
        border-left: 4px solid {ACCENT};
        border-radius: 10px;
        padding: 16px 20px;
        margin: 0.3rem 0 1.2rem 0;
        font-size: 15px;
        line-height: 1.65;
        color: {INK};
    }}
    .section-box b {{ color: {INK}; }}
    .section-box.problem-box {{ border-left-color: {CRITICAL}; }}
    .section-box ul {{ margin: 4px 0 0 0; padding-left: 20px; }}
    .section-box li {{ margin-bottom: 6px; }}
    .section-box li:last-child {{ margin-bottom: 0; }}

    .glossary-term {{
        font-size: 14.5px;
        line-height: 1.6;
        color: {INK};
        margin-bottom: 8px;
    }}
    .glossary-term b {{ color: {INK}; }}
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

# --- Disclaimer banner --------------------------------------------------
# Sits above everything else on the page, including the title, so a viewer
# can't miss it before looking at a single number.
st.markdown(
    '<div class="disclaimer-banner">⚠️ This project uses SIMULATED data for '
    'portfolio purposes only. Not affiliated with or endorsed by Tesla, Inc.</div>',
    unsafe_allow_html=True,
)

st.title("Tesla Service Operations Dashboard")

# --- Project summary ------------------------------------------------------
st.markdown(
    '<p class="project-summary">This dashboard analyzes a simulated Tesla-style vehicle '
    'service operation to find out what drives appointment cancellations. It was built to '
    'apply an aeronautical engineering background (reliability analysis, root-cause thinking, '
    'and operational risk) to a real-world service operations problem. The top finding: '
    'cancellation rate climbs sharply as technician utilization rises, meaning busier service '
    'centers are measurably more likely to lose an appointment.</p>',
    unsafe_allow_html=True,
)

# --- The Problem ---------------------------------------------------------
# A plain-language framing of the business question, aimed at a viewer who
# has never seen this dataset and doesn't care about the methodology yet --
# just "why does this dashboard exist." Placed before any chart so that
# context, not a number, is the first thing a new reader absorbs.
st.subheader("The Problem")
st.markdown(
    '<div class="section-box problem-box">Every cancelled or rescheduled appointment costs '
    'Tesla Service Operations technician time, open bays, and a customer who has to come back '
    'later. This project investigates <b>what drives cancellations and reschedules</b> so that '
    'the team can spot the conditions that make an appointment likely to fall through, before '
    'it happens.</div>',
    unsafe_allow_html=True,
)

# --- How to Read This Dashboard -------------------------------------------
# Defines the two metrics that every chart below is built from, in plain
# language and with a real-world analogy for the less intuitive one
# (utilization), plus the exact formula so a skeptical reader can verify it.
st.subheader("How to Read This Dashboard")
st.markdown(
    '<div class="section-box">'
    '<ul>'
    '<li><b>Cancellation rate</b> — the percentage of booked appointments that ended up '
    'cancelled instead of completed. A higher number means more appointments are falling '
    'through.</li>'
    '<li><b>Technician utilization</b> — how busy, or fully booked, technicians were at a '
    'service center on a given day, as a percentage. Think of it like a restaurant\'s '
    'reservation book for the night: 40% means plenty of open tables, 90% means almost every '
    'slot is taken and there\'s little room to absorb a delay.</li>'
    '<li><b>The math</b> — cancellation rate = (cancelled appointments ÷ total appointments) '
    '× 100.</li>'
    '</ul>'
    '</div>',
    unsafe_allow_html=True,
)

# --- Glossary (collapsed by default) --------------------------------------
# One-line, jargon-free definitions for every channel and appointment type
# used elsewhere in the dashboard. Tucked into an expander so it's there
# for a viewer who needs it without pushing the charts further down the
# page for everyone else.
with st.expander("📖 What Do These Terms Mean?"):
    col_channels, col_types = st.columns(2)

    with col_channels:
        st.markdown("**Booking Channels**")
        st.markdown(
            '<div class="glossary-term"><b>Service Center</b> — you bring your car in and a '
            'technician works on it there.</div>'
            '<div class="glossary-term"><b>Mobile Service</b> — a technician comes to you and '
            'does the repair on-site.</div>'
            '<div class="glossary-term"><b>Collision Center</b> — specialized repair for '
            'accident or body damage.</div>',
            unsafe_allow_html=True,
        )

    with col_types:
        st.markdown("**Appointment Types**")
        st.markdown(
            '<div class="glossary-term"><b>Tire Rotation</b> — moving each tire to a different '
            'position on the car so they wear evenly.</div>'
            '<div class="glossary-term"><b>Brake Fluid/Caliper Service</b> — maintaining the '
            'fluid and hardware that make the brakes stop the car.</div>'
            '<div class="glossary-term"><b>Cabin/HEPA Filter Replacement</b> — swapping the air '
            'filter that cleans the air coming into the cabin.</div>'
            '<div class="glossary-term"><b>12V Battery Service</b> — servicing the small '
            'battery that runs electronics and accessories, separate from the main drive '
            'battery.</div>'
            '<div class="glossary-term"><b>Warranty Repair</b> — fixing a covered defect or '
            'issue at no cost under Tesla\'s warranty.</div>'
            '<div class="glossary-term"><b>Collision Repair</b> — repairing body damage from an '
            'accident.</div>'
            '<div class="glossary-term"><b>Alignment</b> — adjusting the wheels so the car '
            'drives straight and tires wear evenly.</div>',
            unsafe_allow_html=True,
        )

st.divider()

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


# --- Hero metric ------------------------------------------------------
# The single headline finding, built from the numbers above (never typed
# out by hand) so it can't drift out of sync with the data or the sidebar
# filters. This is the first big, styled visual a viewer sees on the page —
# everything else (KPI cards, charts) supports this one number.
if rises_with_workload:
    hero_value = (
        f"Cancellation rate rises {low_rate:.1f}% → {high_rate:.1f}% "
        f"as technician utilization increases"
    )
    hero_sub = (
        f"{max_type} appointments are hit hardest, peaking at {max_rate:.1f}% "
        f"cancellations once utilization reaches {max_bucket}%."
    )
else:
    hero_value = (
        f"{max_type} at {max_bucket}% utilization is the highest-risk combination "
        f"in the data ({max_rate:.1f}%)"
    )
    hero_sub = "Cancellation rate does not rise uniformly with utilization in the current filter selection."

st.markdown(
    f'<div class="hero-metric">'
    f'<div class="hero-metric-label">Key Finding</div>'
    f'<div class="hero-metric-value">{hero_value}</div>'
    f'<div class="hero-metric-sub">{hero_sub}</div>'
    f'</div>',
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

# Emphasis coloring: every bar stays the base near-black EXCEPT the single
# worst one, which is drawn in the same Tesla-red used everywhere else in
# the dashboard to mean "this is the outlier" -- so the reader's eye lands
# on the one bar that matters instead of scanning six similar-looking bars.
worst_idx = by_center["cancellation_rate_pct"].idxmax()
center_colors = [
    CRITICAL if i == worst_idx else ACCENT for i in by_center.index
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


# --- Charts 1b/1c: appointment mix and cancellation rate by channel --------
# Two views of the same new "channel" column, placed side by side with
# st.columns(2) so they read as a pair: how appointments SPLIT across
# channels on the left, how each channel PERFORMS on the right.
by_channel_dist = (
    filtered.groupby("channel").agg(count=("channel", "size")).reset_index()
)
by_channel_dist["pct"] = (by_channel_dist["count"] / by_channel_dist["count"].sum() * 100).round(1)
by_channel_dist = by_channel_dist.sort_values("count", ascending=False)
# A single combined label ("2,988 (59.8%)") since texttemplate can only
# format one field at a time -- building the string ourselves lets the
# label show both the raw count and its share in one line.
by_channel_dist["label"] = (
    by_channel_dist["count"].map("{:,}".format) + " (" + by_channel_dist["pct"].astype(str) + "%)"
)

fig_channel_dist = px.bar(by_channel_dist, x="channel", y="count", text="label")
fig_channel_dist.update_traces(
    marker_color=ACCENT,
    marker_line_width=0,
    textposition="outside",
    customdata=by_channel_dist[["pct"]],
    hovertemplate="<b>%{x}</b><br>Appointments: %{y:,}<br>Share: %{customdata[0]:.1f}%<extra></extra>",
)
fig_channel_dist.update_layout(bargap=0.4)
fig_channel_dist = style_chart(fig_channel_dist, "Appointments")

by_channel_rate = (
    filtered.groupby("channel")
    .agg(cancellation_rate_pct=("is_cancelled", "mean"), n=("is_cancelled", "size"))
    .reset_index()
)
by_channel_rate["cancellation_rate_pct"] = (by_channel_rate["cancellation_rate_pct"] * 100).round(1)
by_channel_rate = by_channel_rate.sort_values("cancellation_rate_pct", ascending=False)

worst_channel_idx = by_channel_rate["cancellation_rate_pct"].idxmax()
channel_colors = [CRITICAL if i == worst_channel_idx else ACCENT for i in by_channel_rate.index]

fig_channel_rate = px.bar(by_channel_rate, x="channel", y="cancellation_rate_pct", text="cancellation_rate_pct")
fig_channel_rate.update_traces(
    marker_color=channel_colors,
    marker_line_width=0,
    texttemplate="%{text:.1f}%",
    textposition="outside",
    customdata=by_channel_rate[["n"]],
    hovertemplate="<b>%{x}</b><br>Cancellation rate: %{y:.1f}%<br>Appointments: %{customdata[0]:,}<extra></extra>",
)
fig_channel_rate.update_layout(bargap=0.4)
fig_channel_rate = style_chart(fig_channel_rate, "Cancellation rate (%)")

col_dist, col_rate = st.columns(2)

with col_dist:
    st.subheader("Appointment Mix by Channel")
    st.caption("How the overall workload splits across the three booking channels.")
    st.plotly_chart(fig_channel_dist, use_container_width=True)
    st.markdown(
        '<span class="chart-caption">Hover any bar for the exact count and share of total appointments.</span>',
        unsafe_allow_html=True,
    )

with col_rate:
    st.subheader("Cancellation Rate by Channel")
    st.caption("Which booking channel cancels most often, same comparison as the chart above.")
    st.plotly_chart(fig_channel_rate, use_container_width=True)
    st.markdown(
        '<span class="chart-caption">Red bar marks the highest cancellation rate. Collision Center has a much '
        'smaller sample (~200 appointments) than the other two channels, so weigh its rate with a bit more '
        'caution. Hover any bar for the exact rate and appointment count.</span>',
        unsafe_allow_html=True,
    )

st.divider()


# --- Chart 2: cancellation rate by utilization bucket -----------------------
by_bucket = (
    filtered.groupby("utilization_bucket", observed=True)
    .agg(cancellation_rate_pct=("is_cancelled", "mean"), n=("is_cancelled", "size"))
    .reset_index()
)
by_bucket["cancellation_rate_pct"] = (by_bucket["cancellation_rate_pct"] * 100).round(1)

worst_bucket_idx = by_bucket["cancellation_rate_pct"].idxmax()
bucket_colors = [CRITICAL if i == worst_bucket_idx else ACCENT for i in by_bucket.index]

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
        fillcolor=DANGER_ZONE_FILL, line_width=0, layer="below",
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
        line=dict(color=ACCENT, width=2),
        marker=dict(size=9, color=ACCENT, line=dict(width=2, color=SURFACE)),
        fill="tozeroy", fillcolor=TREND_FILL,
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
        f'<span class="chart-caption">Chart starts at 30% utilization, since bands below that have too few '
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
    st.caption(f"Cancellation rate rises as technician workload increases, most sharply for **{max_type}**.")
else:
    st.caption(f"Cancellation rate varies by technician workload, highest for **{max_type}** at **{max_bucket}%** workload.")

# --- Every cell gets a hover tooltip with its exact rate + sample size -----
tooltip_text = pd.DataFrame(index=pivot.index, columns=pivot.columns, dtype=object)
for r in pivot.index:
    for c in pivot.columns:
        n = int(cell_counts.loc[r, c])
        note = f"{pivot.loc[r, c]:.1f}% cancelled ({n} appointments)"
        if r == max_type and c == max_bucket:
            note += " (highest in the dataset)"
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
    pivot.style.background_gradient(cmap="Reds", vmin=0, vmax=max(pivot.values.max(), 1))
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
# NOTE: deliberately no blanket "td { color: ... }" rule here.
# background_gradient() above already gives every cell its OWN explicit
# per-cell text color (black on pale cells, near-white on the darkest red
# cells) via text_color_threshold -- it targets each cell's ID selector
# directly (e.g. "#T_xxx_row1_col3"), which is self-contained and doesn't
# depend on the surrounding theme at all. A blanket "td" rule here would
# look like it only affects a fallback, but a bare-tag "td" selector is
# actually MORE specific than pandas' own per-cell ID selector once you
# count selector parts (id+tag beats id alone), so it would silently
# override every cell's carefully-computed contrast color with one fixed
# color -- which is exactly the bug that made text on the darkest red
# cells (e.g. the highlighted Alignment/80-100% cell) unreadable.

# st.dataframe's Styler support doesn't reliably render custom CSS like
# borders or tooltips, so we render the Styler's own HTML directly instead
# -- this keeps the highlight border and hover tooltips intact. Wrapped in
# a div that (a) scrolls horizontally instead of dragging the whole page
# sideways on a phone (this table, with its multi-index header and 7
# appointment types, is wider than a phone screen), and (b) paints its own
# light background, since the table's colors are fixed regardless of theme
# -- without an explicit light background here, this card would sit
# directly on a dark page background in dark mode with no boundary of its
# own.
st.markdown(
    f'<div style="overflow-x: auto; background: #fcfcfb; border-radius: 8px; padding: 8px;">'
    f'{styled_pivot.to_html()}</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<span class="chart-caption">Darker red = higher cancellation rate. The red-bordered ⚠ cell marks the '
    'single highest-risk combination. Hover any cell for its exact rate and appointment count.</span>',
    unsafe_allow_html=True,
)

st.divider()


# --- Key Insights section ---------------------------------------------
# Plain-language takeaways built from the same numbers driving the hero
# metric and charts above, so a non-technical reader can skim this section
# alone and still walk away with the main findings.
worst_channel_row = by_channel_rate.iloc[0]
best_channel_row = by_channel_rate.iloc[-1]

insight_bullets = []
if rises_with_workload:
    insight_bullets.append(
        f"<b>Workload effect:</b> Cancellation rate climbs from {low_rate:.1f}% to {high_rate:.1f}% "
        f"as technician utilization moves from the lowest to the highest workload band. Busier "
        f"periods measurably increase the chance an appointment falls through."
    )
else:
    insight_bullets.append(
        f"<b>Workload effect:</b> Cancellation rate varies with technician utilization, though not "
        f"in a single consistent direction across every band in the current filter selection."
    )
insight_bullets.append(
    f"<b>{max_type} risk:</b> {max_type} appointments are the single riskiest combination in the "
    f"data, reaching a {max_rate:.1f}% cancellation rate once utilization hits {max_bucket}%. This "
    f"appointment type may need extra scheduling buffer during busy periods."
)
insight_bullets.append(
    f"<b>Channel effect:</b> {worst_channel_row['channel']} appointments cancel at "
    f"{worst_channel_row['cancellation_rate_pct']:.1f}%, the highest of the three booking channels, "
    f"versus {best_channel_row['cancellation_rate_pct']:.1f}% for {best_channel_row['channel']}."
)
insight_bullets.append(
    f"<b>Bottom line:</b> With {cancellation_rate:.1f}% of all appointments cancelled overall, "
    f"workload-aware scheduling (capping bookings once utilization crosses roughly 80%) is the "
    f"most direct lever for cutting lost appointments."
)

st.subheader("Key Insights")
st.markdown(
    '<div class="insights-box"><ul><li>' + "</li><li>".join(insight_bullets) + "</li></ul></div>",
    unsafe_allow_html=True,
)


# --- Methodology section -------------------------------------------------
st.subheader("Methodology")
st.markdown(
    "This dashboard runs on a **synthetic** dataset of about **5,000 simulated appointments** "
    "generated with `numpy`/`pandas`, spread across an **assumed 90-day scheduling window** "
    "(not a real Tesla reporting period).\n\n"
    "The service center markets (6 real Tesla service-center cities), booking channels "
    "(Service Center / Mobile Service / Collision Center), and appointment categories "
    "(Tire Rotation, Brake Fluid/Caliper Service, Alignment, Warranty Repair, etc.) are modeled "
    "on real, publicly known aspects of Tesla's service network. Which specific appointments "
    "happened, on which day, at which center, and with what outcome is entirely simulated.\n\n"
    "Critically, the relationship this dashboard analyzes, cancellation likelihood rising with "
    "technician utilization, was **intentionally built into the simulation itself** (cancellation "
    "probability is generated as a function of utilization). The project's purpose is to practice "
    "detecting, quantifying, and visualizing that kind of operational risk pattern with SQL, pandas, "
    "and Plotly. **This is not real Tesla data and does not reflect Tesla's actual operations, "
    "technician performance, or scheduling behavior.**"
)


# --- Footer -----------------------------------------------------------
st.markdown(
    '<div class="site-footer">Built by Madhushree Patil &nbsp;·&nbsp; '
    '<a href="https://mpatil2703.github.io/portfolio/" target="_blank" '
    'rel="noopener noreferrer">Portfolio</a></div>',
    unsafe_allow_html=True,
)
