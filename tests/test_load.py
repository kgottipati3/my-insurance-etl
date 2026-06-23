import pytest
from unittest.mock import MagicMock, patch
from src.load import log_quarantined_records 

# ---------------------------------------------------------
# FIXTURES: The Fake Data Payloads
# ---------------------------------------------------------
@pytest.fixture
def fake_clean_records():
    return [{
        "claim_id": "CF#TEST01",
        "patient_id": "99000U",
        "total_cost": 500.00
    }]

@pytest.fixture
def fake_quarantined_records():
    return [{
        "record_key": "CF#TEST02",
        "field_name": "Single",
        "error_message": "Time travel detected",
        "raw_payload": {"claim_id": "CF#TEST02", "date": "bad_date"}
    }]

# THE TEST


@patch('src.load.execute_values')
def test_load_inserts_rejected_records_to_audit_log(mock_execute_values, fake_quarantined_records):
    """Proves bad data is correctly routed to the audit schema."""
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    audit_id = 888
    source_name = "claim"
    
    # UPDATED FUNCTION CALL
    log_quarantined_records(mock_conn, source_name, fake_quarantined_records, audit_id)

    # Verify that execute_values was called once
    assert mock_execute_values.called
    
    # Extract the SQL query and the values passed to it
    called_args = mock_execute_values.call_args[0]
    sql_query = called_args[1]
    sql_values = called_args[2]

    # Verify the query targets the correct audit table
    assert "audit.data_load_error_details" in sql_query.lower()
    
    # Verify the test data was packaged correctly for the DB
    first_row_values = sql_values[0]
    assert first_row_values[0] == audit_id
    assert first_row_values[1] == source_name
    assert first_row_values[2] == "CF#TEST02"
    assert first_row_values[4] == "Time travel detected"
    
    # Verify the transaction was committed
    assert mock_conn.commit.called