# TO RUN: streamlit run scripts/lancedb_viewer.py

import streamlit as st
import lancedb
import os

st.set_page_config(layout="wide")
st.title("LanceDB Viewer")

# 1. Connect to Database
db_path = st.text_input("Path to LanceDB folder", value=r"C:\Users\anyth\MINE\dev\scrappy\.scrappy\lancedb\jina")
# db_path = st.text_input("Path to LanceDB folder", value=r"C:\Users\anyth\MINE\dev\scrappy\.scrappy\lancedb\nomic")
# db_path = st.text_input("Path to LanceDB folder", value=r"C:\Users\anyth\MINE\dev\scrappy\.scrappy\lancedb")

if os.path.exists(db_path):
    db = lancedb.connect(db_path)
    tables = db.table_names()

    if tables:
        # 2. Select Table
        selected_table = st.selectbox("Select Table", tables)
        tbl = db.open_table(selected_table)

        # 3. Search / Filter
        limit = st.slider("Limit rows", 10, 1000, 100)

        # Load data
        df = tbl.search().limit(limit).to_pandas()

        # 4. Display
        st.write(f"Showing top {limit} rows from **{selected_table}**")
        st.dataframe(df)

        # Optional: Attempt to show images if an 'im_file' or 'path' column exists
        img_col = next((col for col in ['im_file', 'path', 'image_path'] if col in df.columns), None)
        if img_col:
            st.subheader("Image Preview")
            st.image(df[img_col].tolist()[:10], width=150)
    else:
        st.warning("No tables found in this database.")
else:
    st.error("Database path not found.")