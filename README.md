# Job Bot

## Overview

This project builds a repeatable daily workflow to discover and prepare remote Data Engineering job applications for a candidate. The first implementation step focuses on data collection from Indeed and ZipRecruiter using the client-defined filters.

## Objective

- Find Data Engineering roles posted in the last 24 hours
- Filter for 100% Remote and USA-based jobs only
- Keep the candidate email consistent with the resume
- Capture all application form fields and generate pre-filled application data
- Store tracking metadata for reporting and human review
- Preserve a human-in-the-loop final submit step

## What this README covers

1. Data sources: Indeed and ZipRecruiter
2. Required filters and normalization
3. Application form data structure and storage
4. Daily workflow and production expectations
5. Next implementation steps

---

## 1. Source data collection

### Primary data sources

- **Indeed**
- **ZipRecruiter**

These sources are prioritized because they are the most stable for programmatic extraction and the best place to start delivering value.

### Target filters

For every search request, the implementation must enforce:

- `role`: Data Engineering
- `location`: United States
- `remote`: 100% Remote
- `posted`: within last 24 hours
- `email`: use the resume email for all applications

Optional filters to add if helpful:

- salary floor
- excluded companies
- exclude staffing/recruiting agencies
- exclude non-data-engineering roles

### Normalized job object

Each job returned from the source should be normalized to the following model:

```json
{
  "source": "Indeed|ZipRecruiter",
  "job_title": "Data Engineer",
  "company": "Example Corp",
  "location": "Remote, United States",
  "remote": true,
  "posted_date": "2026-05-03T18:00:00Z",
  "url": "https://...",
  "description": "Full job description text...",
  "requirements": "Key requirements extracted...",
  "salary": "if available",
  "id": "source-specific-id",
  "raw_payload": {}
}
```

---

## 2. Indeed implementation notes

### Recommended approach

1. Use Indeed search API if available.
2. If no API access, use a stable page search URL with query parameters.
3. Extract job card data and follow job detail links for the full description.

### Core filters for Indeed

- query: `Data Engineering`
- location: `United States` or `Remote`
- remote filter: `100% Remote`
- date filter: last 24 hours

### Key data to capture

- job title
- company name
- location details
- remote status
- job posting date
- job description text
- application URL
- estimated application type (external vs ATS)

### Production guardrails

- Rate-limit requests to avoid IP blocking
- Use headers and browser-like behavior if scraping HTML
- Protect the candidate email by not altering it
- Log skipped jobs and reasons

---

## 3. ZipRecruiter implementation notes

### Recommended approach

1. Use ZipRecruiter public search API or a filtered search page.
2. Apply the same hard filters as Indeed.
3. Normalize the returned jobs into the shared model.

### Core filters for ZipRecruiter

- keywords: `Data Engineering`
- location: `United States` or `Remote`
- remote: `true`
- date posted: within last 24 hours

### Key data to capture

- job title
- company
- URL
- posted date
- remote indicator
- description / requirements
- salary information if present

### Production guardrails

- Use proxies or regional routing if needed for stable scraping
- Avoid aggressive pagination beyond the 24-hour window
- Deduplicate by URL + job title + company
- Save raw response payload for debugging

---

## 4. Application data storage

The system must capture not only job discovery data, but also all fields needed for later application preparation.

### Application form record model

```json
{
  "job_id": "xyz",
  "source": "Indeed",
  "job_title": "Data Engineer",
  "company": "Example Corp",
  "application_url": "https://...",
  "candidate_email": "candidate@example.com",
  "resume_file": "candidate_resume.pdf",
  "cover_letter": "Custom cover letter text...",
  "tailored_resume_summary": "Key resume bullets tailored to job...",
  "form_fields": {
    "first_name": "John",
    "last_name": "Doe",
    "email": "candidate@example.com",
    "phone": "555-1234",
    "linkedin": "https://linkedin.com/in/example",
    "resume": "attached",
    "cover_letter": "attached or pasted"
  },
  "status": "prepared|reviewed|submitted|skipped",
  "skip_reason": "Missing remote filter|Not a good match",
  "review_notes": "Human review needed for cover letter and form field",
  "created_at": "2026-05-04T08:00:00Z",
  "updated_at": "2026-05-04T08:05:00Z"
}
```

### Storage destination options

- Google Sheets / Airtable for reporting and tracking
- CSV / JSON output for processing
- Database (PostgreSQL / SQLite) for production reliability

---

## 5. Daily workflow

### Step 1: Discover jobs

- Run a scheduled task once per day
- Query ZipRecruiter and Indeed with the client filters
- Normalize and deduplicate results
- Save raw job details and metadata

### Step 2: Filter and narrow

- Apply hard criteria
- Confirm remote and USA-based status
- Annotate excluded jobs and skip reasons

### Step 3: Tailor content

- Load candidate resume from `.docx` or `.pdf`
- Use Claude to generate:
  - a tailored resume version or resume summary
  - a custom cover letter
- Ensure no invented experience is added

### Step 4: Pre-fill application data

- Open application page in browser automation or use Claude in Chrome
- Fill application fields with candidate details and tailored text
- Store the pre-filled form data
- Stop before final submit

### Step 5: Human review and submit

- Provide the human reviewer with job details, tailored content, and form preview
- Human checks quality
- Human clicks the final `Submit`

### Step 6: Report output

- Create daily summary of:
  - jobs matched
  - jobs prepared
  - jobs submitted
  - jobs skipped and reasons
- Store results in the tracking system

---

## 6. Production-level requirements

- Respect job board Terms of Service
- Keep all actual submission decisions human-approved
- Use robust retry and error handling
- Log everything at the job-level
- Persist raw payloads for debugging
- Maintain a clear separation between search-only scraping and form submission preparation

### Logging and audit

Every step should log:

- source name
- request / response timestamps
- job match status
- skip reason
- form preparation status
- human review status

### Error handling

- Retry transient network failures
- Back off on rate limits
- Fail gracefully when the source layout changes
- Alert when the capture rate drops or no new jobs are found

---

## 7. Tech choices

### Recommended stack

- `Node.js` with Apify API client for orchestration
- `Apify` actors for production-grade job board scraping
- `Claude` for resume tailoring and cover letters
- `Google Sheets` / `Airtable` / `CSV` for tracking
- `Selenium` / `Playwright` / `Claude in Chrome` for form pre-fill

### Why Apify API?

- Apify actors handle all anti-bot detection and rotating proxies
- Fully managed and maintained by Apify team
- No local blocking issues or 403 errors
- Production-safe with rate limiting and retries built-in
- Simple API calls with normalized output
- Scales easily for multiple sources

---

## 8. Next implementation tasks

1. Build the Indeed data extractor
2. Build the ZipRecruiter data extractor
3. Normalize and deduplicate search results
4. Persist each job and application form record
5. Add a reporting layer for daily summaries

---

## 9. How to run

This repository includes both Node.js and Python starter implementations for the first discovery step.

### Node.js setup (production-ready with Apify API)

```bash
npm install
cp .env.example .env
# edit .env with your Apify token and candidate email
npm run discover
```

### Python setup (Recommended)

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env with your Apify token and candidate email
python src/workflow/discover.py
```

The workflow now uses Apify actors for robust, production-safe job discovery.

### Output

- `data/jobs-YYYYMMDD.json`
- `data/summary-YYYYMMDD.json`

### How the data is fetched

- **Node.js with Apify API**: the workflow now calls Apify actor APIs instead of local scraping.
- **Indeed**: Apify `apify/indeed-scraper` actor is triggered with:
  - `searchTerm`: `Data Engineering`
  - `locationFilter`: `United States`
  - `positionTypes`: `['remote']`
  - Results are normalized and deduplicated.
- **ZipRecruiter**: Apify `apify/ziprecruiter-scraper` actor is triggered with:
  - `search`: `Data Engineering`
  - `location`: `United States`
  - `remote`: `true`
  - `days`: `1`
  - Results are normalized and deduplicated.

This is production-ready because:
- Apify handles all anti-bot detection
- Proxies and rate limiting are managed automatically
- No local 403 blocking issues
- Normalized output for consistent processing

This is live scraping of the job board search pages, not mocked data.

---

## 10. Summary

This implementation plan starts with production-quality job discovery from Indeed and ZipRecruiter. It uses the exact client filters, stores application preparation data, and preserves the human final-submit requirement. The next step is to build the code modules that query each source, normalize results, and save the pre-filled application form data for human review.
