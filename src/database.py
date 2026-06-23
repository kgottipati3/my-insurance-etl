import logging
import psycopg2
from src.config import config

# Enterprise logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_db_connection():
    logger.info("Initiating database connection sequence...")

    try:
        # Establish the connection using the centralized config object
        conn = psycopg2.connect(
            host=config.db_host,
            port=config.db_port,
            dbname=config.db_name,
            user=config.db_user,
            password=config.db_pass
        )
        logger.info(f"Database connection established successfully to {config.db_host}:{config.db_port}.")
        return conn
        
    except psycopg2.Error as e:
        logger.error(f"FATAL: Database connection failed: {e}")
        raise