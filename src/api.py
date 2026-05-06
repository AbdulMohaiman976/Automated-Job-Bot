import sys
import os
import json
from glob import glob
from contextlib import redirect_stdout, redirect_stderr
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from datetime import datetime
import shutil

# Add the project root to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(BASE_DIR)

from src.workflow.discover import run_discovery
from src.utils.cv_processor import process_cv
from src.workflow.optimize import tailor_cv, generate_cover_letter
from src.workflow.apply import signal_review_complete
from src.storage.tracker import (
    get_tracker_summary, 
    save_parsed_profile, 
    save_tailored_application,
    get_dashboard_stats,
    JobStatus,
    UPLOADS_DIR, 
    PROFILES_DIR,
    APPLICATIONS_DIR,
    DATA_DIR
)

app = FastAPI(title="Job-Bot API")

# Simple state to track background processes
discovery_status = {"running": False, "last_run": None, "error": None, "last_message": None}
application_status = {"running": False, "current_job": None, "error": None}
DISCOVERY_LOG_FILE = os.path.join(BASE_DIR, "scratch", "discover.log")


class _TeeWriter:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


def _append_discovery_log(message: str):
    os.makedirs(os.path.dirname(DISCOVERY_LOG_FILE), exist_ok=True)
    with open(DISCOVERY_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message.rstrip("\n") + "\n")


def _reset_discovery_log():
    os.makedirs(os.path.dirname(DISCOVERY_LOG_FILE), exist_ok=True)
    with open(DISCOVERY_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

frontend_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if origin.strip()
]

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_latest_jobs_file(mode="unique"):
    suffix = "-all" if mode == "all" else "-unique"
    files = glob(os.path.join(DATA_DIR, f"jobs{suffix}-*.json"))
    
    if not files:
        files = glob(os.path.join(DATA_DIR, "jobs-*.json"))
        
    if not files:
        return None
    files.sort(reverse=True)
    return files[0]

@app.get("/jobs")
async def get_jobs(mode: str = "unique"):
    latest_file = get_latest_jobs_file(mode)
    if not latest_file:
        return []
    
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            jobs = json.load(f)
            
        # Merge with tracker status
        tracker = get_tracker_summary()
        status_map = {a["job_id"]: a["status"] for a in tracker.get("applications", [])}
        
        for job in jobs:
            jid = str(job.get('id') or job.get('job_id'))
            job["status"] = status_map.get(jid, JobStatus.DISCOVERED)
            
        return jobs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_stats():
    return get_dashboard_stats()

@app.get("/summary")
async def get_summary():
    files = glob(os.path.join(DATA_DIR, "summary-*.json"))
    if not files:
        return {}
    files.sort(reverse=True)
    try:
        with open(files[0], "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def get_health():
    return {
        "ok": True,
        "discovery_running": discovery_status["running"],
        "application_running": application_status["running"],
    }

def run_discovery_task():
    discovery_status["running"] = True
    discovery_status["error"] = None
    discovery_status["last_message"] = "Starting discovery"
    _reset_discovery_log()
    try:
        with open(DISCOVERY_LOG_FILE, "a", encoding="utf-8") as log_file:
            tee = _TeeWriter(sys.stdout, log_file)
            with redirect_stdout(tee), redirect_stderr(tee):
                print(f"[{datetime.now().isoformat()}] Discovery task started")
                run_discovery()
        discovery_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        discovery_status["last_message"] = "Discovery complete"
    except Exception as e:
        discovery_status["error"] = str(e)
        discovery_status["last_message"] = f"Discovery failed: {e}"
        _append_discovery_log(f"[ERROR {datetime.utcnow().isoformat()}] {e}")
    finally:
        discovery_status["running"] = False

@app.post("/discover")
async def start_discovery(background_tasks: BackgroundTasks):
    if discovery_status["running"]:
        return {"message": "Discovery is already in progress"}

    background_tasks.add_task(run_discovery_task)
    return {"message": "Discovery started in background"}

@app.get("/discover/status")
async def get_discovery_status():
    return discovery_status


@app.get("/discover/logs")
async def get_discovery_logs(limit: int = 25):
    if not os.path.exists(DISCOVERY_LOG_FILE):
        return {"lines": []}

    with open(DISCOVERY_LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    return {"lines": lines[-max(1, min(limit, 200)) :]}

@app.post("/cv/upload")
async def upload_cv(file: UploadFile = File(...)):
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    file_path = os.path.join(UPLOADS_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        profile = process_cv(file_path)
        if not profile:
            raise ValueError("LLM failed to extract structured data from CV")
            
        save_parsed_profile(profile)
        return {"message": "CV processed successfully", "profile": profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cv/file")
async def get_cv_file():
    files = glob(os.path.join(UPLOADS_DIR, "*"))
    if not files:
        raise HTTPException(status_code=404, detail="No CV uploaded")
    files.sort(key=os.path.getmtime, reverse=True)
    from fastapi.responses import FileResponse
    return FileResponse(files[0])

@app.get("/cv/profile")
async def get_cv_profile():
    profile_path = os.path.join(PROFILES_DIR, "parsed_profile.json")
    if not os.path.exists(profile_path):
        return {}
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/jobs/tailored/{job_id}")
async def get_tailored_details(job_id: str):
    job_dir = os.path.join(APPLICATIONS_DIR, job_id)
    filename = os.path.join(job_dir, "tailored_cv.json")
    if not os.path.exists(filename):
        raise HTTPException(status_code=404, detail="No tailoring found for this job")
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

@app.post("/jobs/tailor/{job_id}")
async def tailor_job(job_id: str):
    # Find job in latest file
    latest_file = get_latest_jobs_file()
    if not latest_file:
        raise HTTPException(status_code=404, detail="No jobs discovered yet")
        
    with open(latest_file, "r", encoding="utf-8") as f:
        jobs = json.load(f)
        
    job = next((j for j in jobs if str(j.get('id') or j.get('job_id')) == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Get profile
    profile = await get_cv_profile()
    if not profile:
        raise HTTPException(status_code=400, detail="CV not processed yet")
        
    try:
        t_cv = tailor_cv(profile, job.get('description', ''))
        t_cl = generate_cover_letter(profile, job.get('description', ''))
        save_tailored_application(job_id, {"cv": t_cv, "cover_letter": t_cl})
        return {"message": "Job tailored successfully", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/apply/status")
async def get_apply_status():
    return application_status

@app.post("/apply/review/complete")
async def review_complete():
    signal_review_complete()
    return {"message": "Review signal sent"}

@app.post("/apply/skip")
async def apply_skip():
    from src.workflow.apply import signal_skip
    signal_skip()
    return {"message": "Skip signal sent"}

@app.get("/apply/tracker")
async def get_apply_tracker():
    return get_tracker_summary()


async def run_apply_task(selected_jobs, profile):
    application_status["running"] = True
    application_status["total"] = len(selected_jobs)
    application_status["current_idx"] = 0
    application_status["error"] = None
    
    try:
        from src.workflow.apply import SequentialApplier
        from src.workflow.optimize import tailor_cv, generate_cover_letter
        
        applier = SequentialApplier(profile, tailor_cv, generate_cover_letter)
        try:
            for i, job in enumerate(selected_jobs):
                application_status["current_idx"] = i + 1
                application_status["current_job"] = {
                    "title": job.get('job_title'),
                    "company": job.get('company')
                }
                await applier.apply_to_job(job)
        finally:
            await applier.close()
    except Exception as e:
        application_status["error"] = str(e)
    finally:
        application_status["running"] = False
        application_status["current_job"] = None

async def start_applications_impl(job_ids: List[str], background_tasks: BackgroundTasks):
    if application_status["running"]:
        return {"message": "Applications are already in progress"}

    latest_file = get_latest_jobs_file()
    if not latest_file:
        raise HTTPException(status_code=404, detail="No jobs found")

    with open(latest_file, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    selected_jobs = [j for j in jobs if (str(j.get('id') or j.get('job_id')) in job_ids)]

    if not selected_jobs:
        raise HTTPException(status_code=404, detail="No valid jobs selected")

    profile = await get_cv_profile()
    if not profile:
        raise HTTPException(status_code=400, detail="CV not processed yet")

    background_tasks.add_task(run_apply_task, selected_jobs, profile)
    return {"message": f"Sequential application for {len(selected_jobs)} jobs started."}


@app.post("/apply/start")
@app.post("/apply/bulk")
async def start_applications(job_ids: List[str], background_tasks: BackgroundTasks):
    return await start_applications_impl(job_ids, background_tasks)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
