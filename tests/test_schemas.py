import pytest
from pydantic import ValidationError
from datetime import date
from src.schemas import ClaimModel

def test_valid_claim_passes(valid_claim_data, mock_db_context):
    claim = ClaimModel.model_validate(valid_claim_data, context=mock_db_context)
    
    assert claim.claim_id == "CF#1000078NN"
    assert claim.total_cost == 782.08
    assert claim.date_of_service == date(2017, 10, 10)

def test_structural_regex_swap_caught(valid_claim_data, mock_db_context):
    valid_claim_data["claim_id"] = "62000U"
    valid_claim_data["patient_id"] = "CF#1000078NN"
    
    with pytest.raises(ValidationError) as exc_info:
        ClaimModel.model_validate(valid_claim_data, context=mock_db_context)
    
    assert "String should match pattern" in str(exc_info.value)

def test_chronological_time_travel_caught(valid_claim_data, mock_db_context):
    valid_claim_data["date_of_service"] = "1/3/2019"
    valid_claim_data["claim_date"] = "10/10/2017"
    
    with pytest.raises(ValidationError) as exc_info:
        ClaimModel.model_validate(valid_claim_data, context=mock_db_context)
    
    assert "Chronological Swap Detected" in str(exc_info.value)
