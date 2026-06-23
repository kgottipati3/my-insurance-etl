import csv
import logging
import os

# Enterprise logging setup
logger = logging.getLogger(__name__)

def extract_csv_data(file_path: str) -> list[dict]:
    """  
    Args: file_path: The full system path to the physical CSV file.
    """
    if not os.path.exists(file_path):
        logger.error(f"FATAL: Extraction failed. File not found at path: {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")

    records = []
    
    try:        
        with open(file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                # 2. Strip accidental whitespace from headers and values
                clean_row = {}
                for key, value in row.items():
                    # Ignore entirely empty columns
                    if key is not None:
                        clean_key = str(key).strip()
                        clean_value = str(value).strip() if value is not None else None
                        clean_row[clean_key] = clean_value
                        
                records.append(clean_row)
                
        logger.info(f"Successfully extracted {len(records)} rows from {os.path.basename(file_path)}.")
        return records

    except PermissionError:
        logger.error(f"FATAL: Permission denied. The pipeline lacks read access to: {file_path}")
        raise
    except Exception as e:
        logger.error(f"FATAL: Unexpected error while reading {file_path}: {e}")
        raise