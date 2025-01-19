from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from app.models import AnalysisTask
from app.database import get_db
from app.celery import analyze_pull_request
from app.core.logging_config import logger

import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins not recommended for production
    allow_credentials=True,  # Allow cookies and authentication headers
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, etc.)
    allow_headers=["*"],  # Allow all HTTP headers
)

class AnalyzePRRequest(BaseModel):
    pr_url: str

@app.post("/analyze-pr")
async def analyze_pr(request: AnalyzePRRequest, db: Session = Depends(get_db)):
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.search(pattern, request.pr_url)

    if not match:
        raise ValueError("Invalid GitHub PR URL format")

    owner, repo, pr_number = match.groups()

    db_task = AnalysisTask(repo=repo, pr_number=pr_number, status="PENDING")
    db.add(db_task)
    db.commit()
    logger.info(f"Analysis task created for PR: {pr_number}")
    analyze_pull_request.delay(repo, pr_number, owner, db_task.id)
    return {"task_id": db_task.id, "message": "Analysis started"}

@app.get("/status/{task_id}")
async def get_status(task_id: str, db: Session = Depends(get_db)):
    db_task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "status": db_task.status}

@app.get("/results/{task_id}")
async def get_results(task_id: str, db: Session = Depends(get_db)):
    db_task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    if db_task.status != "SUCCESS":
        raise HTTPException(status_code=400, detail="Task is not completed yet")
    return {"task_id": task_id, "results": db_task.result}
