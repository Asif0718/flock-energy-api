# Urja portal protocol discovery

## Evidence

Both assignment documents were read completely. The user supplied portal.har with six HTTP 200 JSON exchanges after successfully using the portal in their browser. This is captured evidence, not an independently successful direct live test. Direct curl access failed with exit 7 and independent web access also failed; no connected browser was available. The raw HAR is excluded from Git and not used at runtime.

## Authentication

Origin: https://urja-ops.flockenergy.tech

POST /login uses application/x-www-form-urlencoded fields email and password. Captured headers include Accept: application/json, x-sveltekit-action: true, the matching Origin, and Referer ending in /login. The successful HTTP 200 body is:

```json
{"type":"redirect","status":303,"location":"/meters"}
```

The HTTP status itself is not 303. No CSRF field appears in the captured form. This does not prove all login variants lack CSRF requirements. Cookie/Set-Cookie data is absent in the supplied capture: actual cookie names, attributes, issuance, and lifetime are unverified. HTTPX preserves real cookies received at runtime without hardcoding names. Authentication checks the action result and validates a protected search response.

## Observed endpoints

| Method | Path | Response |
|---|---|---|
| POST | /login | JSON action redirect |
| GET | /meters/__data.json?x-sveltekit-invalidated=010 | Indexed user data in SvelteKit nodes |
| GET | /portal/meters/search?q=&page=1 | data array, total 403, page 1, pageSize 20 |
| GET | /meters/J100000/__data.json?x-sveltekit-invalidated=001 | Indexed detail and hierarchy in nodes[2].data |
| GET | /portal/meters/J100000/geo | Numeric strings in data.latitude and data.longitude |
| GET | /portal/meters/J100000/energy | data array of timestamp and numeric strings |

No guessed upstream /api/v1 endpoints or HTML selectors are used. The wrapper owns its own /api/v1 routes. Geo is recorded but outside the core implemented scope.

## Data structures

Search rows contain meterId, serialNo, make, phaseType, installStatus, dtCode. The captured page has 20 rows. Output names use snake_case. Parameter names q/page are observed, but nonempty search and later-page behavior remain unverified.

Detail is a SvelteKit indexed graph: dictionaries/lists reference other entries by numeric index. Two nodes are skipped; nodes[2] has the detail graph. The decoded root contains meterId, detail, hierarchy. detail.data has parameterName/parameterValue pairs for Meter ID, Serial No, Make, Phase Type, Installation Status, Installation Type. Both decoded meter IDs must match the request.

Hierarchy contains Meter ID, installation information, Zone, Circle, Division, Subdivision, Sub Station, Feeder, DT. Human-readable labels are preserved; no network-wide hierarchy tree was captured.

Energy fields are timestamp, kwh, kvah, voltR. Dates use dd/mm/yyyy HH:MM; numbers are strings. The first timestamp is 23/06/2026 23:30. Values rise over time, consistent with cumulative registers. Timezone and reset semantics are unverified; no interval totals are inferred.

Whitespace is collapsed. Empty strings and n/a, null, none, - normalize to null in nullable fields. These sentinel rules are adapter policy, not observed source anomalies. Dates become ISO local timestamps and numeric values become finite numbers. Missing required fields, invalid numbers, and schema changes fail with 502. Unknown indexed graph tags, negative references, and cycles are rejected.

## Failure assumptions and verification gaps

No failed login, expired session, nonexistent meter, timeout, or server failure was captured. Mock tests exercise defensive assumptions: 401 or login redirect triggers one reauthentication; 403 means denied access; HTML with HTTP 200 fails as unexpected content rather than triggering speculative login loops. Tests do not establish live failure semantics.

Live verification remains necessary for cookie issuance, expiry, invalid IDs, failed login, later pages, nonempty search, and permission failures. Fixtures retain response-only meter data and three energy samples; no login payloads or request cookies are copied.

## Additional captured detail format

The user supplied J100004.har after this meter returned a detail-schema error. Its detail graph decodes to detail.classData, a JSON string containing installed_meter. That object has MeterId, SerialNo, Make, PhaseType, InstallationStatus, and InstallationType. The adapter now maps both observed detail representations to the same output model and checks the embedded ID. A response-only fixture and regression tests cover successful decoding, malformed JSON, absent objects, and missing fields.

## Follow-up live API observations

Read-only calls through the user-started local wrapper returned 200 for page 2 (20 rows, total 403), q=J100004 (one matching row), and J100004 consumption (337 readings). Earlier detail and energy checks returned 200 for J100000, J100002, J100003, J100005, and J100006. These calls establish end-to-end wrapper results but do not expose raw upstream cookies or error envelopes. J100004 detail remained 502 on the running process despite the captured fixture passing the corrected parser, so restart/retest is still needed. J999999 detail returned a schema-error 502; the missing-meter envelope needs inspection before mapping it accurately to 404. Omitted nullable descriptive/numeric fields now normalize to null under both observed detail variants.

## Generic HTML capability

A standalone BeautifulSoup table parser is implemented and covered by synthetic tests. No HTML data response is present in either capture, so portal-specific HTML selection and response mapping remain unverified and are not automatically invoked. Generic parsing does not establish compatibility with unseen Urja HTML pages.
