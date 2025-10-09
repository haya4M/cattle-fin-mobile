import streamlit as st
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
from datetime import date

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
    # 月別集計と予測グラフ（リッチ＋オプション付き）
    # ===============================
    st.markdown("### 📈 月別収支（予測付き・前年比較）")
    
    import matplotlib.pyplot as plt
    
    # --- データ整形 ---
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
    
    # --- 昨年度以前の平均（月別） ---
    monthly_avg = past_data.groupby("month_num")["純収支"].mean()
    predicted = monthly_avg.to_frame(name="予測純収支")
    
    # --- グラフ描画（棒＋折れ線） ---
    fig, ax = plt.subplots(figsize=(7, 4))
    
    # 今年の実績
    ax.bar(this_year_data["month_num"], this_year_data["純収支"],
           color="#4C72B0", alpha=0.8, label=f"{current_year} 実績")
    
    # 前年実績
    if not prev_year_data.empty:
        ax.plot(prev_year_data["month_num"], prev_year_data["純収支"],
                color="gray", linestyle="-.", linewidth=2, marker="s", label=f"{prev_year} 実績")
    
    # 予測：今月まで実線
    months = predicted.index
    values = predicted["予測純収支"]
    
    ax.plot(months[months <= this_month], values[months <= this_month],
            color="red", marker="o", linestyle="-", linewidth=2, label="予測（〜今月）")
    
    # 予測：来月以降点線
    ax.plot(months[months > this_month], values[months > this_month],
            color="red", marker="o", linestyle="--", linewidth=2, label="予測（今後）")
    
    # 軸・装飾
    ax.set_title(f"{current_year} 年 月別純収支（前年比較＋予測）", fontsize=14, fontweight="bold")
    ax.set_xlabel("月", fontsize=12)
    ax.set_ylabel("金額（円）", fontsize=12)
    ax.set_xticks(range(1, 13))
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    st.pyplot(fig)
    
    
    # ===============================
    # 費目別の支出内訳グラフ
    # ===============================
    st.markdown("### 💰 費目別の支出内訳（円グラフ）")
    
    # 直近の年の支出データだけ抽出
    expense_df = df[(df["type"] == "支出") & (df["month"].str.startswith(current_year))]
    
    if expense_df.empty:
        st.info(f"{current_year}年の支出データがありません。")
    else:
        category_sum = expense_df.groupby("category")["amount"].sum().sort_values(ascending=False)
    
        # 円グラフ
        fig2, ax2 = plt.subplots(figsize=(6, 4))
        wedges, texts, autotexts = ax2.pie(
            category_sum,
            labels=category_sum.index,
            autopct="%1.1f%%",
            startangle=90,
            pctdistance=0.8,
            textprops={'fontsize': 10}
        )
        ax2.set_title(f"{current_year}年 支出の内訳", fontsize=13, fontweight="bold")
        st.pyplot(fig2)
    
    # CSV出力
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📤 CSVとして保存",
        data=csv,
        file_name="cattle_finance_data.csv",
        mime="text/csv"
    )

st.caption("© 2025 食肉牛DXプロジェクト - スマホ対応版")
