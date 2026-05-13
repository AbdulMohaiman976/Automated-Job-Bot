import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

from src.config import CANDIDATE_EMAIL


INDEED_DOMAINS = ("indeed.com", "indeed.co.", "indeed.ca", "indeed.com.au")


def _is_indeed_url(url: str) -> bool:
    return any(d in url.lower() for d in INDEED_DOMAINS)


class IndeedApplier:
    """
    Drives the Indeed Easy Apply multi-step modal from open to Review page.
    The driver is passed in from SequentialApplier — no new browser is spawned.
    After run() returns 'review_reached', the caller shows the HITL banner.
    After run() returns 'external_redirect', the caller falls back to generic fill_form().
    """

    # Selectors for the "Apply now" / "Apply on Indeed" button on the listing page
    _APPLY_BTN = [
        "button[id*='applyButton']",
        ".ia-IndeedApplyButton",
        "#applyButtonLinkContainer a",
        "div[id='applyButtonLinkContainer'] a",
        "span[id='applyButtonLinkContainer'] a",
        "a[data-tn-element='applyButton']",
        "button[data-tn-element='applyButton']",
        "button[class*='apply' i]",
        "a[class*='apply' i][href*='apply']",
    ]

    # "Next" / "Continue" button inside the multi-step apply flow
    _NEXT_BTN = [
        "button[class*='ia-continueButton']",
        "button[id='form-action-continue']",
        "button[data-testid='continue-button']",
        "button[aria-label*='continue' i]",
        "button[class*='continue' i]",
        "button[type='submit']",
        "input[type='submit']",
    ]

    # Indicators that we're on the final Review / Submit page
    _REVIEW_INDICATORS = [
        "button[data-testid='submit-application-button']",
        "button[aria-label*='submit application' i]",
        "button[class*='ia-submitButton']",
        "button[id='form-action-submit']",
        "input[value*='Submit' i][type='submit']",
    ]

    def __init__(self, driver, cv_data: dict, cover_letter: str = "", cv_filepath: str = None):
        self.driver = driver
        self.cv = cv_data
        self.cover_letter = cover_letter
        self.cv_filepath = cv_filepath

    # ------------------------------------------------------------------ helpers

    def _find(self, selectors: list, timeout: float = 5):
        """Return first visible element matching any of the selectors, or None."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for sel in selectors:
                try:
                    for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                        if el.is_displayed():
                            return el
                except Exception:
                    pass
            time.sleep(0.4)
        return None

    def _safe_fill(self, el, value: str) -> bool:
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.1)
            try:
                el.click()
            except Exception:
                pass
            # Clear existing value via JS then send_keys
            self.driver.execute_script("arguments[0].value = '';", el)
            el.send_keys(str(value))
            return True
        except Exception:
            return False

    def _fill_any(self, selectors: list, value: str) -> bool:
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        if self._safe_fill(el, value):
                            return True
            except Exception:
                pass
        return False

    # ------------------------------------------------------------------ step fillers

    def _fill_contact(self):
        full_name = self.cv.get("full_name", "")
        parts = full_name.split() if full_name else []
        first = parts[0] if parts else ""
        last = " ".join(parts[1:]) if len(parts) > 1 else ""
        email = self.cv.get("email", "") or CANDIDATE_EMAIL
        phone = self.cv.get("phone", "")
        location = self.cv.get("location", "")

        self._fill_any([
            "input[name*='name.first' i]", "input[id*='name.first' i]",
            "input[name*='firstName' i]", "input[id*='firstName' i]",
            "input[placeholder*='first name' i]",
        ], first)

        self._fill_any([
            "input[name*='name.last' i]", "input[id*='name.last' i]",
            "input[name*='lastName' i]", "input[id*='lastName' i]",
            "input[placeholder*='last name' i]",
        ], last)

        self._fill_any([
            "input[name*='email' i]", "input[id*='email' i]",
            "input[type='email']", "input[placeholder*='email' i]",
        ], email)

        if phone:
            self._fill_any([
                "input[name*='phone' i]", "input[id*='phone' i]",
                "input[type='tel']", "input[placeholder*='phone' i]",
            ], phone)

        if location:
            self._fill_any([
                "input[name*='location' i]", "input[id*='location' i]",
                "input[name*='city' i]", "input[placeholder*='city' i]",
            ], location)

    def _upload_resume(self):
        if not self.cv_filepath or not os.path.exists(self.cv_filepath):
            return
        try:
            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if inputs:
                inputs[0].send_keys(os.path.abspath(self.cv_filepath))
                print("    [OK] Uploaded resume file")
                time.sleep(1.5)
        except Exception as e:
            print(f"    [WARN] Resume upload error: {e}")

    def _fill_cover_letter(self):
        if not self.cover_letter:
            return
        self._fill_any([
            "textarea[name*='cover' i]", "textarea[id*='cover' i]",
            "textarea[name*='letter' i]", "textarea[placeholder*='cover' i]",
            "textarea[aria-label*='cover letter' i]",
            # Indeed's own cover letter textarea
            "textarea[id*='coverletter' i]", "textarea[name*='coverletter' i]",
        ], self.cover_letter)

    def _handle_screening_questions(self):
        """
        Best-effort: answer radio Yes/No questions and simple selects.
        Text questions and complex dropdowns are left for human review.
        """
        try:
            # Select "Yes" for any visible Yes/No radio groups
            radios = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            for radio in radios:
                try:
                    rid = radio.get_attribute("id") or ""
                    label_text = ""
                    if rid:
                        labels = self.driver.find_elements(By.CSS_SELECTOR, f"label[for='{rid}']")
                        if labels:
                            label_text = labels[0].text.lower()
                    val = (radio.get_attribute("value") or "").lower()
                    if ("yes" in label_text or val == "yes") and not radio.is_selected():
                        radio.click()
                except Exception:
                    pass

            # Pick first real option in any visible <select>
            selects = self.driver.find_elements(By.CSS_SELECTOR, "select")
            for sel_el in selects:
                try:
                    if sel_el.is_displayed():
                        sel_obj = Select(sel_el)
                        options = sel_obj.options
                        if len(options) > 1:
                            sel_obj.select_by_index(1)
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------ login handling

    def _is_login_wall(self) -> bool:
        """Detect if Indeed is showing a login/signup prompt or modal."""
        try:
            url = self.driver.current_url.lower()
            if any(k in url for k in ('login', 'signin', 'sign-in', '/account/', 'auth')):
                return True
            # Check for visible login-specific elements
            login_selectors = [
                "button[data-tn-element='google-auth-button']",
                "#ifl-GoogleSignInButton",
                "a[href*='accounts.google.com']",
                "button[class*='google' i]",
                "div[id*='loginPage' i]",
                "div[class*='SignIn' i]",
                "form[id*='login' i]",
            ]
            for sel in login_selectors:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if any(e.is_displayed() for e in els):
                    return True
            # Text-based fallback
            body = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            return (
                ("continue with google" in body or "continue with email" in body)
                and ("sign in" in body or "log in" in body or "create account" in body)
            )
        except Exception:
            return False

    def _wait_for_login(self, timeout_seconds: int = 300) -> bool:
        """
        Pause and wait for the user to complete Indeed login in the browser.
        Returns True once login is detected, False on timeout.
        """
        print()
        print("=" * 62)
        print("  [WARN]  INDEED LOGIN REQUIRED")
        print("  Please log in to Indeed in the Chrome window")
        print("  (Continue with Google OR Continue with email).")
        print(f"  Waiting up to {timeout_seconds // 60} minutes for you to log in...")
        print("=" * 62)
        print()

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(2)
            try:
                if not self._is_login_wall():
                    url = self.driver.current_url.lower()
                    if 'indeed.com' in url:
                        print("  [OK] Login complete — continuing application...")
                        time.sleep(2)
                        return True
            except Exception:
                pass

        print("  [ERR] Login wait timed out — leaving page open for human review")
        return False

    # ------------------------------------------------------------------ navigation

    def _on_review_page(self) -> bool:
        """True if the current page is the final Review / Submit page."""
        if self._find(self._REVIEW_INDICATORS, timeout=1):
            return True
        try:
            body = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            return "review your application" in body or "submit application" in body
        except Exception:
            return False

    def _click(self, selectors: list, label: str) -> bool:
        el = self._find(selectors, timeout=6)
        if not el:
            return False
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)
            el.click()
            print(f"    [OK] Clicked {label}")
            time.sleep(2)
            return True
        except ElementClickInterceptedException:
            try:
                self.driver.execute_script("arguments[0].click();", el)
                time.sleep(2)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def _fill_current_step(self):
        self._fill_contact()
        self._upload_resume()
        self._fill_cover_letter()
        self._handle_screening_questions()

    def _navigate_to_review(self, max_steps: int = 12) -> bool:
        for step in range(1, max_steps + 1):
            print(f"  -> Indeed apply step {step}")

            if self._on_review_page():
                print("  [OK] Reached Review page — pausing for human review")
                return True

            self._fill_current_step()
            time.sleep(0.5)

            advanced = self._click(self._NEXT_BTN, "Next/Continue")
            if not advanced:
                # Maybe we're already on review
                if self._on_review_page():
                    print("  [OK] Reached Review page — pausing for human review")
                    return True
                print(f"  [WARN] Stuck on step {step} — leaving for human review")
                return False

        print("  [WARN] Max steps reached without finding Review page")
        return False

    # ------------------------------------------------------------------ public

    def run(self, job_url: str) -> str:
        """
        Drive the Indeed application from listing page to Review page.

        Returns:
            'review_reached'     — stopped at Review page, HITL can proceed
            'external_redirect'  — Indeed redirected to a company site, caller falls back to generic fill
            'failed'             — could not proceed
        """
        print(f"  [Indeed] Opening: {job_url}")
        self.driver.get(job_url)
        time.sleep(3)

        # Handle login wall BEFORE clicking Apply (page may redirect to login on load)
        if self._is_login_wall():
            logged_in = self._wait_for_login()
            if not logged_in:
                return 'failed'
            # After login Indeed usually redirects back to the job — reload to be safe
            if not _is_indeed_url(self.driver.current_url) or 'viewjob' not in self.driver.current_url:
                self.driver.get(job_url)
                time.sleep(3)

        # Click the Apply button on the listing page
        clicked = self._click(self._APPLY_BTN, "Apply button")
        if not clicked:
            print("  [WARN] Apply button not found — checking if already on an application page")
            if self._on_review_page():
                return 'review_reached'
            return 'external_redirect'

        time.sleep(2)

        # Login wall can also appear AFTER clicking Apply (session expired mid-session)
        if self._is_login_wall():
            logged_in = self._wait_for_login()
            if not logged_in:
                return 'failed'
            # Re-click Apply after login
            self.driver.get(job_url)
            time.sleep(3)
            self._click(self._APPLY_BTN, "Apply button (after login)")
            time.sleep(2)

        # If we were redirected off Indeed, it's an external application
        if not _is_indeed_url(self.driver.current_url):
            print(f"  -> Redirected to external site: {self.driver.current_url}")
            return 'external_redirect'

        success = self._navigate_to_review()
        return 'review_reached' if success else 'failed'
