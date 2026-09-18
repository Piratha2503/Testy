# API Test Agent — 16 Session Plan

Swagger-driven automated API testing tool · MVP scope · CLI only

Source: `api_test_agent_16_session_plan.pdf` (இதுவே working copy)

| | |
|---|---|
| SESSION | 3 hrs / day |
| EFFECTIVE | ~2.5 hrs |
| TOTAL | 40 hrs |
| DURATION | 3.5 weeks |
| HARD LIMIT | 4 weeks |

**STACK:** Python 3.11+ · `requests` · `PyYAML` · `anthropic` SDK · `pytest` · `csv` (stdlib)

**NOT IN MVP:** FastAPI · Database · Docker · LangChain · n8n · Frontend · Async

---

## PHASE 1 · FOUNDATION — NO LLM

### 01 · Project setup + Swagger parser
- venv, folder structure, `requirements.txt`
- `core/swagger.py` — OpenAPI 3 parse, `$ref` resolve, circular ref guard
- `Endpoint` dataclass — path, method, request_schema, documented_codes

> **DONE WHEN:** Spec file-ஐ படிச்சு `Endpoint` objects list return ஆகும்.

### 02 · API client + Guardrails
- `config.yaml` — base_url, auth, timeout, allowed_methods
- `core/client.py` — `require_host_substring` check, method allowlist, blocked patterns
- Response truncate (500 chars), timeout handling

> **DONE WHEN:** Production-மாதிரி host கொடுத்தா program `GuardrailError` ஓட exit ஆகும்.

### 03 · Parser-ஐ real spec மேல validate பண்றது
- உங்க actual swagger (இல்ல Petstore spec) load பண்ணுங்க
- `main.py list` command — endpoints-ஐ table ஆ print
- Break ஆகற இடம் fix — `allOf`, missing schema, nested `$ref`

> **DONE WHEN:** `python main.py list` → எல்லா endpoints-ும் method, path, documented codes ஓட print ஆகும்.

### 04 · Test case JSON format + கையால 5 cases
- Schema fix: `name`, `category`, `body`, `query`, `expected_status`, `reason`
- ஒரு endpoint-க்கு கையால 5 test cases எழுதுங்க
- `testcases/` folder, git-ல commit

> **DONE WHEN:** Format final. LLM இதை generate பண்ண முடியும்-னு உறுதி.

---

## PHASE 2 · WORKING TOOL

### 05 · Executor — replay loop
- `core/executor.py` — testcase JSON படிச்சு client call பண்ணும்
- `GuardrailError`-ஐ `SKIPPED` ஆ record பண்ணு, crash ஆகாம

> **DONE WHEN:** கையால எழுதின 5 cases run ஆகி, response status terminal-ல print ஆகும்.

### 06 · Verdict logic
- 5xx எப்பவுமே → **FAIL**
- expected_status match → **PASS**
- Documented, ஆனா expected இல்ல → **NEEDS_REVIEW**
- வேற எதுவும் → **FAIL**

> **DONE WHEN:** ஒவ்வொரு case-க்கும் verdict வரும். Precision முக்கியம் — சந்தேகம்னா `NEEDS_REVIEW`.

### 07 · CSV reporter + CLI wiring
- `core/reporter.py` — endpoint, case, input, expected, actual, verdict, ms
- `main.py run --all` / `--endpoint` / `--limit`
- Run summary: total / pass / fail / review counts

> **DONE WHEN:** LLM இல்லாத ஒரு **WORKING TOOL**. இங்க நிறுத்தினாலும் மிச்சம் இருக்கு.

---

### 08 · உங்க real staging API மேல முதல் run — ⚑ CHECKPOINT
- Staging base_url, real auth token
- GET endpoints, path param இல்லாதது மட்டும்
- CSV output-ஐ கண்ணால review பண்ணுங்க

> **DONE WHEN:** Real API-ல real result.
> **இது வரலைன்னா PLAN-ஐ நிறுத்தி ஏன்-னு கண்டுபிடிங்க** — LLM வரைக்கும் காத்திருக்காதீங்க.

---

## PHASE 3 · REALITY HARDENING — ⚠️ TIMELINE RISK ZONE

### 09 · Auth + seed data
- Token refresh / expiry handling
- `seed_data.yaml` — valid `user_id`, `order_id` path params-க்கு
- Third-party call பண்ற endpoints-ஐ skip list-ல போடுங்க

> **DONE WHEN:** Path param உள்ள endpoints-ும் run ஆகும். 404 noise இல்ல.

### 10 · Real swagger quirks + POST enable
- Spec-ல documented codes vs actual behaviour வித்தியாசம் — **இதுவே ஒரு finding**
- `allowed_methods`-ல POST சேருங்க, blocked patterns tighten பண்ணுங்க

> **DONE WHEN:** 10+ endpoints clean-ஆ run ஆகும், rerun பண்ணா same output.

---

## PHASE 4 · LLM LAYER

### 11 · Generator — ஒரு endpoint மட்டும்
- `core/generator.py` — anthropic SDK direct, `temperature=0`
- Prompt: 6 cases, JSON array only, invalid input → 4xx expect பண்ணு
- Token usage log பண்ணுங்க

> **DONE WHEN:** ஒரு endpoint-க்கு auto-generated JSON file. Executor அத run பண்ணும்.

### 12 · Output validation
- `validate_schema()` — required keys, type check, status range
- Fence strip, JSON parse failure-ல retry once
- Invalid case-ஐ silently drop பண்ணாம, log பண்ணுங்க

> **DONE WHEN:** LLM தப்பான JSON கொடுத்தாலும் executor crash ஆகாது.

### 13 · Generate-ஐ scale பண்றது
- `generate --all` — Python outer loop, endpoint-by-endpoint
- Prompt caching (system prompt same, 60 iterations)
- `--limit` flag default-ஆ வைக்கங்க — accidental full run தடுக்க

> **DONE WHEN:** எல்லா endpoints-க்கும் `testcases/` folder நிரம்பும். Cost print ஆகும்.

### 14 · Generated cases review + prompt tune
- Generated cases-ஐ கையால படிங்க — nonsense-ஆ, useful-ஆ?
- False positive அதிகம்னா prompt tighten பண்ணுங்க
- Final cases-ஐ git-ல commit

> **DONE WHEN:** Cases quality ok. இது தான் tool-ஓட credibility.

---

## PHASE 5 · SHIP

### 15 · Cost tracking + run summary
- Per-run token + $ cost, CSV-ல ஒரு column
- Manager Excel கேட்டா `openpyxl` — ஒரு function தான்

> **DONE WHEN:** Real numbers கையில. Estimate இல்ல.

### 16 · README + demo prep
- Setup steps, config explain, guardrails warning
- 5 நிமிஷ demo script
- Coverage table — agent எது cover பண்ணும், எது manual வேணும்

> **DONE WHEN:** Pitch பண்ண ready.

---

## DEFINITION OF DONE — MVP

- `run --all` → 10 endpoints, ~60 cases, 2 நிமிஷத்துக்குள்ள முடியும்
- ரெண்டு தடவ run பண்ணா **exactly same output** (deterministic)
- குறைஞ்சது **ஒரு real bug** கண்டுபிடிச்சிருக்கும் — இது தான் முக்கியம்
- CSV-ஐ QA / manager பாத்தா அவங்களுக்கு புரியும்

---

## NON-NEGOTIABLE RULES

1. **Staging மட்டும்.** `require_host_substring` இல்லாம program run ஆகக்கூடாது.
2. **Third-party APIs-ஐ touch பண்ணாதீங்க** — Stripe, Amadeus, YPSILON, webbeds, bank APIs. ToS violation, சில இடங்கள்ல illegal.
3. API console-ல **spend limit** போடுங்க ($20 hard cap). Infinite loop bug-ல இருந்து உங்கள காப்பாத்தும்.
4. Session-ல முடியலன்னா அடுத்த session-க்கு தள்ளுங்க — நேரம் கெடுக்காதீங்க.
5. Security testing phase-க்கு போகும்போது முன்னாடி **written authorization** வாங்குங்க.
6. **YAGNI** — future features (dev agent communication, security checks, Slack/Jira, triage agent) எல்லாம் Session 16-க்கு அப்புறம். இப்போ அதுக்கான abstraction கூட எழுதாதீங்க.

---

## Progress

**10 / 16 முடிஞ்சது** · Phase 1 ✅ Phase 2 ✅ Phase 3 ✅ · அடுத்து Phase 4 — LLM layer

- [x] **01** Project setup + Swagger parser — *2026-09-12* · `7d6b655`
  - venv (Python 3.12.3), folder structure, `requirements.txt`, `.gitignore`
  - `core/swagger.py` — YAML/JSON load, local `$ref` resolve, circular ref guard (`$circular_ref` marker), `MAX_REF_DEPTH=40` cap, `Endpoint` dataclass
  - Path-level + operation-level parameters merge; `application/json` request body எடுக்குது; `default` / `4XX` மாதிரி non-numeric response codes drop ஆகுது
  - `tests/test_swagger.py` — 12 tests pass, `tests/fixtures/mini_spec.yaml`-ல Pet ↔ Category circular ref
  - **DONE WHEN ✅** — `parse_file()` spec-ஐ படிச்சு 3 `Endpoint` objects return பண்ணுது
  - ⚠️ பாக்கி: `allOf` merge இன்னும் இல்ல — session 03-ல real spec மேல பாக்கும்போது சேர்க்கணும்
- [x] **02** API client + Guardrails — *2026-09-12*
  - `config.yaml` — base_url, `require_host_substring`, auth, timeout, allowed_methods, blocked host/path lists. `config.local.yaml` (gitignored) deep-merge ஆகி override பண்ணும்; `${ENV_VAR}` placeholder expand ஆகும்
  - `core/client.py` — `ConfigError`, `GuardrailError`, `Response` dataclass, `ApiClient`
  - Guardrails: staging substring check `__init__`-லயே (socket open ஆகற முன்னாடி), third-party host block, method allowlist, `DELETE` hard-block (config-ஆல கூட enable பண்ண முடியாது), blocked path regex, absolute URL refuse, unfilled `{param}` refuse, redirects follow பண்ணல
  - Response 500 chars-க்கு truncate; timeout / connection error → `status=None` ஓட `Response`, crash இல்ல
  - `tests/test_client.py` — 27 tests. மொத்தம் **39 pass**
  - **DONE WHEN ✅** — production host (`api.acme.com`) கொடுத்தா `GuardrailError`, exit code 2. `require_host_substring` காலியா இருந்தாலும் அதே
  - ⚠️ `base_url` இப்போ `http://localhost:8080` placeholder — session 08-ல real staging value `config.local.yaml`-ல வரணும்
- [x] **03** Parser real-spec validate + `main.py list` — *2026-09-12*
  - Real spec: efly staging (`/efly/v3/api-docs`, OpenAPI **3.1.0**, 72 paths → **104 endpoints**, 136 schemas). `specs/` gitignored
  - Parser real spec-ல **crash ஆகல, fix எதுவும் வேணாம்** — circular marker 0, truncated marker 0, duplicate key 0, missing operationId 0
  - `allOf` / `oneOf` / `anyOf` / `discriminator` / `nullable` — spec-ல **ஒன்னும் இல்ல** (springdoc generate பண்ணது). அதனால session 01-ல விட்ட `allOf` merge **எழுதல** — YAGNI. தேவைப்பட்டா அப்போ சேர்க்கலாம்
  - `main.py` — `list` command, `--spec` / `--method` / `--grep` / `--runnable`, ASCII table (Windows console cp1252-க்காக)
  - GUARDRAIL column — ஒவ்வொரு endpoint-ஐயும் client guardrails அனுமதிக்குமா (`ok` / `method` / `blocked`). 104-ல **32 மட்டும் callable**
  - `config.yaml` — `spec_path` key; `booking` / `/sync` / `/purge` blocked patterns சேர்த்தது (கீழ finding 3 பாக்க)
  - `tests/test_main.py` — 11 tests. மொத்தம் **50 pass**. ரெண்டு தடவ run → byte-identical output
  - **DONE WHEN ✅** — `python main.py list` 104 endpoints-ஐ method, path, documented codes ஓட print பண்ணுது

  **Findings — sessions 06 / 08 / 10-க்கு:**
  1. ⚠️ **எல்லா 104 endpoint-ும் `200` மட்டும் document பண்ணியிருக்கு.** 400/401/404 எதுவும் spec-ல இல்ல. Verdict rule-ல `documented_codes`-ஓட ஒரே வேலை — mismatch ஒன்னை `FAIL`-ல இருந்து `NEEDS_REVIEW`-க்கு இறக்கறது. Documented set `{200}` மட்டும்னா அந்த இறக்கம் ஒருநாளும் நடக்காது, எல்லா mismatch-ும் நேரா `FAIL` ஆகும். "சந்தேகம்னா NEEDS_REVIEW" ங்கற precision rule செயலிழக்கும்
     (expected_status match ஆனா PASS தான் — அதனால சரியான 404-ஐ இது பாதிக்காது. முதல்ல நான் "false FAIL வெள்ளம்" னு எழுதினேன், அது மிகைப்படுத்தல்)
     இது **spec-ஓட குறை**, tool-ஓட குறை இல்ல — session 10-ல finding ஆ report பண்ணலாம்
  2. ⚠️ Spec-ல `servers[0].url` — **bare IP + port + `/efly`, `staging` ங்கற substring இல்ல**. Session 08-ல `require_host_substring` ஆ என்ன வைக்கறதுன்னு முடிவு பண்ணணும். இது open question. (Real host `config.local.yaml`-ல மட்டும் — RULE 5)
  3. ⚠️ **Booking endpoints** (`/booking/book`, `/booking/cancel`, `/package-bookings`) + `/sync` + `/purge` — supplier-க்கு போகலாம் (RULE 2). இப்போ blocked patterns-ல போட்டாச்சு. 12 booking endpoints-ும் block ஆகுது
  4. `resolve_refs` output 96 KB → 241 KB (2.5x). Session 11-ல `request_schema` LLM-க்கு அனுப்பும்போது token cost-ல தெரியும். அப்போ trim பண்ணணும்

  **🔴 Session 03-ல `GET /api/v1/website-slots`-ஐ கையால probe பண்ணப்போ கிடைச்சது — ரெண்டும் real findings:**

  | Input | HTTP | Body-ல | சரியா? |
  |---|---|---|---|
  | `?sortBy=zzz` | **200** | `validation_Code: 40000` | ❌ 400 வரணும் |
  | `?page=-5` | **200** | `validation_Code: 40000` | ❌ 400 வரணும் |
  | `?size=999999` | **200** | `validation_Code: 40000` | ❌ 400 வரணும் |
  | `?page=abc` | **200** | `validation_Code: 40000` | ❌ 400 வரணும் |
  | `/website-slots/99999999` | **500** | `validation_Code: "404"` | ❌ 404 வரணும் |
  | `/api/v1/no-such-thing` | 404 | — | ✅ |

  **A. Validation error-ஐ HTTP 200-ல அனுப்புது.** Error envelope body-க்குள்ள `validation_Code: "40000"` னு இருக்கு. `?page=-5` க்கு HTTP **400** தான் வரணும் — அது HTTP-ஓட விதி, இந்த API-ஓட விருப்பம் இல்ல. 200 வருது = **FAIL**. அவ்ளோதான்

  > **முடிவு: tool-ல எந்த மாற்றமும் இல்ல.** Test case format `expected_status` ஓட generic-ஆவே இருக்கும். `validation_Code` மாதிரி API-specific field **சேர்க்கக்கூடாது** — அது efly-ஓட envelope convention மட்டும்; அடுத்த API-ல `errorCode` ஆ இருக்கும். ஒவ்வொரு API-க்கும் field சேர்த்தா இது test agent இல்ல, efly script
  >
  > API தப்பா இருக்கறதை tool ஏத்துக்கிட்டா, அந்த தப்பு report-ல தெரியவே தெரியாது. Session 06 verdict rule (status-only) அப்படியே இருக்கட்டும் — இந்த FAIL-கள் **உண்மையான findings**, false positive இல்ல

  **B. Not-found resource-க்கு HTTP 500 வருது** (`/website-slots/99999999`). Body-ல `"validation_Code": "404"` னு சரியாவே இருக்கு, ஆனா HTTP status 500. Unhandled exception → generic 500 handler. **இது backend bug**, tool-ஓட குறை இல்ல. PLAN-ஓட "5xx எப்பவுமே FAIL" rule இதை சரியா பிடிக்கும்
  > DEFINITION OF DONE-ல இருக்கற *"குறைஞ்சது ஒரு real bug கண்டுபிடிச்சிருக்கும்"* — LLM வரதுக்கு முன்னாடியே, session 03-லயே கிடைச்சுடுச்சு
- [x] **04** Test case JSON format + கையால 5 cases — *2026-09-12*
  - `core/testcase.py` — `TestCase` dataclass, `TestCaseError`, `parse_document()`, `load_file()`, `load_dir()`, `slug_for()`
  - Format: ஒரு endpoint = ஒரு file. Top-level-ல `endpoint {method, path}` + `cases[]`. Case-ல `name`, `category`, `expected_status`, `reason` (required) + `path_params`, `query`, `body` (optional)
  - `CATEGORIES` = `happy_path`, `boundary`, `invalid_input`, `not_found`, `auth` — சின்ன list-ஆ வெச்சிருக்கு; category report-ல group பண்றதுக்கு, author-ஓட எண்ணத்தை விவரிக்க இல்ல
  - **Unknown key reject ஆகும், ignore ஆகாது.** Session 11-ல LLM ஒரு field கண்டுபிடிச்சா அது சத்தமா fail ஆகணும், அமைதியா drop ஆகக்கூடாது
  - `path_params` vs path-ல இருக்கற `{...}` cross-check — ரெண்டு பக்கமும் (விடுபட்டா, அதிகமா இருந்தா)
  - `expected_status` int 100–599; `True` (Python-ல bool ஒரு int) reject ஆகும்
  - `slug_for()` pure function — session 13-ல rerun பண்ணா overwrite ஆகணும், சேரக்கூடாது
  - `testcases/get_api-v1-website-slots.json` — கையால 5 cases
  - `tests/test_testcase.py` — 34 tests. மொத்தம் **86 pass**
  - **DONE WHEN ✅** — LLM பண்ணக்கூடிய 12 தவறுகளை வெச்சு சோதிச்சேன் (field rename, invented field, status-ஆ string, status-ஆ `40000`, made-up category, empty reason, query-ஆ list, path param தவறு, `cases`-ஆ object, duplicate name, endpoint block இல்ல): **12/12 reject**

  **இந்த 5 cases-ஐ real API மேல ஓட்டினா (session 05/06 preview):**

  | case | want | got | verdict |
  |---|---|---|---|
  | default listing | 200 | 200 | PASS |
  | page size at documented maximum (100) | 200 | 200 | PASS |
  | page size one above maximum (101) | 400 | **200** | **FAIL** |
  | sortBy column that does not exist | 400 | **200** | **FAIL** |
  | order direction that is not asc or desc | 400 | **200** | **FAIL** |

  மூணு FAIL-ும் **சரியான FAIL** — API 4xx கொடுக்கணும், 200 கொடுக்குது

  **Finding C (புதுசு):** `order=sideways` கொடுத்தா API எந்த complaint-ும் பண்ணல, `validation_Code: 200 SUCCESS` னு normal result திருப்பி அனுப்புது. `sortBy`-ஐ validate பண்றாங்க, `order`-ஐ பண்ணவே இல்ல — அமைதியா ignore. இது A-ஐ விட மோசம்: A-ல குறைஞ்சது body-ல error இருக்கு
- [x] **05** Executor — replay loop — *2026-09-18*
  - `core/executor.py` — `CaseResult`, `RunResults`, `run_case()`, `run_cases()`, `format_result()`, `UnhealthyApiError`
  - **மூணு outcome, ரெண்டு இல்ல:** `RAN` (பதில் வந்துச்சு) · `SKIPPED` (guardrail — நாமளே அனுப்பல) · `ERROR` (அனுப்பினோம், பதிலே இல்ல). SKIPPED-ஐயும் ERROR-ஐயும் ஒரே bucket-ல போட்டா "staging down-ஆ இருந்துச்சு" ங்கறது "வேணும்னே block பண்ணோம்" னு படிக்கும்
  - Outcome ≠ verdict. `404` கூட `RAN` தான் — PASS/FAIL session 06-ல. ரெண்டையும் பிரிச்சு வெச்சா verdict rule மாறும்போது request code-ஐ தொடவேண்டாம்
  - Loop எந்த endpoint-க்கும் crash ஆகாது. 60-ல 3-வது case-ல செத்துப்போற run, result மாதிரி தெரியும் ஆனா result இல்ல
  - Health gate — `run_cases(check_health=True)` default. Unhealthy-ன்னா `UnhealthyApiError`, ஒரு case-ும் ஓடாது
  - `core/client.py` — `Response.response_bytes` சேர்த்தது, **truncate பண்றதுக்கு முன்னாடி** அளக்கப்படுது. `len(body)` 2 MB-க்கும் 501 bytes-க்கும் ஒரே answer கொடுக்கும். `raw.content` (bytes) use பண்றோம், `raw.text` (decoded) இல்ல — multi-byte-ல அது குறைச்சா சொல்லும்
  - `tests/test_executor.py` (26) + client tests. மொத்தம் **126 pass**
  - **DONE WHEN ✅** — 5 cases real API மேல ஓடி status print ஆகுது:
    ```
    RAN      200    164ms     960b  default listing
    RAN      200    164ms     956b  page size at documented maximum
    RAN      200    193ms     130b  page size one above maximum
    RAN      200    160ms     202b  sortBy column that does not exist
    RAN      200    166ms     960b  order direction that is not asc or desc
    5 cases: RAN=5  SKIPPED=0  ERROR=0
    ```
  - மூணு outcome-ும் real host மேல நிரூபிச்சது — path block → `SKIPPED=5`, method block → `SKIPPED=5`, செத்த port → `ERROR=5`, செத்த port + health gate → **0 cases run**
  - Latency-ஐ மறைச்சா ரெண்டு run-ும் byte-identical
  - ℹ️ `run` CLI command **இல்ல** — அது session 07. இப்போ executor library மட்டும்
- [x] **06** Verdict logic — *2026-09-18*
  - `core/verdict.py` — `decide()`, `apply()`, `counts()`, `codes_by_endpoint()`. `CaseResult.verdict` field
  - PLAN-ல இருக்கற rule **அப்படியே**, order-ஓட சேர்த்து: 5xx → FAIL · expected match → PASS · documented ஆனா expected இல்ல → NEEDS_REVIEW · மத்தது FAIL
  - 5xx முதல்ல ங்கறது வேணும்னே — case `500` எதிர்பாத்து `500` வந்தாலும் FAIL. Server error ஒருநாளும் சரியான behaviour இல்ல, அதை assert பண்ற case உடைஞ்ச case
  - `SKIPPED` / `ERROR`-க்கு **verdict இல்ல** (`None`). Call பண்ணாத, இல்ல பதில் வராத case-க்கு PASS-ும் இல்ல FAIL-ும் இல்ல. Report-ல யாரும் செயல்படுத்த முடியாத ஒரு எண்ணை போடக்கூடாது
  - `tests/test_verdict.py` — 29 tests. மொத்தம் **155 pass**
  - **DONE WHEN ✅** — 5 cases-க்கும் verdict வருது

  **🔴 Finding E — rule 3 நம்ம எதிர்பார்ப்புக்கு எதிரா வேலை செய்யுது:**

  Real API மேல ஓட்டினா:

  | case | wanted | got | documented codes-ஓட | codes இல்லாம |
  |---|---|---|---|---|
  | default listing | 200 | 200 | PASS | PASS |
  | size at max (100) | 200 | 200 | PASS | PASS |
  | size 101 | 400 | 200 | **NEEDS_REVIEW** | FAIL |
  | sortBy தப்பு | 400 | 200 | **NEEDS_REVIEW** | FAIL |
  | order தப்பு | 400 | 200 | **NEEDS_REVIEW** | FAIL |
  | | | | `PASS=2 FAIL=0 REVIEW=3` | `PASS=2 FAIL=3 REVIEW=0` |

  Spec எல்லா endpoint-க்கும் `200` document பண்ணியிருக்கு. Case `400` எதிர்பாக்குது, API `200` கொடுக்குது — `200` documented, அதனால rule 3 பிடிச்சு **NEEDS_REVIEW** ஆ மாத்திடுது.

  அதாவது **tool எதுக்காக இருக்கோ அந்த finding-ஏ (invalid input reject ஆகல) `FAIL`-ல இருந்து இறக்கப்படுது.** அதே நேரம் `expected 200 → got 404` (பெரும்பாலும் seed data குறை, session 09-ல சரியாகும்) hard `FAIL` ஆகுது. Precision தலைகீழ்

  > ⚠️ Session 03-ல நான் "documented codes `{200}` மட்டும்னா NEEDS_REVIEW ஒருநாளும் வராது" னு எழுதினேன். **அது தப்பு.** நேர்மாறா — மிக முக்கியமான case-ல தான் வருது

  **முடிவு: rule-ஐ இப்போ மாத்தல.** PLAN சொன்னபடியே implement பண்ணியிருக்கு, behaviour test-ல பதிவாகியிருக்கு. Session 10-ல (`documented codes vs actual behaviour` — அது ஏற்கனவே PLAN-ல இருக்கு) real data வெச்சு முடிவு பண்ணலாம். சாத்தியமான திருத்தம்: ஒரு endpoint-ஓட documented set-ல ஒரே ஒரு code தான் இருந்தா அதை signal ஆ எடுக்கக்கூடாது
- [x] **07** CSV reporter + CLI wiring — *2026-09-18*
  - `core/reporter.py` — `write_csv()`, `summary_lines()`, `row_for()`, `format_input()`, `has_failures()`
  - CSV columns: `endpoint, case, category, input, expected, actual, verdict, outcome, ms, bytes, reason, detail, response`
  - **ஒவ்வொரு row-ும் தனியா முழுமையானது.** எந்த input அந்த result-ஐ உண்டாக்கியதோ அது அதே row-ல (`query={"size":101}`) — ஒரு finding-ஐ ஒரு வரியில இருந்து reproduce பண்ணலாம். `reason` column-ல ஏன் அந்த status எதிர்பாக்கப்பட்டது, `response` column-ல API என்ன சொல்லுச்சு
  - `main.py run` — `--all` / `--endpoint` / `--limit` / `--spec` / `--out` / `--testcases` / `--no-health`
  - **Exit codes:** 0 clean · 1 bad input · 2 guardrail · 3 unhealthy · **4 run முடிஞ்சது, FAIL இருக்கு**. CI-க்கு 4 தான் முக்கியம் — tests fail ஆகும்போது 0 கொடுக்கற tool, tool இல்லாததை விட மோசம்
  - Health gate `run` command-ல, `run_cases`-க்கு வெளிய — செத்த host, ஓடப்போகாத run-ஐ அறிவிக்கக்கூடாது
  - Summary-ல FAIL / NEEDS_REVIEW மட்டும் பட்டியலிடுது. Live lines ஏற்கனவே எல்லா case-ஐயும் காட்டியாச்சு; திரும்ப காட்டினா கவனம் தேவைப்படறது புதையும்
  - `tests/test_reporter.py` (22) + CLI run tests (11). மொத்தம் **188 pass**
  - **DONE WHEN ✅** — LLM இல்லாம வேலை செய்யற tool:
    ```
    5 cases against <staging host>

    RAN           200    159ms     960b  default listing
    ...
    5 cases: PASS=2  FAIL=0  NEEDS_REVIEW=3

    NEEDS_REVIEW:
      GET /api/v1/website-slots  page size one above maximum
        expected 400, got 200  (invalid_input)

    report: reports\run.csv
    ```
  - Exit codes எல்லாம் real host மேல நிரூபிச்சது — production config → **2**, செத்த host → **3**, `/website-slots/99999999` (500 bug) → **4**
  - ரெண்டு run-ஓட CSV `ms` column தவிர **byte-identical**. `ms` தான் அளவீடு, அது மாறத்தான் செய்யும்
- [x] **08** Real staging மேல முதல் run ⚑ — *2026-09-18*
  - **Auth: இல்லவே இல்ல.** Spec-ல `securitySchemes` காலி, top-level `security` இல்ல, எந்த operation-க்கும் security இல்ல. 16 GET endpoints-ஐயும் token இல்லாம கூப்பிட்டு பாத்தேன் — எல்லாமே பதில் சொல்லுது. அதனால `auth.type: none` அப்படியே. **Token refresh (session 09) இந்த API-க்கு தேவையே இல்ல**
  - `require_host_substring` = staging host-ஓட IP, `config.local.yaml`-ல (gitignored). `staging` ங்கற வார்த்தையை விட இது **இறுக்கமானது** — வேற எந்த host-க்கும் match ஆகாது. இது தான் இறுதி முடிவு
  - 14 புது test case files scaffold பண்ணது (spec-ல இருந்து, LLM இல்ல) — callable GET endpoints, path param இல்லாதவை. Paging இருக்கறவைக்கு 2 cases (happy + `page=-1`), இல்லாதவைக்கு 1. **மொத்தம் 28 cases, 15 endpoints**
  - `/api/v1/package-bookings` guardrail-ல block ஆகி scaffold ஆகல — சரி
  - **DONE WHEN ✅** — real API, real result: `PASS=14  FAIL=2  NEEDS_REVIEW=12`, exit 4, 5.5 வினாடி
  - ரெண்டு run-ஓட 28 rows-ும் `ms` தவிர **identical**

  **🔧 நம்ம tool-ஓட ஒரு bug — முதல்ல அது:**

  `default_headers: Accept: application/json` னு மட்டும் இருந்துச்சு. `/package-category-landmark/export` **`406 Not Acceptable`** கொடுத்துச்சு — அது `text/csv` திருப்பி அனுப்புது. `Accept: */*` வெச்சா `200`, 53 KB CSV. அதாவது **API சரியா இருந்துச்சு, நம்ம header தான் தப்பு**. இப்படி ஒரு false FAIL report-ல போயிருந்தா, dev நேரத்தை வீணடிச்சிருப்போம். `Accept: application/json, text/plain, */*` ஆ மாத்தியாச்சு

  **🔴 Finding F — 9/9 paging endpoints `page=-1`-ஐ HTTP 200-ல reject பண்ணுது:**

  | endpoint | body-ல |
  |---|---|
  | `/campaigns` · `/categories` · `/custom-offers` · `/custom-offers/display` · `/query-types` | `40000` · *"page must not be negative"* |
  | `/countries` · `/offer-categories` · `/package-offers` | `40000` · *"Page index must not be less than zero"* |
  | `/reviews` | `40000` · *"Page index must not be less than zero"* |

  ஒன்பதுல ஒன்பதும். இது ஒரு endpoint-ல நடந்த தவறு இல்ல, **முழு application-ஓட pattern**. ரெண்டு வெவ்வேற message இருக்கறதால ரெண்டு வெவ்வேற code path — ஒன்னு custom validation, இன்னொன்னு Spring-ஓட சொந்த `PageRequest` exception — ஆனா ரெண்டுமே 200-ல முடியுது. `@ControllerAdvice`-ல எல்லா exception-ஐயும் 200-ஆ சுருட்டி அனுப்பறாங்கன்னு தோணுது

  **🔴 Finding G — GET-க்கு `202 Accepted`:**

  `/api/v1/convert` (4989 b) · `/api/v1/offer-categories/ids` (167 b). ரெண்டும் data-வை **உடனே** திருப்பி அனுப்புது. `202` ங்கறதுக்கு அர்த்தம் *"ஏத்துக்கிட்டேன், பின்னாடி process பண்றேன், result இப்போ இல்ல"*. Client 202 பாத்து polling ஆரம்பிச்சா, ஏற்கனவே கையில இருக்கற data-க்காக காத்திருக்கும். `200` தான் சரி

  இந்த ரெண்டும் **FAIL** ஆ வந்துச்சு — `202` spec-ல documented இல்ல, அதனால rule 3 அதை மென்மையாக்கல. அதே நேரம் finding F முழுக்க NEEDS_REVIEW ஆ போச்சு. Finding E சொன்னதுக்கு இது நேரடி சான்று
- [x] **09** Seed data (auth தேவையில்ல) — *2026-09-18*
  - **Token refresh எழுதல.** Session 08-ல நிரூபிச்சபடி இந்த API-ல auth இல்லவே இல்ல. இல்லாத ஒரு problem-க்கு code எழுதறது YAGNI மீறல்
  - `core/seed.py` — `load_seed()`, `lookup()`, `resolve_path_params()`, `SeedError`
  - Committed test case-ல `"path_params": {"id": "{{seed}}"}` னு placeholder. Real value gitignored `seed_data.yaml`-ல. Staging reseed ஆனா case-ஐ தொடவேண்டாம், private environment-ஓட உண்மை git-ல போகாது
  - வேணும்னே literal value எழுதலாம் — `{"id": 99999999}` ஒரு not_found case-ஓட நோக்கமே அதுதான், seed-ல விடுபட்டது இல்ல
  - Seed value இல்லைன்னா case **`SKIPPED`**, crash இல்ல, போலி id-ம் இல்ல. `/reviews` staging-ல காலி (`totalRecords: 0`) — போலி id அனுப்பி 404 வாங்கி அதை finding ஆ காட்டறது பொய். ரெண்டு cases அப்படி skip ஆகுது, detail-ல காரணத்தோட
  - Third-party skip list ஏற்கனவே `blocked_path_patterns`-ல (session 03) — `/package-bookings/{id}` scaffold-லயே விலகுது
  - 17 புது case files. **மொத்தம் 58 cases, 32 endpoints**
  - **DONE WHEN ✅** — path param உள்ள endpoints ஓடுது, 404 noise இல்ல: `PASS=29 FAIL=13 NEEDS_REVIEW=14`, SKIPPED=2

  **🔧 நம்ம tool-ல ரெண்டு திருத்தம்:**

  1. Summary-ல `SKIPPED=2 (guardrails)` னு எழுதியிருந்தேன் — ஆனா அந்த ரெண்டும் **seed இல்லாததால** skip ஆனவை. Summary காரணத்தை ஊகிக்கக்கூடாது; வாசகரை தப்பான config file-ஐ தேட வைக்கும். இப்போ `(not sent)`, காரணம் detail column-ல
  2. `/custom-offers/{id}`-க்கு `99999999` னு not_found case எழுதியிருந்தேன். அந்த endpoint **UUID** எதிர்பாக்குது — அது இல்லாத record இல்ல, **தப்பான format**. Case-ஐ ரெண்டா பிரிச்சேன்: well-formed UUID → not_found, bare number → invalid_input. **தப்பான test case ஒரு தப்பான finding-ஐ உண்டாக்கும்**

  **🔴 Finding B விரிவாகுது — 11 endpoints, ஒரே bug:**

  இல்லாத record-க்கு **HTTP 500**. Body-ல `validation_Code: "404"` னு சரியாவே இருக்கு:

  `/campaigns/{id}` · `/categories/{id}` · `/countries/{id}` · `/custom-offers/{id}` · `/custom-offers/{id}/display` · `/hotel-review/single/{id}` · `/offer-categories/{id}` · `/package-offers/{id}` · `/query-types/{id}` · `/reviews/{id}` · `/website-slots/{id}`

  Session 03-ல ஒரு endpoint-ல பாத்தது. இப்போ **11-ல 11**. Service layer `EntityNotFoundException` எறியுது, `@ControllerAdvice` அதை catch பண்ணாம generic 500 handler-க்கு போகுது. Finding F-ஓட (page=-1 → 200) அதே இடத்துல இருக்கற பிரச்சனை — exception mapping

  **Status விநியோகம் (58 cases):** `200` × 43 · `500` × 11 · `202` × 2 · அனுப்பப்படாதது × 2. **404 ஒன்னு கூட இல்ல** — 11 தடவ 404 வரவேண்டிய இடத்துல

  **🔴 Finding H — அந்த 11-ல ரெண்டு வெவ்வேற error shape:**

  - **7** endpoints app-ஓட envelope கொடுக்குது: `{"validation_Code":"404","validation_message":"... not found with id: ..."}`
  - **4** endpoints **Spring-ஓட raw default error page** கொடுக்குது: `{"timestamp":"...","status":500,"error":"Internal Server Error","path":"/efly/api/v1/countries/99999999"}` — `/countries/{id}`, `/hotel-review/single/{id}`, `/offer-categories/{id}`, `/package-offers/{id}`

  அதாவது அந்த 4-ல exception `@ControllerAdvice`-ஐ **எட்டவே இல்ல**. Client-க்கு ரெண்டு வெவ்வேற error format வருது — parse பண்றது கஷ்டம். அத்தோட internal path வெளிய போகுது

  **Determinism-ல ஒரு நுணுக்கம்:** அந்த 4 rows-ஓட `response` column ரெண்டு run-ல வேறுபடுது — Spring-ஓட body-ல timestamp இருக்கு. இது **நம்ம tool-ஓட குறை இல்ல**; verdict, status, input எல்லாம் stable. `response` column server-ஐ அப்படியே பிரதிபலிக்குது, timestamp-ஐ நீக்கறது சாட்சியை திருத்தறது. Diff பண்ணும்போது `verdict` / `actual` மேல பண்ணணும், `response` மேல இல்ல — reporter docstring-ல எழுதியாச்சு
- [x] **10** Swagger quirks + POST enable — *2026-09-18*

  **Finding E-க்கு முடிவு: rule B.** `core/verdict.py`-ல `is_informative()` — ஒரு endpoint-க்கு spec **ஒரே ஒரு** status மட்டும் document பண்ணியிருந்தா, அது signal இல்ல. `{200}` ங்கறது *"200 மட்டும் தான் செல்லுபடி"* ங்கற கூற்று இல்ல; author ஒன்னும் எழுதாதப்போ springdoc போடற default. இல்லாத ஒரு கூற்றை ஆதாரமா எடுக்கக்கூடாது
  - 200 + 404 னு ரெண்டு document பண்ணின spec-ல rule 3 **அப்படியே வேலை செய்யும்** — tool generic-ஆவே இருக்கு, இந்த API-க்காக வளைக்கல
  - விளைவு: 14 நிஜமான findings `NEEDS_REVIEW`-ல இருந்து `FAIL`-க்கு. விலை: இந்த spec-ல `NEEDS_REVIEW` இனி வராது

  **POST enable** (உங்க முடிவு — எல்லா POST-ும்)
  - `allowed_methods`-ல POST. PUT / PATCH சேர்க்கல — அவை இருக்கற record-ஐ மாத்தும். DELETE hard-blocked
  - Blocked patterns tighten: `bulk-import`, `/bulk`, `/store/db`. 48 POST-ல **17 block**, 31 callable
  - ⚠️ **Test cases 12 read-shaped endpoints-க்கு மட்டும்** (`/search/*` 11 + `/hotel-review/fetch`). Create-shaped POST-க்கு cases எழுதல — 31-ல **24-ம் `required` fields declare பண்ணவே இல்ல**, அதனால ஒரு probe body காலி record ஆ சேமிக்கப்படலாம், rerun-ல இன்னொன்னு. அது staging-ல எழுதற முடிவு, scaffold முடிவு இல்ல. வேணும்னா சொல்லுங்க
  - POST case-ஓட வடிவம்: schema object எதிர்பாக்கும் இடத்துல **JSON array** அனுப்பறது. தெளிவா malformed, எந்த API-ஆ இருந்தாலும் record உருவாக்காது

  - **DONE WHEN ✅** — **70 cases, 44 endpoints**: `PASS=29 FAIL=39 NEEDS_REVIEW=0`, SKIPPED=2. ரெண்டு run-ஓட `ms` + `response` தவிர **identical**

  **🔴 Finding I — POST-உம் அதே கதை:**

  Object எதிர்பாக்கற இடத்துல array அனுப்பினா, 12-ல **7 endpoints HTTP 200** (`validation_Code: "IllegalIO Exception"`), **5 endpoints HTTP 500** (Spring raw error). Finding F + H-ஓட அதே முரண்பாடு, POST பக்கம்

  அத்தோட இந்த endpoints-ல envelope-ஓட fields **தலைகீழா** இருக்கு — `"validation_Code": "IllegalIO Exception"`, `"validation_status": "40000"`. மத்த இடங்கள்ல `validation_Code` எண், `validation_status` வார்த்தை. Client ஒரே மாதிரி parse பண்ண முடியாது

  **மொத்த படம் (70 cases, 44 endpoints):** `200` × 50 · `500` × 16 · `202` × 2 · அனுப்பப்படாதது × 2. **`400` ஒன்னு கூட இல்ல, `404` ஒன்னு கூட இல்ல** — 39 case-ல அவை வரவேண்டியிருந்தது
- [ ] 04 Test case JSON format
- [ ] 05 Executor
- [ ] 06 Verdict logic
- [ ] 07 CSV reporter + CLI
- [ ] 08 Real staging run ⚑
- [ ] 09 Auth + seed data
- [ ] 10 Swagger quirks + POST
- [ ] 11 Generator
- [ ] 12 Output validation
- [ ] 13 Generate scale
- [ ] 14 Review + prompt tune
- [ ] 15 Cost tracking
- [ ] 16 README + demo
