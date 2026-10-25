# Assignment requirements audit

Reviewed Task.docx and the complete Flock Energy Assignment Reference Document.docx against the implementation, generated schema, 38 passing tests, supplied HAR captures, and read-only requests to the user-started local server.

## Requirement status

| Requirement | Status and evidence |
|---|---|
| Python 3.10+, FastAPI, Uvicorn, HTTPX, Pydantic, dotenv | Implemented; installed dependencies were usable for the test run through the bundled Python 3.12 fallback |
| BeautifulSoup when HTML parsing is needed | Generic table parser implemented and tested; automatic portal HTML fallback awaits an actual HTML capture |
| Required project layout | app/main.py, client.py, models.py, config.py, __init__.py, requirements.txt, .gitignore, .env.example and all required documentation exist |
| Inspect actual portal protocol | Two browser HAR captures establish login and successful data formats; endpoints and payload names are documented |
| Persistent cookie session | HTTPX AsyncClient owns cookies; mock checks verify login cookies are reused |
| Safe reauthentication | One login and GET retry after 401 or login redirect; mock verified, actual expiry behavior still pending |
| Login validation | Captured SvelteKit action result plus protected meter-search schema check; bare HTTP 200 rejected |
| GET /api/v1/meters | Implemented; live page 2 returns 20 rows, search J100004 returns one row |
| GET /api/v1/meters/{id} | Implemented; multiple IDs verified live; both captured formats pass tests; J100004 needs live retest after restart |
| GET /api/v1/meters/{id}/consumption | Implemented; multiple IDs verified live; J100004 returned 337 readings |
| Different source representations | Both observed detail formats supported: parameter pairs and JSON-encoded classData.installed_meter; same output schema for both |
| Normalize whitespace and missing values | Implemented; sentinel values and omitted nullable fields become null, with regression tests |
| Normalize dates and numbers | Captured dd/mm/yyyy timestamps become ISO local timestamps; numeric strings become finite numbers; source timezone is not invented |
| Consistent validated JSON | Pydantic response models and explicit source validation; identifiers/timestamps remain required |
| Timeouts, connection and upstream failures | Status mapping and sanitized errors implemented and mocked |
| Missing-meter response | Incomplete live behavior: HTTP 404 maps correctly, but live J999999 returned schema-error 502; upstream error envelope needs capture |
| Environment configuration and no committed secrets | .env configures credentials and is Git-ignored; raw HARs are ignored; source has no real credentials |
| Explicit session strategy | One configured operator identity per worker, serialized cookie operations, documented tenant isolation boundary |
| Timeouts and cleanup | Bounded HTTPX timeout, redirects disabled, TLS verification retained, lifespan closes client |
| Separate client and routes | Implemented in app/client.py and app/main.py |
| Concise logging without secrets | Logs wrapper failure status and session-expiry events without bodies, IDs, cookies, credentials or tokens |
| Accurate OpenAPI and /docs | Generated openapi.json exists; schema comparison test passes; /docs verified HTTP 200 |
| Automated independent tests | 38 passing pytest tests using HTTPX MockTransport and response-only fixtures |
| README commands, examples and trade-offs | Completed and updated with live evidence and limitations |
| PROTOCOL findings and anomalies | Completed for both captures; unknown cookie/expiry/error behavior explicitly distinguished |
| Five reflection answers | Five topical sections completed; exact five prompts are absent from both supplied documents |
| Clean dependency installation | User environment has working dependencies; clean install could not be independently repeated in restricted session |
| Git repository | Initialized; .env and HAR ignore checks pass; no commit or remote publication requested |

## Remaining required verification

1. Restart the local server to load the corrected parser, then retest J100004 details live. The captured-response test passes; the old running process still returned 502 during this audit.
2. Capture the raw upstream response for a nonexistent meter, such as J999999, and implement the verified error-envelope mapping to wrapper 404. Returning schema-error 502 is not complete missing-meter behavior.
3. Verify actual session-cookie issuance, failed login, and session expiration. Mocks cover the intended strategy, but sanitized captures do not establish the portal's exact failure signals or cookie attributes.
4. Repeat dependency installation in a clean Python environment before submission, then run schema export and pytest there.
5. If the assignment provider has a separate page listing the five reflection questions, supply it so the reflection can match their exact wording. Both provided documents omit that list.

## Optional or conditional work

- GET /api/v1/hierarchy is explicitly optional. Per-meter hierarchy is already returned in detail; no network-wide hierarchy endpoint was captured.
- POST /api/v1/auth/login is optional when login is managed automatically, as it is here.
- HTML parsing is conditional on receiving HTML data. Existing authorized JSON endpoints are preferred by Task.docx; the generic table parser is available, but verified portal HTML mapping remains conditional on an actual capture.

No document enumerates all possible detail formats. The implementation supports both formats actually observed and rejects unknown structures safely. It cannot truthfully claim compatibility with every unseen source representation without evidence.
