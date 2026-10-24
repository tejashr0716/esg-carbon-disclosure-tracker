from typing import Dict, Any, List, Optional
from src.database import db, normalize_company_name
from src.models import (
    GreenwashingAuditRequest,
    GreenwashingAuditResult,
    ParentCompanyFootprint
)


class CarbonAuditEngine:
    """Evaluates corporate ESG carbon claims against physical EPA facility disclosures."""

    async def get_corporate_footprint(self, parent_company: str) -> Optional[ParentCompanyFootprint]:
        """Aggregate total emissions and facility count across physical EPA assets."""
        norm_query = normalize_company_name(parent_company)
        facilities = await db.search_facilities(parent=norm_query, limit=500)

        if not facilities:
            return None

        total_emissions = sum(f.get("estimated_emissions_mt_co2e", 0.0) for f in facilities)
        states = sorted(list(set(f["state"] for f in facilities if f.get("state"))))
        naics_codes = sorted(list(set(str(f["naics_code"]) for f in facilities if f.get("naics_code"))))
        direct_emitters = sum(1 for f in facilities if "direct" in (f.get("facility_types") or "").lower())

        return ParentCompanyFootprint(
            parent_company=parent_company,
            total_facilities=len(facilities),
            states_active=states,
            primary_naics_codes=naics_codes,
            total_emissions_mt_co2e=round(total_emissions, 2),
            scope1_direct_emitter_count=direct_emitters
        )

    async def audit_greenwashing(self, request: GreenwashingAuditRequest) -> GreenwashingAuditResult:
        """Audit corporate self-reported Scope 1 emissions against EPA regulatory records."""
        footprint = await self.get_corporate_footprint(request.company_name)

        if not footprint or footprint.total_facilities == 0:
            # No EPA physical facilities found on record
            return GreenwashingAuditResult(
                company_name=request.company_name,
                claimed_scope1_mt_co2e=request.claimed_scope1_mt_co2e,
                epa_actual_scope1_mt_co2e=0.0,
                discrepancy_amount_mt_co2e=0.0,
                underreporting_percentage=0.0,
                discrepancy_score=0.0,
                risk_level="LOW",
                facility_evidence_count=0,
                top_emitting_facilities=[]
            )

        epa_actual = footprint.total_emissions_mt_co2e
        claimed = request.claimed_scope1_mt_co2e

        # Discrepancy is positive when actual physical emissions exceed corporate disclosure
        discrepancy = max(0.0, epa_actual - claimed)

        if epa_actual > 0:
            underreporting_pct = round((discrepancy / epa_actual) * 100.0, 2)
            discrepancy_score = round(min(1.0, discrepancy / epa_actual), 4)
        else:
            underreporting_pct = 0.0
            discrepancy_score = 0.0

        if discrepancy_score <= 0.05:
            risk_level = "LOW"
        elif discrepancy_score <= 0.25:
            risk_level = "MODERATE"
        elif discrepancy_score <= 0.50:
            risk_level = "HIGH"
        else:
            risk_level = "SEVERE_MISREPRESENTATION"

        # Fetch top emitting facilities for provenance
        norm_query = normalize_company_name(request.company_name)
        facs = await db.search_facilities(parent=norm_query, limit=5)
        top_facilities = [
            {
                "facility_id": f["facility_id"],
                "name": f["facility_name"],
                "state": f["state"],
                "sector": f["sector_name"],
                "emissions_mt_co2e": f["estimated_emissions_mt_co2e"]
            }
            for f in sorted(facs, key=lambda x: x.get("estimated_emissions_mt_co2e", 0), reverse=True)[:5]
        ]

        result = GreenwashingAuditResult(
            company_name=request.company_name,
            claimed_scope1_mt_co2e=claimed,
            epa_actual_scope1_mt_co2e=epa_actual,
            discrepancy_amount_mt_co2e=round(discrepancy, 2),
            underreporting_percentage=underreporting_pct,
            discrepancy_score=discrepancy_score,
            risk_level=risk_level,
            facility_evidence_count=footprint.total_facilities,
            top_emitting_facilities=top_facilities
        )

        await db.record_audit(result.model_dump())
        return result


carbon_engine = CarbonAuditEngine()
