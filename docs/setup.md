# Setup & Operations Guide: ESG Carbon Disclosure Tracker

## Prerequisites
- Python 3.12+ (tested on Python 3.14)
- Internet access to query the US EPA Envirofacts API (`https://data.epa.gov`)

## Installation
```bash
git clone https://github.com/tejashr0716/esg-carbon-disclosure-tracker.git
cd esg-carbon-disclosure-tracker

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration (.env)
```bash
cp .env.example .env
```

Available configuration flags:
- `EPA_API_BASE_URL`: Live EPA Envirofacts endpoint (`https://data.epa.gov/efservice/PUB_DIM_FACILITY`)
- `DATABASE_URL`: SQLite connection URI
- `DB_PATH`: SQLite database file path (`data/carbon.db`)
- `REQUEST_TIMEOUT_SECONDS`: Maximum timeout for external API requests (`20.0`)

## Running the API Gateway
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## Running Automated Tests
```bash
pytest -v --junitxml=artifacts/test-results.xml
```

## Running Empirical Benchmark
```bash
python benchmarks/benchmark_emissions_ingest.py
```
Outputs empirical audit latency and throughput metrics to `artifacts/benchmark-results.json`.
