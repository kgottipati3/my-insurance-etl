import logging
import os
import sys
import glob
import argparse
import shutil
from datetime import datetime

# Import your custom pipeline modules
from database import get_db_connection
from extract import extract_csv_data
import pre_flight
import post_flight
import load

# Import your Pydantic data contracts and validation engine
from schemas import (
    PatientModel, 
    ProviderModel, 
    ClaimModel, 
    validate_dataframe_rows
)

# Enterprise Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(module)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# THE MODEL REGISTRY: Maps terminal strings to actual Python classes

MODEL_REGISTRY = {
    "patient": PatientModel,
    "provider": ProviderModel,
    "claim": ClaimModel
}

def parse_args():

    parser = argparse.ArgumentParser(description="Enterprise ETL Pipeline Execution")
    
    parser.add_argument("--source_name", type=str, required=True, 
                        help="Name of the data domain (e.g., patient, provider, claim)")
    parser.add_argument("--folder_path", type=str, required=True, 
                        help="The Drop Zone directory path (e.g., data/patient/)")
    parser.add_argument("--target_table", type=str, required=True, 
                        help="Destination database table (e.g., public.patient)")
    parser.add_argument("--pk_field", type=str, required=True, 
                        help="Primary key column for upserts (e.g., patient_id)")
    # ADDED: Optional CDC field for Enterprise History tracking
    parser.add_argument("--cdc_field", type=str, required=False, default=None,
                        help="The timestamp column for CDC history (e.g., last_modified_date)")
    
    return parser.parse_args()


def fetch_reference_data(db_conn) -> dict:
    """
    Fetches all active reference data and Master Data IDs from PostgreSQL at pipeline startup.
    Uses Python Sets for O(1) lightning-fast lookups.
    """
    context_cache = {}
    try:
        with db_conn.cursor() as cursor:
            # 1. Standard Reference Data
            cursor.execute("SELECT specialty_code FROM reference.specialty_code WHERE is_active = TRUE;")
            context_cache['valid_specialties'] = set(row[0] for row in cursor.fetchall())
            
            cursor.execute("SELECT visit_type FROM reference.visit_type WHERE is_active = TRUE;")
            context_cache['valid_visit_types'] = set(row[0] for row in cursor.fetchall())

            cursor.execute("SELECT coverage_type FROM reference.coverage_type WHERE is_active = TRUE;")
            context_cache['valid_coverage_types'] = set(float(row[0]) for row in cursor.fetchall())
            
            # 2. Master Data (Foreign Key Caching)
            # We wrap these in set() so Pydantic can search them instantly
            cursor.execute("SELECT provider_id FROM public.provider;")
            context_cache['valid_providers'] = set(row[0] for row in cursor.fetchall())
            
            cursor.execute("SELECT patient_id FROM public.patient;")
            context_cache['valid_patients'] = set(row[0] for row in cursor.fetchall())

        logger.info("Reference context and Master Data cache successfully loaded into memory.")
        return context_cache
        
    except Exception as e:
        logger.error(f"Failed to fetch reference data: {e}")
        raise


def move_file_with_timestamp(file_path: str, destination_folder: str):

    os.makedirs(destination_folder, exist_ok=True)
    
    base_name = os.path.basename(file_path)
    file_name_no_ext, ext = os.path.splitext(base_name)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_file_name = f"{file_name_no_ext}_{timestamp}{ext}"
    destination_path = os.path.join(destination_folder, new_file_name)
    
    shutil.move(file_path, destination_path)
    logger.info(f"Moved file to {destination_path}")


def process_pipeline(
    db_conn, 
    source_name: str, 
    file_name: str, 
    file_path: str, 
    target_table: str, 
    model_class, 
    pk_field: str,
    cdc_field: str,
    ref_context: dict
):
    """
    The master orchestration function. Executes the 5-step ETL lifecycle for a single file.
    """
    logger.info(f"=== Starting Pipeline for {source_name.upper()} ({file_name}) ===")

    # Define the destination directories based on the source
    archive_dir = f"data/archive/{source_name}/"
    error_dir = f"data/error/{source_name}/"

    # 1. PRE-FLIGHT
    if not pre_flight.check_table_exists(target_table, db_conn):
        return
        
    if pre_flight.is_file_already_loaded(source_name, file_name, db_conn):
        logger.info(f"Cleaning up stale/already-processed file: {file_name}")
        move_file_with_timestamp(file_path, archive_dir)
        return

    audit_id = pre_flight.initialize_audit_run(source_name, file_name, db_conn)
    total_received = 0

    try:
        # 2. EXTRACT
        logger.info(f"Extracting data from {file_path}...")
        raw_records = extract_csv_data(file_path)
        total_received = len(raw_records)
        
        if total_received == 0:
            logger.warning(f"File {file_name} is empty. Closing run.")
            post_flight.finalize_audit_run(db_conn, audit_id, 0, 0, 0, 'SUCCESS')
            move_file_with_timestamp(file_path, archive_dir)
            return

        # 3. TRANSFORM (Validate & Route)
        logger.info("Validating records against Pydantic CDC Data Contracts...")
        # UPDATED: We now catch all THREE lists, and pass the cdc_field
        clean_records, bad_records, history_records = validate_dataframe_rows(
            df_records=raw_records, 
            model_class=model_class, 
            pk_field=pk_field, 
            cdc_field=cdc_field,
            validation_context=ref_context
        )
        
        total_clean = len(clean_records)
        total_bad = len(bad_records)

        # 4. LOAD (Write to Database)
        # Lane 1: UPSERT Clean Records
        if total_clean > 0:
            load.bulk_upsert_data(db_conn, target_table, pk_field, clean_records, audit_id)
            
        # Lane 2: Log Dead Letter True Conflicts
        if total_bad > 0:
            load.log_quarantined_records(db_conn, source_name, bad_records, audit_id)
            
        # Lane 3: Append Safely Superseded Records
        if history_records:
            # Dynamically derive the history table name from the target_table
            history_table = f"{target_table}_history_audit" 
            load.bulk_insert_history(db_conn, history_table, history_records, audit_id)

        # 5. POST-FLIGHT (Success)
        post_flight.finalize_audit_run(db_conn, audit_id, total_received, total_clean, total_bad, 'SUCCESS')
        
        # 6. LIFECYCLE: Move to Archive
        move_file_with_timestamp(file_path, archive_dir)
        logger.info(f"=== Pipeline for {source_name.upper()} Completed Successfully ===\n")

    except Exception as e:
        # 5. POST-FLIGHT (Failure)
        logger.error(f"FATAL: Pipeline crashed during {source_name} processing: {e}")
        post_flight.finalize_audit_run(db_conn, audit_id, total_received, 0, 0, 'FAILED')
        
        # 6. LIFECYCLE: Move to Error
        move_file_with_timestamp(file_path, error_dir)
        raise


def main():
    """
    Entry point. Captures parameters, securely scans the Drop Zone, and processes all files.
    """
    logger.info("Booting up Parameterized Drop-Zone Pipeline...")
    
    # 1. Capture and validate CLI arguments
    args = parse_args()
    source_key = args.source_name.lower()
    
    if source_key not in MODEL_REGISTRY:
        logger.error(f"Invalid source_name '{source_key}'. Must be one of {list(MODEL_REGISTRY.keys())}")
        sys.exit(1)
        
    model_class = MODEL_REGISTRY[source_key]
    folder_path = args.folder_path

    # 2. Establish Database Connection
    db_conn = get_db_connection()
    if not db_conn:
        logger.error("Cannot start pipeline: Database connection failed.")
        sys.exit(1)

    try:
        # 3. Fetch reference cache ONCE
        ref_context = fetch_reference_data(db_conn)

        # 4. Validate Drop Zone exists
        if not os.path.exists(folder_path):
            logger.error(f"Drop Zone directory not found: {folder_path}")
            sys.exit(1)

        # 5. Securely scan the Drop Zone for CSVs only
        search_path = os.path.join(folder_path, "*.csv")
        matching_files = glob.glob(search_path)
        
        if not matching_files:
            logger.info(f"No CSV files found in '{folder_path}'. Pipeline closing cleanly.")
            return

        # 6. Process every valid file found in the Drop Zone
        for file_path in matching_files:
            actual_file_name = os.path.basename(file_path)
            
            process_pipeline(
                db_conn=db_conn,
                source_name=args.source_name,
                file_name=actual_file_name,
                file_path=file_path,
                target_table=args.target_table,
                model_class=model_class,
                pk_field=args.pk_field,
                cdc_field=args.cdc_field, # ADDED
                ref_context=ref_context
            )

    except Exception as e:
        logger.error(f"Pipeline Execution Aborted: {e}")
        sys.exit(1)
        
    finally:
        db_conn.close()
        logger.info("Database connection closed. Pipeline shutdown complete.")


if __name__ == "__main__":
    main()