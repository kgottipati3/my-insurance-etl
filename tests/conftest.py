import pytest
from src.database import get_db_connection

# 1. GLOBAL DATABASE FIXTURE
@pytest.fixture(scope="session")
def db_connection():
    conn = None
    try:
        conn = get_db_connection()
        yield conn
    except Exception as e:
        pytest.fail(f"Could not connect to the database: {e}")
    finally:
        if conn:
            conn.rollback() 
            conn.close()

# 2. GLOBAL MOCK DATA FIXTURES
@pytest.fixture(scope="session")
def mock_db_context():
    """
    Updated to include the Master Data cache for Foreign Key validation,
    using high-performance sets just like the real main.py script.
    """
    return {
        "valid_specialties": {'cardiology', 'neurology', 'pediatrics'},
        "valid_visit_types": {'physical', 'routine', 'illness', 'surgery'},
        "valid_coverage_types": {100.0, 50.0, 0.0},
        "valid_providers": {'N3T5300A'}, 
        "valid_patients": {'62000U'}     
    }

@pytest.fixture
def valid_claim_data():
    return {
        "claim_id": "CF#1000078NN",
        "patient_id": "62000U",
        "provider_id": "N3T5300A",
        "visit_type": "surgery",
        "total_cost": "782.08",
        "coverage_type": "100",
        "date_of_service": "10/10/2017",
        "claim_date": "1/3/2019",
        "billed": "T",
        "last_modified_date": "2/8/2021"
    }