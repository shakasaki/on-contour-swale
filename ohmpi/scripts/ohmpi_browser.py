"""Interactive per-quad waveform & QC browser for the OhmPi campaign.

Run as a Bokeh server app (NOT `python ohmpi_browser.py`):

    conda activate swale
    bokeh serve --show ohmpi/scripts/ohmpi_browser.py

Pick array -> line -> quad with the dropdowns. For the selected quad it shows,
across the whole campaign:

  * raw V/I square wave for one chosen survey (survey dropdown),
  * every voltage sample scattered over absolute time (campaign overview),
  * R and reciprocal R per survey, points coloured by the `keep` QC flag,
  * reciprocal error (%) per survey, with the 5 % / 15 % QC lines.

Derived series (R, rho_a, recip, keep) come from `r_table.parquet`; raw samples
are read lazily, one small parquet per quad, from the cache built by
`build_waveform_cache.py`. Nothing streams the zips at browse time.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models import (ColumnDataSource, Select, Div, Span,
                          DatetimeTickFormatter, HoverTool)
from bokeh.plotting import figure

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"
WF_DIR = CACHE_DIR / "waveforms"

KEEP_COLOR = "#1f77b4"   # quads that pass QC
DROP_COLOR = "#d62728"   # quads that fail QC

# max points drawn in the campaign-wide voltage scatter (a quad holds ~600k samples)
SCATTER_MAX = 4000

# ----------------------------------------------------------------------------
# data
# ----------------------------------------------------------------------------
RT = pl.read_parquet(CACHE_DIR / "r_table.parquet").sort(["array", "line", "quad", "timestamp"])


def _quad_key(quad: str):
    return [int(x) for x in quad.split("_")]


def catalog() -> dict[tuple[str, str], list[str]]:
    """Browsable (array, line) -> sorted quad list, discovered from the waveform cache.

    Cache covers lines A-E; r_table only covers A-D, so E is inspectable for raw
    waveforms but has no derived R/QC series.
    """
    cat: dict[tuple[str, str], list[str]] = {}
    for d in sorted(WF_DIR.glob("*_*")):
        if not d.is_dir():
            continue
        array, line = d.name.rsplit("_", 1)
        quads = sorted((f.stem for f in d.glob("*.parquet")), key=_quad_key)
        if quads:
            cat[(array, line)] = quads
    return cat


CATALOG = catalog()


def arrays() -> list[str]:
    return sorted({a for a, _ in CATALOG})


def lines_for(array: str) -> list[str]:
    return sorted({l for a, l in CATALOG if a == array})


def quads_for(array: str, line: str) -> list[str]:
    return CATALOG.get((array, line), [])


def rt_slice(array: str, line: str, quad: str) -> pl.DataFrame:
    return RT.filter(
        (pl.col("array") == array) & (pl.col("line") == line) & (pl.col("quad") == quad)
    ).sort("timestamp")


def load_wf(array: str, line: str, quad: str) -> pl.DataFrame:
    """Lazy-load one quad's raw samples; empty frame if the cache file is absent."""
    path = WF_DIR / f"{array}_{line}" / f"{quad}.parquet"
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path).with_columns(
        (pl.col("timestamp") + pl.duration(milliseconds=pl.col("time") * 1000)).alias("abs_t"),
        pl.col("timestamp").dt.strftime("%Y-%m-%d %H:%M:%S").alias("ts_str"),
    )


# ----------------------------------------------------------------------------
# widgets
# ----------------------------------------------------------------------------
a0 = arrays()[0]
l0 = lines_for(a0)[0]
q0 = quads_for(a0, l0)[0]

array_sel = Select(title="Array", value=a0, options=arrays())
line_sel = Select(title="Line", value=l0, options=lines_for(a0))
quad_sel = Select(title="Quad (a_b_m_n)", value=q0, options=quads_for(a0, l0))
survey_sel = Select(title="Survey (for raw waveform)", value="", options=[])
info = Div(text="", width=420)

# ----------------------------------------------------------------------------
# sources
# ----------------------------------------------------------------------------
src_wave = ColumnDataSource(dict(time=[], voltage=[], current=[]))      # one survey
src_scatter = ColumnDataSource(dict(abs_t=[], voltage=[]))              # whole campaign
src_r = ColumnDataSource(dict(timestamp=[], R=[], R_rec=[], rho_a=[], color=[]))
src_recip = ColumnDataSource(dict(timestamp=[], recip_err_pct=[], color=[]))

# ----------------------------------------------------------------------------
# figures
# ----------------------------------------------------------------------------
fig_v = figure(width=560, height=210, title="Raw V — selected survey",
              x_axis_label="time within survey [s]", y_axis_label="Vmn [mV]")
fig_v.line("time", "voltage", source=src_wave, color="navy")
fig_v.scatter("time", "voltage", source=src_wave, size=3, color="navy")

fig_i = figure(width=560, height=210, title="Raw I — selected survey", x_range=fig_v.x_range,
              x_axis_label="time within survey [s]", y_axis_label="Iab [mA]")
fig_i.line("time", "current", source=src_wave, color="firebrick")
fig_i.scatter("time", "current", source=src_wave, size=3, color="firebrick")

fig_scatter = figure(width=560, height=240, x_axis_type="datetime",
                    title=f"Voltage samples over the campaign (decimated to ~{SCATTER_MAX})",
                    x_axis_label="date", y_axis_label="Vmn [mV]")
fig_scatter.scatter("abs_t", "voltage", source=src_scatter, size=2, alpha=0.25, color="navy")

fig_r = figure(width=560, height=240, x_axis_type="datetime",
              title="R (blue=keep, red=drop) & reciprocal R",
              x_axis_label="date", y_axis_label="R [Ohm]")
fig_r.scatter("timestamp", "R", source=src_r, size=6, color="color",
             legend_label="R", marker="circle")
fig_r.scatter("timestamp", "R_rec", source=src_r, size=6, color="gray",
             alpha=0.5, legend_label="R_rec", marker="x")
fig_r.legend.location = "top_left"
fig_r.legend.click_policy = "hide"

fig_recip = figure(width=560, height=220, x_axis_type="datetime", x_range=fig_r.x_range,
                  title="Reciprocal error", x_axis_label="date", y_axis_label="recip err [%]")
fig_recip.scatter("timestamp", "recip_err_pct", source=src_recip, size=6, color="color")
for thr, col in ((5.0, "green"), (15.0, "orange")):
    fig_recip.add_layout(Span(location=thr, dimension="width", line_color=col, line_dash="dashed"))

for f in (fig_scatter, fig_r, fig_recip):
    f.xaxis.formatter = DatetimeTickFormatter(months="%Y-%m", days="%m-%d")
fig_r.add_tools(HoverTool(tooltips=[("date", "@timestamp{%F %T}"), ("R", "@R{0.000}"),
                                    ("rho_a", "@rho_a{0.00}")],
                          formatters={"@timestamp": "datetime"}))

# ----------------------------------------------------------------------------
# update logic
# ----------------------------------------------------------------------------
_WF = pl.DataFrame()   # currently-loaded quad's raw samples (cached for survey swaps)
_SUPPRESS = False      # True while we mutate widgets programmatically (mutes callbacks)


def update_survey_plot() -> None:
    """Redraw the single-survey square wave from the cached `_WF` frame."""
    ts = survey_sel.value
    d = _WF.filter(pl.col("ts_str") == ts).sort("time") if (_WF.height and ts) else pl.DataFrame()
    if d.height:
        src_wave.data = dict(time=d["time"].to_list(),
                             voltage=d["voltage"].to_list(),
                             current=d["current"].to_list())
    else:
        src_wave.data = dict(time=[], voltage=[], current=[])


def update_quad() -> None:
    global _WF, _SUPPRESS
    array, line, quad = array_sel.value, line_sel.value, quad_sel.value
    rt = rt_slice(array, line, quad)
    colors = [KEEP_COLOR if k else DROP_COLOR for k in rt["keep"].to_list()]
    src_r.data = dict(timestamp=rt["timestamp"].to_list(), R=rt["R"].to_list(),
                      R_rec=rt["R_rec"].to_list(), rho_a=rt["rho_a"].to_list(), color=colors)
    src_recip.data = dict(timestamp=rt["timestamp"].to_list(),
                          recip_err_pct=rt["recip_err_pct"].to_list(), color=colors)

    _WF = load_wf(array, line, quad)
    if _WF.height:
        step = max(1, _WF.height // SCATTER_MAX)
        sc = _WF.gather_every(step)
        src_scatter.data = dict(abs_t=sc["abs_t"].to_list(), voltage=sc["voltage"].to_list())
        opts = _WF["ts_str"].unique().sort(descending=True).to_list()
    else:
        src_scatter.data = dict(abs_t=[], voltage=[])
        opts = []
    _SUPPRESS = True   # setting options/value here must not re-fire on_survey
    survey_sel.options = opts
    survey_sel.value = opts[0] if opts else ""
    _SUPPRESS = False
    update_survey_plot()

    n_keep = int(rt["keep"].sum()) if rt.height else 0
    med_rho = rt.filter(pl.col("keep"))["rho_a"].median() if n_keep else None
    if rt.height == 0:
        rho_txt = "no r_table / QC data for this line (raw waveforms only)"
    elif med_rho is not None:
        rho_txt = f"median rho_a (kept): {med_rho:.2f} &Omega;&middot;m"
    else:
        rho_txt = "no kept surveys"
    info.text = (
        f"<b>{array} line {line} — quad {quad}</b><br>"
        f"surveys: {rt.height} &nbsp; kept: {n_keep} &nbsp; "
        f"waveform samples: {_WF.height:,}<br>{rho_txt}"
    )


# cascading dropdowns -------------------------------------------------------
# Each handler re-syncs every level below it directly (not via the value-change
# event chain), because setting a value to its current value fires no event and
# would leave stale options downstream (e.g. dipdip->wenner with line 'A').
def on_array(attr, old, new):
    global _SUPPRESS
    if _SUPPRESS:
        return
    _SUPPRESS = True
    line_sel.options = lines_for(new)
    if line_sel.value not in line_sel.options:
        line_sel.value = line_sel.options[0]
    quad_sel.options = quads_for(new, line_sel.value)
    if quad_sel.value not in quad_sel.options:
        quad_sel.value = quad_sel.options[0]
    _SUPPRESS = False
    update_quad()


def on_line(attr, old, new):
    global _SUPPRESS
    if _SUPPRESS:
        return
    _SUPPRESS = True
    quad_sel.options = quads_for(array_sel.value, new)
    if quad_sel.value not in quad_sel.options:
        quad_sel.value = quad_sel.options[0]
    _SUPPRESS = False
    update_quad()


def on_quad(attr, old, new):
    if _SUPPRESS:
        return
    update_quad()


def on_survey(attr, old, new):
    if _SUPPRESS:
        return
    update_survey_plot()


array_sel.on_change("value", on_array)
line_sel.on_change("value", on_line)
quad_sel.on_change("value", on_quad)
survey_sel.on_change("value", on_survey)

update_quad()  # initial fill

controls = row(array_sel, line_sel, quad_sel, survey_sel)
layout = column(
    Div(text="<h2>OhmPi quad browser</h2>"),
    controls,
    info,
    row(column(fig_v, fig_i), column(fig_scatter)),
    row(fig_r, fig_recip),
)
curdoc().add_root(layout)
curdoc().title = "OhmPi quad browser"
