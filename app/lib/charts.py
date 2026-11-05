"""Chart styling and small helpers. One palette, one template, used everywhere."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Categorical slots in fixed order (validated for colorblind separation on adjacent pairs).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
NEUTRAL = "#b4b2a9"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"

STATUS_COLORS = {
    "Active": STATUS["good"], "At risk": STATUS["warning"], "Lapsed": STATUS["serious"], "Churned": STATUS["critical"],
    "Completed": SERIES[0], "Never activated": NEUTRAL,
}
STATUS_ORDER = ["Active", "At risk", "Lapsed", "Churned", "Completed", "Never activated"]
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
CONFIG = {"displayModeBar": False, "responsive": True}


def style(fig: go.Figure, height: int = 320, pct_y: bool = False, pct_x: bool = False, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=INK_2),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=GRID, font=dict(family=FONT, color=INK, size=13)),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text="",
                    font=dict(color=INK_2)),
        bargap=0.35, barcornerradius=4,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickcolor=AXIS, tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=AXIS, tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    if pct_y:
        fig.update_yaxes(tickformat=".0%")
    if pct_x:
        fig.update_xaxes(tickformat=".0%")
    return fig


def show(fig: go.Figure, sql: str | None = None, key: str | None = None) -> None:
    st.plotly_chart(fig, config=CONFIG, key=key)
    if sql:
        show_sql(sql)


def show_sql(sql: str) -> None:
    return


def bar(df: pd.DataFrame, x: str, y: str, color: str | list[str] = SERIES[0], horizontal: bool = False,
        text_fmt: str | None = None, hover: str | None = None, height: int = 320, pct: bool = False) -> go.Figure:
    colors = color if isinstance(color, list) else [color] * len(df)
    text = None
    if text_fmt:
        text = [text_fmt.format(v) for v in df[y]]
    trace = go.Bar(
        x=df[y] if horizontal else df[x], y=df[x] if horizontal else df[y], orientation="h" if horizontal else "v",
        marker=dict(color=colors, line=dict(width=0)), text=text, textposition="outside", cliponaxis=False,
        textfont=dict(color=INK_2), hovertemplate=hover or ("%{y}: %{x}<extra></extra>" if horizontal else "%{x}: %{y}<extra></extra>"),
    )
    fig = go.Figure(trace)
    style(fig, height=height, pct_y=pct and not horizontal, pct_x=pct and horizontal, legend=False)
    if horizontal:
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(showgrid=True, gridcolor=GRID)
        if text_fmt and len(df):
            fig.update_xaxes(range=[0, float(df[y].max()) * 1.18])
    elif text_fmt and len(df):
        fig.update_yaxes(range=[0, float(df[y].max()) * 1.15])
    fig.update_xaxes(tickangle=0)
    return fig


def lines(df: pd.DataFrame, x: str, y: str, group: str | None = None, height: int = 320, pct: bool = False,
          hover_fmt: str = "{:.1%}", order: list[str] | None = None) -> go.Figure:
    fig = go.Figure()
    groups = [None] if group is None else (order or list(dict.fromkeys(df[group])))
    for i, g in enumerate(groups):
        d = df if g is None else df[df[group] == g]
        if d.empty:
            continue
        fmt = "%{y:.1%}" if pct else "%{y:,.0f}"
        fig.add_trace(go.Scatter(
            x=d[x], y=d[y], mode="lines+markers", name=str(g) if g is not None else y,
            line=dict(width=2, color=SERIES[i % len(SERIES)]),
            marker=dict(size=7, color=SERIES[i % len(SERIES)], line=dict(width=2, color="#fcfcfb")),
            hovertemplate=(f"{g}: " if g is not None else "") + fmt + "<extra></extra>",
        ))
    style(fig, height=height, pct_y=pct, legend=group is not None)
    fig.update_layout(hovermode="x unified")
    return fig


def add_event(fig: go.Figure, x, label: str) -> None:
    """Vertical marker for a business event (policy change, incident)."""
    fig.add_vline(x=x, line=dict(color=MUTED, width=1, dash="dot"))
    fig.add_annotation(x=x, y=1, yref="paper", text=label, showarrow=False, xanchor="left", yanchor="top",
                       xshift=4, font=dict(size=12, color=INK_2), bgcolor="rgba(252,252,251,0.85)")


def add_band(fig: go.Figure, x0, x1, label: str) -> None:
    fig.add_vrect(x0=x0, x1=x1, fillcolor="#f0efec", opacity=0.7, line_width=0, layer="below")
    fig.add_annotation(x=x0, y=0.02, yref="paper", text=label, showarrow=False, xanchor="left", yanchor="bottom",
                       xshift=4, font=dict(size=11, color=MUTED))


def pct(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:.0%}"


def pct1(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:.1%}"


def money(v) -> str:
    if v is None or pd.isna(v):
        return "n/a"
    return f"${v / 1_000_000:.2f}M" if abs(v) >= 1_000_000 else f"${v / 1000:,.0f}K" if abs(v) >= 10_000 else f"${v:,.0f}"


def page_header(title: str, question: str) -> None:
    st.title(title)
    st.caption(question)


def insight(text: str) -> None:
    """A one-line takeaway above a chart, written for a non-technical reader."""
    st.markdown(f"<div class='pulse-insight'>{text}</div>", unsafe_allow_html=True)


CSS = """
<style>
  .block-container {padding-top: 2.2rem; max-width: 1180px;}
  h1 {font-size: 1.9rem !important; letter-spacing: -0.01em;}
  h3 {font-size: 1.1rem !important; margin-top: 0.6rem !important;}
  .pulse-insight {border-left: 3px solid #2a78d6; padding: 0.35rem 0.75rem; margin: 0.2rem 0 0.6rem 0;
                  color: #0b0b0b; background: #f3f2ee; border-radius: 0 6px 6px 0; font-size: 0.95rem;}
  .pulse-tag {display:inline-block; padding: 0.05rem 0.5rem; border-radius: 999px; font-size: 0.78rem;
              background:#f0efec; color:#52514e; margin-right: 0.3rem;}
  div[data-testid="stMetricValue"] {font-size: 1.75rem;}
  div[data-testid="stMetricLabel"] p {color: #52514e;}
</style>
"""
