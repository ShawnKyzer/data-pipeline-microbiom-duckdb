# Data Pipeline Microbiome DuckDB 🦠 🔬 🦆 📊

## Prerequisites and Setup Guide 📚

### Required Software
- Python 3.11
- Git
- VS Code (Recommended) or PyCharm

### System Requirements
- Minimum 8GB RAM
- 10GB free disk space
- Unix-based system Linux preferred; Windows 10/11 compatible

### Python Knowledge Prerequisites
- Basic Python syntax
- Understanding of virtual environments
- Basic SQL knowledge
- Familiarity with pandas

## Project Structure 📁

```
data-pipeline-microbiom-duckdb
├── application_development/      # Streamlit applications
│   ├── run_streamlit.sh
│   ├── streamlit_app-amaze.py
│   └── streamlit_app.py
├── data_ingestion_pipeline/     # Core pipeline components
│   ├── hmp_data_ingestions_pipeline.py
│   ├── hmp_data_ingestions_pipeline_tests.py
│   └── hmp_microbiome.duckdb    # DuckDB database created by pipeline
├── diagrams/                    # Project documentation
│   ├── biom_erd.png
│   ├── database-erd-detailed.mermaid
│   ├── database-erd-detailed.png
│   ├── database-erd.mermaid
│   ├── data_pipeline_flow.png
│   └── prefect-pipeline.mermaid
├── notebooks/                   # Tutorial notebooks
│   ├── Lesson_2_Basic_HMP_Analytics.ipynb
│   └── Lesson_3_Optimize_and_Export.ipynb
├── requirements.txt            # Project dependencies
└── README.md                  # Project documentation
```

## Getting Started 🚀

### Initial Setup

1. **Clone the Repository**
```bash
git clone https://github.com/ShawnKyzer/data-pipeline-microbiom-duckdb.git
```

2. **Create Virtual Environment**
```bash
# Unix/MacOS
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
.\venv\Scripts\activate
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
```

## Learning Path 📘

### Lesson 1: DuckDB Fundamentals & Pipeline Basics
- Introduction to DuckDB
- Running the ingestion pipeline
- Basic SQL queries with DuckDB
- Understanding the data model

### Lesson 2: Analytics & Optimization
- Working through Lesson 2 notebook
- Basic analytics queries
- Performance optimization
- Data exploration techniques

### Lesson 3 & 4: Advanced Analytics & Streamlit
- Working through Lesson 3 notebook
- Building interactive dashboards
- Deploying Streamlit applications
- Advanced visualization techniques

## Running the Project Components 🔧


### 1. Running Tests
```bash
python -m pytest -v hmp_data_ingestions_pipeline_tests.py
```

### 2. Data Pipeline
```bash
cd data_ingestion_pipeline
python hmp_data_ingestions_pipeline.py
```

### 3. Interactive Notebooks
```bash
jupyter lab
# Navigate to notebooks/Lesson_2_Basic_HMP_Analytics.ipynb
```

### 4. Launch Streamlit Application
```bash
cd application_development
bash run_streamlit.sh
# Or directly with Python:
streamlit run streamlit_app.py
```

## Key Components 🔑

### Prefect / DuckDB Pipeline
- High-performance analytical database
- SQL interface for data processing
- Optimized for analytical queries
- Integrated with Python ecosystem

### Streamlit Applications
- Interactive data visualization
- Real-time analytics dashboard
- Custom filtering and analysis
- Shareable web interface

### Analytics Notebooks
- Step-by-step tutorials
- Performance optimization techniques
- Query optimization examples
- Advanced analytical methods


## Common Issues and Solutions 🔧

### DuckDB Issues
- **Connection Problems**: Ensure database file path is correct
- **Memory Issues**: Monitor memory usage with large datasets
- **Performance**: Check query optimization and indexing

### Streamlit Issues
- **Port Conflicts**: Change port in run_streamlit.sh
- **Display Problems**: Check browser compatibility
- **Performance**: Optimize data loading and caching

## Additional Resources 📚

- [DuckDB Documentation](https://duckdb.org/docs/)
- [Streamlit Documentation](https://docs.streamlit.io)
- [Python DuckDB API](https://duckdb.org/docs/api/python/overview)
- [Streamlit Components](https://streamlit.io/components)
- [NIH Human Microbiome Project](https://hmpdacc.org/)


## Support and Contact 📧

- Course Instructor: Shawn Kyzer
- Email: shawnkyzer@gmail.com

## License 📄

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments 🙏

- DuckDB Development Team
- Streamlit Team
- Contributing Students and Teaching Assistants
- [NIH Human Microbiome Project](https://en.wikipedia.org/wiki/Human_Microbiome_Project)
