from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Facility(BaseModel):
    facility_id: int
    facility_name: str
    state: str
    city: str
    zip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    naics_code: str
    sector_name: str
    year: int
    parent_company: Optional[str] = None
    facility_types: str = "Direct Emitter"
    reported_subparts: str = ""
    estimated_emissions_mt_co2e: float = 0.0


class ParentCompanyFootprint(BaseModel):
    parent_company: str
    total_facilities: int
    states_active: List[str]
    primary_naics_codes: List[str]
    total_emissions_mt_co2e: float
    scope1_direct_emitter_count: int


class GreenwashingAuditRequest(BaseModel):
    company_name: str = Field(..., min_length=1, description="Target corporate entity name")
    claimed_scope1_mt_co2e: float = Field(..., ge=0.0, description="Self-reported Scope 1 emissions in MT CO2e")
    reporting_year: int = Field(default=2022, ge=2010, le=2030)
    claim_statement: Optional[str] = Field(default=None, description="Public corporate ESG disclosure or net-zero pledge")


class GreenwashingAuditResult(BaseModel):
    company_name: str
    claimed_scope1_mt_co2e: float
    epa_actual_scope1_mt_co2e: float
    discrepancy_amount_mt_co2e: float
    underreporting_percentage: float
    discrepancy_score: float = Field(..., ge=0.0, le=1.0, description="0.0 = completely truthful, 1.0 = severe greenwashing")
    risk_level: str = Field(..., description="LOW, MODERATE, HIGH, SEVERE_MISREPRESENTATION")
    facility_evidence_count: int
    top_emitting_facilities: List[Dict[str, Any]] = Field(default_factory=list)


class SyncResponse(BaseModel):
    status: str
    records_ingested: int
    duration_seconds: float


class HealthResponse(BaseModel):
    status: str
    database_status: str
    total_facilities_indexed: int
    unique_parent_companies: int
