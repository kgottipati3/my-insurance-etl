import logging
from pydantic import BaseModel, Field, field_validator, model_validator, ValidationInfo, ValidationError
from typing import Optional, Any
from datetime import date
from dateutil import parser

# Initialize the logger
logger = logging.getLogger(__name__)


# 1. THE DATE PARSER
def parse_flexible_date(v: Any) -> Optional[date]:
    """Safely converts messy strings like '9-19-1948' and '1/7/2016' into Python dates."""
    if v is None or str(v).strip() == "":
        return None
    if isinstance(v, date):
        return v
    try:
        return parser.parse(str(v)).date()
    except (ValueError, TypeError):
        raise ValueError(f"Invalid date format: {v}")



# 2. PATIENT CONTRACT

class PatientModel(BaseModel):
    # REGEX: Must be digits followed by exactly one 'U' (e.g., "62000U")
    patient_id: str = Field(..., pattern=r'^\d+U$')
    fname: Optional[str] = Field(None, max_length=100)
    lname: Optional[str] = Field(None, max_length=100)
    date_of_birth: Optional[date] = None
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zipcode: Optional[str] = Field(None, max_length=20)
    date_of_residence: Optional[date] = None
    last_modified_date: date

    @field_validator('date_of_birth', 'date_of_residence', 'last_modified_date', mode='before')
    def parse_dates(cls, v):
        return parse_flexible_date(v)

    @field_validator('date_of_birth')
    def check_dob_past(cls, v):
        if v and v > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        return v



# 3. PROVIDER CONTRACT

class ProviderModel(BaseModel):
    # REGEX: Must start with N3T, followed by digits, end with A (e.g., "N3T5300A")
    provider_id: str = Field(..., pattern=r'^N3T\d+A$')
    fname: Optional[str] = Field(None, max_length=100)
    lname: Optional[str] = Field(None, max_length=100)
    facility_name: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zipcode: Optional[str] = Field(None, max_length=20)
    specialty_code: Optional[str] = Field(None, max_length=50)
    start_date: Optional[date] = None

    @field_validator('start_date', mode='before')
    def parse_dates(cls, v):
        return parse_flexible_date(v)

    @field_validator('specialty_code')
    def validate_specialty(cls, v, info: ValidationInfo):
        if v is None: return v
        context = info.context
        if context and 'valid_specialties' in context:
            if v not in context['valid_specialties']:
                raise ValueError(f"Invalid specialty_code '{v}'. Must be one of {context['valid_specialties']}")
        return v



# 4. CLAIM CONTRACT

class ClaimModel(BaseModel):
    # AGGRESSIVE REGEX TO CATCH STRUCTURAL SWAPS
    claim_id: str = Field(..., pattern=r'^CF#\d+[A-Z]+$')  
    patient_id: str = Field(..., pattern=r'^\d+U$')        
    provider_id: str = Field(..., pattern=r'^N3T\d+A$')    
    
    visit_type: str = Field(..., max_length=100)
    total_cost: Optional[float] = None
    coverage_type: Optional[float] = None
    date_of_service: date
    claim_date: date
    billed: Optional[str] = Field(None, max_length=1)
    last_modified_date: date

    @field_validator('date_of_service', 'claim_date', 'last_modified_date', mode='before')
    def parse_dates(cls, v):
        return parse_flexible_date(v)

    @field_validator('total_cost', 'coverage_type', 'billed', mode='before')
    def clean_empty_strings(cls, v):
        if v == "" or str(v).strip() == "":
            return None
        return v

    @field_validator('visit_type')
    def validate_visit_type(cls, v, info: ValidationInfo):
        context = info.context
        if context and 'valid_visit_types' in context:
            if v not in context['valid_visit_types']:
                raise ValueError(f"Invalid visit_type '{v}'. Must be one of {context['valid_visit_types']}")
        return v

    @field_validator('coverage_type')
    def validate_coverage(cls, v, info: ValidationInfo):
        if v is None: return v
        context = info.context
        if context and 'valid_coverage_types' in context:
            if v not in context['valid_coverage_types']:
                raise ValueError(f"Invalid coverage_type '{v}'. Must be exactly one of {context['valid_coverage_types']}")
        return v
    
    @field_validator('provider_id')
    def validate_provider_fk(cls, v, info: ValidationInfo):
        context = info.context
        # Check if the provider exists in our in-memory cache
        if context and 'valid_providers' in context:
            if v not in context['valid_providers']:
                raise ValueError(f"Orphan Record Blocked: Provider ID '{v}' does not exist in the database.")
        return v

    @field_validator('patient_id')
    def validate_patient_fk(cls, v, info: ValidationInfo):
        context = info.context
        # Check if the patient exists in our in-memory cache
        if context and 'valid_patients' in context:
            if v not in context['valid_patients']:
                raise ValueError(f"Orphan Record Blocked: Patient ID '{v}' does not exist in the database.")
        return v
    
    @model_validator(mode='after')
    def catch_chronological_swaps(self):
        if self.date_of_service > self.claim_date:
            raise ValueError(
                f"Chronological Swap Detected: date_of_service ({self.date_of_service}) "
                f"is AFTER the claim_date ({self.claim_date}). Time travel is not permitted."
            )
        return self



# 5. THE VALIDATION ENGINE (CDC UPGRADE)

def validate_dataframe_rows(
    df_records: list[dict], 
    model_class, 
    pk_field: str, 
    cdc_field: str | None, 
    validation_context: dict
):
    """
    Validates dictionaries against a Pydantic model.
    Implements a dynamic CDC Tie-Breaker and Dead Letter Queue for In-Batch Duplicates.
    """
    clean_records = []
    quarantined_records = []
    history_records = []

    # 1. BATCH PRE-FLIGHT: Group by Primary Key
    pk_groups = {}
    for index, record in enumerate(df_records):
        pk_val = str(record.get(pk_field, ''))
        if pk_val:
            if pk_val not in pk_groups:
                pk_groups[pk_val] = []
            pk_groups[pk_val].append({"index": index, "record": record})

    # Sets to track which row indexes to skip during final validation
    conflicted_indices = set()
    superseded_indices = set()

    # 2. RESOLUTION ENGINE: Evaluate Ties Dynamically
    for pk_val, items in pk_groups.items():
        if len(items) > 1:
            # No CDC field? Route ALL duplicates straight to Dead Letter Queue.
            if not cdc_field:
                for item in items:
                    conflicted_indices.add(item["index"])
                continue

            # Have a CDC field? Execute Time-Travel logic:
            try:
                sorted_items = sorted(
                    items, 
                    key=lambda x: parser.parse(str(x["record"].get(cdc_field, "1900-01-01"))), 
                    reverse=True
                )
                
                date_1 = parser.parse(str(sorted_items[0]["record"].get(cdc_field, "1900-01-01")))
                date_2 = parser.parse(str(sorted_items[1]["record"].get(cdc_field, "1900-01-01")))

                if date_1 > date_2:
                    for item in sorted_items[1:]:
                        superseded_indices.add(item["index"])
                else:
                    for item in items:
                        conflicted_indices.add(item["index"])
            
            except Exception as e:
                logger.warning(f"Date parsing failed for ID {pk_val}: {e}")
                for item in items:
                    conflicted_indices.add(item["index"])

    # 3. VALIDATION & ROUTING LOOP
    for index, record in enumerate(df_records):
        pk_val = str(record.get(pk_field, ''))
        
        # Route 1: True Conflicts
        if index in conflicted_indices:
            quarantined_records.append({
                "record_key": pk_val,
                "field_name": pk_field,
                "error_message": "CRITICAL: Unresolvable duplicate. No CDC timestamp, or timestamps are identical.",
                "raw_payload": record
            })
            continue

        # Route 2: Safely Superseded
        if index in superseded_indices:
            history_records.append({
                "record_key": pk_val,
                "raw_payload": record
            })
            continue

        # Route 3: Normal Pydantic Validation
        try:
            valid_model = model_class.model_validate(record, context=validation_context)
            clean_records.append(valid_model)
            
        except ValidationError as e:
            # 1. Pydantic specific errors: Extract only the field names and the clean message
            clean_errors = []
            for err in e.errors():
                field_name = err['loc'][0] if err['loc'] else 'Unknown Field'
                clean_errors.append(f"{field_name}: {err['msg']}")
                
            quarantined_records.append({
                "record_key": str(record.get(pk_field, f'ROW_INDEX_{index}')),
                "field_name": "Multiple",
                "error_message": " | ".join(clean_errors), # Joins multiple errors cleanly
                "raw_payload": record
            })
            
        except Exception as e:
            # 2. Fallback for any other random Python system crashes
            quarantined_records.append({
                "record_key": str(record.get(pk_field, f'ROW_INDEX_{index}')),
                "field_name": "Multiple",
                "error_message": f"System Error: {str(e)}",
                "raw_payload": record
            })

    return clean_records, quarantined_records, history_records