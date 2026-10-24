# Architecture: ESG Carbon Disclosure Tracker

## System Architecture

The **ESG Carbon Disclosure Tracker** is an automated sustainability audit microservice. It continuously synchronizes with the US Environmental Protection Agency (EPA) Greenhouse Gas Reporting Program (GHGRP) API, resolves corporate parent ownership across direct emitting facilities, computes verified Scope 1 footprints, and flags corporate greenwashing discrepancies in real time.

```mermaid
flowchart TD
    Client[ESG Analyst / Compliance Auditor / Financial Institution] -->|HTTP / JSON with X-Request-ID| API[FastAPI Gateway Layer]
    API --> Middleware[Request Correlation Middleware]
    Middleware --> Routes{API Endpoints}

    Routes -->|POST /api/emissions/sync| EPAClient[EPA Envirofacts Client]
    Routes -->|GET /api/facilities| QuerySvc[Facility Query Engine]
    Routes -->|GET /api/corporate/{parent}/footprint| FootprintAgg[Corporate Footprint Aggregator]
    Routes -->|POST /api/audit/greenwashing-check| DiscrepancyEngine[Greenwashing Audit Engine]

    EPAClient -->|HTTPS REST Stream| EPAAPI[US EPA Envirofacts PUB_DIM_FACILITY]
    EPAClient -->|Batch Ingest| SQLite[(SQLite Database WAL Mode)]

    FootprintAgg --> SQLite
    DiscrepancyEngine --> FootprintAgg
    DiscrepancyEngine --> RiskClassifier[Risk Level & Discrepancy Scorer]

    RiskClassifier -->|Persist Provenance| SQLite
    RiskClassifier --> Output[Greenwashing Audit Result]
```

## Quantitative Greenwashing Discrepancy Model

### 1. Corporate Parent Normalization & Entity Resolution
- Corporate names in EPA facility disclosures contain varying ownership share percentages (e.g., `ASHLAND INC (100%)`, `Diamond Generating Corp (14.0%)`).
- The parser removes share percentages and legal suffixes to produce a standardized canonical identifier (`parent_company_norm`).

### 2. Physical Facility Footprint Aggregation
For any corporate entity, total Scope 1 direct emissions are calculated as the sum of all physical reporting assets under its operational control:
$$\text{Scope 1}_{\text{actual}} = \sum_{i \in \text{Facilities}} \text{Emissions}_i$$

### 3. Discrepancy & Underreporting Formula
Given a self-reported corporate disclosure $D_{\text{claimed}}$:
$$\Delta = \max\left(0.0, \, \text{Scope 1}_{\text{actual}} - D_{\text{claimed}}\right)$$
$$\text{Underreporting Percentage} = \frac{\Delta}{\text{Scope 1}_{\text{actual}}} \times 100\%$$
$$\text{Discrepancy Score} = \min\left(1.0, \, \frac{\Delta}{\text{Scope 1}_{\text{actual}}}\right)$$

### 4. Regulatory Risk Classification
- $\text{Discrepancy Score} \le 0.05$: **LOW** (truthful disclosure within allowable measurement error)
- $0.05 < \text{Discrepancy Score} \le 0.25$: **MODERATE**
- $0.25 < \text{Discrepancy Score} \le 0.50$: **HIGH**
- $\text{Discrepancy Score} > 0.50$: **SEVERE_MISREPRESENTATION** (Active Greenwashing Alert)
