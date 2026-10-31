# Harness: citizen.json Profile Creation

## Purpose
This file documents how to create and maintain the `data/citizen.json` synthetic profile used by `agent/first_run.py`. If the profile is lost or needs regeneration, follow the steps below.

## Profile Structure

The profile is a JSON object with two top-level keys:

### `personal`
Personal details filled into the first application form step.

| Field | Type | Example |
|---|---|---|
| `full_name` | string | `"Aarav Sharma"` |
| `dob` | string (YYYY-MM-DD) | `"2005-04-05"` |
| `category` | string | `"General"` |
| `course` | string | `"B.Tech"` |
| `state` | string | `"Maharashtra"` |
| `district` | string | `"Pune"` |
| `block` | string | `"Haveli"` |

### `education`
Education details filled into the second application form step.

| Field | Type | Example |
|---|---|---|
| `college` | string | `"Demo Institute of Technology"` |
| `course_year` | string | `"Third Year"` |
| `marks` | string (percentage) | `"82.5"` |
| `annual_income` | string (₹) | `"450000"` |
| `marksheet_path` | string (relative to repo root) | `"data/demo_marksheet.pdf"` |

## Creation Steps

1. **Ensure the marksheet file exists** at `data/demo_marksheet.pdf` (or update `marksheet_path` to point to a valid file).

2. **Create `data/citizen.json`** with the structure above, using synthetic (fake) data only. Never use real personal information.

3. **Verify the profile is loadable** by running:
   ```bash
   python -c "from agent.first_run import load_profile; print(load_profile())"
   ```

## Usage

`agent/first_run.py` reads this profile and automates the browser to fill the scholarship application form. The profile values are used in order:

1. Personal information (step 1) → full_name, dob, category, course, state, district, block
2. Education information (step 2) → college, course_year, marks, annual_income
3. Marksheet upload → uses `marksheet_path` to locate the file

## Regeneration Note

If you need to rebuild the profile from scratch, follow the order:
1. Place a valid marksheet PDF at `data/demo_marksheet.pdf` (or update the path)
2. Fill in `data/citizen.json` with appropriate synthetic data
3. Run `python agent/first_run.py` to verify the automation works end-to-end