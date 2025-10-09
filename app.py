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
# データベース関連関数
# ======================================
def init_db():
    conn = sqlite3.connect("cattle_finance.db")
    c = conn.cursor()
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

# ======================================
# 共通ユーティリティ
# ======================================
def filter_by_year(df, selected_years):
    """選択された年度のみ抽出"""
    if df.empty:
        return df
    df["year"] = df["month"].str[:4]
    return df[df["year"].isin(selected_years)]

# ======================================
# グラフ描画関数群
# ======================================
def plot_monthly_summary(df, selected_years):
    """月別純収支（前年比率付き）"""
    if df.empty:
        st.info("データがありません。")
        return

    df["year"] = df["month"].str[:4]
    df["month_num"] = df["month"].str[5:7].astype(int)
    summary = df.groupby(["year", "month_num", "type"])["amount"].sum().unstack(fill_value=0)
    summary["純収支"] = summary.get("収入", 0) - summary.get("支出", 0)
    summary = summary.reset_index()

    fig = go.Figure()
    colors = px.colors.qualitative.Set2

    for i, year in enumerate(selected_years):
        data_y = summary[summary["year"] == year]
        fig.add_trace(go.Bar(
            x=data_y["month_num"],
            y=data_y["純収支"],
            name=f"{year} 純収支",
            marker_color=colors[i % len(colors)],
            opacity=0.85
        ))

    # === 前年比率ライン ===
    if len(selected_years) >= 2:
        selected_years_sorted = sorted(selected_years)
        current = selected_years_sorted[-1]
        prev = selected_years_sorted[-2]

        current_data = summary[summary["year"] == current].set_index("month_num")
        prev_data = summary[summary["year"] == prev].set_index("month_num")

        compare = pd.DataFrame({
            "前年比(%)": (current_data["純収支"] / prev_data["純収支"] - 1) * 100
        }).dropna()

        if not compare.empty:
            fig.add_trace(go.Scatter(
                x=compare.index,
                y=compare["前年比(%)"],
                mode="lines+markers",
                name=f"{current} 前年比率（対 {prev}）",
                yaxis="y2",
                line=dict(color="red", width=3)
            ))

    fig.update_layout(
        title=f"📈 月別純収支と前年比率（{', '.join(selected_years)} 年）",
        xaxis_title="月",
        yaxis_title="純収支（円）",
        yaxis2=dict(title="前年比（％）", overlaying="y", side="right", showgrid=False),
        template="plotly_dark",
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.3, x=0.5, xanchor="center")
    )
    st.plotly_chart(fig, use_container_width=True)


def plot_expense_pie(df, selected_years):
    """費目別支出内訳（複数年度横並び）"""
    df = filter_by_year(df, selected_years)
    expense_df = df[df["type"] == "支出"]

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
    df = filter_by_year(df, selected_years)
    if df.empty:
        st.info("選択された年度のデータがありません。")
        return

    trend_df = df.groupby(["month", "type"])["amount"].sum().reset_index()
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
    df = filter_by_year(df, selected_years)
    expense_df = df[df["type"] == "支出"]

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
# データ入力フォーム
# ======================================
def data_input_form(conn):
    with st.expander("📥 新規データ入力", expanded=False):
        date_val = st.date_input("日付", value=date.today())
        category = st.selectbox(
            "費目",
            ["飼料費", "光熱水費", "獣医費", "子牛購入費", "牛売上", "補助金", "地価費", "人件費", "その他"]
        )
        type_ = st.radio("区分", ["支出", "収入"], horizontal=True)
        amount = st.number_input("金額（円）", min_value=0, step=1000)
        note = st.text_input("備考", placeholder="例：配合飼料、子牛販売 など")

        if st.button("💾 登録する"):
            insert_data(conn, date_val, category, type_, amount, note)
            st.success("登録しました ✅")

# ======================================
# メインアプリ
# ======================================
def main():
    st.title("🐮 食肉牛 収支管理（スマホ対応）")
    st.caption("Streamlit Cloudでどこからでも入力OK📱")

    conn = init_db()
    df = load_data(conn)

    # === 年度選択 ===
    if not df.empty:
        available_years = sorted(df["month"].str[:4].unique().tolist())
        current_year = str(date.today().year)
        selected_years = st.multiselect(
            "📆 表示する年度を選択",
            available_years,
            default=[current_year] if current_year in available_years else [available_years[-1]]
        )
        if not selected_years:
            st.warning("少なくとも1つの年度を選択してください。")
            return
    else:
        st.info("まだデータが登録されていません。下のフォームから追加してください。")
        selected_years = []

    # === 先にグラフを表示 ===
    if not df.empty:
        st.markdown("### 📊 収支グラフ分析")
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 月別収支＋前年比率",
            "💰 費目別支出内訳（比較）",
            "📉 収入・支出トレンド",
            "📊 費目別トレンド比較"
        ])

        with tab1:
            plot_monthly_summary(df, selected_years)
        with tab2:
            plot_expense_pie(df, selected_years)
        with tab3:
            plot_trend(df, selected_years)
        with tab4:
            plot_category_trend(df, selected_years)
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📤 CSVとして保存", csv, "cattle_finance_data.csv", "text/csv")

    # === 次にデータ入力フォーム ===
    data_input_form(conn)

    # === 最後に登録データ表示 ===
    st.markdown("### 📋 登録済みデータ")
    if df.empty:
        st.info("まだデータが登録されていません。")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption("© 2025 食肉牛DXプロジェクト - スマホ対応版")

# ======================================
# 実行
# ======================================
if __name__ == "__main__":
    main()
