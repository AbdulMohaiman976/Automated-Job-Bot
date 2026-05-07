import os
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit, urlunsplit

# Add the project root to sys.path so we can import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src import config
from src.discovery.linkedin_api import fetch_linkedin_jobs_via_apify_api
from src.discovery.indeed_api import fetch_indeed_jobs_via_apify_api
from src.storage.tracker import save_jobs, save_summary
from src.utils.logger import error, log


def canonical_job_url(url):
    if not url:
        return ""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def deduplicate_jobs(jobs):
    seen = set()
    deduped = []
    for job in jobs:
        url = canonical_job_url(job.get("url", ""))
        key = url or f"{job.get('source', '').lower().strip()}::{job.get('job_title', '').lower().strip()}::{job.get('company', '').lower().strip()}"

        if key in seen:
            continue

        seen.add(key)
        deduped.append(job)
    return deduped


def run_discovery():
    try:
        log("=== Starting daily discovery workflow (Multi-Source-Python) ===")
        if not config.APIFY_TOKEN:
            error("APIFY_TOKEN environment variable is not set. Please set it in .env file.")
            raise RuntimeError("APIFY_TOKEN environment variable is not set")

        log(f"Search: '{config.JOB_KEYWORDS}' | Location: '{config.JOB_LOCATION}'")

        source_jobs = {
            "LinkedIn": [],
            "Indeed": [],
        }
        errors = []

        fetchers = {
            "LinkedIn": fetch_linkedin_jobs_via_apify_api,
            "Indeed": fetch_indeed_jobs_via_apify_api,
        }

        with ThreadPoolExecutor(max_workers=len(fetchers)) as executor:
            future_map = {executor.submit(fetcher): source for source, fetcher in fetchers.items()}
            for future in as_completed(future_map):
                source = future_map[future]
                try:
                    jobs = future.result() or []
                    source_jobs[source] = jobs
                    
                    # Live Update: Save jobs from this source immediately so they show up in UI
                    if jobs:
                        try:
                            log(f"Live Update: Saving {len(jobs)} jobs from {source}...")
                            save_jobs(jobs, suffix="all")
                            
                            # Also save to unique so the dashboard 'Apply' tab shows them immediately
                            deduped_partial = deduplicate_jobs(jobs)
                            save_jobs(deduped_partial, suffix="unique")
                        except Exception as e:
                            log(f"Live Update Warning: {e}")
                except Exception as exc:
                    message = f"{source} discovery failed: {exc}"
                    errors.append(message)
                    error(message)

        all_jobs = source_jobs["LinkedIn"] + source_jobs["Indeed"]
        deduped_jobs = deduplicate_jobs(all_jobs)

        summary = {
            "date": datetime.utcnow().isoformat(),
            "total_discovered": len(all_jobs),
            "total_deduplicated": len(deduped_jobs),
            "by_source": {
                "LinkedIn": len(source_jobs["LinkedIn"]),
                "Indeed": len(source_jobs["Indeed"]),
            },
            "errors": errors,
        }

        # Save both lists for the frontend to toggle
        save_jobs(all_jobs, suffix="all")
        save_jobs(deduped_jobs, suffix="unique")
        save_summary(summary)

        log("=== Daily discovery workflow complete ===")
        log(
            "LinkedIn: {linkedin}, Indeed: {indeed}".format(
                linkedin=len(source_jobs["LinkedIn"]),
                indeed=len(source_jobs["Indeed"]),
            )
        )
        log(f"Total Unique Jobs: {len(deduped_jobs)}")
        if errors:
            log(f"Discovery finished with warnings: {errors}")

    except Exception as exc:
        error(f"Daily discovery workflow failed: {exc}")
        raise


if __name__ == "__main__":
    try:
        run_discovery()
    except Exception:
        sys.exit(1)
