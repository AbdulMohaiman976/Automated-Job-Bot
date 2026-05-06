import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional

from src.utils.logger import error, log
from src.config import JOB_KEYWORDS, JOB_LOCATION, MAX_AGE_DAYS, REMOTE_ONLY, USER_AGENT


def build_indeed_url(keywords: str, location: str, max_age_days: int, remote_only: bool) -> str:
    params = {
        "q": keywords,
        "l": location,
        "fromage": str(max_age_days),
        "sort": "date",
        "radius": "0",
        "limit": "50",
    }
    if remote_only:
        params["remotejob"] = "1"
    query = "&".join(f"{key}={requests.utils.quote(value)}" for key, value in params.items())
    return f"https://www.indeed.com/jobs?{query}"


def parse_posted_age(text: str) -> Optional[str]:
    if not text:
        return None
    value = text.lower().strip()
    if "just posted" in value or "today" in value:
        return None
    return None


def fetch_indeed_jobs() -> List[Dict]:
    url = build_indeed_url(JOB_KEYWORDS, JOB_LOCATION, MAX_AGE_DAYS, REMOTE_ONLY)
    log(f"Fetching Indeed jobs from {url}")

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    jobs = []

    selectors = [".job_seen_beacon", ".result", ".tapItem"]
    for selector in selectors:
        for card in soup.select(selector):
            link = card.select_one("a[data-jk], a[title], a[href*='/rc/clk'], a[href*='/company/']")
            if not link:
                continue
            job_path = link.get("href", "")
            if not job_path:
                continue
            job_url = job_path if job_path.startswith("http") else f"https://www.indeed.com{job_path}"
            title_tag = card.select_one("h2.jobTitle span, h2.title span, .jobTitle")
            company_tag = card.select_one("span.companyName, .company, .companyName")
            location_tag = card.select_one("div.companyLocation, .location")
            snippet_tag = card.select_one("div.job-snippet, .summary")
            posted_tag = card.select_one("span.date, .date")

            jobs.append(
                {
                    "source": "Indeed",
                    "job_title": title_tag.get_text(strip=True) if title_tag else "Data Engineering",
                    "company": company_tag.get_text(strip=True) if company_tag else "Unknown",
                    "location": location_tag.get_text(strip=True) if location_tag else JOB_LOCATION,
                    "remote": REMOTE_ONLY or "remote" in (location_tag.get_text(strip=True).lower() if location_tag else ""),
                    "posted_date": parse_posted_age(posted_tag.get_text(strip=True)) if posted_tag else None,
                    "url": job_url,
                    "description": snippet_tag.get_text(strip=True) if snippet_tag else "",
                    "requirements": None,
                    "salary": None,
                    "id": f"indeed-{requests.utils.quote(job_url)}",
                    "raw_payload": {
                        "posted_text": posted_tag.get_text(strip=True) if posted_tag else "",
                        "snippet": snippet_tag.get_text(strip=True) if snippet_tag else ""
                    },
                }
            )

    log(f"Indeed discovered {len(jobs)} jobs")
    return jobs
