import pytest
from httpx import AsyncClient, ASGITransport
from src.database import db, normalize_company_name
from src.epa_client import map_naics_to_sector, estimate_co2e_emissions, epa_client
from src.carbon_engine import carbon_engine
from src.models import GreenwashingAuditRequest
from src.main import app


# -------------------------------------------------------------
# 1. NAICS Mapping & Emissions Modeling Tests
# -------------------------------------------------------------
def test_naics_mapping_known_sectors():
    assert "Electric Power" in map_naics_to_sector("221112")
    assert "Petroleum Refineries" in map_naics_to_sector("324110")
    assert "Chemical" in map_naics_to_sector("325199")
    assert "Iron and Steel" in map_naics_to_sector("331110")
    assert "Cement" in map_naics_to_sector("327310")
    assert "Oil and Gas" in map_naics_to_sector("211120")


def test_naics_mapping_unknown_and_empty():
    assert map_naics_to_sector("999999") == "General Manufacturing"
    assert map_naics_to_sector("") == "Unclassified Industrial"
    assert map_naics_to_sector(None) == "Unclassified Industrial"


def test_estimate_co2e_emissions_multipliers():
    single = estimate_co2e_emissions("Direct Emitter", "C", "221112")
    multi = estimate_co2e_emissions("Direct Emitter", "C,D,Y", "221112")
    assert single == 480000.0
    assert multi > single


# -------------------------------------------------------------
# 2. Parent Company Normalization Tests
# -------------------------------------------------------------
def test_normalize_company_name_percentages():
    assert normalize_company_name("ASHLAND INC (100%)") == "ashland inc"
    assert normalize_company_name("Valero Energy Corp (74.5%)") == "valero energy corp"
    assert normalize_company_name("Company A (50.0%); Company B (50.0%)") == "company a"


def test_normalize_company_name_punctuation_and_whitespace():
    assert normalize_company_name("   Chevron,   U.S.A.   Inc.   ") == "chevron u s a inc"
    assert normalize_company_name("") == ""
    assert normalize_company_name(None) == ""


def test_normalize_company_name_multiple_semicolons():
    res = normalize_company_name("Tenaska Energy Inc; Diamond Generating Corp; Empeco IV LLC")
    assert res == "tenaska energy inc"


# -------------------------------------------------------------
# 3. Database & Facilities Persistence Tests
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_database_batch_insert_and_count():
    db.init_sync_db()
    test_facilities = [
        {
            "facility_id": 99901,
            "facility_name": "Test Power Plant 1",
            "state": "TX",
            "city": "HOUSTON",
            "naics_code": "221112",
            "sector_name": "Electric Power Generation & Utilities",
            "year": 2022,
            "parent_company": "Apex Energy Holdings (100%)",
            "facility_types": "Direct Emitter",
            "reported_subparts": "C",
            "estimated_emissions_mt_co2e": 500000.0
        },
        {
            "facility_id": 99902,
            "facility_name": "Test Chemical Unit 2",
            "state": "LA",
            "city": "BATON ROUGE",
            "naics_code": "325199",
            "sector_name": "Basic Chemical Manufacturing",
            "year": 2022,
            "parent_company": "Apex Energy Holdings (100%)",
            "facility_types": "Direct Emitter",
            "reported_subparts": "C,V",
            "estimated_emissions_mt_co2e": 200000.0
        }
    ]
    await db.insert_facilities_batch(test_facilities, clear_existing=False)
    count = await db.get_total_facilities_count()
    assert count >= 2


@pytest.mark.asyncio
async def test_database_search_filtering():
    facs_tx = await db.search_facilities(state="TX")
    assert all(f["state"] == "TX" for f in facs_tx)

    facs_parent = await db.search_facilities(parent="Apex Energy")
    assert len(facs_parent) >= 2


@pytest.mark.asyncio
async def test_database_insert_overwrite():
    # Insert updated facility with same id
    updated = [{
        "facility_id": 99901,
        "facility_name": "Test Power Plant 1 - Updated",
        "state": "TX",
        "parent_company": "Apex Energy Holdings (100%)",
        "estimated_emissions_mt_co2e": 550000.0
    }]
    await db.insert_facilities_batch(updated, clear_existing=False)
    res = await db.search_facilities(parent="Apex Energy")
    match = next(f for f in res if f["facility_id"] == 99901)
    assert match["facility_name"] == "Test Power Plant 1 - Updated"
    assert match["estimated_emissions_mt_co2e"] == 550000.0


# -------------------------------------------------------------
# 4. Corporate Footprint Aggregation Tests
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_corporate_footprint_aggregation():
    fp = await carbon_engine.get_corporate_footprint("Apex Energy Holdings")
    assert fp is not None
    assert fp.total_facilities >= 2
    assert fp.total_emissions_mt_co2e >= 700000.0
    assert "TX" in fp.states_active
    assert "LA" in fp.states_active


@pytest.mark.asyncio
async def test_corporate_footprint_non_existent():
    fp = await carbon_engine.get_corporate_footprint("NonExistentCorporationXYZ999")
    assert fp is None


# -------------------------------------------------------------
# 5. Greenwashing Discrepancy & Risk Level Tests
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_greenwashing_truthful_disclosure():
    req = GreenwashingAuditRequest(
        company_name="Apex Energy Holdings",
        claimed_scope1_mt_co2e=800000.0
    )
    res = await carbon_engine.audit_greenwashing(req)
    assert res.discrepancy_amount_mt_co2e == 0.0
    assert res.discrepancy_score == 0.0
    assert res.risk_level == "LOW"


@pytest.mark.asyncio
async def test_greenwashing_low_risk_boundary_case():
    fp = await carbon_engine.get_corporate_footprint("Apex Energy Holdings")
    actual = fp.total_emissions_mt_co2e
    # Claim 97% of actual (3% discrepancy <= 5% -> LOW)
    req = GreenwashingAuditRequest(
        company_name="Apex Energy Holdings",
        claimed_scope1_mt_co2e=actual * 0.97
    )
    res = await carbon_engine.audit_greenwashing(req)
    assert res.risk_level == "LOW"
    assert res.discrepancy_score <= 0.05


@pytest.mark.asyncio
async def test_greenwashing_moderate_underreporting():
    fp = await carbon_engine.get_corporate_footprint("Apex Energy Holdings")
    actual = fp.total_emissions_mt_co2e
    req = GreenwashingAuditRequest(
        company_name="Apex Energy Holdings",
        claimed_scope1_mt_co2e=actual * 0.85
    )
    res = await carbon_engine.audit_greenwashing(req)
    assert res.discrepancy_amount_mt_co2e > 0.0
    assert 0.05 < res.discrepancy_score <= 0.25
    assert res.risk_level == "MODERATE"


@pytest.mark.asyncio
async def test_greenwashing_high_underreporting():
    fp = await carbon_engine.get_corporate_footprint("Apex Energy Holdings")
    actual = fp.total_emissions_mt_co2e
    req = GreenwashingAuditRequest(
        company_name="Apex Energy Holdings",
        claimed_scope1_mt_co2e=actual * 0.60
    )
    res = await carbon_engine.audit_greenwashing(req)
    assert 0.25 < res.discrepancy_score <= 0.50
    assert res.risk_level == "HIGH"


@pytest.mark.asyncio
async def test_greenwashing_severe_misrepresentation():
    fp = await carbon_engine.get_corporate_footprint("Apex Energy Holdings")
    actual = fp.total_emissions_mt_co2e
    req = GreenwashingAuditRequest(
        company_name="Apex Energy Holdings",
        claimed_scope1_mt_co2e=actual * 0.10
    )
    res = await carbon_engine.audit_greenwashing(req)
    assert res.discrepancy_score > 0.50
    assert res.risk_level == "SEVERE_MISREPRESENTATION"
    assert len(res.top_emitting_facilities) > 0


@pytest.mark.asyncio
async def test_greenwashing_unknown_company():
    req = GreenwashingAuditRequest(
        company_name="Ghost Corporation 123",
        claimed_scope1_mt_co2e=50000.0
    )
    res = await carbon_engine.audit_greenwashing(req)
    assert res.epa_actual_scope1_mt_co2e == 0.0
    assert res.risk_level == "LOW"
    assert res.facility_evidence_count == 0


# -------------------------------------------------------------
# 6. EPA Client Tests
# -------------------------------------------------------------
def test_epa_client_fallback_structure():
    fallbacks = epa_client.get_fallback_facilities()
    assert len(fallbacks) >= 4
    for f in fallbacks:
        assert "facility_id" in f
        assert "facility_name" in f
        assert "estimated_emissions_mt_co2e" in f


@pytest.mark.asyncio
async def test_epa_client_live_fetch():
    facs = await epa_client.fetch_live_facilities(state="WA", limit=5)
    assert len(facs) > 0
    assert "WA" in facs[0]["state"]


# -------------------------------------------------------------
# 7. API Gateway & Endpoints Tests
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "HEALTHY"
        assert data["total_facilities_indexed"] > 0


@pytest.mark.asyncio
async def test_api_sync_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/emissions/sync?state=TX&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["records_ingested"] > 0


@pytest.mark.asyncio
async def test_api_facilities_list_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/facilities?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0


@pytest.mark.asyncio
async def test_api_facilities_state_filter():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/facilities?state=TX&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        for f in data:
            assert f["state"] == "TX"


@pytest.mark.asyncio
async def test_api_facilities_parent_filter():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/facilities?parent=Apex%20Energy&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1


@pytest.mark.asyncio
async def test_api_corporate_footprint_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/corporate/Apex%20Energy/footprint")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_facilities"] >= 2
        assert data["total_emissions_mt_co2e"] > 0


@pytest.mark.asyncio
async def test_api_corporate_footprint_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/corporate/CompletelyFakeCorporation999/footprint")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_audit_greenwashing_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "company_name": "Apex Energy",
            "claimed_scope1_mt_co2e": 150000.0,
            "reporting_year": 2022
        }
        resp = await ac.post("/api/audit/greenwashing-check", json=payload, headers={"X-Request-ID": "test-green-trace"})
        assert resp.status_code == 200
        assert resp.headers.get("X-Request-ID") == "test-green-trace"
        data = resp.json()
        assert data["company_name"] == "Apex Energy"
        assert data["discrepancy_score"] > 0.0


@pytest.mark.asyncio
async def test_api_audit_history_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/audit/history?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0


@pytest.mark.asyncio
async def test_api_request_correlation_id_generated_when_missing():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers


@pytest.mark.asyncio
async def test_api_validation_error_negative_claimed_emissions():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "company_name": "Apex Energy",
            "claimed_scope1_mt_co2e": -500.0
        }
        resp = await ac.post("/api/audit/greenwashing-check", json=payload)
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_validation_error_invalid_year():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "company_name": "Apex Energy",
            "claimed_scope1_mt_co2e": 500.0,
            "reporting_year": 1980
        }
        resp = await ac.post("/api/audit/greenwashing-check", json=payload)
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_facilities_invalid_limit():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/facilities?limit=0")
        assert resp.status_code == 422
