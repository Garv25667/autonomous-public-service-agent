"# Harness: Synthetic Profile & Execution Contracts

## Purpose
This file documents the test harness, data schemas, and runtime contracts used by the agent automation pipeline. It serves as the reproducible ground truth for testing against the mock scholarship portal without using real citizen data (zero-PII compliance).

---

## 1. Profile Structure (`data/citizen.json`)

The profile is a JSON object with two top-level sections:

### `personal`
Personal details filled into Step 1 of the application wizard.

| Field | Type | Example | Notes |
|---|---|---|---|
| `full_name` | string | `"Aarav Sharma"` | Required by portal |
| `dob` | string (YYYY-MM-DD) | `"2005-04-05"` | Required by portal |
| `category` | string | `"General"` | Selected in dropdown |
| `course` | string | `"B.Tech"` | Selected in dropdown |
| `state` | string | `"Maharashtra"` | Cascading dropdown trigger |
| `district` | string | `"Pune"` | Populated after state selection |
| `block` | string | `"Haveli"` | Populated after district selection |

### `education`
Academic details filled into Step 2 of the application wizard.

| Field | Type | Example | Notes |
|---|---|---|---|
| `college` | string | `"Demo Institute of Technology"` | Free text institution name |
| `course_year` | string | `"Third Year"` | Selected in dropdown |
| `marks` | string (percentage) | `"82.5"` | Previous exam percentage |
| `annual_income` | string (₹) | `"450000"` | Annual family income in INR |
| `marksheet_path` | string | `"data/demo_marksheet.pdf"` | Relative path to uploaded file (< 2 MB) |

---

## 2. Receipt Structure (`data/receipt.json`)

Upon successful submission through the human approval gate, the receipt details are extracted from the DOM and serialized:

| Field | Type | Example | Source |
|---|---|---|---|
| `receipt_id` | string | `"SCH-EF30697C"` | Extracted from `#receipt-id` DOM element |
| `confirmation` | string | `"Application received"` | Heading text on `/receipt/<id>` page |
| `receipt_url` | string | `"http://127.0.0.1:5000/receipt/SCH-EF30697C"` | Full URL of the confirmed receipt |
| `full_name` | string | `"Aarav Sharma"` | Verified applicant name |
| `course` | string | `"B.Tech"` | Verified course |
| `college` | string | `"Demo Institute of Technology"` | Verified college |

---

## 3. Automation Contracts & Handlers

### Human Approval & JS Confirm Dialog
On the final `/review` step, submitting triggers a native JavaScript `confirm()` dialog (`onclick="return confirm('Submit this demo application?')"`).
- Playwright by default automatically dismisses (cancels) unhandled dialogs, which cancels form submission.
- The automation registers a dialog listener before clicking the submit button:
  ```python
  page.once("dialog", lambda dialog: dialog.accept())
  ```
- The approval gate explicitly prompts the user via CLI before dispatching the final click.

### Artifacts Captured
- `education_verified.png`: Snapshot of Step 2 after filling and uploading the marksheet.
- `review_page.png`: Snapshot of the review summary table prior to human approval.
- `submission_receipt.png`: Snapshot of the generated receipt with reference ID.
- `data/receipt.json`: Serialized output of the submission receipt.

---

## 4. Verification & Health Checks

### PowerShell Profile Load Test
To verify `data/citizen.json` can be loaded cleanly by Python (use single quotes in PowerShell to prevent parser errors):
```powershell
python -c 'from agent.first_run import load_profile; print(load_profile())'
```

### End-to-End Test Run
1. Start the portal:
   ```powershell
   python app.py
   ```
2. In a separate terminal, execute the baseline automation:
   ```powershell
   python agent/first_run.py
   ```
3. Enter `yes` when prompted for final submission approval.
4. Verify that `data/receipt.json` and `submission_receipt.png` are created.

---

## 5. Regeneration Steps

If recreating the environment from scratch:
1. Ensure a valid sample PDF exists at `data/demo_marksheet.pdf` (size under 2 MB).
2. Create `data/citizen.json` using only synthetic test data (never real citizen data).
3. Validate loading via the PowerShell test above.
4. Run `python agent/first_run.py` to confirm the entire flow succeeds.

---

## 6. Step 3: LLM Client & Semantic Perception Harness

### Architecture & Components
- **`agent/llm/client.py`**: Unified `LLMClient` backed by Google GenAI (`google-genai`). Provides structured JSON generation via `LLMClient.generate_json(schema, prompt)` with automatic exponential backoff on 429 rate limits.
- **`agent/llm/cache.py`**: Disk cache keyed on `sha256(model + prompt)` in `.cache/llm/`. Eliminates duplicate API calls, saving free-tier quota and keeping CI runs deterministic and zero-cost.
- **`agent/llm/schemas.py`**: Pydantic v2 schemas (`DropdownMatch`, `CitizenProfile`, `PersonalInfo`, `EducationInfo`).
- **`agent/perception.py`**: 4-tier fallback semantic matcher:
  1. **Tier 1 (Exact)**: Case-insensitive string match (Confidence: `1.0`)
  2. **Tier 2 (Synonym)**: Domain dictionary mapping (`"B.Tech"` $\rightarrow$ `"Bachelor of Technology"`, `"GEN"` $\rightarrow$ `"General"`) (Confidence: `0.95`)
  3. **Tier 3 (Fuzzy)**: `rapidfuzz.fuzz.token_sort_ratio` $\ge 80$ (Confidence: `0.80 - 0.94`)
  4. **Tier 4 (LLM Fallback)**: Gemini Flash-Lite structured JSON output adhering to `DropdownMatch`. Rejects choices with confidence $< 0.75$.

### Quota Guardrail
- Hard cap on maximum LLM calls per run (`max_calls_per_run`, default 10).
- Automatically raises `QuotaExceededError` instead of exhausting the daily Gemini quota.

### Unit Tests
Execute the Step 3 test suite:
```powershell
python -m unittest tests/unit/test_llm_and_perception.py
```
Validates profile schema parsing, cache roundtrip, quota call cap enforcement, and all 4 matching tiers.

---

## 7. Step 4: State Machine, Checkpointing & Safety Guards Harness

### Components & Responsibilities
- **`agent/states.py`**:
  - `RunState`: Core state model tracking status (`running`, `needs_human`, `failed`, `done`), plan step index, action budget, seen page hashes, and audit events.
  - `PlanStep`: Typed discrete workflow steps (`step_id`, `name`, `intent`, `status`, `retries`).
  - `AuditEvent`: Append-only audit record logging every browser action with timestamp, selector, redacted summary, status, and screenshot reference.
- **`agent/guards.py` (`RuntimeGuards`)**:
  - **Loop Detection**: Flags `LoopDetectedError` if identical page hash is encountered 3 times consecutively.
  - **Step Retry Guard**: Limits any single step to max 3 attempts before escalating.
  - **Action Budget**: Hard cap (default 80 browser actions) to prevent runaway execution.
  - **Idempotency Guard**: Rejects duplicate submission attempts if `submitted=True` or `receipt_id` exists.
  - **Wall-Clock Timeout**: Fails if total duration exceeds safety threshold (default 300s).
- **`agent/checkpoint.py` (`Checkpointer`)**:
  - Automatically persists `RunState` into a local SQLite database (`data/agent_runs.sqlite`).
  - Guarantees clean crash recovery and human-in-the-loop pause/resume for CAPTCHAs and approvals.

### Unit Tests
Execute the complete test suite:
```powershell
python -m unittest discover tests
```
Runs all 13 unit tests across Step 3 and Step 4 with 100% pass rate.


---

## 8. Step 5A: Deterministic Page Verifier (`agent/verifier.py`)

### Architecture & Capabilities
The Verifier acts as the agent's diagnostic sensor, executing deterministic page-level checks after every browser interaction:
- **`VerificationResult`**: Typed Pydantic diagnosis returned after inspecting DOM/URL states.
  - `success`: Boolean indicating if expected transition succeeded.
  - `issue_type`: Diagnostic classification:
    - `"none"`: Page transition valid.
    - `"server_error_500"`: Detected portal 500 error (`?flaky_500=1`).
    - `"human_gate"`: Detected CAPTCHA/OTP challenge (`/human-check`, `?gate=1`).
    - `"session_expired"`: Detected unexpected redirect to `/login` (`?expire_session=1`).
    - `"popup_or_modal"`: Detected dismissible notice blocking UI (`?popup=1`).
    - `"validation_error"`: Detected form alert banner (`.alert.error`).
    - `"url_mismatch"`: Current URL does not match step pattern.
    - `"missing_heading"`: Expected `h1` heading not displayed.
    - `"field_mismatch"`: Form input read-back value differs from typed input.

### Unit Tests
Execute the verification suite:
```powershell
python -m unittest tests/unit/test_verifier.py
```
Validates classification of all portal failure toggles and success states.

---

## 9. Step 5B: Self-Healing Recovery Handler (`agent/recovery.py`)

### Architecture & Strategies
The Recovery Handler consumes `VerificationResult` instances and applies targeted self-healing strategies:
- **`dismiss_popup`**: Clicks `[data-dismiss]` elements to clear overlay notices (`?popup=1`).
- **`relogin_and_resume`**: Re-authenticates on `/login` and navigates back to the checkpointed step (`?expire_session=1`).
- **`backoff_and_retry`**: Applies exponential backoff and passes `fail_once=0` on 500 server errors (`?flaky_500=1`).
- **`pause_for_human`**: Switches `RunState.status` to `needs_human` and saves a checkpoint when encountering CAPTCHAs or OTPs (`?gate=1`).
- **`fix_field_and_retry`**: Flags validation errors for field correction.
- **`reload_and_retry`**: Reloads the page on URL or heading mismatches.
- **`escalate_failure`**: Triggers graceful failure when step retries exceed the limit (default 3).

### Unit Tests
Execute the complete test suite:
```powershell
python -m unittest discover tests
```
Runs all 31 unit tests across all project milestones (100% pass rate).

---

## 10. Step 6: Secret Substitution Layer & PII Log-Scan Harness (`agent/tools/secrets.py`)

### Architecture & Zero-PII Compliance (Feature F1)
The Secret Substitution Layer ensures no real citizen personal data (name, DOB, ID, income, address) is ever exposed in outbound LLM prompts or API logs:
- **`SecretVault`**:
  - Automatically identifies sensitive fields vs. non-sensitive fields from citizen profiles.
  - Generates deterministic placeholder tokens (e.g. `{{full_name}}`, `{{dob}}`, `{{annual_income}}`).
  - **`mask_profile()`**: Produces sanitized profile copies where sensitive fields are replaced by tokens before being passed to LLM planners or mappers.
  - **`substitute()`**: Restores real values strictly locally in the browser executor immediately before typing into the form.
  - **`scan_for_leaks()` / `assert_no_leaks()`**: Scans outbound LLM prompts and log entries, raising `PIILeakDetectedError` if any raw sensitive value appears.

### Unit Tests & Log-Scan Verification
Execute the Step 6 PII protection suite:
```powershell
python -m unittest tests/unit/test_secrets_and_pii.py
```
Validates placeholder registration, two-way redaction/substitution, profile masking, leak detection, and proves **0 PII leaks** across all outbound prompts.

---

## 11. Step 7: Receipt Extraction & Final Approval Gate (`agent/receipt.py`, `agent/approval.py`)

### Architecture & Rules (Feature F6)
- **`ReceiptExtractor`**:
  - Deterministic regex extraction from DOM (`\b(SCH-[A-F0-9]{8})\b`).
  - **Zero LLM Rule**: The LLM is strictly prohibited from writing or guessing the receipt reference ID.
  - Rejects malformed or fabricated receipts (`InvalidReceiptError`).
  - Serializes verified receipt records to `data/receipt.json`.
- **`ApprovalGate` & `ReviewSummaryTable`**:
  - Pre-submission summary: Renders an aligned table displaying every field, value submitted, source, and confidence score.
  - **Bypass Prevention**: Without explicit user approval (`explicit_approval=True`), the gate halts with `awaiting_approval` and transitions state to `needs_human`.
  - **Dry-Run Mode**: When `dry_run=True`, the gate stops before the final submission click and reports `dry_run_halted`.

### Unit Tests
Execute the Step 7 test suite:
```powershell
python -m unittest tests/unit/test_receipt_and_approval.py
```
Validates receipt regex enforcement, DOM extraction without LLM, JSON serialization, review table generation, dry-run mode, and proves the approval gate cannot be bypassed.
