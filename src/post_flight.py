import logging
import psycopg2

logger = logging.getLogger(__name__)

def finalize_audit_run(db_conn, audit_id: int, records_received: int, records_loaded: int, records_rejected: int, status: str):
    """
    Updates the audit.data_load_details table at the end of the pipeline execution.
    Locks in the final row counts, sets the end time, and marks the job as SUCCESS or FAILED.
    """
    query = """
        UPDATE audit.data_load_details 
        SET records_received = %s,
            records_loaded = %s,
            records_rejected = %s,
            job_status = %s,
            load_end_time = CURRENT_TIMESTAMP
        WHERE audit_id = %s;
    """
    try:
        with db_conn.cursor() as cursor:
            cursor.execute(query, (records_received, records_loaded, records_rejected, status, audit_id))
        
        db_conn.commit()
        logger.info(f"Audit Run Closed. ID: {audit_id} marked as {status} ({records_loaded} loaded, {records_rejected} rejected).")
        
    except psycopg2.Error as e:
        db_conn.rollback()
        logger.error(f"Database error during audit finalization: {e}")
        # Note: We usually don't raise an exception here. If the data loaded successfully 
        # but the audit update failed, we don't want to crash the whole application and trigger a retry.