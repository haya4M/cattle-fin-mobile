import streamlit as st
import pandas as pd
import sqlite3
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
        ["飼料費", "電気代", "水道代", "獣医費", "子牛購入費", "牛売上", "補助金", "地価費", "その他"]
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

    # 月別集計
    st.markdown("### 📈 月別収支")
    summary = df.groupby(["month", "type"])["amount"].sum().unstack(fill_value=0)
    summary["純収支"] = summary.get("収入", 0) - summary.get("支出", 0)
    st.bar_chart(summary["純収支"])

    # CSV出力
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📤 CSVとして保存",
        data=csv,
        file_name="cattle_finance_data.csv",
        mime="text/csv"
    )

st.caption("© 2025 食肉牛DXプロジェクト - スマホ対応版")
