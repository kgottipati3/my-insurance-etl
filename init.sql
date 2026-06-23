-- =================================================================================
-- 1. SCHEMAS
-- =================================================================================
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS reference;
CREATE SCHEMA IF NOT EXISTS public;

-- =================================================================================
-- 2. AUDIT SCHEMA (The Control Plane)
-- =================================================================================

-- Table 1: data_load_details
CREATE TABLE audit.data_load_details (
    audit_id SERIAL PRIMARY KEY,
    source_name VARCHAR(100),
    file_name VARCHAR(255),
    records_received INT,
    records_loaded INT,
    records_rejected INT,
    job_status VARCHAR(50),
    load_start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    load_end_time TIMESTAMP
);

-- Table 2: data_load_error_details
CREATE TABLE audit.data_load_error_details (
    error_id SERIAL PRIMARY KEY,
    audit_id INT REFERENCES audit.data_load_details(audit_id),
    source_name VARCHAR(100),
    record_key VARCHAR(255),
    field_name VARCHAR(100),
    error_message TEXT,
    raw_payload JSONB,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =================================================================================
-- 3. REFERENCE SCHEMA (The Lookup Plane)
-- =================================================================================

-- Table 3: specialty_code
CREATE TABLE reference.specialty_code (
    specialty_code VARCHAR(50) PRIMARY KEY,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 4: visit_type
CREATE TABLE reference.visit_type (
    visit_type VARCHAR(100) PRIMARY KEY,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 5: coverage_type (Financial Domain Constraint)
CREATE TABLE reference.coverage_type (
    coverage_type NUMERIC(5, 2) PRIMARY KEY,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =================================================================================
-- 4. PUBLIC SCHEMA (The Core Data Plane with Dual Lineage)
-- =================================================================================

-- Table 6: patient
CREATE TABLE public.patient (
    patient_id VARCHAR(50) PRIMARY KEY, 
    fname VARCHAR(100),
    lname VARCHAR(100),
    date_of_birth DATE,
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    zipcode VARCHAR(20),
    date_of_residence DATE,
    last_modified_date DATE,
    
    -- Dual Lineage Tracking
    created_audit_id INT REFERENCES audit.data_load_details(audit_id),
    updated_audit_id INT REFERENCES audit.data_load_details(audit_id)
);

-- Table 7: provider
CREATE TABLE public.provider (
    provider_id VARCHAR(50) PRIMARY KEY,
    fname VARCHAR(100),
    lname VARCHAR(100),
    facility_name VARCHAR(255),
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    zipcode VARCHAR(20),
    specialty_code VARCHAR(50) REFERENCES reference.specialty_code(specialty_code),
    start_date DATE,
    
    -- Dual Lineage Tracking
    created_audit_id INT REFERENCES audit.data_load_details(audit_id),
    updated_audit_id INT REFERENCES audit.data_load_details(audit_id)
);

-- Table 8: claim
CREATE TABLE public.claim (
    claim_id VARCHAR(100) PRIMARY KEY,
    patient_id VARCHAR(50) REFERENCES public.patient(patient_id),
    provider_id VARCHAR(50) REFERENCES public.provider(provider_id),
    visit_type VARCHAR(100) REFERENCES reference.visit_type(visit_type),
    total_cost NUMERIC(10, 2),
    coverage_type NUMERIC(5, 2) REFERENCES reference.coverage_type(coverage_type),
    date_of_service DATE,
    claim_date DATE,
    billed VARCHAR(1),       
    last_modified_date DATE,
    
    -- Dual Lineage Tracking
    created_audit_id INT REFERENCES audit.data_load_details(audit_id),
    updated_audit_id INT REFERENCES audit.data_load_details(audit_id)
);

-- ==========================================
-- 1. PATIENT HISTORY AUDIT TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS public.patient_history_audit (
    history_id SERIAL PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,    -- No UNIQUE constraint
    fname VARCHAR(100),
    lname VARCHAR(100),
    date_of_birth DATE,
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    zipcode VARCHAR(20),
    date_of_residence DATE,
    last_modified_date DATE,
    
    -- CDC Lineage Tracking
    created_audit_id INT,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 2. CLAIM HISTORY AUDIT TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS public.claims_history_audit (
    history_id SERIAL PRIMARY KEY,
    claim_id VARCHAR(50) NOT NULL,      -- No UNIQUE constraint
    patient_id VARCHAR(50),
    provider_id VARCHAR(50),
    visit_type VARCHAR(50),
    total_cost DECIMAL(12, 2),
    coverage_type VARCHAR(50),
    date_of_service DATE,
    claim_date_billed DATE,
    last_modified_date DATE,
    
    -- CDC Lineage Tracking
    created_audit_id INT,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 3. PROVIDER HISTORY AUDIT TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS public.providers_history_audit (
    history_id SERIAL PRIMARY KEY,
    provider_id VARCHAR(50) NOT NULL,   -- No UNIQUE constraint
    fname VARCHAR(100),
    lname VARCHAR(100),
    facility_name VARCHAR(255),
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    zipcode VARCHAR(20),
    specialty_code VARCHAR(50),
    start_date DATE,                    -- Note: No last_modified_date here!
    
    -- CDC Lineage Tracking
    created_audit_id INT,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =================================================================================
-- 5. SEED REFERENCE DATA
-- =================================================================================

INSERT INTO reference.specialty_code (specialty_code) VALUES 
('family_physician'),
('orthopedist'),
('heart_surgeon'),
('physical_therapist');

INSERT INTO reference.visit_type (visit_type) VALUES 
('physical'),
('routine'),
('illness'),
('surgery');

INSERT INTO reference.coverage_type (coverage_type) VALUES 
(100),
(50),
(0);