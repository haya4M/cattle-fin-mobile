import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
import plotly.express as px
import plotly.graph_objects as go
import matplotlib
import matplotlib.font_manager as fm

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
# データ入力フォーム
# ======================================
def data_input_form(conn):
    with st.expander("📥 新規データ入力", expanded=True):
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
# グラフ描画関数群
# ======================================
def plot_monthly_summary(df):
    summary = df.groupby(["month", "type"])["amount"].sum().unstack(fill_value=0)
    summary["純収支"] = summary.get("収入", 0) - summary.get("支出", 0)
    summary = summary.sort_index()
    summary["year"] = summary.index.str[:4]
    summary["month_num"] = summary.index.str[5:7].astype(int)

    current_year = str(date.today().year)
    prev_year = str(date.today().year - 1)
    this_month = date.today().month

    past_data = summary[summary["year"] < current_year]
    this_year_data = summary[summary["year"] == current_year]
    prev_year_data = summary[summary["year"] == prev_year]

    monthly_avg = past_data.groupby("month_num")["純収支"].mean()
    predicted = monthly_avg.to_frame(name="予測純収支")

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=this_year_data["month_num"],
        y=this_year_data["純収支"],
        name=f"{current_year} 実績",
        marker_color="#4C72B0",
        opacity=0.85
    ))

    if not prev_year_data.empty:
        fig.add_trace(go.Scatter(
            x=prev_year_data["month_num"],
            y=prev_year_data["純収支"],
            mode="lines+markers",
            name=f"{prev_year} 実績",
            line=dict(color="gray", dash="dot", width=2),
            marker=dict(symbol="square")
        ))

    months = predicted.index
    values = predicted["予測純収支"]

    fig.add_trace(go.Scatter(
        x=months[months <= this_month],
        y=values[months <= this_month],
        mode="lines+markers",
        name="予測（〜今月）",
        line=dict(color="red", width=3)
    ))

    fig.add_trace(go.Scatter(
        x=months[months > this_month],
        y=values[months > this_month],
        mode="lines+markers",
        name="予測（今後）",
        line=dict(color="red", width=3, dash="dash")
    ))

    fig.update_layout(
        title=f"{current_year} 年 月別純収支（予測＋前年比）",
        xaxis_title="月",
        yaxis_title="金額（円）",
        template="plotly_dark",
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.3, x=0.5, xanchor="center"),
        bargap=0.2
    )
    st.plotly_chart(fig, use_container_width=True)


def plot_expense_pie(df):
    current_year = str(date.today().year)
    expense_df = df[(df["type"] == "支出") & (df["month"].str.startswith(current_year))]

    if expense_df.empty:
        st.info(f"{current_year}年の支出データがありません。")
        return

    category_summary = expense_df.groupby("category")["amount"].sum().reset_index()
    fig = px.pie(
        category_summary,
        names="category",
        values="amount",
        title=f"{current_year}年 費目別支出内訳",
        color_discrete_sequence=px.colors.qualitative.Set3,
    )
    fig.update_traces(textinfo="percent+label", pull=[0.05]*len(category_summary))
    st.plotly_chart(fig, use_container_width=True)


def plot_trend(df):
    trend_df = df.groupby(["month", "type"])["amount"].sum().reset_index()
    trend_df["month_num"] = trend_df["month"].str[5:7].astype(int)

    fig = px.line(
        trend_df,
        x="month_num",
        y="amount",
        color="type",
        markers=True,
        color_discrete_map={"収入": "#2E86DE", "支出": "#E74C3C"},
        title="月別 収入・支出 トレンド",
        template="plotly_dark"
    )
    fig.update_layout(xaxis_title="月", yaxis_title="金額（円）", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def plot_category_trend(df):
    current_year = str(date.today().year)
    expense_df = df[(df["type"] == "支出") & (df["month"].str.startswith(current_year))]

    if expense_df.empty:
        st.info(f"{current_year}年の支出データがありません。")
        return

    category_trend = expense_df.groupby(["month", "category"])["amount"].sum().reset_index()
    category_trend["month_num"] = category_trend["month"].str[5:7].astype(int)

    fig = px.line(
        category_trend,
        x="month_num",
        y="amount",
        color="category",
        markers=True,
        title=f"{current_year}年 費目別 支出トレンド",
        template="plotly_dark"
    )
    fig.update_layout(xaxis_title="月", yaxis_title="金額（円）", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

# ======================================
# メインアプリ
# ======================================
def main():
    st.title("🐮 食肉牛 収支管理（スマホ対応）")
    st.caption("Streamlit Cloudでどこからでも入力OK📱")

    conn = init_db()
    data_input_form(conn)

    df = load_data(conn)
    st.markdown("### 📋 登録済みデータ")
    if df.empty:
        st.info("まだデータが登録されていません。")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### 📊 収支グラフ分析")
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 月別収支（予測＋前年比）",
        "💰 費目別支出内訳",
        "📉 収入・支出トレンド",
        "📊 費目別トレンド比較"
    ])

    with tab1:
        plot_monthly_summary(df)
    with tab2:
        plot_expense_pie(df)
    with tab3:
        plot_trend(df)
    with tab4:
        plot_category_trend(df)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📤 CSVとして保存", csv, "cattle_finance_data.csv", "text/csv")

    st.caption("© 2025 食肉牛DXプロジェクト - スマホ対応版")

# ======================================
# 実行
# ======================================
if __name__ == "__main__":
    main()
