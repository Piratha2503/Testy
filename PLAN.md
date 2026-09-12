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

**2 / 16 முடிஞ்சது** · Phase 1 — Foundation

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
- [ ] 03 Parser real-spec validate — ⏳ அடுத்தது
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
