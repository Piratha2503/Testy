# CLAUDE.md

இந்த file-ஐ படிச்சிட்டு தான் வேலை ஆரம்பிக்கணும். Full roadmap [PLAN.md](PLAN.md)-ல இருக்கு.

## Project

**API Test Agent** — Swagger-driven automated API testing tool. ஒரு OpenAPI 3 spec-ஐ படிச்சு, endpoints-க்கு test cases generate பண்ணி (LLM), அவற்றை staging API மேல run பண்ணி, PASS/FAIL/NEEDS_REVIEW verdict-ஓட CSV report கொடுக்கும்.

- **CLI only.** Web UI, API server, daemon எதுவும் இல்ல.
- Personal / internal use tool. Production service இல்ல.
- 16-session fixed plan, 40 hrs budget, hard limit 4 weeks.

## Stack

Python 3.12 · `requests` · `PyYAML` · `anthropic` SDK · `pytest` · `csv` (stdlib)

**NOT IN MVP — இதுல எதையும் சேர்க்கக்கூடாது:** FastAPI, database, Docker, LangChain, n8n, frontend, async/await.

## Commands

venv-ஐ activate பண்ணாம, நேரடியா interpreter path-ஐ use பண்ணுங்க:

```bash
.venv/Scripts/python.exe -m pytest -v          # tests
.venv/Scripts/python.exe -m pytest -q          # tests, சுருக்கமா
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

```bash
.venv/Scripts/python.exe main.py list --spec specs/efly.json
.venv/Scripts/python.exe main.py list --method GET --runnable   # guardrails அனுமதிக்கறது மட்டும்
.venv/Scripts/python.exe main.py list --grep booking
.venv/Scripts/python.exe main.py health                 # API உயிரோட இருக்கா? exit 0=ஆம் 3=இல்ல
```

`run` (S07) / `generate` (S13) வரும்போது இங்க சேர்க்கணும்.

## Layout

```
core/swagger.py     OpenAPI 3 parser — $ref resolve, circular guard, Endpoint dataclass
core/client.py      HTTP client + guardrails - config load, staging check, method allowlist
core/testcase.py    test case file format - TestCase dataclass, strict validation
core/executor.py    (S05) testcase replay loop
core/reporter.py    (S07) CSV output
core/generator.py   (S11) anthropic SDK — test case generation
main.py             CLI entry point - `list`, `health` (S07-ல `run`, S13-ல `generate`)
testcases/          test case JSON files (S04 கையால, S13 generated)
reports/            CSV output — git-ல போகாது
tests/              pytest + fixtures/mini_spec.yaml (dummy petstore spec)
specs/              downloaded OpenAPI specs - gitignored
config.yaml         base_url, require_host_substring, auth, timeout, allowed_methods
config.local.yaml   real secrets — gitignored
seed_data.yaml      (S09) real path param values — gitignored
```

## NON-NEGOTIABLE RULES

இவை suggestions இல்ல. மீறக்கூடாது.

1. **Staging மட்டும்.** `require_host_substring` check இல்லாம program run ஆகவே கூடாது. Production host கொடுத்தா `GuardrailError`-ஓட exit ஆகணும்.
2. **Third-party APIs-ஐ touch பண்ணக்கூடாது** — Stripe, Amadeus, YPSILON, webbeds, bank APIs. ToS violation, சில இடங்கள்ல illegal.
3. Anthropic API console-ல **$20 hard cap** வெச்சிருக்கணும். `generate` commands எப்பவும் `--limit` default-ஓட வரணும் — accidental full run தடுக்க.
4. Security testing phase-க்கு போகும் முன்னாடி **written authorization** வாங்கணும்.
5. Real credentials, tokens, staging URLs — எதுவும் git-ல போகக்கூடாது. `config.local.yaml`, `seed_data.yaml`, `.env` எல்லாம் gitignored.

## Working conventions

- **YAGNI கண்டிப்பா.** Future features (dev agent communication, security checks, Slack/Jira, triage agent) session 16-க்கு அப்புறம். இப்போ அதுக்கான abstraction கூட எழுதக்கூடாது.
- **ஒரு session = ஒரு commit.** Commit message format: `Session NN: <என்ன பண்ணோம்>`.
- Session முடிஞ்சதும் [PLAN.md](PLAN.md)-ல Progress checkbox-ஐ tick பண்ணணும்.
- Session-ல முடியலைன்னா அடுத்த session-க்கு தள்ளணும். நேரம் கெடுக்கக்கூடாது.
- ஒவ்வொரு session-ஓட "DONE WHEN" criteria PLAN.md-ல இருக்கு. அதை நிரூபிச்சு காட்டணும் — "ஆகிடுச்சு" னு சொன்னா போதாது.
- **Determinism முக்கியம்.** ரெண்டு தடவ run பண்ணா exactly same output வரணும். LLM calls `temperature=0`.
- Verdict logic-ல precision > recall. சந்தேகம்னா `NEEDS_REVIEW`, `FAIL` இல்ல.
- **Tool generic-ஆ இருக்கணும்.** ஒரு API-ஓட quirk-க்கு ஏற்ப test format-ஐயோ verdict logic-ஐயோ வளைக்கக்கூடாது. API-specific field (உதா: `validation_Code`, `errorCode`) சேர்க்குறது = அந்த API-க்கான script ஆகிடும். HTTP-ஓட விதியை வைச்சு assert பண்ணணும் — API மீறினா அது finding, tool-ஓட குறை இல்ல.

## Git

- Remote: `https://github.com/Piratha2503/Testy` (private)
- Branch: `main`
- இந்த repo-க்கு மட்டும் local identity: `Piratha2503 <pirathaban1992@gmail.com>` (global config touch பண்ணல)
- **Push பண்ண முன்னாடி கேட்கணும்.**

## Current status

**Phase 1 ✅ முடிஞ்சது** — 01 parser · 02 client + guardrails · 03 real spec + `main.py list` · 04 test case format. **105 tests passing.**
**அடுத்தது: Session 05** — `core/executor.py`, replay loop.

**Real spec:** efly staging, OpenAPI 3.1, 104 endpoints. `specs/efly.json` (gitignored, `/efly/v3/api-docs`-ல இருந்து download). Guardrails 104-ல 32-ஐ மட்டும் allow பண்ணுது.

**Health check:** `config.local.yaml`-ல `health_check.path` = `/api/v1/website-slots` (size=1). 400-க்கு மேல எது வந்தாலும் unhealthy. Session 05-ல executor இதை run-க்கு முன்னாடி கூப்பிடணும்.

⚠️ **தீர்க்கப்படாத ரெண்டு விஷயம்:**
1. Spec-ல எல்லா endpoint-ும் `200` மட்டும் document பண்ணியிருக்கு — அதனால `documented_codes` verdict-ல எந்த signal-ும் கொடுக்காது, `NEEDS_REVIEW` எந்த case-லும் வராது.
2. Staging host bare IP + port — bare IP, `staging` substring இல்ல. `require_host_substring` ஆ என்ன வைக்கறது? Session 08-ல முடிவு பண்ணணும். இப்போ `config.yaml`-ல `localhost` placeholder.
