import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.figure_factory as ff
from typing import List, Dict, Optional, Tuple
import numpy as np
from datetime import datetime
import os
import sys
import gc
import seaborn as sns
from scipy import stats

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

# Visualization utilities
def get_column_type(df: pd.DataFrame, column: str) -> str:
    """Determine the type of data in a column"""
    if df[column].dtype in ['int64', 'float64']:
        if len(df[column].unique()) < 10:
            return 'categorical_numeric'
        return 'numeric'
    elif df[column].dtype == 'bool':
        return 'boolean'
    elif pd.api.types.is_datetime64_any_dtype(df[column]):
        return 'datetime'
    else:
        if len(df[column].unique()) < 10:
            return 'categorical'
        return 'text'

def create_distribution_plot(df: pd.DataFrame, column: str) -> go.Figure:
    """Create an appropriate distribution plot based on data type"""
    col_type = get_column_type(df, column)
    
    if col_type == 'numeric':
        # Create both histogram and box plot
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=df[column], name='Distribution', histnorm='probability'))
        fig.add_trace(go.Box(x=df[column], name='Box Plot', boxpoints='outliers'))
        fig.update_layout(title=f'Distribution of {column}', bargap=0.1)
    elif col_type in ['categorical', 'categorical_numeric', 'boolean']:
        # Create bar chart for categories
        value_counts = df[column].value_counts()
        fig = go.Figure(go.Bar(x=value_counts.index, y=value_counts.values))
        fig.update_layout(title=f'Distribution of {column}', xaxis_title=column, yaxis_title='Count')
    else:
        # Create text summary for other types
        fig = go.Figure()
        fig.add_annotation(text="Text or datetime field - distribution not applicable",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    
    fig.update_layout(height=400, width=700)
    return fig

def create_correlation_plot(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    """Create correlation plot based on data types"""
    x_type = get_column_type(df, x_col)
    y_type = get_column_type(df, y_col)
    
    if x_type == 'numeric' and y_type == 'numeric':
        # Scatter plot with regression line
        fig = px.scatter(df, x=x_col, y=y_col, trendline="ols")
        correlation = df[x_col].corr(df[y_col])
        fig.add_annotation(text=f'Correlation: {correlation:.2f}',
                          xref="paper", yref="paper", x=0.05, y=0.95)
    elif x_type in ['categorical', 'categorical_numeric'] and y_type == 'numeric':
        # Box plot
        fig = px.box(df, x=x_col, y=y_col)
    else:
        # Heatmap for categorical variables
        contingency = pd.crosstab(df[x_col], df[y_col])
        fig = px.imshow(contingency, aspect="auto")
        
    fig.update_layout(height=400, width=700, title=f'Relationship between {x_col} and {y_col}')
    return fig

def create_time_series_plot(df: pd.DataFrame, time_col: str, value_col: str) -> go.Figure:
    """Create time series plot"""
    fig = px.line(df, x=time_col, y=value_col)
    fig.update_layout(height=400, width=700, title=f'{value_col} over {time_col}')
    return fig

def create_summary_stats(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Create summary statistics based on column type"""
    col_type = get_column_type(df, column)
    
    if col_type == 'numeric':
        stats = df[column].describe()
        stats['skewness'] = df[column].skew()
        stats['kurtosis'] = df[column].kurtosis()
        return pd.DataFrame(stats)
    elif col_type in ['categorical', 'categorical_numeric', 'boolean']:
        return pd.DataFrame({
            'unique_values': len(df[column].unique()),
            'most_common': df[column].mode()[0],
            'most_common_count': df[column].value_counts().iloc[0],
            'missing_values': df[column].isnull().sum()
        }, index=[0])
    else:
        return pd.DataFrame({
            'unique_values': len(df[column].unique()),
            'missing_values': df[column].isnull().sum()
        }, index=[0])

# Database initialization and query functions remain the same
def init_database():
    """Initialize database connection with proper error handling"""
    if st.session_state.db_conn is not None:
        return st.session_state.db_conn
        
    try:
        import duckdb
        db_path = '../hmp_microbiome.duckdb'
        
        if not os.path.exists(db_path):
            st.error(f"Database file not found at {db_path}")
            return None
            
        conn = duckdb.connect(db_path, read_only=True, config={'memory_limit': '4GB'})
        conn.execute("SELECT 1").fetchall()
        
        st.session_state.db_conn = conn
        return conn
        
    except ImportError:
        st.error("Failed to import DuckDB. Please install: pip install duckdb==0.9.2")
        return None
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        return None

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
        tables_df = run_query(conn, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main';")
        tables = tables_df['table_name'].tolist() if tables_df is not None else ["organisms", "genes", "gene_qualifiers", "sequences"]

        # Sidebar
        st.sidebar.header("📊 Query Configuration")
        
        table = st.sidebar.selectbox("Select Table:", tables)
        
        # Get columns for selected table
        schema_query = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}';"
        columns_df = run_query(conn, schema_query)
        columns = columns_df['column_name'].tolist() if columns_df is not None else []

        # Column selection
        selected_columns = st.sidebar.multiselect(
            "Select Columns:",
            columns,
            default=columns[:5] if columns else None
        )

        # Row limit
        limit = st.sidebar.slider("Number of rows:", 5, 1000, 100)
        
        # Main content area
        tab1, tab2, tab3 = st.tabs(["📋 Data View", "📊 Visualizations", "🔍 SQL Query"])
        
        with tab1:
            if selected_columns:
                query = f"SELECT {', '.join(selected_columns)} FROM {table} LIMIT {limit};"
            else:
                query = f"SELECT * FROM {table} LIMIT {limit};"
                
            data = run_query(conn, query)
            
            if data is not None:
                st.dataframe(data)
                
                # Download options
                if st.button("Download as CSV"):
                    csv = data.to_csv(index=False)
                    st.download_button("Click to Download", csv, f"{table}_data.csv", "text/csv")
        
        with tab2:
            if data is not None:
                st.subheader("Data Visualization")
                
                # Auto-detect numeric and categorical columns
                numeric_cols = data.select_dtypes(include=['int64', 'float64']).columns
                cat_cols = data.select_dtypes(include=['object', 'bool']).columns
                
                # Distribution Analysis
                st.markdown("### 📊 Distribution Analysis")
                col = st.selectbox("Select column for distribution analysis:", data.columns)
                if col:
                    dist_fig = create_distribution_plot(data, col)
                    st.plotly_chart(dist_fig)
                    
                    # Show summary statistics
                    with st.expander("Show Summary Statistics"):
                        st.dataframe(create_summary_stats(data, col))
                
                # Correlation Analysis
                if len(numeric_cols) >= 2:
                    st.markdown("### 🔗 Correlation Analysis")
                    col1, col2 = st.columns(2)
                    with col1:
                        x_col = st.selectbox("Select X axis:", data.columns)
                    with col2:
                        y_col = st.selectbox("Select Y axis:", 
                                           [c for c in data.columns if c != x_col])
                    
                    if x_col and y_col:
                        corr_fig = create_correlation_plot(data, x_col, y_col)
                        st.plotly_chart(corr_fig)
                
                # Time Series Analysis (if applicable)
                datetime_cols = data.select_dtypes(include=['datetime64']).columns
                if len(datetime_cols) > 0:
                    st.markdown("### 📈 Time Series Analysis")
                    time_col = st.selectbox("Select time column:", datetime_cols)
                    value_col = st.selectbox("Select value column:", 
                                           [c for c in numeric_cols if c != time_col])
                    
                    if time_col and value_col:
                        time_fig = create_time_series_plot(data, time_col, value_col)
                        st.plotly_chart(time_fig)
                
                # Categorical Analysis
                if len(cat_cols) >= 2:
                    st.markdown("### 📊 Categorical Analysis")
                    cat_col1 = st.selectbox("Select first categorical column:", cat_cols)
                    cat_col2 = st.selectbox("Select second categorical column:", 
                                          [c for c in cat_cols if c != cat_col1])
                    
                    if cat_col1 and cat_col2:
                        contingency = pd.crosstab(data[cat_col1], data[cat_col2])
                        fig = px.imshow(contingency, 
                                      title=f'Relationship between {cat_col1} and {cat_col2}')
                        st.plotly_chart(fig)

        with tab3:
            st.subheader("Custom SQL Query")
            custom_query = st.text_area("Enter your SQL query:", value=f"SELECT * FROM {table} LIMIT 5;")
            
            if st.button("Run Query"):
                results = run_query(conn, custom_query)
                if results is not None:
                    st.dataframe(results)
                    
                    # Offer visualization options for custom query results
                    if len(results.columns) > 0:
                        st.markdown("### Visualize Query Results")
                        viz_type = st.selectbox("Select visualization type:", 
                                              ["Distribution", "Correlation", "Time Series"])
                        
                        if viz_type == "Distribution":
                            col = st.selectbox("Select column:", results.columns)
                            if col:
                                fig = create_distribution_plot(results, col)
                                st.plotly_chart(fig)
                        elif viz_type == "Correlation":
                            col1, col2 = st.columns(2)
                            with col1:
                                x_col = st.selectbox("Select X axis:", results.columns)
                            with col2:
                                y_col = st.selectbox("Select Y axis:", 
                                                   [c for c in results.columns if c != x_col])
                            if x_col and y_col:
                                fig = create_correlation_plot(results, x_col, y_col)
                                st.plotly_chart(fig)
                        elif viz_type == "Time Series":
                            datetime_cols = results.select_dtypes(include=['datetime64']).columns
                            if len(datetime_cols) > 0:
                                time_col = st.selectbox("Select time column:", datetime_cols)
                                value_col = st.selectbox("Select value column:", 
                                                       [c for c in results.columns if c != time_col])
                                if time_col and value_col:
                                    fig = create_time_series_plot(results, time_col, value_col)
                                    st.plotly_chart(fig)

    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")
        st.info("Please try restarting the application.")

if __name__ == "__main__":
    main()