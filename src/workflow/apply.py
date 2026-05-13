import json
import os
import time
import threading
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.config import USER_AGENT, CANDIDATE_EMAIL
from src.storage.tracker import log_application, save_tailored_application, JobStatus, APPLICATIONS_DIR
from src.workflow.optimize import render_tailored_cv_latex
from src.workflow.indeed_apply import IndeedApplier, _is_indeed_url
from src.workflow.linkedin_apply import run_linkedin_agent

# Global events for human-in-the-loop review
review_event = threading.Event()
skip_event = threading.Event()


def _load_tailored_for_job(job_id):
    """Load the pre-generated tailored CV and cover letter for a job."""
    filepath = os.path.join(APPLICATIONS_DIR, job_id, "tailored_cv.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _build_plain_text_cv(cv_data):
    """Convert structured CV JSON into a clean plain-text resume string."""
    lines = []

    name = cv_data.get("full_name", "")
    if name:
        lines.append(name)

    contact_parts = []
    if cv_data.get("email"):
        contact_parts.append(cv_data["email"])
    if cv_data.get("phone"):
        contact_parts.append(cv_data["phone"])
    if cv_data.get("location"):
        contact_parts.append(cv_data["location"])
    if contact_parts:
        lines.append(" | ".join(contact_parts))

    links = cv_data.get("links", [])
    if isinstance(links, list) and links:
        lines.append(" | ".join(links))

    lines.append("")

    if cv_data.get("summary"):
        lines.append("PROFESSIONAL SUMMARY")
        lines.append(cv_data["summary"])
        lines.append("")

    skills = cv_data.get("skills", [])
    if isinstance(skills, list) and skills:
        lines.append("TECHNICAL SKILLS")
        lines.append(", ".join(skills))
        lines.append("")

    experience = cv_data.get("experience", [])
    if isinstance(experience, list) and experience:
        lines.append("EXPERIENCE")
        for exp in experience:
            role = exp.get("role") or exp.get("title") or exp.get("job_title") or exp.get("position", "")
            company = exp.get("company") or exp.get("organization", "")
            duration = exp.get("duration") or exp.get("dates") or exp.get("period", "")
            lines.append(f"{role} at {company} ({duration})")

            desc = exp.get("description") or exp.get("bullet_points") or exp.get("highlights")
            if isinstance(desc, list):
                for bullet in desc:
                    lines.append(f"  - {bullet}")
            elif isinstance(desc, str):
                for bullet in desc.split("\n"):
                    b = bullet.strip().lstrip("-•* ").strip()
                    if b:
                        lines.append(f"  - {b}")
            lines.append("")

    education = cv_data.get("education", [])
    if isinstance(education, list) and education:
        lines.append("EDUCATION")
        for edu in education:
            degree = edu.get("degree") or edu.get("title") or edu.get("program", "")
            institution = edu.get("institution") or edu.get("school") or edu.get("university", "")
            year = edu.get("year") or edu.get("duration") or edu.get("dates", "")
            lines.append(f"{degree} - {institution} ({year})")
        lines.append("")

    projects = cv_data.get("projects", [])
    if isinstance(projects, list) and projects:
        lines.append("PROJECTS")
        for proj in projects:
            title = proj.get("title") or proj.get("name", "")
            lines.append(title)
            desc = proj.get("description")
            if isinstance(desc, list):
                for bullet in desc:
                    lines.append(f"  - {bullet}")
            elif isinstance(desc, str):
                for bullet in desc.split("\n"):
                    b = bullet.strip().lstrip("-•* ").strip()
                    if b:
                        lines.append(f"  - {b}")
            lines.append("")

    certifications = cv_data.get("certifications", [])
    if isinstance(certifications, list) and certifications:
        lines.append("CERTIFICATIONS")
        for cert in certifications:
            lines.append(f"  - {cert}")
        lines.append("")

    return "\n".join(lines)


def _generate_cv_text_file(cv_data, job_id):
    """Generate a plain-text .txt file of the tailored CV for form file uploads."""
    text = _build_plain_text_cv(cv_data)
    temp_dir = os.path.join(APPLICATIONS_DIR, job_id)
    os.makedirs(temp_dir, exist_ok=True)
    filepath = os.path.join(temp_dir, "tailored_cv.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    return filepath


class SequentialApplier:
    def __init__(self, cv_data, tailor_func, cover_letter_func):
        self.cv_data = cv_data
        self.tailor_func = tailor_func
        self.cover_letter_func = cover_letter_func
        self.driver = None

    def init_browser(self):
        if not self.driver:
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            # Using persistent user data directory
            user_data_dir = os.path.join(os.getcwd(), "user_data_uc")
            os.makedirs(user_data_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={user_data_dir}")
            
            self.driver = uc.Chrome(options=options)
            
            # Deep stealth overriding
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                """
            })

    def _try_fill(self, selector, value):
        """Try to fill a form field matching the selector, returns True if found."""
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    time.sleep(0.15)
                    try:
                        el.click()
                    except:
                        pass
                    el.clear()
                    el.send_keys(str(value))
                    return True
        except Exception:
            pass
        return False

    def _try_fill_any(self, selectors, value):
        """Try multiple selectors in order, fill the first match."""
        for selector in selectors:
            if self._try_fill(selector, value):
                return True
        return False

    def _try_upload_file(self, filepath):
        """Try to find a file input and upload the CV file."""
        try:
            file_selectors = [
                "input[type='file']",
                "input[type='file'][name*='cv' i]",
                "input[type='file'][name*='resume' i]",
                "input[type='file'][id*='cv' i]",
                "input[type='file'][id*='resume' i]",
                "input[type='file'][accept*='pdf' i]",
                "input[type='file'][accept*='doc' i]",
            ]

            for selector in file_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    # Input type=file doesn't need to be displayed to accept keys
                    elements[0].send_keys(os.path.abspath(filepath))
                    print(f"  [OK] Uploaded CV file via: {selector}")
                    return True

            all_file_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if all_file_inputs:
                all_file_inputs[0].send_keys(os.path.abspath(filepath))
                print(f"  [OK] Uploaded CV file via first file input")
                return True

        except Exception as e:
            print(f"  [WARN] File upload failed: {e}")
        return False

    def fill_form(self, tailored_cv, cover_letter, cv_filepath=None):
        try:
            full_name = tailored_cv.get("full_name", "")
            email = tailored_cv.get("email", "") or CANDIDATE_EMAIL
            phone = tailored_cv.get("phone", "")
            location = tailored_cv.get("location", "")
            summary = tailored_cv.get("summary", "")

            name_parts = full_name.split() if full_name else []
            first_name = name_parts[0] if name_parts else ""
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

            if cv_filepath and os.path.exists(cv_filepath):
                self._try_upload_file(cv_filepath)
                time.sleep(1)

            # Identity fields
            self._try_fill_any([
                "input[name*='full_name' i]", "input[id*='full_name' i]",
                "input[name*='fullname' i]", "input[id*='fullname' i]",
                "input[name*='display_name' i]", "input[id*='display_name' i]",
                "input[name*='name' i][name*='full' i]",
                "input[placeholder*='full name' i]",
            ], full_name)

            self._try_fill_any([
                "input[name*='first_name' i]", "input[id*='first_name' i]",
                "input[name*='firstname' i]", "input[id*='firstname' i]",
                "input[name*='given' i]", "input[id*='given' i]",
                "input[placeholder*='first name' i]",
            ], first_name)

            self._try_fill_any([
                "input[name*='last_name' i]", "input[id*='last_name' i]",
                "input[name*='lastname' i]", "input[id*='lastname' i]",
                "input[name*='surname' i]", "input[id*='surname' i]",
                "input[name*='family' i]", "input[id*='family' i]",
                "input[placeholder*='last name' i]",
            ], last_name)

            self._try_fill_any([
                "input[type='email']",
                "input[name*='email' i]", "input[id*='email' i]",
                "input[placeholder*='email' i]",
            ], email)

            if phone:
                self._try_fill_any([
                    "input[type='tel']",
                    "input[name*='phone' i]", "input[id*='phone' i]",
                    "input[name*='mobile' i]", "input[id*='mobile' i]",
                    "input[name*='telephone' i]", "input[id*='telephone' i]",
                    "input[placeholder*='phone' i]",
                ], phone)

            if location:
                self._try_fill_any([
                    "input[name*='location' i]", "input[id*='location' i]",
                    "input[name*='city' i]", "input[id*='city' i]",
                    "input[name*='address' i]", "input[id*='address' i]",
                    "input[placeholder*='city' i]",
                ], location)

            links = tailored_cv.get('links', [])
            if isinstance(links, list):
                for link in links:
                    l_lower = link.lower()
                    if 'linkedin' in l_lower:
                        self._try_fill_any([
                            "input[name*='linkedin' i]", "input[id*='linkedin' i]",
                            "input[placeholder*='linkedin' i]",
                        ], link)
                    elif 'github' in l_lower:
                        self._try_fill_any([
                            "input[name*='github' i]", "input[id*='github' i]",
                            "input[placeholder*='github' i]",
                        ], link)
                    elif 'portfolio' in l_lower or 'website' in l_lower:
                        self._try_fill_any([
                            "input[name*='portfolio' i]", "input[id*='portfolio' i]",
                            "input[name*='website' i]", "input[id*='website' i]",
                            "input[placeholder*='website' i]",
                            "input[placeholder*='portfolio' i]",
                        ], link)

            if summary:
                self._try_fill_any([
                    "textarea[name*='summary' i]", "textarea[id*='summary' i]",
                    "textarea[name*='about' i]", "textarea[id*='about' i]",
                    "textarea[placeholder*='summary' i]",
                ], summary)

            if cover_letter:
                self._try_fill_any([
                    "textarea[name*='cover' i]", "textarea[id*='cover' i]",
                    "textarea[name*='letter' i]", "textarea[id*='letter' i]",
                    "textarea[name*='motivation' i]", "textarea[id*='motivation' i]",
                    "textarea[placeholder*='cover letter' i]",
                ], cover_letter)

            print("  [OK] Form auto-fill completed")
            return True
        except Exception as e:
            print(f"Error during auto-fill: {e}")
            return False

    def wait_for_cloudflare(self):
        """Wait if a Cloudflare challenge is detected on the current page."""
        try:
            print("Checking for Cloudflare challenge...")
            for i in range(30):
                title = self.driver.title
                cf_titles = ("Just a moment", "Attention Required", "Security check", "Cloudflare")
                if any(t in title for t in cf_titles):
                    print(f"  Cloudflare detected (attempt {i+1}). Waiting for you to solve it...")
                    if i in (5, 15):
                        self.driver.refresh()
                    time.sleep(2)
                else:
                    elements = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "#challenge-running, #cf-challenge-running, .cf-browser-verification"
                    )
                    if elements:
                        print(f"  Cloudflare element detected (attempt {i+1}). Waiting...")
                        if i in (5, 15):
                            self.driver.refresh()
                        time.sleep(2)
                    else:
                        return True
            print("  Cloudflare did not resolve within timeout.")
        except Exception as e:
            print(f"  Cloudflare check error: {e}")
        return False

    def wait_for_cloudflare_on_url(self, url: str):
        """Open a URL then wait for any Cloudflare challenge to clear."""
        self.driver.get(url)
        time.sleep(3)
        self.wait_for_cloudflare()
        time.sleep(1)

    def apply_to_job(self, job):
        job_id = str(job.get('id') or job.get('job_id'))
        job_title = job.get('job_title', 'Unknown Title')
        company = job.get('company', 'Unknown Company')
        job_url = job.get('url') or job.get('job_url')
        job_source = (job.get('source') or '').lower()

        if not job_url:
            log_application(job_id, job_title, company, JobStatus.FAILED, "Missing application URL")
            return False

        try:
            tailored_data = _load_tailored_for_job(job_id)

            if tailored_data:
                tailored_cv = tailored_data.get("cv", {})
                cover_letter = tailored_data.get("cover_letter", "")
                print(f"Using pre-generated tailored CV and cover letter for {job_title}")
            else:
                print(f"Tailoring application for {job_title} at {company}...")
                job_desc = job.get('description', '')
                tailored_cv = self.tailor_func(self.cv_data, job_desc)
                cover_letter = self.cover_letter_func(self.cv_data, job_desc)
                save_tailored_application(job_id, {
                    "cv": tailored_cv,
                    "cv_latex": render_tailored_cv_latex(tailored_cv),
                    "cover_letter": cover_letter
                })

            log_application(job_id, job_title, company, JobStatus.TAILORED)
            cv_filepath = _generate_cv_text_file(tailored_cv, job_id)

            self.init_browser()
            self.wait_for_cloudflare_on_url(job_url)

            # ── Route by job source ───────────────────────────────────────────
            if job_source == 'linkedin' or 'linkedin.com' in job_url.lower():
                print(f"[LinkedIn Agent] Starting LangGraph agent for: {job_title} at {company}")
                result = run_linkedin_agent(
                    driver=self.driver,
                    job_url=job_url,
                    cv_data=tailored_cv,
                    cover_letter=cover_letter,
                    cv_filepath=cv_filepath,
                )
                if result == 'external':
                    # LinkedIn job redirects to external site — use generic filler
                    print(f"[Generic Filler] LinkedIn external apply for: {job_title}")
                    self.wait_for_cloudflare()
                    self.fill_form(tailored_cv, cover_letter, cv_filepath)
                elif result == 'already_applied':
                    log_application(job_id, job_title, company, JobStatus.SUBMITTED, "Already applied via LinkedIn")
                    return True
                elif result == 'failed':
                    print(f"[LinkedIn Agent] Could not complete — leaving browser open for manual apply")

            elif job_source == 'indeed' or _is_indeed_url(job_url):
                print(f"[Indeed Agent] Starting for: {job_title} at {company}")
                agent = IndeedApplier(
                    driver=self.driver,
                    cv_data=tailored_cv,
                    cover_letter=cover_letter,
                    cv_filepath=cv_filepath,
                )
                result = agent.run(job_url)
                if result == 'external_redirect':
                    print(f"[Generic Filler] Indeed external apply for: {job_title}")
                    self.wait_for_cloudflare()
                    self.fill_form(tailored_cv, cover_letter, cv_filepath)
                elif result == 'failed':
                    print(f"[Indeed Agent] Could not reach review page — leaving for human review")

            else:
                # Generic path: open URL and fill form directly
                print(f"[Generic Filler] Filling form for: {job_title} at {company}")
                self.wait_for_cloudflare()
                self.fill_form(tailored_cv, cover_letter, cv_filepath)

            log_application(job_id, job_title, company, JobStatus.READY)

            print(f"--- [Job {job_id}] REVIEW REQUIRED ---")
            print(f"Role: {job_title} | Company: {company}")
            print(f"Action: Review the form in the browser, then click 'Submit Done' in the dashboard.")

            review_event.clear()
            skip_event.clear()

            # Wait for human signal
            while not review_event.is_set() and not skip_event.is_set():
                try:
                    self.driver.title  # raises if browser was closed
                except Exception:
                    print(f"Browser closed for: {job_title}")
                    log_application(job_id, job_title, company, JobStatus.FAILED, "User closed browser")
                    return False
                time.sleep(1)

            if skip_event.is_set():
                print(f"Skipped: {job_title}")
                log_application(job_id, job_title, company, JobStatus.FAILED, "User skipped during review")
                return False

            log_application(job_id, job_title, company, JobStatus.SUBMITTED)
            print(f"[OK] Submitted: {job_title}")

            # Clean up: close tab and open blank to keep browser alive for next job
            try:
                self.driver.close()
            except Exception:
                pass
            try:
                if not self.driver.window_handles:
                    self.driver.execute_script("window.open('');")
                self.driver.switch_to.window(self.driver.window_handles[-1])
            except Exception:
                pass

            return True

        except Exception as e:
            print(f"Failed to apply to {job_title}: {e}")
            log_application(job_id, job_title, company, JobStatus.FAILED, str(e))
            return False

    def close(self):
        if self.driver:
            self.driver.quit()

def bulk_apply(jobs, cv_data, tailor_func, cover_letter_func):
    applier = SequentialApplier(cv_data, tailor_func, cover_letter_func)
    try:
        for job in jobs:
            applier.apply_to_job(job)
    finally:
        applier.close()

def signal_review_complete():
    review_event.set()

def signal_skip():
    skip_event.set()
