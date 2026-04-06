# pip install streamlit pandas plotly
from __future__ import annotations

import hmac
import html
import os

import pandas as pd
import plotly.colors as pc
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

BAR_CHART_HEIGHT = 520
PIE_ROW_HEIGHT = 480


def _extended_color_palette() -> list[str]:
    parts: list[list[str]] = [
        list(pc.qualitative.Plotly),
        list(pc.qualitative.Dark24),
        list(pc.qualitative.Set3),
        list(pc.qualitative.D3),
    ]
    g10 = getattr(pc.qualitative, "G10", None)
    if g10 is not None:
        parts.append(list(g10))
    return [c for group in parts for c in group]


def _color_map_for_keys(keys: list[str]) -> dict[str, str]:
    pal = _extended_color_palette()
    sorted_unique = sorted({str(k) for k in keys})
    return {k: pal[i % len(pal)] for i, k in enumerate(sorted_unique)}


# 「年齢」（CSV の年代）: 凡例イメージに合わせた並び・色
_AGE_ORDER: list[str] = [
    "10代前半",
    "18～25",
    "26～30",
    "31～35",
    "36～45",
    "46～60",
    "61以上",
    "不明",
]
_AGE_COLORS: dict[str, str] = {
    "10代前半": "#0d47a1",
    "18～25": "#42a5f5",
    "26～30": "#ff9800",
    "31～35": "#ffcc80",
    "36～45": "#2e7d32",
    "46～60": "#a5d6a7",
    "61以上": "#8d3b2c",
    "不明": "#f8bbd0",
}


def _normalize_wave_dash(s: str) -> str:
    return str(s).strip().replace("〜", "～")


def _canonical_age_label(raw: str) -> str | None:
    t = _normalize_wave_dash(raw)
    if t in _AGE_COLORS:
        return t
    for canon in _AGE_ORDER:
        if _normalize_wave_dash(canon) == t:
            return canon
    return None


def _color_map_age_keys(keys: list[str]) -> dict[str, str]:
    pal = _extended_color_palette()
    out: dict[str, str] = {}
    fb = 0
    for k in keys:
        ks = str(k)
        canon = _canonical_age_label(ks)
        if canon is not None:
            out[ks] = _AGE_COLORS[canon]
        else:
            out[ks] = pal[fb % len(pal)]
            fb += 1
    return out


def category_colors_for_dimension(dimension: str, keys: list[str]) -> dict[str, str]:
    if dimension == "年齢":
        return _color_map_age_keys(keys)
    return _color_map_for_keys(keys)


def ordered_legend_labels(dimension: str, present: set[str]) -> list[str]:
    if dimension == "年齢":
        used: set[str] = set()
        out: list[str] = []
        for canon in _AGE_ORDER:
            for p in present:
                if p in used:
                    continue
                if _canonical_age_label(p) == canon:
                    out.append(p)
                    used.add(p)
                    break
        for p in sorted(present - used):
            out.append(p)
        return out
    return sorted(present)


def legend_title_for_dimension(dimension: str) -> str:
    return {
        "年齢": "年代",
        "性別": "性別",
        "CEFR": "CEFR",
        "年齢×性別": "年齢×性別",
        "性別×CEFR": "性別×CEFR",
    }.get(dimension, dimension)


def render_category_legend_swatches(title: str, items: list[tuple[str, str]]) -> None:
    if not items:
        return
    cells: list[str] = []
    for label, color in items:
        safe = html.escape(str(label))
        cells.append(
            '<div style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap;">'
            f'<span style="flex-shrink:0;width:14px;height:14px;border-radius:50%;background:{color};border:1px solid #bbb;"></span>'
            f'<span style="font-size:15px;color:#333;">{safe}</span>'
            "</div>"
        )
    row = (
        '<div style="display:flex;flex-direction:row;flex-wrap:wrap;align-items:center;'
        'column-gap:20px;row-gap:10px;">'
        + "".join(cells)
        + "</div>"
    )
    block = (
        f'<div style="font-weight:600;font-size:1rem;margin-bottom:10px;color:#333;">{html.escape(title)}</div>'
        + row
    )
    st.markdown(block, unsafe_allow_html=True)


st.set_page_config(page_title="属性別流入ダッシュボード_ライト版", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "fc_info.csv")

COL_STATUS = "ステータス"
COL_DATE = "FC実施年月日"
COL_GENDER = "性別"
COL_AGE = "年代"
COL_CEFR = "CEFR"
STATUS_ENROLLED = "入会"
LABEL_UNKNOWN = "不明"


def _configured_app_password() -> str | None:
    """リポジトリに含めず Secrets / 環境変数で設定する。"""
    try:
        sec = getattr(st, "secrets", None)
        if sec is not None:
            for key in ("app_password", "APP_PASSWORD"):
                if key in sec:
                    p = str(sec[key]).strip()
                    if p:
                        return p
    except (FileNotFoundError, KeyError, TypeError, RuntimeError):
        pass
    env = os.environ.get("APP_PASSWORD", "").strip()
    return env if env else None


def _passwords_match(entered: str, expected: str) -> bool:
    a, b = entered.strip().encode("utf-8"), expected.encode("utf-8")
    if len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)


def ensure_password_gate() -> None:
    expected = _configured_app_password()
    if expected is None:
        st.error(
            "閲覧用パスワードが設定されていません。"
            " Streamlit Cloud の **Secrets** に `app_password = \"...\"` を追加するか、"
            " 環境変数 `APP_PASSWORD` を設定してください。"
        )
        st.stop()

    if st.session_state.get("auth_ok"):
        return

    st.title("属性別流入ダッシュボード_ライト版")
    st.caption("続行するにはパスワードを入力してください。")

    with st.form("password_gate", clear_on_submit=False):
        _ = st.text_input("パスワード", type="password", key="gate_password_input")
        submitted = st.form_submit_button("ログイン")

    if submitted:
        entered = st.session_state.get("gate_password_input") or ""
        if _passwords_match(entered, expected):
            st.session_state.auth_ok = True
            st.rerun()
        st.error("パスワードが正しくありません。")

    st.stop()


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
        return df[COL_AGE].fillna(LABEL_UNKNOWN).astype(str)
    if dimension == "性別":
        return df[COL_GENDER].fillna(LABEL_UNKNOWN).astype(str)
    if dimension == "CEFR":
        return df[COL_CEFR].fillna(LABEL_UNKNOWN).astype(str)
    if dimension == "年齢×性別":
        a = df[COL_AGE].fillna(LABEL_UNKNOWN).astype(str)
        g = df[COL_GENDER].fillna(LABEL_UNKNOWN).astype(str)
        return a + "×" + g
    if dimension == "性別×CEFR":
        g = df[COL_GENDER].fillna(LABEL_UNKNOWN).astype(str)
        c = df[COL_CEFR].fillna(LABEL_UNKNOWN).astype(str)
        return g + "×" + c
    raise ValueError(dimension)


def apply_exclude_unknown(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """内訳の項目において「不明」に該当する行を除く。"""
    if dimension == "年齢":
        return df.loc[df[COL_AGE].fillna(LABEL_UNKNOWN).astype(str) != LABEL_UNKNOWN].copy()
    if dimension == "性別":
        return df.loc[df[COL_GENDER].fillna(LABEL_UNKNOWN).astype(str) != LABEL_UNKNOWN].copy()
    if dimension == "CEFR":
        return df.loc[df[COL_CEFR].fillna(LABEL_UNKNOWN).astype(str) != LABEL_UNKNOWN].copy()
    if dimension == "年齢×性別":
        a = df[COL_AGE].fillna(LABEL_UNKNOWN).astype(str)
        g = df[COL_GENDER].fillna(LABEL_UNKNOWN).astype(str)
        return df.loc[(a != LABEL_UNKNOWN) & (g != LABEL_UNKNOWN)].copy()
    if dimension == "性別×CEFR":
        g = df[COL_GENDER].fillna(LABEL_UNKNOWN).astype(str)
        c = df[COL_CEFR].fillna(LABEL_UNKNOWN).astype(str)
        return df.loc[(g != LABEL_UNKNOWN) & (c != LABEL_UNKNOWN)].copy()
    return df.copy()


def period_labels_and_key(df: pd.DataFrame, time_mode: str) -> tuple[pd.Series, list[str]]:
    dt = df[COL_DATE]
    valid = dt.notna()
    period = pd.Series(pd.NA, index=df.index, dtype="string")

    if time_mode == "年別":
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
    df: pd.DataFrame,
    base_mode: str,
    time_mode: str,
    dimension: str,
    exclude_unknown: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    d = apply_base_filter(df, base_mode)
    d = d.loc[d[COL_DATE].notna()].copy()
    if d.empty:
        return pd.DataFrame(), []

    if exclude_unknown:
        d = apply_exclude_unknown(d, dimension)
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


def _bar_chart_min_width(n_x: int, n_series: int) -> int:
    if n_x <= 0:
        return 900
    px_per_group = max(32.0, min(96.0, 24.0 + 14.0 * max(n_series, 1)))
    return int(max(880, min(6000, n_x * px_per_group + 220)))


def _pie_row_min_width(n_periods: int) -> int:
    if n_periods <= 0:
        return 900
    return int(max(880, min(14000, n_periods * 300 + 120)))


def render_plotly_horizontal_scroll(
    fig: go.Figure,
    *,
    height: int,
    min_width: int,
) -> None:
    fig.update_layout(
        height=height,
        width=min_width,
        autosize=False,
    )
    fragment = fig.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        config={"responsive": False, "displayModeBar": True},
    )
    wrapper = (
        '<div style="overflow-x:auto;overflow-y:hidden;width:100%;'
        "-webkit-overflow-scrolling:touch;padding-bottom:4px;\">"
        f'<div style="min-width:{min_width}px;">{fragment}</div></div>'
    )
    components.html(wrapper, height=height + 48, scrolling=False)


def plot_grouped_bar(
    counts: pd.DataFrame,
    period_order: list[str],
    dimension: str,
    bar_axis: str,
) -> tuple[go.Figure, int]:
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
        fig.update_layout(height=BAR_CHART_HEIGHT, width=900, autosize=False)
        return fig, 900

    categories = sorted(counts["_cat"].unique().tolist())
    periods = [p for p in period_order if p in set(counts["_period"])]

    if bar_axis == "時間を横軸（項目で色分け）":
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

    series_colors = category_colors_for_dimension(dimension, [str(s) for s in color_dim])

    fig = go.Figure()
    for s in color_dim:
        y = []
        for x in x_vals:
            row = counts[(counts[x_key] == x) & (counts[series_key] == s)]
            y.append(int(row["count"].sum()) if not row.empty else 0)
        c = series_colors[str(s)]
        fig.add_trace(
            go.Bar(
                name=str(s),
                x=x_vals,
                y=y,
                marker=dict(color=c),
                hovertemplate="%{x}<br>%{fullData.name}<br>人数: %{y}<extra></extra>",
            )
        )

    min_w = _bar_chart_min_width(len(x_vals), len(color_dim))
    fig.update_layout(
        barmode="group",
        template="plotly_white",
        colorway=_extended_color_palette(),
        xaxis_title=x_title,
        yaxis_title="人数",
        legend_title_text=legend_title,
        height=BAR_CHART_HEIGHT,
        width=min_w,
        autosize=False,
        margin=dict(l=48, r=24, t=48, b=120),
        xaxis=dict(tickangle=-35),
    )
    return fig, min_w


def plot_pies_row(
    counts: pd.DataFrame,
    period_order: list[str],
    dimension: str,
) -> tuple[go.Figure, int]:
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
        fig.update_layout(height=PIE_ROW_HEIGHT, width=900, autosize=False)
        return fig, 900

    n = len(periods)
    all_labels = sorted(counts["_cat"].astype(str).unique().tolist())
    pie_cat_colors = category_colors_for_dimension(dimension, all_labels)

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
        slice_colors = [pie_cat_colors.get(str(lab), "#999999") for lab in labels]
        fig.add_trace(
            go.Pie(
                labels=labels,
                values=values,
                name=per,
                marker=dict(colors=slice_colors),
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

    min_w = _pie_row_min_width(n)
    fig.update_layout(
        template="plotly_white",
        showlegend=False,
        height=PIE_ROW_HEIGHT,
        width=min_w,
        autosize=False,
        margin=dict(l=24, r=24, t=60, b=24),
        title_text=f"項目: {dimension}",
    )
    return fig, min_w


def main():
    ensure_password_gate()

    st.title("属性別流入ダッシュボード_ライト版")
    st.caption("26/3/2時点の顧客管理シートより作成。左側の「表示形式」を選択しグラフを反映させます。")

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

    st.sidebar.header("表示形式")
    base_mode = st.sidebar.radio(
        "①（ベース）",
        ["FC件数ベース", "入会件数ベース"],
        horizontal=True,
    )
    time_mode = st.sidebar.radio(
        "②（時間軸）",
        ["年別", "半年ごと"],
        horizontal=True,
    )

    dimension = st.sidebar.radio(
        "表示する項目",
        ["年齢", "性別", "CEFR", "年齢×性別", "性別×CEFR"],
        horizontal=True,
    )

    st.session_state.setdefault("exclude_unknown", False)
    if st.sidebar.button(
        "「不明」除去&表示" if st.session_state.exclude_unknown else "「不明」除去&表示",
        use_container_width=True,
        key="btn_exclude_unknown",
    ):
        st.session_state.exclude_unknown = not st.session_state.exclude_unknown
    exclude_unknown = bool(st.session_state.exclude_unknown)

    st.sidebar.markdown("---")
    if st.sidebar.button("ログアウト", use_container_width=True):
        st.session_state.pop("auth_ok", None)
        st.rerun()

    counts, period_order = build_counts(
        raw, base_mode, time_mode, dimension, exclude_unknown=exclude_unknown
    )
    if counts.empty and not raw.empty:
        st.warning("日付が取れる行がありません。`FC実施年月日` を確認してください。")

    tab_bar, tab_pie = st.tabs(["棒グラフ", "円グラフ"])

    with tab_bar:
        bar_axis = st.radio(
            "棒グラフの軸",
            ["時間を横軸（項目で色分け）", "項目を横軸（時間で色分け）"],
            horizontal=True,
        )
        fig_bar, bar_w = plot_grouped_bar(counts, period_order, dimension, bar_axis)
        render_plotly_horizontal_scroll(
            fig_bar,
            height=BAR_CHART_HEIGHT,
            min_width=bar_w,
        )

    with tab_pie:
        if not counts.empty:
            present = set(counts["_cat"].astype(str).unique().tolist())
            cm = category_colors_for_dimension(dimension, list(present))
            legend_items = [
                (lab, cm.get(lab, "#999999"))
                for lab in ordered_legend_labels(dimension, present)
            ]
            render_category_legend_swatches(
                legend_title_for_dimension(dimension),
                legend_items,
            )
        fig_pie, pie_w = plot_pies_row(counts, period_order, dimension)
        render_plotly_horizontal_scroll(
            fig_pie,
            height=PIE_ROW_HEIGHT,
            min_width=pie_w,
        )


if __name__ == "__main__":
    main()
