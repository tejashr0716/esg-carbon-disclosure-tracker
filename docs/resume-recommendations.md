# Verified XYZ Résumé Recommendations: ESG Carbon Disclosure Tracker

## 1. Verified XYZ Résumé Bullets

1. **Accomplished** sub-3ms greenwashing discrepancy and corporate carbon surveillance, **as measured by** achieving a 2.03ms P50 latency (2.94ms P95) and evaluating 450.77 corporate audits per second across 500 benchmarked runs, **by doing** engineering an automated discrepancy model comparing self-reported Scope 1 pledges against regulatory physical EPA facility assets.
2. **Accomplished** automated entity resolution across global industrial parent corporations, **as measured by** standardizing complex multi-partner equity shares and ownership percentages into canonical footprints across 32 passing automated tests in 8.1s, **by doing** building an asynchronous ingestion pipeline with NAICS sector mapping and normalized SQLite indexing.
3. **Accomplished** verifiable corporate sustainability compliance and audit durability, **as measured by** capturing 100% of audit traces with UUIDv4 request correlation headers and physical facility evidence breakdowns, **by doing** developing an asynchronous SQLite WAL-mode audit engine featuring multi-tier risk classification (LOW, MODERATE, HIGH, SEVERE_MISREPRESENTATION).

---

## 2. Claim-to-Evidence Table

| Résumé Claim | Metric / Value | Verification Source |
| :--- | :--- | :--- |
| **Audit Latency** | Min: 1.41ms, Mean: 2.21ms, P50: 2.03ms, P95: 2.94ms | `artifacts/benchmark-results.json` (`audit_latency_ms`) |
| **Audit Throughput** | 450.77 audits / second (500 runs in 1.109s) | `artifacts/benchmark-results.json` (`throughput_audits_per_second`) |
| **Test Suite Coverage** | 32 passed, 0 failed, 100% pass rate in 8.14s | `artifacts/test-summary.json` & `artifacts/test-results.xml` |
| **Live API Integration** | Real US EPA Envirofacts GHGRP API (`PUB_DIM_FACILITY`) | `src/epa_client.py`, verified status 200 |
| **Audit Durability** | SQLite WAL-mode persistence of audit JSON and facility IDs | `src/database.py`, verified table `corporate_audits` |

---

## 3. Forbidden Claims Guide

- **DO NOT** claim full global Scope 3 supply chain carbon tracking (the EPA GHGRP mandates Scope 1 direct physical facility emissions).
- **DO NOT** claim integration with paid proprietary ESG rating agencies (MSCI, Sustainalytics) (engine operates purely on sovereign US regulatory disclosures).
- **DO NOT** claim satellite remote sensing imaging ingestion (connects to official US EPA ground facility registry and emissions accounting).
