# Flock Energy Urja API

FastAPI wrapper implementing the requests observed in the user-provided portal HAR. Credentials are loaded only from environment settings; raw captures are never loaded by the application.

## Install and run

Python 3.10+ is required. From this directory in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` to set `URJA_EMAIL` and `URJA_PASSWORD`, then run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Swagger UI: http://127.0.0.1:8000/docs. Login occurs automatically on the first API request. Swagger's default UI assets need internet access.

## Requests

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/meters?q=&page=1"
curl.exe "http://127.0.0.1:8000/api/v1/meters/J100000"
curl.exe "http://127.0.0.1:8000/api/v1/meters/J100000/consumption"
curl.exe "http://127.0.0.1:8000/openapi.json"
```

Search returns `data`, `total`, `page`, and `page_size`. One captured row normalizes to:

```json
{"meter_id":"J100000","serial_number":"SE33962","make":"HPL","phase_type":"single","installation_status":"Decommissioned","dt_code":"DT-001"}
```

Detail adds `installation_type` and a `hierarchy` dictionary. Its `dt_code` is null because the source detail has a descriptive DT label rather than a separate code. The adapter does not guess codes from labels.

Consumption returns `meter_id` and `readings`, with `timestamp`, `kwh`, `kvah`, and `voltage_r`. The source energy values are cumulative registers, not interval usage. Dates become ISO timestamps without an invented timezone. Numeric fields become finite numbers; blank and sentinel values become null in nullable fields. Invalid dates and numbers fail validation rather than silently becoming zero.

## Export and test

```powershell
.\.venv\Scripts\python.exe -m scripts.export_openapi
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app tests scripts
```

Export writes `openapi.json` from the implemented application without credentials or network calls. Run export before tests; one test compares the artifact to the application schema. Tests use HTTPX MockTransport and response-only fixtures, never live credentials. They cover captured data, login validation, cookies, expiry, normalization, upstream failures, invalid input, cleanup, and schema consistency.

## Architecture and trade-offs

`app/main.py` defines routes and error mapping; `app/client.py` owns portal requests and the SvelteKit indexed-JSON decoder; `app/models.py` validates and normalizes data; `app/config.py` loads environment settings.

Each worker deliberately owns one service-operator session. An asyncio lock serializes authenticated request operations and cookie updates. Unrelated tenants must use separate instances/settings; this is not a per-user login service. Application lifespan closes HTTPX resources. No caller can supply portal credentials.

A 401 or redirect to `/login` triggers one login and GET retry. Login must match the captured action result and pass a protected meter-search schema check. A bare HTTP 200 is insufficient. HTTPX uses bounded timeouts, TLS verification, and no automatic redirects. Logs and error responses exclude credentials, cookies, tokens, and upstream bodies.

| Failure | API status |
|---|---|
| Invalid API inputs | 422 |
| Upstream resource not found | 404 |
| Missing configured credentials | 503 |
| Timeout | 504 |
| Connection, upstream authentication, permission, schema, or server failure | 502 |

Upstream authentication failures are 502 because the failing credentials belong to the service identity, not the API caller.

No database, cache, or browser automation is needed. BeautifulSoup4 powers the generic HTML table parser in app/html_parser.py. All observed portal routes return JSON, so automatic portal HTML fallback is not enabled without a real source capture. Global hierarchy is omitted because only per-meter hierarchy was captured; it is returned in detail. No unobserved filters/date parameters are invented. The decoder supports the observed JSON-compatible indexed graph and fails on unsupported tags, references, or cycles. Search forwards the observed q/page parameters, and live checks through the locally running API confirmed page 2 and search for J100004.

The run command binds to loopback. Add caller authentication/access control before exposing operator data remotely.

## Verification status

OpenAPI was exported from the application and all 38 automated tests passed. Compilation and captured-detail decoder checks passed. Live checks through the user-started local server confirmed detail and consumption responses for J100000, J100002, J100003, J100005, and J100006. Page 2 and search for J100004 returned HTTP 200, and its consumption returned 337 readings. The running server still rejected J100004 detail; the corrected parser passes its captured-response regression test but needs a server restart and live retest. A nonexistent meter J999999 returned 502 rather than the required 404; its actual upstream error envelope remains to be captured. Direct upstream access from the restricted session remains unavailable.

The existing .venv points to a Python 3.13 installation inaccessible to this session. Verification used the bundled Python 3.12 runtime, appending the .venv package directory after its own compatible native packages. Standard local setup commands above remain the recommended path.

See PROTOCOL.md for observed behavior and REFLECTION.md for implementation reflection.

Meter details support both observed representations: parameterName/parameterValue rows and JSON-encoded classData.installed_meter (captured for J100004). Restart an existing server after pulling code changes, or use uvicorn --reload during local development.

See REQUIREMENTS_AUDIT.md for the requirement-by-requirement status and remaining submission checks. Omitted nullable descriptive and energy fields normalize to null; meter identifiers and timestamps remain required.

## HTML table parser

`app.html_parser.parse_html_table` converts a selected table with a header row to dictionaries. It decodes entities, collapses whitespace, handles nested cell text, drops script/style text, and normalizes empty/sentinel values. Explicit numeric columns become finite floats; explicit date formats become ISO strings. Other columns remain strings so identifiers keep leading zeros.

```python
from app.html_parser import parse_html_table
rows = parse_html_table(html, numeric_columns=("kwh",),
                        datetime_columns={"timestamp": "%d/%m/%Y %H:%M"})
```

This parser is tested with synthetic HTML, not invented Urja fixtures. Ambiguous headers, merged/nested tables, ragged rows, invalid numbers, and invalid dates raise ValueError. Table selection and column conversions are explicit. Connecting it to a portal endpoint requires an actual HTML capture and verified mapping, including pagination metadata for search and hierarchy for detail. Existing portal endpoints continue to reject unexpected HTML with 502; a login/error page must not become a successful empty-data response.
