import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
import duckdb
from bs4 import BeautifulSoup
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.SeqFeature import SeqFeature, FeatureLocation
import atexit
from prefect.testing.utilities import prefect_test_harness

from hmp_data_ingestions_pipeline import (
    initialize_database,
    get_organism_directories,
    get_processed_organisms,
    find_gbk_file,
    download_and_extract_gbk,
    parse_gbk_data,
    insert_organism_data,
    cleanup_temp_dir,
    generate_processing_report
)

# Fixtures
@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.duckdb")
    yield db_path
    cleanup_temp_dir(temp_dir)


@pytest.fixture(scope="session", autouse=True)
def prefect_test_fixture():
    with prefect_test_harness():
        yield

    # Clean up Prefect server on test session exit
    atexit.register(lambda: None)  # This prevents the ValueError on closed file

@pytest.fixture
def mock_logger():
    """Mock the Prefect logger."""
    with patch('prefect.get_run_logger') as mock:
        yield mock.return_value

@pytest.fixture
def sample_gbk_record():
    """Create a sample GenBank record for testing."""
    # Create a mock sequence record
    sequence = Seq("ATGCGATCGATCGATCG")
    record = SeqRecord(
        sequence,
        id="TEST123",
        annotations={
            "organism": "Test Bacteria",
            "taxonomy": ["Bacteria", "Proteobacteria", "Gammaproteobacteria"]
        }
    )
    
    # Add sample features
    # Fixed: removed strand from constructor, using location strand instead
    feature = SeqFeature(
        FeatureLocation(0, 9, strand=1),  # strand is part of FeatureLocation
        type="CDS",
        qualifiers={
            "locus_tag": ["TEST_001"],
            "gene": ["testA"],
            "product": ["test protein"],
            "translation": ["MGRID"]
        }
    )
    record.features = [feature]
    
    return record

# Test Database Initialization
def test_initialize_database(temp_db, mock_logger):
    """Test database initialization."""
    initialize_database(temp_db)
    
    # Verify tables were created
    conn = duckdb.connect(temp_db)
    tables = conn.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'main'
    """).fetchall()
    
    expected_tables = {
        'organisms', 'genes', 'gene_qualifiers',
        'sequences', 'processing_log'
    }
    
    actual_tables = {table[0] for table in tables}
    assert expected_tables.issubset(actual_tables)
    conn.close()

# Test Organism Directory Fetching
@pytest.mark.asyncio
async def test_get_organism_directories(mock_logger):
    """Test fetching organism directories."""
    mock_html = """
    <html>
        <body>
            <a href="org1/">Org1</a>
            <a href="org2/">Org2</a>
            <a href="file.txt">Not a directory</a>
        </body>
    </html>
    """
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.text = mock_html
        mock_get.return_value.raise_for_status = Mock()
        
        base_url = "http://test.com/"
        directories = get_organism_directories(base_url)
        
        assert len(directories) == 2
        assert "http://test.com/org1/" in directories
        assert "http://test.com/org2/" in directories

def test_get_processed_organisms(temp_db):
    """Test getting processed organisms."""
    # Initialize database and insert test data
    initialize_database(temp_db)
    conn = duckdb.connect(temp_db)
    conn.execute("""
        INSERT INTO processing_log (url, status)
        VALUES 
            ('http://test.com/org1', 'SUCCESS'),
            ('http://test.com/org2', 'ERROR')
    """)
    conn.close()
    
    processed = get_processed_organisms(temp_db)
    assert len(processed) == 1
    assert 'http://test.com/org1' in processed

def test_find_gbk_file():
    """Test finding GBK file URL."""
    mock_html = """
    <html>
        <body>
            <a href="test.scaffold.gbk.tgz">GBK file</a>
            <a href="other.txt">Other file</a>
        </body>
    </html>
    """
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.text = mock_html
        mock_get.return_value.raise_for_status = Mock()
        
        url = find_gbk_file("http://test.com/org1")
        assert url.endswith('.scaffold.gbk.tgz')

def test_parse_gbk_data(sample_gbk_record):
    """Test parsing GenBank data."""
    with patch('Bio.SeqIO.parse') as mock_parse:
        # Return an iterator instead of a list
        mock_parse.return_value = iter([sample_gbk_record])
        
        data = parse_gbk_data("dummy.gbk", "http://test.com/org1")
        
        # Verify the parsed data
        assert data['accession'] == "TEST123"
        assert data['organism_name'] == "Test Bacteria"
        assert data['taxonomy'] == "Bacteria;Proteobacteria;Gammaproteobacteria"
        assert data['genome_size'] == len(sample_gbk_record.seq)
        assert data['source_url'] == "http://test.com/org1"
        
        # Verify feature data
        assert len(data['features']) == 1
        feature = data['features'][0]
        assert feature['locus_tag'] == "TEST_001"
        assert feature['gene_name'] == "testA"
        assert feature['product'] == "test protein"

def test_insert_organism_data(temp_db, sample_gbk_record):
    """Test inserting organism data into database."""
    # Initialize database
    initialize_database(temp_db)
    
    # Create test data
    organism_data = {
        'accession': 'TEST123',
        'organism_name': 'Test Bacteria',
        'taxonomy': 'Bacteria;Proteobacteria',
        'genome_size': 1000,
        'source_url': 'http://test.com/org1',
        'features': [{
            'locus_tag': 'TEST_001',
            'gene_name': 'testA',
            'product': 'test protein',
            'location_start': 0,
            'location_end': 9,
            'strand': '+',
            'qualifiers': {'gene': ['testA']},
            'sequence': 'ATGCGATCG'
        }]
    }
    
    # Insert data
    insert_organism_data(temp_db, organism_data)
    
    # Verify insertion
    conn = duckdb.connect(temp_db)
    
    # Check organism
    organism = conn.execute("""
        SELECT * FROM organisms 
        WHERE accession = 'TEST123'
    """).fetchone()
    assert organism is not None
    
    # Check gene
    gene = conn.execute("""
        SELECT * FROM genes 
        WHERE locus_tag = 'TEST_001'
    """).fetchone()
    assert gene is not None
    
    conn.close()

def test_generate_processing_report(temp_db):
    """Test generating processing report."""
    # Initialize database and insert test data
    initialize_database(temp_db)
    conn = duckdb.connect(temp_db)
    
    # Insert test organisms and genes
    conn.execute("""
        INSERT INTO organisms (organism_id, organism_name, genome_size)
        VALUES (1, 'Test Bacteria 1', 1000)
    """)
    
    conn.execute("""
        INSERT INTO genes (gene_id, organism_id, locus_tag)
        VALUES (1, 1, 'TEST_001')
    """)
    
    conn.execute("""
        INSERT INTO processing_log (url, status)
        VALUES ('http://test.com/org1', 'SUCCESS')
    """)
    
    conn.close()
    
    report = generate_processing_report(temp_db)
    
    assert "Test Bacteria 1" in report
    assert "Total Organisms Processed: 1" in report
    assert "Total Genes Processed: 1" in report

def test_cleanup_temp_dir():
    """Test cleanup of temporary directory."""
    # Create temp directory and file
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, "test.txt")
    with open(temp_file, 'w') as f:
        f.write("test")
    
    # Clean up
    cleanup_temp_dir(temp_dir)
    
    # Verify cleanup
    assert not os.path.exists(temp_dir)

# Integration Tests
def test_full_pipeline_integration(temp_db):
    """Test full pipeline integration with complete tar mock."""
    with patch('requests.get') as mock_get, \
         patch('Bio.SeqIO.parse') as mock_parse, \
         patch('tarfile.open') as mock_tarfile, \
         patch('prefect.get_run_logger') as mock_logger:

        logger = mock_logger.return_value

        # Mock response class
        class MockResponse:
            def __init__(self, content=None, text=None):
                self.content = content
                self.text = text
                
            def raise_for_status(self):
                pass
                
            def iter_content(self, chunk_size=None):
                if isinstance(self.content, bytes):
                    yield self.content

        # Mock response handler with more specific URL handling
        def mock_get_response(*args, **kwargs):
            url = args[0]
            if url == "http://test.com":  # Base URL
                return MockResponse(text='<html><a href="org1/">Org1</a></html>')
            elif "org1" in url and not url.endswith('.tgz'):  # Organism directory
                return MockResponse(text='<html><a href="test.scaffold.gbk.tgz">GBK file</a></html>')
            elif url.endswith('.tgz'):  # GBK file download
                return MockResponse(content=b"mock tar content")
            return MockResponse(text='')

        mock_get.side_effect = mock_get_response

        # Create mock file with proper name matching the expected GBK pattern
        class MockTarInfo:
            def __init__(self, name):
                self.name = name

        class MockTarFile:
            def __init__(self):
                self.files = {
                    "test.scaffold.gbk": b"Mock GBK content"
                }
                
            def getmembers(self):
                return [MockTarInfo(name) for name in self.files.keys()]
                
            def getnames(self):
                return list(self.files.keys())
                
            def extractfile(self, member):
                if isinstance(member, str):
                    filename = member
                else:
                    filename = member.name
                    
                if filename in self.files:
                    mock_file = MagicMock()
                    mock_file.read.return_value = self.files[filename]
                    return mock_file
                return None
                
            def extractall(self, path=None):
                for filename, content in self.files.items():
                    file_path = os.path.join(path, filename)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, 'wb') as f:
                        f.write(content)

            def __enter__(self):
                return self
                
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_tarfile.return_value = MockTarFile()

        # Create GenBank record with required annotations
        mock_record = SeqRecord(
            Seq("ATGC"),
            id="TEST123",
            name="TEST123",
            description="Test Organism TEST123",
            annotations={
                "organism": "Test Bacteria",
                "taxonomy": ["Bacteria", "Proteobacteria"],
                "source": "Test Source"
            }
        )

        feature = SeqFeature(
            FeatureLocation(0, 3, strand=1),
            type="CDS",
            qualifiers={
                "locus_tag": ["TEST_001"],
                "gene": ["testA"],
                "product": ["test protein A"]
            }
        )
        mock_record.features = [feature]
        mock_parse.return_value = iter([mock_record])

        # Initialize database
        initialize_database(temp_db)

        # Run the pipeline
        from hmp_data_ingestions_pipeline import process_hmp_data
        process_hmp_data(
            base_url="http://test.com",
            db_path=temp_db,
            max_concurrent=1
        )

        # Verify results
        conn = duckdb.connect(temp_db)
        try:
            # Check organism insertion
            organism_count = conn.execute(
                "SELECT COUNT(*) FROM organisms"
            ).fetchone()[0]
            assert organism_count > 0, "No organisms were inserted into the database"

            # Verify organism data
            organism = conn.execute("""
                SELECT accession, organism_name, taxonomy
                FROM organisms
                WHERE accession = 'TEST123'
            """).fetchone()
            assert organism is not None, "TEST123 organism not found"
            assert organism[0] == "TEST123", f"Wrong accession: {organism[0]}"
            assert organism[1] == "Test Bacteria", f"Wrong organism name: {organism[1]}"

            # Verify gene data
            gene = conn.execute("""
                SELECT g.locus_tag, g.gene_name, g.product
                FROM genes g
                JOIN organisms o ON g.organism_id = o.organism_id
                WHERE o.accession = 'TEST123'
            """).fetchone()
            assert gene is not None, "Gene not found"
            assert gene[0] == "TEST_001", f"Wrong locus tag: {gene[0]}"
            assert gene[1] == "testA", f"Wrong gene name: {gene[1]}"

            # Verify processing log
            log_entry = conn.execute("""
                SELECT status
                FROM processing_log
                WHERE url = 'http://test.com/org1/'
            """).fetchone()
            assert log_entry is not None, "No log entry found"
            assert log_entry[0] == "SUCCESS", f"Wrong status: {log_entry[0]}"
            
        finally:
            conn.close()