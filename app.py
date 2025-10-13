import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
import plotly.express as px
import plotly.graph_objects as go
import matplotlib

# ======================================
# 日本語フォント設定
# ======================================
try:
    matplotlib.rcParams['font.family'] = 'IPAexGothic'
except Exception:
    matplotlib.rcParams['font.family'] = 'MS Gothic'

# ======================================
# ページ設定
# ======================================
st.set_page_config(
    page_title="食肉牛 収支管理",
    page_icon="🐮",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ======================================
# データベース関連関数（finance + headcount）
# ======================================
DB_FILE = "cattle_finance.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    # finance table
    c.execute('''
        CREATE TABLE IF NOT EXISTS finance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            month TEXT,
            category TEXT,
            type TEXT,
            amount REAL,
            note TEXT
        )
    ''')
    # headcount table: month (YYYY-MM) を主キーとして管理
    c.execute('''
        CREATE TABLE IF NOT EXISTS headcount (
            month TEXT PRIMARY KEY,
            headcount INTEGER,
            note TEXT
        )
    ''')
    conn.commit()
    return conn

def insert_data(conn, date_val, category, type_, amount, note):
    month = date_val.strftime("%Y-%m")
    conn.execute(
        "INSERT INTO finance (date, month, category, type, amount, note) VALUES (?, ?, ?, ?, ?, ?)",
        (str(date_val), month, category, type_, amount, note)
    )
    conn.commit()

def load_data(conn):
    return pd.read_sql("SELECT * FROM finance ORDER BY date DESC", conn)

def upsert_headcount(conn, month_key, headcount_val, note=""):
    """month_key: 'YYYY-MM' """
    c = conn.cursor()
    # try update first
    c.execute("SELECT COUNT(1) FROM headcount WHERE month = ?", (month_key,))
    exists = c.fetchone()[0] > 0
    if exists:
        c.execute("UPDATE headcount SET headcount = ?, note = ? WHERE month = ?", (headcount_val, note, month_key))
    else:
        c.execute("INSERT INTO headcount (month, headcount, note) VALUES (?, ?, ?)", (month_key, headcount_val, note))
    conn.commit()

def load_headcounts(conn):
    return pd.read_sql("SELECT * FROM headcount ORDER BY month DESC", conn)

# ======================================
# 共通ユーティリティ
# ======================================
def filter_by_year(df, selected_years):
    """選択された年度のみ抽出（df の month は 'YYYY-MM'）"""
    if df.empty or not selected_years:
        return pd.DataFrame()
    df = df.copy()
    df["year"] = df["month"].str[:4]
    return df[df["year"].isin(selected_years)]

# ======================================
# グラフ描画関数群
# ======================================
def plot_monthly_summary(df, head_df, selected_years):
    """月別純収支（前年比率付き）＋ 1頭あたり純収支ライン（頭数未登録月は除外）"""
    if df.empty:
        st.info("データがありません。")
        return

    # prepare summary: year, month_num, 純収支
    df2 = df.copy()
    df2["year"] = df2["month"].str[:4]
    df2["month_num"] = df2["month"].str[5:7].astype(int)
    summary = df2.groupby(["year", "month_num", "type"])["amount"].sum().unstack(fill_value=0)
    summary["純収支"] = summary.get("収入", 0) - summary.get("支出", 0)
    summary = summary.reset_index()  # columns: year, month_num, 収入, 支出, 純収支

    # Build month_key 'YYYY-MM' for merging headcounts
    summary["month_key"] = summary["year"] + "-" + summary["month_num"].apply(lambda x: f"{int(x):02d}")

    # headcounts DF -> dict
    head_map = {}
    if head_df is not None and not head_df.empty:
        head_map = dict(zip(head_df["month"], head_df["headcount"]))

    # merge headcount into summary
    summary["headcount"] = summary["month_key"].map(head_map).astype("Float64")  # allow NaN

    # compute per-head value where headcount > 0
    summary["per_head"] = summary.apply(lambda r: (r["純収支"] / r["headcount"]) if (pd.notna(r["headcount"]) and r["headcount"] != 0) else pd.NA, axis=1)

    # Filter by selected years
    summary_sel = summary[summary["year"].isin(selected_years)]

    if summary_sel.empty:
        st.info("選択した年度にデータがありません。")
        return

    # Plotly figure
    fig = go.Figure()
    colors = px.colors.qualitative.Set2

    # Bars: each selected year's 純収支
    for i, year in enumerate(selected_years):
        ydata = summary_sel[summary_sel["year"] == year].sort_values("month_num")
        if ydata.empty:
            continue
        fig.add_trace(go.Bar(
            x=ydata["month_num"],
            y=ydata["純収支"],
            name=f"{year} 純収支",
            marker_color=colors[i % len(colors)],
            opacity=0.85
        ))

    # Per-head traces: one line per selected year (use yaxis 'y2')
    for i, year in enumerate(selected_years):
        ydata = summary_sel[summary_sel["year"] == year].sort_values("month_num")
        per_head = ydata[["month_num", "per_head"]].dropna()
        if not per_head.empty:
            fig.add_trace(go.Scatter(
                x=per_head["month_num"],
                y=per_head["per_head"],
                mode="lines+markers",
                name=f"{year} 1頭あたり純収支",
                yaxis="y2",
                line=dict(width=3, dash="solid"),
                marker=dict(size=6)
            ))

    # 前年比率（%）ライン: 対象は選択年度の最新とその1つ前（sorted）
    if len(selected_years) >= 2:
        sel_sorted = sorted(selected_years)
        current = sel_sorted[-1]
        prev = sel_sorted[-2]
        cur_df = summary[summary["year"] == current].set_index("month_num")
        prev_df = summary[summary["year"] == prev].set_index("month_num")
        # calculate % change where prev exists and prev != 0
        compare = []
        months_common = sorted(set(cur_df.index).intersection(set(prev_df.index)))
        for m in months_common:
            prev_val = prev_df.at[m, "純収支"]
            cur_val = cur_df.at[m, "純収支"]
            if prev_val is None or prev_val == 0:
                continue
            pct = (cur_val / prev_val - 1) * 100
            compare.append((m, pct))
        if compare:
            cmp_df = pd.DataFrame(compare, columns=["month_num", "前年比(%)"]).sort_values("month_num")
            # plot on a second right axis (y3)
            fig.add_trace(go.Scatter(
                x=cmp_df["month_num"],
                y=cmp_df["前年比(%)"],
                mode="lines+markers",
                name=f"{current} 前年比（対{prev}）(%)",
                yaxis="y3",
                line=dict(color="red", width=3, dash="dash"),
                marker=dict(symbol="diamond", size=7)
            ))

    # layout: main y, y2 (per-head), y3 (前年比%)
    fig.update_layout(
        title=f"📈 月別純収支、1頭あたり純収支、前年比（{', '.join(selected_years)} 年）",
        xaxis=dict(title="月", tickmode="linear", dtick=1),
        yaxis=dict(title="純収支（円）"),
        template="plotly_dark",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
        bargap=0.2,
        margin=dict(t=80, b=120)
    )

    # define y2 (per-head, 円) on right, slightly left of y3
    fig.update_layout(
        yaxis2=dict(
            title="1頭あたり純収支（円）",
            overlaying="y",
            side="right",
            position=0.92,
            showgrid=False
        ),
        yaxis3=dict(
            title="前年比（％）",
            overlaying="y",
            side="right",
            position=0.98,
            showgrid=False,
            tickformat=".1f"
        )
    )

    # Need to explicitly map traces to yaxis2/yaxis3 - already assigned via trace.yaxis when adding traces
    st.plotly_chart(fig, use_container_width=True)


def plot_expense_pie(df, selected_years):
    """費目別支出内訳（複数年度横並び）"""
    df_sel = filter_by_year(df, selected_years)
    expense_df = df_sel[df_sel["type"] == "支出"]

    if expense_df.empty:
        st.info("選択された年度の支出データがありません。")
        return

    st.markdown("### 💰 費目別支出内訳（年度比較）")

    n_years = len(selected_years)
    n_cols = 3 if n_years >= 3 else n_years
    year_chunks = [selected_years[i:i+n_cols] for i in range(0, n_years, n_cols)]

    for chunk in year_chunks:
        cols = st.columns(len(chunk))
        for col, year in zip(cols, chunk):
            with col:
                year_data = expense_df[expense_df["month"].str[:4] == year]
                cat_sum = year_data.groupby("category")["amount"].sum().reset_index()
                if cat_sum.empty:
                    st.write(f"🟡 {year}：データなし")
                    continue
                fig = px.pie(
                    cat_sum,
                    names="category",
                    values="amount",
                    title=f"{year} 年",
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig.update_traces(textinfo="percent+label", pull=[0.05]*len(cat_sum))
                st.plotly_chart(fig, use_container_width=True)


def plot_trend(df, selected_years):
    """収入・支出トレンド"""
    df_sel = filter_by_year(df, selected_years)
    if df_sel.empty:
        st.info("選択された年度のデータがありません。")
        return

    trend_df = df_sel.groupby(["month", "type"])["amount"].sum().reset_index()
    trend_df["month_num"] = trend_df["month"].str[5:7].astype(int)

    fig = px.line(
        trend_df,
        x="month_num",
        y="amount",
        color="type",
        markers=True,
        line_dash="type",
        color_discrete_map={"収入": "#2E86DE", "支出": "#E74C3C"},
        title=f"📉 月別 収入・支出トレンド（{', '.join(selected_years)} 年）",
        template="plotly_dark"
    )
    fig.update_layout(xaxis_title="月", yaxis_title="金額（円）", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def plot_category_trend(df, selected_years):
    """費目別支出トレンド比較"""
    df_sel = filter_by_year(df, selected_years)
    expense_df = df_sel[df_sel["type"] == "支出"]

    if expense_df.empty:
        st.info("選択された年度の支出データがありません。")
        return

    category_trend = expense_df.groupby(["month", "category"])["amount"].sum().reset_index()
    category_trend["month_num"] = category_trend["month"].str[5:7].astype(int)

    fig = px.line(
        category_trend,
        x="month_num",
        y="amount",
        color="category",
        markers=True,
        title=f"📊 費目別 支出トレンド（{', '.join(selected_years)} 年）",
        template="plotly_dark"
    )
    fig.update_layout(xaxis_title="月", yaxis_title="金額（円）", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

# ======================================
# データ入力フォーム（finance）および頭数フォーム（headcount）
# ======================================
def data_input_form(conn):
    with st.expander("📥 新規データ入力（収支）", expanded=False):
        date_val = st.date_input("日付", value=date.today())
        category = st.selectbox(
            "費目",
            ["飼料費", "光熱水費", "獣医費", "子牛購入費", "牛売上", "補助金", "地価費", "人件費", "その他"]
        )
        type_ = st.radio("区分", ["支出", "収入"], horizontal=True)
        amount = st.number_input("金額（円）", min_value=0, step=1000)
        note = st.text_input("備考", placeholder="例：配合飼料、子牛販売 など")

        if st.button("💾 登録する（収支）"):
            insert_data(conn, date_val, category, type_, amount, note)
            st.success("収支データを登録しました ✅")

def headcount_input_form(conn):
    with st.expander("🐮 月別頭数登録 / 更新", expanded=False):
        # use a date_input but store only year-month
        date_for_month = st.date_input("対象月を選択（任意の日付を選び、その月を使用）", value=date.today())
        month_key = date_for_month.strftime("%Y-%m")
        headcount_val = st.number_input("頭数（整数）", min_value=0, step=1, value=0)
        note = st.text_input("備考（任意）", placeholder="例：計測日時、メモなど")

        if st.button("💾 登録する（頭数）"):
            # We treat 0 as valid (but per spec, headcount==0 will exclude per-head calculation)
            upsert_headcount(conn, month_key, int(headcount_val), note)
            st.success(f"{month_key} の頭数を登録／更新しました ✅")

# ======================================
# メインアプリ
# ======================================
def main():
    st.title("🐮 食肉牛 収支管理（スマホ対応）")
    st.caption("Streamlit Cloudでどこからでも入力OK📱")

    conn = init_db()
    df = load_data(conn)
    head_df = load_headcounts(conn)

    # === 年度選択 ===
    available_years = []
    if df is not None and not df.empty:
        available_years = sorted(df["month"].str[:4].unique().tolist())
    current_year = str(date.today().year)
    # default selection: current year if present, else last available
    default_sel = [current_year] if current_year in available_years else ([available_years[-1]] if available_years else [])

    selected_years = st.multiselect(
        "📆 表示する年度を選択（複数可）",
        available_years,
        default=default_sel
    )

    if not selected_years and available_years:
        st.warning("少なくとも1つの年度を選択してください。")
        # still allow continuing to show forms; return would block forms
    # === 先にグラフを表示 ===
    if df is None or df.empty:
        st.info("まだ収支データが登録されていません。下のフォームから追加してください。")
    else:
        st.markdown("### 📊 収支グラフ分析")
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 月別収支＋前年比＋1頭あたり",
            "💰 費目別支出内訳（比較）",
            "📉 収入・支出トレンド",
            "📊 費目別トレンド比較"
        ])

        with tab1:
            if selected_years:
                plot_monthly_summary(df, head_df, selected_years)
            else:
                st.info("表示する年度を選択してください。")

        with tab2:
            if selected_years:
                plot_expense_pie(df, selected_years)
            else:
                st.info("表示する年度を選択してください。")

        with tab3:
            if selected_years:
                plot_trend(df, selected_years)
            else:
                st.info("表示する年度を選択してください。")

        with tab4:
            if selected_years:
                plot_category_trend(df, selected_years)
            else:
                st.info("表示する年度を選択してください。")
            # CSVダウンロード（全データ）
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📤 CSVとして保存", csv, "cattle_finance_data.csv", "text/csv")

    # === 次に入力フォーム（収支 + 頭数） ===
    data_input_form(conn)
    headcount_input_form(conn)

    # === 最後に登録データ表示 ===
    st.markdown("### 📋 登録済みデータ（収支）")
    if df is None or df.empty:
        st.info("まだ収支データが登録されていません。")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### 🐮 月別頭数データ")
    if head_df is None or head_df.empty:
        st.info("頭数データが登録されていません。")
    else:
        st.dataframe(head_df, use_container_width=True, hide_index=True)

    st.caption("© 2025 食肉牛DXプロジェクト - スマホ対応版")

# ======================================
# 実行
# ======================================
if __name__ == "__main__":
    main()
