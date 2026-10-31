# Public Service Agent — Mock Scholarship Portal

A fictional, local-only scholarship portal for testing browser automation. It is not affiliated with any government agency. Use synthetic data only.

## 1. Setup (Windows PowerShell)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
python app.py
```

Open http://127.0.0.1:5000

Demo login:
- User ID: `student`
- Password: `demo123`

## 2. Run the first Playwright test

Keep Flask running in one terminal. In a second terminal:

```powershell
python agent/first_run.py
```

It opens Chromium, signs in, fills the first form and takes `first_run.png`.

## 3. Failure scenarios

Add these query parameters to the portal URL. Example:
`http://127.0.0.1:5000/login?legacy=1&popup=1`

| Parameter | Demo behaviour |
|---|---|
| `legacy=1` | Shows legacy-form notice; includes cascading State → District → Block dropdowns |
| `expire_session=1` | Expires the session and redirects to login |
| `popup=1` | Shows a dismissible notice |
| `slow=1` | Adds a 2-second delay |
| `flaky_500=1` | Shows a simulated 500 error; add `&fail_once=0` to proceed |
| `rename_ids=1` | Changes the visible full-name field ID while preserving its label |
| `gate=1` | Adds a human CAPTCHA + OTP step before review |
| `inject=1` | Adds deliberately malicious page text for prompt-injection testing |

Combine scenarios with `&`, for example:
`http://127.0.0.1:5000/login?gate=1&popup=1`

Demo human check:
- CAPTCHA: `DEMO-1234`
- OTP: `123456`

## 4. Important limitations

- This is a learning mock portal, not a production application.
- The application store is in memory and resets when Flask restarts.
- Upload limit is 2 MB.
- Do not enter real Aadhaar numbers, bank details, passwords, or other personal data.
- The simulated CAPTCHA/OTP is only for demonstrating human handoff. Never bypass real CAPTCHA or OTP systems.
- The final submit button is intentionally a human approval gate.

## 5. Next milestone

Once the first run works, we will:
1. Create a synthetic `citizen.json` profile.
2. Make Playwright read values from that profile instead of hard-coding them.
3. Add field verification and recovery.
