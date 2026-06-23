# Enterprise Insurance Data Pipeline

An automated, fault-tolerant ETL pipeline designed to extract, validate, and load vendor claims data into a PostgreSQL Data Warehouse. 

This project was engineered with a strict focus on data integrity, decoupled architecture, and scalable validation using Python and Pydantic.

## Architectural Highlights

* **Decoupled Rules Engine:** Business logic (Regex formatting, chronological time-travel checks, financial constraints) is isolated in `schemas.py` using **Pydantic**.
* **Stateless Validation:** Reference data (Coverage Types, Visit Types) is cached in-memory at pipeline startup to prevent N+1 database querying bottlenecks.
* **Non-Destructive Loading:** Invalid records do not crash the pipeline. They are intercepted and routed to an isolated `audit.data_load_error_details` table for administrative review.
* **Ephemeral Testing:** The Pytest suite utilizes `MagicMock` and `tmp_path` fixtures to thoroughly test database Upserts and CSV extraction without polluting the repository or requiring a live database connection.

## Technology Stack
* **Language:** Python 3.11
* **Database:** PostgreSQL 15
* **Validation:** Pydantic & Pydantic-Settings
* **Infrastructure:** Docker & Docker Compose
* **Testing:** Pytest (with session-scoped Fixtures & Mocking)

---
1. Local Setup & Installation
Prerequisites:
Docker Desktop installed and running.
Git installed.

Installation
Clone the repository and build the isolated Docker containers. The docker-compose.yaml file defines both the Python ETL environment and the PostgreSQL database.

git clone <your-repository-url>
cd my-insurance-etl
# Build the ETL Pipeline Docker image
docker-compose build etl_pipeline
## 2. Running the Pipeline

### Booting the Infrastructure
First, spin up the PostgreSQL database container in detached mode. This container holds your tables and schemas.

```bash
docker-compose up -d enterprise_pg_db
Executing the Data Loads
Run the orchestrator script for patient, provider, and claim.
docker-compose run --rm etl_pipeline python src/main.py --source_name "patient" --folder_path "data/patient" --target_table "public.patient" --pk_field "patient_id" --cdc_field "last_modified_date"
docker-compose run --rm etl_pipeline python src/main.py --source_name "provider" --folder_path "data/provider" --target_table "public.provider" --pk_field "provider_id"
docker-compose run --rm etl_pipeline python src/main.py --source_name "claim" --folder_path "data/claim" --target_table "public.claim" --pk_field "claim_id" --cdc_field "last_modified_date"   

5. Future Development Roadmap
To scale this pipeline for massive enterprise workloads, the following improvements are prioritized.

Priority 1: ELT Pattern
The Challenge: The current in-memory Python Master Data Cache (checking Foreign Keys via set()) is incredibly fast for thousands of rows but will cause Out-Of-Memory (OOM) crashes if scaled to millions of patients.
The Solution: Transition to an ELT pattern. Python will load raw validated data into temporary staging schemas, and heavy Foreign Key validation will be offloaded to PostgreSQL using LEFT JOIN operations before inserting into public.

Priority 2: Workflow Orchestration
The Challenge: Pipelines must be executed manually via CLI commands and lack dynamic dependency mapping.
The Solution: Wrap the Python execution commands in Airflow DAGs. This will automatically enforce the execution order (Patients/Providers -> Claims), handle automated retries on network failures, and provide a visual UI for monitoring batch jobs.

Priority 3:Data Quality Observability & Alerting
The Challenge: Failures are safely logged in the database, but Business User/Data Scientists must proactively run SQL queries to find them.
The Solution: Integrate a Slack or Microsoft Teams webhook at the end of the main.py execution. If the quarantined_records count is greater than 0, the pipeline will automatically push an alert to the Data Governance channel with the specific Audit ID.

Priority 4: Cloud Storage Integration (AWS S3)
The Challenge: The pipeline currently relies on the local file system (data/DropZone).
The Solution: Implement boto3 to allow the Extract module to read streams directly from AWS S3 buckets. Utilize S3 Event Notifications to automatically trigger the pipeline when a vendor uploads a new file.

Priority 5: Advanced CI/CD Integration
The Challenge: Testing and formatting are currently manual steps before pushing to the repository.
The Solution: Implement GitHub Actions. On every Pull Request, the pipeline will automatically spin up a temporary Postgres database and run pytest.
