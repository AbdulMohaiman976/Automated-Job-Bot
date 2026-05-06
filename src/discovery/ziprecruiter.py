import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional

from src.utils.logger import error, log
from src.config import JOB_KEYWORDS, JOB_LOCATION, MAX_AGE_DAYS, USER_AGENT


def build_ziprecruiter_url(keywords: str, location: str, max_age_days: int) -> str:
    params = {
        "search": keywords,
        "location": location,
        "radius": "0",
        "days": str(max_age_days),
        "remote": "true",
        "page": "1",
    }
    query = "&".join(f"{key}={requests.utils.quote(value)}" for key, value in params.items())
    return f"https://www.ziprecruiter.com/candidate/search?{query}"


def parse_posted_age(text: str) -> Optional[str]:
    if not text:
        return None
    value = text.lower().strip()
    if "just posted" in value or "today" in value:
        return None
    return None


def fetch_ziprecruiter_jobs() -> List[Dict]:
    url = build_ziprecruiter_url(JOB_KEYWORDS, JOB_LOCATION, MAX_AGE_DAYS)
    log(f"Fetching ZipRecruiter jobs from {url}")

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    jobs = []

    selectors = ["article.job_result", ".job_result", ".job_card"]
    for selector in selectors:
        for card in soup.select(selector):
            link = card.select_one("a[href*='/r/'], a[href*='/job/']")
            if not link:
                continue
            job_path = link.get("href", "")
            if not job_path:
                continue
            job_url = job_path if job_path.startswith("http") else f"https://www.ziprecruiter.com{job_path}"
            title_tag = card.select_one("h2, .job_title, .just_job_title")
            company_tag = card.select_one("span.company_name, .company, .job_company")
            location_tag = card.select_one("span.location, .location, .job_location")
            snippet_tag = card.select_one("p.job_snippet, .job-snippet, .job_description")
            posted_tag = card.select_one("span.posted, .post_date, .job_age")

            jobs.append(
                {
                    "source": "ZipRecruiter",
                    "job_title": title_tag.get_text(strip=True) if title_tag else "Data Engineering",
                    "company": company_tag.get_text(strip=True) if company_tag else "Unknown",
                    "location": location_tag.get_text(strip=True) if location_tag else JOB_LOCATION,
                    "remote": True,
                    "posted_date": parse_posted_age(posted_tag.get_text(strip=True)) if posted_tag else None,
                    "url": job_url,
                    "description": snippet_tag.get_text(strip=True) if snippet_tag else "",
                    "requirements": None,
                    "salary": None,
                    "id": f"ziprecruiter-{requests.utils.quote(job_url)}",
                    "raw_payload": {
                        "posted_text": posted_tag.get_text(strip=True) if posted_tag else "",
                        "snippet": snippet_tag.get_text(strip=True) if snippet_tag else ""
                    },
                }
            )

    log(f"ZipRecruiter discovered {len(jobs)} jobs")
    return jobs
