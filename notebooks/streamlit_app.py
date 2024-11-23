# streamlit_app.py

import streamlit as st
import duckdb
import pandas as pd

# Connect to DuckDB database
conn = duckdb.connect('../hmp_microbiome.duckdb')

# Streamlit app starts here
def main():
    st.title("DuckDB Interactive Query App")
    st.markdown("This app allows you to query the microbiome database interactively!")

    # Sidebar for user input
    st.sidebar.header("Query Options")
    table = st.sidebar.selectbox("Select a table to query:", ["organisms", "genes", "gene_qualifiers", "sequences"])
    limit = st.sidebar.slider("Number of rows to display:", min_value=5, max_value=100, value=10)

    # Display table preview
    st.subheader(f"Preview of `{table}` Table")
    query = f"SELECT * FROM {table} LIMIT {limit};"
    df = conn.execute(query).fetchdf()
    st.dataframe(df)

    # Custom SQL Query Section
    st.subheader("Run Custom SQL Query")
    custom_query = st.text_area("Enter your SQL query below:", value="SELECT * FROM organisms LIMIT 5;")
    
    if st.button("Run Query"):
        try:
            result = conn.execute(custom_query).fetchdf()
            st.dataframe(result)
        except Exception as e:
            st.error(f"Error: {e}")

    # Visualization Example: Genome Size Distribution
    if table == "organisms":
        st.subheader("Genome Size Distribution")
        genome_query = """
        SELECT genome_size 
        FROM organisms;
        """
        genome_data = conn.execute(genome_query).fetchdf()
        st.bar_chart(genome_data['genome_size'])

if __name__ == "__main__":
    main()