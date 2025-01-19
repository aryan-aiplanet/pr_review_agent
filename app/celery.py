from celery import Celery
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import AnalysisTask
from app.pr_review_agent import generate_pr_review
import json
from app.core.config import settings
from app.core.logging_config import logger
import traceback
from typing import Optional

import re


redis_url = settings.REDIS_URL

# SSL options for rediss:// URLs
ssl_options = {
    "ssl_cert_reqs": "CERT_NONE"  # Change this to "CERT_REQUIRED" or "CERT_OPTIONAL" for stricter security
} if redis_url.startswith("rediss://") else None

celery_app = Celery("tasks", broker=redis_url, backend=redis_url, broker_transport_options={"ssl": ssl_options} if ssl_options else {})

import requests

def get_pr_details(repo: str, pr_number: int, owner:str, github_token: Optional[str] = None):
    """
    Fetch the details of a GitHub Pull Request, including file changes, status, and patches.

    Args:
        pr_url (str): URL of the GitHub Pull Request.
        github_token (str): GitHub personal access token for authentication.

    Returns:
        dict: A dictionary containing file details, including changes, statuses, and patches.
    """


    # Construct the API URL
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"

    # Headers for the API request
    if github_token:
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
    else:
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }


    # Make the API request
    response = requests.get(api_url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch PR details: {response.status_code} - {response.text}")

    # Process the response JSON
    files = response.json()
    return files

@celery_app.task
def analyze_pull_request(repo: str, pr_number: int, owner:str, task_id: int, github_token: Optional[str] = None):
    """
    Simulate analysis of a GitHub PR with database updates.
    """
    db: Session = SessionLocal()
    db_task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
    if db_task:
        db_task.status = "IN_PROGRESS"
        db.commit()
    
    try:
        logger.info("Fetching PR details...")
        diff = get_pr_details(repo, pr_number, owner,github_token)

        logger.info("Generating review of the Pull Request")
        review = generate_pr_review(diff)
        review = json.loads(review)
            # Update task result and status in the database
        logger.info("Updating status SUCCESS in DB")
        if db_task:
            db_task.status = "SUCCESS"
            db_task.result = review
            db.commit()
            db.close()

        return review
    except Exception as e:
        if db_task:
            db_task.status = "FAILED"
            db_task.result = str(e)
            db.commit()
            db.close()
        logger.error(f"Error occurred: {str(e)}\n{traceback.format_exc()}")
        return traceback.format_exc()


  
