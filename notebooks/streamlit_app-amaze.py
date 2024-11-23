import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import List, Dict, Optional
import numpy as np
from datetime import datetime
import os
import sys
import gc

# Force garbage collection
gc.collect()

# Initialize session state
if 'db_conn' not in st.session_state:
    st.session_state.db_conn = None

# Set page configuration
st.set_page_config(
    page_title="Microbiome Database Explorer",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database connection with robust error handling
def init_database():
    """Initialize database connection with proper error handling"""
    if st.session_state.db_conn is not None:
        return st.session_state.db_conn
        
    try:
        # Import DuckDB here to avoid immediate loading
        import duckdb
        
        # Set DuckDB config before connecting
        db_path = '../hmp_microbiome.duckdb'
        
        if not os.path.exists(db_path):
            st.error(f"Database file not found at {db_path}")
            st.info("Please ensure the database file exists and try again.")
            return None
            
        # Try to connect with memory settings
        conn = duckdb.connect(db_path, read_only=True, config={'memory_limit': '4GB'})
        
        # Test connection
        conn.execute("SELECT 1").fetchall()
        
        st.session_state.db_conn = conn
        return conn
        
    except ImportError:
        st.error("Failed to import DuckDB. Please ensure it's installed correctly:")
        st.code("pip install duckdb==0.9.2")
        return None
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        st.info("Try restarting the application with:")
        st.code("streamlit run streamlit_app.py --server.maxUploadSize 1024")
        return None

# Safe query execution
def run_query(conn, query: str) -> Optional[pd.DataFrame]:
    if conn is None:
        return None
        
    try:
        return conn.execute(query).fetchdf()
    except Exception as e:
        st.error(f"Query failed: {str(e)}")
        return None

def main():
    try:
        st.title("🧬 Microbiome Database Explorer")
        
        # Initialize database connection
        conn = init_database()
        if conn is None:
            st.warning("Please fix the database connection issues above to continue.")
            st.stop()
            
        # Get available tables
        try:
            tables_df = run_query(conn, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main';")
            if tables_df is None:
                tables = ["organisms", "genes", "gene_qualifiers", "sequences"]
            else:
                tables = tables_df['table_name'].tolist()
        except:
            tables = ["organisms", "genes", "gene_qualifiers", "sequences"]

        # Sidebar
        st.sidebar.header("📊 Query Configuration")
        
        table = st.sidebar.selectbox(
            "Select Table:",
            tables,
            help="Choose a table to explore"
        )
        
        # Get columns for selected table
        try:
            schema_query = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}';"
            columns_df = run_query(conn, schema_query)
            columns = columns_df['column_name'].tolist() if columns_df is not None else []
        except:
            columns = []
            st.warning(f"Could not fetch columns for table {table}")

        # Column selection
        selected_columns = st.sidebar.multiselect(
            "Select Columns:",
            columns,
            default=columns[:5] if columns else None
        )

        # Simple query builder
        limit = st.sidebar.slider("Number of rows:", 5, 100, 10)
        
        # Main content area
        tab1, tab2 = st.tabs(["📋 Data View", "🔍 SQL Query"])
        
        with tab1:
            if selected_columns:
                query = f"""
                SELECT {', '.join(selected_columns)}
                FROM {table}
                LIMIT {limit};
                """
            else:
                query = f"SELECT * FROM {table} LIMIT {limit};"
                
            data = run_query(conn, query)
            
            if data is not None:
                st.dataframe(data)
                
                # Download options
                if st.button("Download as CSV"):
                    csv = data.to_csv(index=False)
                    st.download_button(
                        "Click to Download",
                        csv,
                        f"{table}_data.csv",
                        "text/csv"
                    )
        
        with tab2:
            st.subheader("Custom SQL Query")
            custom_query = st.text_area(
                "Enter your SQL query:",
                value=f"SELECT * FROM {table} LIMIT 5;"
            )
            
            if st.button("Run Query"):
                results = run_query(conn, custom_query)
                if results is not None:
                    st.dataframe(results)

    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")
        st.info("Please try restarting the application. If the error persists, check the following:")
        st.markdown("""
        1. Ensure DuckDB is installed correctly: `pip install duckdb==0.9.2`
        2. Check if the database file exists and is accessible
        3. Try running with less memory usage: `streamlit run streamlit_app.py --server.maxUploadSize 512`
        """)

if __name__ == "__main__":
    main()