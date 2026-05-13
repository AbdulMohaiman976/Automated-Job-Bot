"""
LinkedIn Easy Apply agent built with LangGraph.

Graph:
  START -> open_job -> check_login -> [wait_login ->] click_easy_apply
        -> fill_step ⟷ advance (loop) -> review -> END
                                      -> handle_error -> END

The LLM (Groq) is used only where intelligence is genuinely needed:
  - Screening questions: reads the question, answers from CV evidence
  - Step-type detection fallback when selectors are ambiguous
Everything else (contact info, resume, cover letter) uses deterministic
Selenium selectors for speed and reliability.
"""

import json
import os
import time
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import ElementClickInterceptedException

from src.config import CANDIDATE_EMAIL, GROQ_API_KEY


# ── State ─────────────────────────────────────────────────────────────────────

class LinkedInState(TypedDict):
    driver: Any          # Selenium WebDriver — not serialized, in-memory only
    job_url: str
    cv_data: dict
    cover_letter: str
    cv_filepath: str
    step_count: int
    max_steps: int
    login_done: bool
    result: str          # 'review_reached' | 'external' | 'failed' | 'already_applied'
    error: str


# ── Low-level Selenium helpers ────────────────────────────────────────────────

def _find(driver, selectors: list, timeout: float = 6):
    """Return first visible element matching any selector, or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in selectors:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.is_displayed():
                        return el
            except Exception:
                pass
        time.sleep(0.35)
    return None


def _safe_fill(driver, el, value: str) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.1)
        try:
            el.click()
        except Exception:
            pass
        driver.execute_script("arguments[0].value = '';", el)
        el.send_keys(str(value))
        return True
    except Exception:
        return False


def _fill_any(driver, selectors: list, value: str, skip_if_filled=True) -> bool:
    """Fill first visible matching element. Skips if already has a value."""
    for sel in selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if not el.is_displayed():
                    continue
                if skip_if_filled and (el.get_attribute("value") or "").strip():
                    continue
                if _safe_fill(driver, el, value):
                    return True
        except Exception:
            pass
    return False


def _click(driver, selectors: list, label: str = "", timeout: float = 8) -> bool:
    el = _find(driver, selectors, timeout)
    if not el:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.3)
        el.click()
        if label:
            print(f"    [OK] Clicked: {label}")
        time.sleep(1.5)
        return True
    except ElementClickInterceptedException:
        try:
            driver.execute_script("arguments[0].click();", el)
            time.sleep(1.5)
            return True
        except Exception:
            return False
    except Exception:
        return False


def _modal_text(driver) -> str:
    """Extract visible text from the Easy Apply modal (capped at 2000 chars)."""
    for sel in [".jobs-easy-apply-modal", "div[role='dialog']", ".artdeco-modal"]:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    return el.text[:2000]
        except Exception:
            pass
    return ""


def _modal_fields(driver) -> list:
    """
    Extract all visible, unfilled form fields from the modal.
    Returns list of dicts: {label, type, id, name, current_value}
    """
    fields = []
    modal = None
    for sel in [".jobs-easy-apply-modal", "div[role='dialog']", ".artdeco-modal"]:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    modal = el
                    break
        except Exception:
            pass
        if modal:
            break
    if not modal:
        return fields

    try:
        inputs = modal.find_elements(
            By.CSS_SELECTOR,
            "input:not([type='hidden']):not([type='file']), select, textarea"
        )
        for inp in inputs:
            try:
                if not inp.is_displayed():
                    continue
                itype = inp.get_attribute("type") or inp.tag_name
                iid = inp.get_attribute("id") or ""
                iname = inp.get_attribute("name") or ""
                current = inp.get_attribute("value") or ""

                label_text = ""
                if iid:
                    try:
                        lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{iid}']")
                        label_text = lbl.text.strip()
                    except Exception:
                        pass
                if not label_text:
                    try:
                        label_text = inp.find_element(By.XPATH, "ancestor::label").text.strip()
                    except Exception:
                        pass
                if not label_text:
                    label_text = inp.get_attribute("aria-label") or inp.get_attribute("placeholder") or ""

                fields.append({
                    "label": label_text,
                    "type": itype,
                    "id": iid,
                    "name": iname,
                    "current_value": current,
                })
            except Exception:
                pass
    except Exception:
        pass
    return fields


# ── Login detection ───────────────────────────────────────────────────────────

def _is_login_wall(driver) -> bool:
    try:
        url = driver.current_url.lower()
        if any(k in url for k in ("login", "signin", "sign-in", "authwall", "checkpoint", "uas/oauth")):
            return True
        # Treat Google OAuth page as still-in-login (user may have clicked "Continue with Google")
        if "accounts.google.com" in url or "google.com/o/oauth" in url:
            return True
        login_selectors = [
            "#username", "#password",
            "form[action*='login']",
            "button[aria-label*='Sign in with Google' i]",
            ".sign-in-modal",
            "a[data-tracking-control-name*='sign-in' i]",
        ]
        for sel in login_selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if any(e.is_displayed() for e in els):
                return True
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        return ("sign in" in body or "log in" in body) and "new to linkedin" in body
    except Exception:
        return False


# ── Review page detection ─────────────────────────────────────────────────────

def _is_review_page(driver) -> bool:
    review_selectors = [
        "button[aria-label*='Submit application' i]",
        "button[aria-label='Review your application']",
        "button[aria-label*='submit your application' i]",
    ]
    for sel in review_selectors:
        try:
            if any(e.is_displayed() for e in driver.find_elements(By.CSS_SELECTOR, sel)):
                return True
        except Exception:
            pass
    try:
        text = _modal_text(driver).lower()
        return "submit application" in text or "review your application" in text
    except Exception:
        return False


# ── LLM: intelligent screening question answering ─────────────────────────────

def _llm_answer_fields(cv_data: dict, fields: list, modal_context: str) -> list:
    """
    Ask Groq to read visible form fields and return answers based on CV data.
    Returns: [{id, value}, ...]
    Only called when there are unfilled fields that need intelligent answers.
    """
    if not GROQ_API_KEY or not fields:
        return []
    try:
        llm = ChatGroq(
            api_key=GROQ_API_KEY,
            model="llama-3.3-70b-versatile",
            temperature=0,
        )
        prompt = f"""You are a job application assistant. A candidate is filling a LinkedIn Easy Apply form.

CURRENT FORM STEP (what the user sees):
{modal_context[:1200]}

VISIBLE FORM FIELDS (unfilled):
{json.dumps(fields, indent=2)}

CANDIDATE CV:
{json.dumps(cv_data, indent=2)}

TASK: Return the correct value for each field based ONLY on the candidate's CV.
Rules:
- "years of experience" -> calculate from CV dates (be conservative)
- work authorization / eligibility -> "Yes"
- "how did you hear" -> "LinkedIn"
- salary / compensation -> leave empty ("")
- open-text questions -> 1-2 sentences using CV evidence only, never fabricate
- yes/no radio -> answer "yes" for standard eligibility questions
- "notice period" / "when can you start" -> "Immediately" or "2 weeks"
- if a question can't be answered from CV -> return ""

Return a JSON array ONLY, no explanation:
[{{"id": "field_id", "value": "answer"}}, ...]"""

        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content.strip()
        if "[" in text and "]" in text:
            text = text[text.find("["):text.rfind("]") + 1]
        return json.loads(text)
    except Exception as e:
        print(f"    [WARN] LLM screening answer error: {e}")
        return []


def _apply_llm_answers(driver, answers: list):
    """Apply LLM-generated field answers to the form."""
    for item in answers:
        fid = item.get("id", "")
        val = item.get("value", "")
        if not fid or not val:
            continue
        try:
            el = driver.find_element(By.ID, fid)
            if not el.is_displayed():
                continue
            tag = el.tag_name.lower()
            itype = (el.get_attribute("type") or "").lower()

            if tag == "select":
                sel_obj = Select(el)
                try:
                    sel_obj.select_by_visible_text(val)
                except Exception:
                    if len(sel_obj.options) > 1:
                        sel_obj.select_by_index(1)
            elif itype == "radio":
                if val.lower() in ("yes", "true", "1") and not el.is_selected():
                    driver.execute_script("arguments[0].click();", el)
            elif itype == "checkbox":
                if val.lower() in ("yes", "true", "1") and not el.is_selected():
                    driver.execute_script("arguments[0].click();", el)
            else:
                current = (el.get_attribute("value") or "").strip()
                if not current:
                    _safe_fill(driver, el, val)
        except Exception:
            pass


# ── Graph nodes ───────────────────────────────────────────────────────────────

def node_open_job(state: LinkedInState) -> dict:
    driver = state["driver"]
    print(f"  [LinkedIn Agent] Opening: {state['job_url']}")
    try:
        driver.get(state["job_url"])
        time.sleep(3)
    except Exception as e:
        return {"result": "failed", "error": f"Could not open URL: {e}"}
    return {}


def node_check_login(state: LinkedInState) -> dict:
    driver = state["driver"]
    try:
        login_needed = _is_login_wall(driver)
        return {"login_done": not login_needed}
    except Exception:
        return {"login_done": False}


def node_wait_login(state: LinkedInState) -> dict:
    driver = state["driver"]
    timeout = 300
    print()
    print("=" * 64)
    print("  [WARN]  LINKEDIN LOGIN REQUIRED")
    print()
    print("  IMPORTANT: Use your LinkedIn EMAIL + PASSWORD to sign in.")
    print("  Do NOT click 'Continue with Google' — Google blocks sign-in")
    print("  from automated browsers and the window will close.")
    print()
    print("  Steps:")
    print("    1. Click 'Sign in' in the Chrome window")
    print("    2. Enter your LinkedIn email and password")
    print("    3. Complete any verification if asked")
    print("    4. The bot will continue automatically once logged in")
    print()
    print("  After first login your session is saved — future runs")
    print("  will not need to log in again.")
    print(f"  Waiting up to {timeout // 60} minutes...")
    print("=" * 64)
    print()

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        try:
            if not _is_login_wall(driver):
                url = driver.current_url.lower()
                if "linkedin.com" in url:
                    print("  [OK] Login complete — navigating back to the job...")
                    time.sleep(1)
                    driver.get(state["job_url"])
                    time.sleep(3)
                    return {"login_done": True}
        except Exception as e:
            err = str(e).lower()
            # Browser was closed by user or crashed
            if any(k in err for k in ("no such window", "target window", "session deleted", "unable to connect")):
                return {"result": "failed", "error": "Browser was closed during login"}
            pass

    return {"result": "failed", "error": "Login timed out after 5 minutes"}


def node_click_easy_apply(state: LinkedInState) -> dict:
    driver = state["driver"]

    easy_apply_selectors = [
        "button.jobs-apply-button",
        "button[aria-label*='Easy Apply' i]",
        ".jobs-apply-button--top-card",
        ".jobs-unified-top-card__content button.artdeco-button--primary",
        "button[data-control-name='jobdetails_topcard_inapply']",
    ]

    clicked = _click(driver, easy_apply_selectors, "Easy Apply button", timeout=10)

    if not clicked:
        # Check if it's a regular (non-Easy-Apply) external link
        external_selectors = [
            "button[aria-label*='Apply' i]:not([aria-label*='Easy' i])",
            "a[data-control-name='jobdetails_topcard_inapply']",
        ]
        if _find(driver, external_selectors, timeout=3):
            print("  -> External apply button found (not Easy Apply) — falling back to generic filler")
            return {"result": "external"}

        # Check if already applied
        try:
            body = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "applied" in body and "you applied" in body:
                print("  -> Already applied to this job")
                return {"result": "already_applied"}
        except Exception:
            pass

        return {"result": "failed", "error": "Easy Apply button not found on this job page"}

    time.sleep(2)

    # Verify modal opened
    modal = _find(driver, [".jobs-easy-apply-modal", "div[role='dialog']", ".artdeco-modal"], timeout=6)
    if not modal:
        return {"result": "failed", "error": "Easy Apply modal did not open after clicking"}

    print("  [OK] Easy Apply modal opened")
    return {}


def node_fill_step(state: LinkedInState) -> dict:
    """
    Fill the current modal step using deterministic selectors + LLM for unknowns.
    """
    driver = state["driver"]
    cv = state["cv_data"]

    print(f"  -> Filling modal step {state['step_count'] + 1}")

    # ── 1. Contact info (deterministic) ───────────────────────────────────────
    phone = cv.get("phone", "")
    location = cv.get("location", "")

    if phone:
        _fill_any(driver, [
            "input[id*='phoneNumber-nationalNumber' i]",
            "input[id*='phoneNumber' i]",
            "input[name*='phoneNumber' i]",
            "input[type='tel']",
        ], phone)

    if location:
        _fill_any(driver, [
            "input[id*='city' i]",
            "input[id*='location' i]",
            "input[placeholder*='city' i]",
            "input[placeholder*='location' i]",
        ], location)

    # ── 2. Resume upload ───────────────────────────────────────────────────────
    cv_filepath = state.get("cv_filepath", "")
    if cv_filepath and os.path.exists(cv_filepath):
        try:
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            for fi in file_inputs:
                try:
                    fi.send_keys(os.path.abspath(cv_filepath))
                    print("    [OK] Uploaded resume")
                    time.sleep(1.5)
                    break
                except Exception:
                    pass
        except Exception:
            pass

    # ── 3. Cover letter (deterministic) ───────────────────────────────────────
    cover_letter = state.get("cover_letter", "")
    if cover_letter:
        _fill_any(driver, [
            "textarea[id*='cover-letter' i]",
            "textarea[id*='coverLetter' i]",
            "textarea[name*='cover' i]",
            "textarea[aria-label*='cover letter' i]",
        ], cover_letter)

    # ── 4. LLM screening question answering ───────────────────────────────────
    context = _modal_text(driver)
    all_fields = _modal_fields(driver)
    unfilled = [
        f for f in all_fields
        if f["type"] not in ("file", "hidden", "submit", "button")
        and not f.get("current_value", "").strip()
    ]

    if unfilled:
        llm_answers = _llm_answer_fields(cv, unfilled, context)
        if llm_answers:
            _apply_llm_answers(driver, llm_answers)
            print(f"    [OK] LLM answered {len(llm_answers)} screening field(s)")

    # ── 5. Fallback: radio Yes/No groups ──────────────────────────────────────
    try:
        radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        for radio in radios:
            try:
                rid = radio.get_attribute("id") or ""
                val = (radio.get_attribute("value") or "").lower()
                label_text = ""
                if rid:
                    lbls = driver.find_elements(By.CSS_SELECTOR, f"label[for='{rid}']")
                    if lbls:
                        label_text = lbls[0].text.lower()
                if ("yes" in label_text or val == "yes") and not radio.is_selected():
                    radio.click()
            except Exception:
                pass
    except Exception:
        pass

    time.sleep(0.5)
    return {}


def node_advance(state: LinkedInState) -> dict:
    """Click the Next / Continue button to move to the next modal step."""
    driver = state["driver"]

    next_selectors = [
        "button[aria-label*='Continue to next step' i]",
        "button[aria-label*='next step' i]",
        "button[aria-label='Review your application']",
        "button[data-easy-apply-next-button]",
    ]

    clicked = _click(driver, next_selectors, "Next step", timeout=5)

    if not clicked:
        # Fallback: click the primary button in the modal footer
        try:
            modal_btns = driver.find_elements(
                By.CSS_SELECTOR, ".jobs-easy-apply-modal footer button, div[role='dialog'] footer button"
            )
            for btn in reversed(modal_btns):
                txt = (btn.text or "").strip().lower()
                aria = (btn.get_attribute("aria-label") or "").lower()
                if any(k in txt or k in aria for k in ("next", "continue", "review")):
                    driver.execute_script("arguments[0].click();", btn)
                    print("    [OK] Clicked footer Next button (fallback)")
                    time.sleep(2)
                    clicked = True
                    break
        except Exception:
            pass

    if clicked:
        return {"step_count": state["step_count"] + 1}

    # Could not advance — might already be on review
    return {}


def node_review(state: LinkedInState) -> dict:
    """Reached the LinkedIn Review page — pause for human-in-the-loop."""
    print()
    print("=" * 64)
    print("  [OK]  LINKEDIN APPLICATION FULLY FILLED")
    print("  Review the pre-filled form in the Chrome window.")
    print("  Make any edits you need, then:")
    print("    1. Click 'Submit application' in LinkedIn")
    print("    2. Click 'Submit Done' in the Job Bot dashboard")
    print("=" * 64)
    print()
    return {"result": "review_reached"}


def node_handle_error(state: LinkedInState) -> dict:
    err = state.get("error") or state.get("result") or "unknown error"
    result = state.get("result") or "failed"
    print(f"  [ERR] LinkedIn agent stopped: {err}")
    if result not in ("external", "already_applied"):
        print("  Leaving browser open — you can apply manually.")
    return {"result": result or "failed"}


# ── Routing ───────────────────────────────────────────────────────────────────

def _route_after_check_login(state: LinkedInState) -> str:
    if state.get("result") in ("failed", "external", "already_applied"):
        return "handle_error"
    return "wait_login" if not state.get("login_done") else "click_easy_apply"


def _route_after_wait_login(state: LinkedInState) -> str:
    return "handle_error" if state.get("result") == "failed" else "click_easy_apply"


def _route_after_click_apply(state: LinkedInState) -> str:
    if state.get("result") in ("failed", "external", "already_applied"):
        return "handle_error"
    return "fill_step"


def _route_after_fill(state: LinkedInState) -> str:
    driver = state["driver"]
    if _is_review_page(driver):
        return "review"
    if state["step_count"] >= state["max_steps"]:
        return "handle_error"
    return "advance"


def _route_after_advance(state: LinkedInState) -> str:
    driver = state["driver"]
    if _is_review_page(driver):
        return "review"
    if state["step_count"] >= state["max_steps"]:
        return "handle_error"
    return "fill_step"


# ── Build and compile graph ───────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(LinkedInState)

    g.add_node("open_job", node_open_job)
    g.add_node("check_login", node_check_login)
    g.add_node("wait_login", node_wait_login)
    g.add_node("click_easy_apply", node_click_easy_apply)
    g.add_node("fill_step", node_fill_step)
    g.add_node("advance", node_advance)
    g.add_node("review", node_review)
    g.add_node("handle_error", node_handle_error)

    g.set_entry_point("open_job")
    g.add_edge("open_job", "check_login")

    g.add_conditional_edges("check_login", _route_after_check_login, {
        "wait_login": "wait_login",
        "click_easy_apply": "click_easy_apply",
        "handle_error": "handle_error",
    })
    g.add_conditional_edges("wait_login", _route_after_wait_login, {
        "click_easy_apply": "click_easy_apply",
        "handle_error": "handle_error",
    })
    g.add_conditional_edges("click_easy_apply", _route_after_click_apply, {
        "fill_step": "fill_step",
        "handle_error": "handle_error",
    })
    g.add_conditional_edges("fill_step", _route_after_fill, {
        "advance": "advance",
        "review": "review",
        "handle_error": "handle_error",
    })
    g.add_conditional_edges("advance", _route_after_advance, {
        "fill_step": "fill_step",
        "review": "review",
        "handle_error": "handle_error",
    })

    g.add_edge("review", END)
    g.add_edge("handle_error", END)

    return g.compile()


_graph = _build_graph()


# ── Public API ────────────────────────────────────────────────────────────────

def run_linkedin_agent(
    driver,
    job_url: str,
    cv_data: dict,
    cover_letter: str,
    cv_filepath: str,
) -> str:
    """
    Run the LangGraph LinkedIn Easy Apply agent.

    Returns:
        'review_reached'  — form filled, stopped at Review page for HITL
        'external'        — job uses external apply link (not Easy Apply)
        'already_applied' — already applied to this job
        'failed'          — could not complete (browser left open for manual apply)
    """
    initial: LinkedInState = {
        "driver": driver,
        "job_url": job_url,
        "cv_data": cv_data,
        "cover_letter": cover_letter,
        "cv_filepath": cv_filepath,
        "step_count": 0,
        "max_steps": 15,
        "login_done": False,
        "result": "",
        "error": "",
    }
    final = _graph.invoke(initial)
    return final.get("result", "failed")
