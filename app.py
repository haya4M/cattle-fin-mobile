import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
import plotly.express as px
import plotly.graph_objects as go
import matplotlib
import matplotlib.font_manager as fm

# ======================================
# 日本語フォント設定（バックアップ用途）
# ======================================
try:
    matplotlib.rcParams['font.family'] = 'IPAexGothic'
except:
    # Windowsの場合（MSゴシックがあれば）
    matplotlib.rcParams['font.family'] = 'MS Gothic'

# ===============================
# ページ設定（スマホ最適化）
# ===============================
st.set_page_config(
    page_title="食肉牛 収支管理",
    page_icon="🐮",
    layout="centered",  # スマホ表示に最適
    initial_sidebar_state="collapsed"
)

# ===============================
# データベース初期化
# ===============================
conn = sqlite3.connect('cattle_finance.db')
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

# ===============================
# タイトル
# ===============================
st.title("🐮 食肉牛 収支管理（スマホ対応）")
st.caption("Streamlit Cloudでどこからでも入力OK📱")

# ===============================
# データ入力フォーム（折りたたみ式）
# ===============================
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
        month = date_val.strftime("%Y-%m")
        c.execute(
            "INSERT INTO finance (date, month, category, type, amount, note) VALUES (?,?,?,?,?,?)",
            (str(date_val), month, category, type_, amount, note)
        )
        conn.commit()
        st.success("登録しました ✅")

# ===============================
# データ表示
# ===============================
st.markdown("### 📋 登録済みデータ")

df = pd.read_sql("SELECT * FROM finance ORDER BY date DESC", conn)
if df.empty:
    st.info("まだデータが登録されていません。")
else:
    st.dataframe(df, use_container_width=True, hide_index=True)

# ===============================
# グラフ表示（タブ切り替え付き）
# ===============================
import matplotlib.pyplot as plt

st.markdown("### 📊 収支グラフ分析")

tab1, tab2, tab3, tab4 = st.tabs([
    "📈 月別収支（予測＋前年比）",
    "💰 費目別支出内訳",
    "📉 収入・支出トレンド",
    "📊 費目別トレンド比較"
])

# ----------------------------------------------------------------------
# 📈 タブ1：月別収支（予測＋前年比）
# ----------------------------------------------------------------------
with tab1:
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

    fig, ax = plt.subplots(figsize=(7, 4))

    # 棒：今年の実績
    ax.bar(this_year_data["month_num"], this_year_data["純収支"],
           color="#4C72B0", alpha=0.8, label=f"{current_year} 実績")

    # 折れ線：前年実績
    if not prev_year_data.empty:
        ax.plot(prev_year_data["month_num"], prev_year_data["純収支"],
                color="gray", linestyle="-.", linewidth=2, marker="s", label=f"{prev_year} 実績")

    # 折れ線：予測（実線＋点線）
    months = predicted.index
    values = predicted["予測純収支"]
    ax.plot(months[months <= this_month], values[months <= this_month],
            color="red", marker="o", linestyle="-", linewidth=2, label="予測（〜今月）")
    ax.plot(months[months > this_month], values[months > this_month],
            color="red", marker="o", linestyle="--", linewidth=2, label="予測（今後）")

    ax.set_title(f"{current_year} 年 月別純収支（予測＋前年比）", fontsize=14, fontweight="bold")
    ax.set_xlabel("月")
    ax.set_ylabel("金額（円）")
    ax.set_xticks(range(1, 13))
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    st.pyplot(fig)


# ----------------------------------------------------------------------
# 💰 タブ2：費目別支出内訳（円グラフ）
# ----------------------------------------------------------------------
with tab2:
    st.markdown("#### 💰 費目別支出内訳")

    current_year = str(date.today().year)
    expense_df = df[(df["type"] == "支出") & (df["month"].str.startswith(current_year))]

    if expense_df.empty:
        st.info(f"{current_year}年の支出データがありません。")
    else:
        category_summary = expense_df.groupby("category")["amount"].sum().reset_index()
        fig2 = px.pie(
            category_summary,
            names="category",
            values="amount",
            title=f"{current_year}年 費目別支出内訳",
            color_discrete_sequence=px.colors.qualitative.Set3,
        )
        fig2.update_traces(textinfo="percent+label", pull=[0.05]*len(category_summary))
        st.plotly_chart(fig2, use_container_width=True)

# ----------------------------------------------------------------------
# 📉 タブ3：収入・支出トレンド折れ線グラフ
# ----------------------------------------------------------------------
with tab3:
    st.markdown("#### 📉 収入・支出トレンド")

    trend_df = df.groupby(["month", "type"])["amount"].sum().reset_index()
    trend_df["year"] = trend_df["month"].str[:4]
    trend_df["month_num"] = trend_df["month"].str[5:7].astype(int)

    fig3 = px.line(
        trend_df,
        x="month_num",
        y="amount",
        color="type",
        line_dash="type",
        markers=True,
        color_discrete_map={"収入": "#2E86DE", "支出": "#E74C3C"},
        title="月別 収入・支出 トレンド",
    )
    fig3.update_layout(
        xaxis_title="月",
        yaxis_title="金額（円）",
        template="plotly_dark",  # ★背景を黒ベースでリッチに
        hovermode="x unified"
    )
    st.plotly_chart(fig3, use_container_width=True)

# ===============================
# 📈 タブ4：費目別の支出トレンド折れ線グラフ
# ===============================
with tab4:
    st.markdown("#### 📊 費目別トレンド比較")

    current_year = str(date.today().year)
    expense_df = df[(df["type"] == "支出") & (df["month"].str.startswith(current_year))]

    if expense_df.empty:
        st.info(f"{current_year}年の支出データがありません。")
    else:
        category_trend = expense_df.groupby(["month", "category"])["amount"].sum().reset_index()
        category_trend["month_num"] = category_trend["month"].str[5:7].astype(int)

        fig4 = px.line(
            category_trend,
            x="month_num",
            y="amount",
            color="category",
            markers=True,
            title=f"{current_year}年 費目別 支出トレンド",
            template="plotly_dark",
        )
        fig4.update_layout(
            xaxis_title="月",
            yaxis_title="金額（円）",
            hovermode="x unified",
            legend_title="費目"
        )
        st.plotly_chart(fig4, use_container_width=True)

    # CSV出力
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📤 CSVとして保存",
        data=csv,
        file_name="cattle_finance_data.csv",
        mime="text/csv"
    )

st.caption("© 2025 食肉牛DXプロジェクト - スマホ対応版")
