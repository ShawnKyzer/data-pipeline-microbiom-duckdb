import os
import requests
from bs4 import BeautifulSoup
import tarfile
from Bio import SeqIO
import duckdb
import tempfile
from pathlib import Path
from typing import List, Dict, Set, Tuple
from urllib.parse import urljoin
import pandas as pd
from datetime import timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor

from prefect import task, flow, get_run_logger
from prefect.tasks import task_input_hash
from prefect.context import get_run_context
from prefect.utilities.annotations import quote
from prefect import variables
from prefect.artifacts import create_markdown_artifact
@task(
    retries=3,
    retry_delay_seconds=30,
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(hours=24)
)
def initialize_database(db_path: str) -> None:
    """Initialize the DuckDB database with the schema."""
    logger = get_run_logger()
    logger.info(f"Initializing database at {db_path}")
    
    db = duckdb.connect(db_path)
    tables = """
    CREATE TABLE IF NOT EXISTS organisms (
        organism_id INTEGER PRIMARY KEY,
        accession VARCHAR,
        organism_name VARCHAR,
        taxonomy VARCHAR,
        genome_size INTEGER,
        processing_date TIMESTAMP,
        source_url VARCHAR
    );

    CREATE TABLE IF NOT EXISTS genes (
        gene_id INTEGER PRIMARY KEY,
        organism_id INTEGER,
        locus_tag VARCHAR,
        gene_name VARCHAR,
        product VARCHAR,
        location_start INTEGER,
        location_end INTEGER,
        strand VARCHAR(1),
        FOREIGN KEY (organism_id) REFERENCES organisms(organism_id)
    );

    CREATE TABLE IF NOT EXISTS gene_qualifiers (
        qualifier_id INTEGER PRIMARY KEY,
        gene_id INTEGER,
        qualifier_name VARCHAR,
        qualifier_value VARCHAR,
        FOREIGN KEY (gene_id) REFERENCES genes(gene_id)
    );

    CREATE TABLE IF NOT EXISTS sequences (
        sequence_id INTEGER PRIMARY KEY,
        gene_id INTEGER,
        sequence_type VARCHAR,
        sequence TEXT,
        FOREIGN KEY (gene_id) REFERENCES genes(gene_id)
    );

    CREATE TABLE IF NOT EXISTS processing_log (
        url VARCHAR PRIMARY KEY,
        status VARCHAR,
        processed_date TIMESTAMP,
        error_message VARCHAR
    );
    """
    for statement in tables.split(';'):
        if statement.strip():
            db.execute(statement)
    
    db.close()
    logger.info("Database initialization complete")

@task(
    retries=3,
    retry_delay_seconds=60,
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(hours=12)
)
def get_organism_directories(base_url: str) -> List[str]:
    """Fetch list of organism directories from HMP."""
    logger = get_run_logger()
    logger.info(f"Fetching organism directories from {base_url}")
    
    response = requests.get(base_url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    directories = [
        urljoin(base_url, link.get('href'))
        for link in soup.find_all('a')
        if link.get('href', '').endswith('/')
        and link.get('href') != '../'
    ]
    
    logger.info(f"Found {len(directories)} organism directories")
    return directories

@task(retries=3, retry_delay_seconds=30)
def get_processed_organisms(db_path: str) -> Set[str]:
    """Get set of already processed organism URLs."""
    db = duckdb.connect(db_path)
    processed = set(
        row[0] for row in db.execute(
            "SELECT url FROM processing_log WHERE status = 'SUCCESS'"
        ).fetchall()
    )
    db.close()
    return processed

@task(retries=2, retry_delay_seconds=30)
def find_gbk_file(org_url: str) -> str:
    """Find the GBK file URL for an organism."""
    logger = get_run_logger()
    
    response = requests.get(org_url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    for link in soup.find_all('a'):
        href = link.get('href', '')
        if href.endswith('.scaffold.gbk.tgz'):
            return urljoin(org_url, href)
    
    raise FileNotFoundError(f"No GBK file found for {org_url}")

@task(retries=3, retry_delay_seconds=60)
def download_and_extract_gbk(gbk_url: str) -> Tuple[str, str]:
    """Download and extract GBK file, return path and content."""
    logger = get_run_logger()
    logger.info(f"Downloading {gbk_url}")
    
    temp_dir = tempfile.mkdtemp()
    response = requests.get(gbk_url, stream=True)
    response.raise_for_status()
    
    tgz_path = os.path.join(temp_dir, 'temp.tgz')
    with open(tgz_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    with tarfile.open(tgz_path, 'r:gz') as tar:
        tar.extractall(path=temp_dir)
    
    gbk_files = list(Path(temp_dir).glob('*.gbk'))
    if not gbk_files:
        raise FileNotFoundError("No GBK file found in archive")
    
    return str(gbk_files[0]), temp_dir

@task(retries=2)
def parse_gbk_data(gbk_file: str, source_url: str) -> Dict:
    """Parse GBK file into structured data."""
    logger = get_run_logger()
    
    record = next(SeqIO.parse(gbk_file, "genbank"))
    
    organism_data = {
        'accession': record.id,
        'organism_name': record.annotations.get('organism', ''),
        'taxonomy': ';'.join(record.annotations.get('taxonomy', [])),
        'genome_size': len(record.seq),
        'source_url': source_url,
        'features': []
    }
    
    for feature in record.features:
        if feature.type in ['CDS', 'gene', 'rRNA', 'tRNA']:
            feature_data = {
                'locus_tag': feature.qualifiers.get('locus_tag', [''])[0],
                'gene_name': feature.qualifiers.get('gene', [''])[0],
                'product': feature.qualifiers.get('product', [''])[0],
                'location_start': int(feature.location.start),
                'location_end': int(feature.location.end),
                'strand': '+' if feature.location.strand == 1 else '-',
                'qualifiers': feature.qualifiers,
                'sequence': str(feature.extract(record.seq))
            }
            organism_data['features'].append(feature_data)
    
    logger.info(f"Parsed {len(organism_data['features'])} features from {organism_data['organism_name']}")
    return organism_data

@task(retries=3)
def insert_organism_data(db_path: str, organism_data: Dict) -> None:
    """Insert parsed organism data into database."""
    logger = get_run_logger()
    db = duckdb.connect(db_path)
    
    try:
        # Insert organism
        db.execute("""
            INSERT INTO organisms (accession, organism_name, taxonomy, genome_size, 
                                 processing_date, source_url)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            RETURNING organism_id
        """, [
            organism_data['accession'],
            organism_data['organism_name'],
            organism_data['taxonomy'],
            organism_data['genome_size'],
            organism_data['source_url']
        ])
        organism_id = db.fetchone()[0]
        
        # Process features in batches
        batch_size = 1000
        features = organism_data['features']
        
        for i in range(0, len(features), batch_size):
            batch = features[i:i + batch_size]
            for feature in batch:
                # Insert gene
                db.execute("""
                    INSERT INTO genes (organism_id, locus_tag, gene_name, product,
                                     location_start, location_end, strand)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    RETURNING gene_id
                """, [
                    organism_id,
                    feature['locus_tag'],
                    feature['gene_name'],
                    feature['product'],
                    feature['location_start'],
                    feature['location_end'],
                    feature['strand']
                ])
                gene_id = db.fetchone()[0]
                
                # Insert qualifiers
                for name, values in feature['qualifiers'].items():
                    if isinstance(values, list):
                        value = values[0] if values else ''
                    else:
                        value = str(values)
                    
                    db.execute("""
                        INSERT INTO gene_qualifiers (gene_id, qualifier_name, qualifier_value)
                        VALUES (?, ?, ?)
                    """, [gene_id, name, value])
                
                # Insert sequence
                db.execute("""
                    INSERT INTO sequences (gene_id, sequence_type, sequence)
                    VALUES (?, 'DNA', ?)
                """, [gene_id, feature['sequence']])
        
        # Log success
        db.execute("""
            INSERT INTO processing_log (url, status, processed_date)
            VALUES (?, 'SUCCESS', CURRENT_TIMESTAMP)
        """, [organism_data['source_url']])
        
        logger.info(f"Successfully inserted data for {organism_data['organism_name']}")
        
    except Exception as e:
        logger.error(f"Error inserting data: {str(e)}")
        db.execute("""
            INSERT INTO processing_log (url, status, processed_date, error_message)
            VALUES (?, 'ERROR', CURRENT_TIMESTAMP, ?)
        """, [organism_data['source_url'], str(e)])
        raise
    
    finally:
        db.close()

@task
def cleanup_temp_dir(temp_dir: str) -> None:
    """Clean up temporary directory."""
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

@task
def generate_processing_report(db_path: str) -> str:
    """Generate a processing report."""
    db = duckdb.connect(db_path)
    
    # Gather statistics
    stats = {
        'total_organisms': db.execute("SELECT COUNT(*) FROM organisms").fetchone()[0],
        'total_genes': db.execute("SELECT COUNT(*) FROM genes").fetchone()[0],
        'processing_status': db.execute("""
            SELECT status, COUNT(*) 
            FROM processing_log 
            GROUP BY status
        """).fetchall(),
        'top_organisms': db.execute("""
            SELECT o.organism_name, COUNT(g.gene_id) as gene_count
            FROM organisms o
            LEFT JOIN genes g ON o.organism_id = g.organism_id
            GROUP BY o.organism_name
            ORDER BY gene_count DESC
            LIMIT 10
        """).fetchall()
    }
    
    db.close()
    
    # Create status table rows
    status_rows = []
    for status, count in stats['processing_status']:
        status_rows.append(f"| {status} | {count:,} |")
    
    # Create organism table rows
    organism_rows = []
    for org, count in stats['top_organisms']:
        organism_rows.append(f"| {org} | {count:,} |")
    
    # Build report using concatenation instead of f-strings
    report = "\n".join([
        "# HMP Data Processing Report",
        "",
        "## Processing Statistics",
        f"- Total Organisms Processed: {stats['total_organisms']:,}",
        f"- Total Genes Processed: {stats['total_genes']:,}",
        "",
        "## Processing Status",
        "| Status | Count |",
        "|--------|-------|",
        "\n".join(status_rows),
        "",
        "## Top 10 Organisms by Gene Count",
        "| Organism | Gene Count |",
        "|----------|------------|",
        "\n".join(organism_rows)
    ])
    
    return report

@flow(
    name="HMP Data Processing Pipeline",
    description="Process Human Microbiome Project bacterial genome data",
    version="1.0"
)
def process_hmp_data(
    base_url: str = "https://ftp.ncbi.nih.gov/genomes/HUMAN_MICROBIOM/Bacteria/",
    db_path: str = "hmp_microbiome.duckdb",
    max_concurrent: int = 4
) -> None:
    """Main flow for processing HMP data."""
    logger = get_run_logger()
    
    # Initialize database
    initialize_database(db_path)
    
    # Get organism directories and filter already processed
    directories = get_organism_directories(base_url)
    processed = get_processed_organisms(db_path)
    to_process = [d for d in directories if d not in processed]
    
    logger.info(f"Found {len(to_process)} organisms to process")
    
    # Process organisms using async with concurrent execution
    async def process_organism(org_url: str):
        try:
            # Find GBK file
            gbk_url = find_gbk_file(org_url)
            
            # Download and extract
            gbk_file, temp_dir = download_and_extract_gbk(gbk_url)
            
            # Parse and insert data
            organism_data = parse_gbk_data(gbk_file, org_url)
            insert_organism_data(db_path, organism_data)
            
            # Cleanup
            cleanup_temp_dir(temp_dir)
            
        except Exception as e:
            logger.error(f"Error processing {org_url}: {str(e)}")
    
    async def process_all_organisms():
        # Create a thread pool for concurrent execution
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            # Create tasks for each organism
            tasks = []
            loop = asyncio.get_event_loop()
            
            for org_url in to_process:
                task = loop.run_in_executor(executor, process_organism, org_url)
                tasks.append(task)
            
            # Wait for all tasks to complete
            await asyncio.gather(*tasks)
    
    # Run the async processing
    asyncio.run(process_all_organisms())
    
    # Generate and save report
    report = generate_processing_report(db_path)
    create_markdown_artifact(
        key="processing-report",
        markdown=report,
        description="HMP Data Processing Report"
    )

if __name__ == "__main__":
    process_hmp_data()