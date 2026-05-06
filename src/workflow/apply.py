import asyncio
import json
import os
from playwright.async_api import async_playwright
from src.config import USER_AGENT
from src.storage.tracker import log_application, save_tailored_application, JobStatus

# Global events for human-in-the-loop review
review_event = asyncio.Event()
skip_event = asyncio.Event()

class SequentialApplier:
    def __init__(self, cv_data, tailor_func, cover_letter_func):
        self.cv_data = cv_data
        self.tailor_func = tailor_func
        self.cover_letter_func = cover_letter_func
        self.browser = None
        self.context = None
        self.page = None

    async def init_browser(self):
        if not self.browser:
            p = await async_playwright().start()
            self.browser = await p.chromium.launch(headless=False)
            self.context = await self.browser.new_context(user_agent=USER_AGENT)
            self.page = await self.context.new_page()

    async def fill_form(self, tailored_cv, cover_letter):
        try:
            page = self.page
            
            # 1. Identity
            ident_fields = {
                "full_name": ["name", "full_name", "display_name", "full-name"],
                "first_name": ["first_name", "firstname", "given-name"],
                "last_name": ["last_name", "lastname", "family-name"],
                "email": ["email", "e-mail", "email_address"],
                "phone": ["phone", "tel", "mobile", "telephone", "contact_number"]
            }
            
            for key, selectors in ident_fields.items():
                val = tailored_cv.get(key, "")
                if not val and "name" in key:
                     val = tailored_cv.get("full_name", "")
                
                if val:
                    for s in selectors:
                        selector = f"input[name*='{s}' i], input[id*='{s}' i], input[placeholder*='{s}' i]"
                        if await page.query_selector(selector):
                            await page.fill(selector, str(val))
                            break

            # 2. Links
            links = tailored_cv.get('links', [])
            if isinstance(links, list):
                for link in links:
                    l_lower = link.lower()
                    selector = ""
                    if 'linkedin' in l_lower:
                        selector = "input[name*='linkedin' i], input[id*='linkedin' i]"
                    elif 'github' in l_lower:
                        selector = "input[name*='github' i], input[id*='github' i]"
                    elif 'portfolio' in l_lower or 'website' in l_lower:
                        selector = "input[name*='portfolio' i], input[id*='website' i], input[name*='personal' i]"
                    
                    if selector and await page.query_selector(selector):
                        await page.fill(selector, link)

            # 3. Summary / Cover Letter
            summary = tailored_cv.get('summary', '')
            if summary:
                s_selector = "textarea[name*='summary' i], textarea[id*='summary' i], textarea[placeholder*='summary' i]"
                if await page.query_selector(s_selector):
                    await page.fill(s_selector, summary)

            # Actual Cover Letter field
            cl_selector = "textarea[name*='cover' i], textarea[id*='cover' i], textarea[name*='letter' i]"
            if await page.query_selector(cl_selector):
                await page.fill(cl_selector, cover_letter)

            return True
        except Exception as e:
            print(f"Error during auto-fill: {e}")
            return False

    async def apply_to_job(self, job):
        job_id = str(job.get('id') or job.get('job_id'))
        job_title = job.get('job_title', 'Unknown Title')
        company = job.get('company', 'Unknown Company')
        job_url = job.get('url') or job.get('job_url')
        
        if not job_url:
            log_application(job_id, job_title, company, JobStatus.FAILED, "Missing application URL")
            return False

        try:
            # 1. Tailor
            print(f"Tailoring application for {job_title} at {company}...")
            job_desc = job.get('description', '')
            tailored_cv = self.tailor_func(self.cv_data, job_desc)
            cover_letter = self.cover_letter_func(self.cv_data, job_desc)
            
            save_tailored_application(job_id, {
                "cv": tailored_cv,
                "cover_letter": cover_letter
            })
            log_application(job_id, job_title, company, JobStatus.TAILORED)

            # 2. Navigate
            await self.init_browser()
            await self.page.goto(job_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)

            # 3. Auto-fill
            print(f"Auto-filling form...")
            await self.fill_form(tailored_cv, cover_letter)
            log_application(job_id, job_title, company, JobStatus.READY)

            # 4. Wait for human
            print(f"--- [Job {job_id}] REVIEW REQUIRED ---")
            print(f"Role: {job_title}")
            print(f"Company: {company}")
            print(f"Action: Please review the auto-filled form in the browser.")
            print(f"Awaiting signal: 'Submit Done' or 'Skip' from dashboard...")
            
            review_event.clear()
            skip_event.clear()
            
            # Wait for either event
            done_task = asyncio.create_task(review_event.wait())
            skip_task = asyncio.create_task(skip_event.wait())
            
            done, pending = await asyncio.wait(
                [done_task, skip_task], 
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel the pending task
            for task in pending:
                task.cancel()
            
            if skip_task in done:
                print(f"User skipped job: {job_title}")
                log_application(job_id, job_title, company, JobStatus.FAILED, "User skipped during review")
                return False
            
            log_application(job_id, job_title, company, JobStatus.SUBMITTED)
            print(f"Application for {job_title} marked as SUBMITTED.")
            return True

        except Exception as e:
            print(f"Failed to apply to {job_title}: {e}")
            log_application(job_id, job_title, company, JobStatus.FAILED, str(e))
            return False

    async def close(self):
        if self.browser:
            await self.browser.close()

async def bulk_apply(jobs, cv_data, tailor_func, cover_letter_func):
    applier = SequentialApplier(cv_data, tailor_func, cover_letter_func)
    try:
        for job in jobs:
            await applier.apply_to_job(job)
    finally:
        await applier.close()

def signal_review_complete():
    review_event.set()

def signal_skip():
    skip_event.set()
