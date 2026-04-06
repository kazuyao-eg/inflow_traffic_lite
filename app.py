# pip install streamlit pandas plotly
from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(page_title="入会者分析ダッシュボード", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "fc_info.csv")

COL_STATUS = "ステータス"
COL_DATE = "FC実施年月日"
COL_GENDER = "性別"
COL_AGE = "年代"
COL_CEFR = "CEFR"
STATUS_ENROLLED = "入会"


@st.cache_data
def load_fc_info(path: str) -> pd.DataFrame:
    last_err: Exception | None = None
    df = None
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except UnicodeDecodeError as e:
            last_err = e
    if df is None:
        raise last_err if last_err else RuntimeError("CSV を読めませんでした")
    df.columns = df.columns.astype(str).str.strip()
    for c in (COL_STATUS, COL_GENDER, COL_AGE, COL_CEFR):
        if c in df.columns:
            df[c] = df[c].astype("string").replace({"<NA>": pd.NA})
    if COL_DATE in df.columns:
        df[COL_DATE] = pd.to_datetime(df[COL_DATE], errors="coerce")
    return df


def apply_base_filter(df: pd.DataFrame, base_mode: str) -> pd.DataFrame:
    if base_mode == "入会件数ベース":
        return df.loc[df[COL_STATUS] == STATUS_ENROLLED].copy()
    return df.copy()


def category_series(df: pd.DataFrame, dimension: str) -> pd.Series:
    if dimension == "年齢":
        return df[COL_AGE].fillna("不明").astype(str)
    if dimension == "性別":
        return df[COL_GENDER].fillna("不明").astype(str)
    if dimension == "CEFR":
        return df[COL_CEFR].fillna("不明").astype(str)
    if dimension == "年齢×性別":
        a = df[COL_AGE].fillna("不明").astype(str)
        g = df[COL_GENDER].fillna("不明").astype(str)
        return a + "×" + g
    raise ValueError(dimension)


def period_labels_and_key(df: pd.DataFrame, time_mode: str) -> tuple[pd.Series, list[str]]:
    dt = df[COL_DATE]
    valid = dt.notna()
    period = pd.Series(pd.NA, index=df.index, dtype="string")

    if time_mode == "年月":
        period.loc[valid] = dt.dt.strftime("%Y-%m")
        order = sorted(period.dropna().unique(), key=lambda x: pd.Period(x, freq="M"))
    elif time_mode == "年別":
        period.loc[valid] = dt.dt.year.astype("Int64").astype(str) + "年"
        order = sorted(period.dropna().unique(), key=lambda x: int(str(x).replace("年", "")))
    else:
        half = dt.dt.month.le(6)
        y = dt.dt.year.astype("Int64").astype(str)
        period.loc[valid & half] = y[valid & half] + "年1~6月"
        period.loc[valid & ~half] = y[valid & ~half] + "年7~12月"
        order = sorted(
            period.dropna().unique(),
            key=lambda s: (int(s[:4]), 0 if "1~6" in s else 1),
        )

    return period, order


def build_counts(
    df: pd.DataFrame, base_mode: str, time_mode: str, dimension: str
) -> tuple[pd.DataFrame, list[str]]:
    d = apply_base_filter(df, base_mode)
    d = d.loc[d[COL_DATE].notna()].copy()
    if d.empty:
        return pd.DataFrame(), []

    period, period_order = period_labels_and_key(d, time_mode)
    d["_period"] = period
    d = d.loc[d["_period"].notna()]
    if d.empty:
        return pd.DataFrame(), []

    d["_cat"] = category_series(d, dimension)
    ct = (
        d.groupby(["_period", "_cat"], observed=False)
        .size()
        .reset_index(name="count")
    )
    return ct, period_order


def plot_grouped_bar(
    counts: pd.DataFrame,
    period_order: list[str],
    dimension: str,
    bar_axis: str,
) -> go.Figure:
    if counts.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="表示できるデータがありません",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    categories = sorted(counts["_cat"].unique().tolist())
    periods = [p for p in period_order if p in set(counts["_period"])]

    if bar_axis == "時間を横軸（内訳で色分け）":
        x_vals = periods
        color_dim = categories
        x_key, series_key = "_period", "_cat"
        x_title = "時間"
        legend_title = dimension
    else:
        x_vals = categories
        color_dim = periods
        x_key, series_key = "_cat", "_period"
        x_title = dimension
        legend_title = "時間"

    fig = go.Figure()
    for s in color_dim:
        y = []
        for x in x_vals:
            row = counts[(counts[x_key] == x) & (counts[series_key] == s)]
            y.append(int(row["count"].sum()) if not row.empty else 0)
        fig.add_trace(
            go.Bar(name=str(s), x=x_vals, y=y, hovertemplate="%{x}<br>%{fullData.name}<br>人数: %{y}<extra></extra>")
        )

    fig.update_layout(
        barmode="group",
        xaxis_title=x_title,
        yaxis_title="人数",
        legend_title_text=legend_title,
        height=520,
        margin=dict(l=48, r=24, t=48, b=120),
        xaxis=dict(tickangle=-35),
    )
    return fig


def plot_pies_row(
    counts: pd.DataFrame,
    period_order: list[str],
    dimension: str,
) -> go.Figure:
    periods = [p for p in period_order if p in set(counts["_period"])]
    if not periods:
        fig = go.Figure()
        fig.add_annotation(
            text="表示できるデータがありません",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    n = len(periods)
    fig = make_subplots(
        rows=1,
        cols=n,
        specs=[[{"type": "domain"}] * n],
        subplot_titles=periods,
        horizontal_spacing=min(0.06, 0.2 / max(n, 1)),
    )

    for i, per in enumerate(periods, start=1):
        sub = counts[counts["_period"] == per]
        labels = sub["_cat"].tolist()
        values = sub["count"].astype(int).tolist()
        fig.add_trace(
            go.Pie(
                labels=labels,
                values=values,
                name=per,
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "人数: %{value}<br>"
                    "割合: %{percent}<extra></extra>"
                ),
                textinfo="percent",
                showlegend=False,
            ),
            row=1,
            col=i,
        )

    fig.update_layout(
        showlegend=False,
        height=480,
        margin=dict(l=24, r=24, t=60, b=24),
        title_text=f"内訳: {dimension}",
    )
    return fig


def main():
    st.title("入会者分析ダッシュボード")

    if not os.path.isfile(CSV_PATH):
        st.error(f"`fc_info.csv` が見つかりません（配置先: `{CSV_PATH}`）。")
        st.stop()

    try:
        raw = load_fc_info(CSV_PATH)
    except Exception as e:
        st.error(f"CSV の読み込みに失敗しました: {e}")
        st.stop()

    required = [COL_STATUS, COL_DATE, COL_GENDER, COL_AGE, COL_CEFR]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        st.error(f"必要な列がありません: {missing}")
        st.stop()

    st.sidebar.header("表示形式の切り替え")
    base_mode = st.sidebar.radio(
        "①（ベース）",
        ["FC件数ベース", "入会件数ベース"],
        horizontal=True,
        help="FC件数ベース: CSV の全行（日付が有効なもの）。入会件数ベース: ステータスが「入会」の行のみ。",
    )
    time_mode = st.sidebar.radio(
        "②（時間軸）",
        ["年月", "年別", "半年ごと"],
        horizontal=True,
    )

    dimension = st.sidebar.radio(
        "内訳の項目",
        ["年齢", "性別", "CEFR", "年齢×性別"],
        horizontal=True,
        help="「年齢」は CSV の「年代」列に対応します。",
    )

    counts, period_order = build_counts(raw, base_mode, time_mode, dimension)
    if counts.empty and not raw.empty:
        st.warning("日付が取れる行がありません。`FC実施年月日` を確認してください。")

    tab_bar, tab_pie = st.tabs(["棒グラフ", "円グラフ"])

    with tab_bar:
        bar_axis = st.radio(
            "棒グラフの軸",
            ["時間を横軸（内訳で色分け）", "内訳を横軸（時間で色分け）"],
            horizontal=True,
        )
        fig_bar = plot_grouped_bar(counts, period_order, dimension, bar_axis)
        st.plotly_chart(fig_bar, use_container_width=True)

    with tab_pie:
        st.caption("各円グラフは対応する期間の合計を100%とした割合です。ホバーで人数と割合を表示します。")
        fig_pie = plot_pies_row(counts, period_order, dimension)
        st.plotly_chart(fig_pie, use_container_width=True)


if __name__ == "__main__":
    main()
