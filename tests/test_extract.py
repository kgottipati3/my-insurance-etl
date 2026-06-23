import pytest
from src.extract import extract_csv_data

def test_extract_reads_standard_csv(tmp_path):
    test_file = tmp_path / "happy_path.csv"
    test_file.write_text(
        "claim_id,patient_id,total_cost\n"
        "CF#100,62000U,500.00\n"
        "CF#101,63000U,250.00"
    )

    extracted_data = extract_csv_data(str(test_file))

    assert len(extracted_data) == 2
    assert extracted_data[0]['claim_id'] == "CF#100"
    assert extracted_data[1]['total_cost'] == "250.00"

def test_extract_strips_whitespace_from_headers_and_values(tmp_path):
    test_file = tmp_path / "dirty_spaces.csv"
    test_file.write_text(
        " claim_id , patient_id \n"
        " CF#999 ,  99000U  "
    )

    extracted_data = extract_csv_data(str(test_file))
    
    assert "claim_id" in extracted_data[0]
    assert extracted_data[0]["claim_id"] == "CF#999"
    assert extracted_data[0]["patient_id"] == "99000U"

def test_extract_handles_empty_file_gracefully(tmp_path):
    test_file = tmp_path / "empty.csv"
    test_file.write_text("") 

    extracted_data = extract_csv_data(str(test_file))
    
    assert isinstance(extracted_data, list)
    assert len(extracted_data) == 0