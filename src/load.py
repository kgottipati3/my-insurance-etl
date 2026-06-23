import logging
import psycopg2
from psycopg2.extras import execute_values, Json
from pydantic import BaseModel

# Enterprise logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# LANE 1: CURRENT STATE (UPSERT)

def bulk_upsert_data(db_conn, target_table: str, pk_field: str, records: list[BaseModel], audit_id: int) -> int:
    """
    Loads clean Pydantic models into the main target table.
    Uses an UPSERT (ON CONFLICT DO UPDATE) to keep the current state accurate.
    """
    if not records:
        return 0

    first_record = records[0].model_dump()
    base_columns = list(first_record.keys())
    
    db_columns = base_columns + ['created_audit_id', 'updated_audit_id']
    columns_list_str = ', '.join(db_columns)

    values = []
    for record in records:
        record_dict = record.model_dump()
        row_values = tuple([record_dict[col] for col in base_columns] + [audit_id, audit_id])
        values.append(row_values)

    update_clauses = []
    for col in db_columns:
        if col not in [pk_field, 'created_audit_id']:
            update_clauses.append(f"{col} = EXCLUDED.{col}")
            
    update_str = ", ".join(update_clauses)

    upsert_query = f"""
        INSERT INTO {target_table} ({columns_list_str}) 
        VALUES %s
        ON CONFLICT ({pk_field}) 
        DO UPDATE SET 
            {update_str};
    """

    try:
        with db_conn.cursor() as cursor:
            execute_values(cursor, upsert_query, values)
        db_conn.commit()
        
        logger.info(f"SUCCESS: Upserted {len(records)} records into {target_table}.")
        return len(records)

    except psycopg2.Error as e:
        db_conn.rollback()
        logger.error(f"FATAL: Database error during bulk upsert into {target_table}: {e}")
        raise



# LANE 2: DEAD LETTER QUEUE (ERROR TABLE)

def log_quarantined_records(db_conn, source_name: str, quarantined_records: list[dict], audit_id: int) -> int:
    """
    Inserts broken/invalid rows directly into the audit.data_load_error_details table.
    """
    if not quarantined_records:
        return 0

    insert_query = """
        INSERT INTO audit.data_load_error_details 
        (audit_id, source_name, record_key, field_name, error_message, raw_payload)
        VALUES %s
    """

    values = []
    for err in quarantined_records:
        values.append((
            audit_id,
            source_name,
            err.get('record_key'),
            err.get('field_name'),
            err.get('error_message'),
            Json(err.get('raw_payload')) 
        ))

    try:
        with db_conn.cursor() as cursor:
            execute_values(cursor, insert_query, values)
        db_conn.commit()
        
        logger.info(f"SECURED: Logged {len(quarantined_records)} quarantined records into audit schema.")
        return len(quarantined_records)

    except psycopg2.Error as e:
        db_conn.rollback()
        logger.error(f"FATAL: Failed to write error logs to database: {e}")
        raise



# LANE 3: HISTORICAL SNAPSHOTS (APPEND-ONLY)

def bulk_insert_history(db_conn, target_history_table: str, history_records: list[dict], audit_id: int) -> int:
    """
    Loads safely superseded records into the CDC history audit table.
    Uses a standard INSERT. No 'ON CONFLICT' logic is used because 
    this table actively tracks chronological duplicates.
    """
    if not history_records:
        return 0

    # 1. Extract the raw dictionaries we wrapped in schemas.py
    raw_data_list = [item["raw_payload"] for item in history_records]
    
    # 2. Dynamically extract columns from the first raw CSV row
    base_columns = list(raw_data_list[0].keys())
    
    # 3. Append the single Lineage tracking column for immutable tables
    db_columns = base_columns + ['created_audit_id']
    columns_list_str = ', '.join(db_columns)

    # 4. Format the data values
    values = []
    for record in raw_data_list:
        row_values = tuple([record.get(col) for col in base_columns] + [audit_id])
        values.append(row_values)

    # 5. Generate the pure INSERT query for execute_values
    insert_query = f"""
        INSERT INTO {target_history_table} ({columns_list_str}) 
        VALUES %s;
    """

    try:
        with db_conn.cursor() as cursor:
            execute_values(cursor, insert_query, values)
        db_conn.commit()
        
        logger.info(f"SUCCESS: Archived {len(history_records)} superseded updates into {target_history_table}.")
        return len(history_records)

    except psycopg2.Error as e:
        db_conn.rollback()
        logger.error(f"FATAL: Database error during historical insert into {target_history_table}: {e}")
        raise