# PR Review Agent

An AI-powered Pull Request review system that automatically analyzes code changes and provides comprehensive feedback on style, bugs, performance, best practices, and security.

## Features

- Automatic PR analysis using LangGraph and LangChain
- Smart token management for large PRs
- Language-aware code analysis
- Asynchronous processing with Celery
- Comprehensive review categories:
  - Code style and formatting
  - Potential bugs and errors
  - Performance improvements
  - Security vulnerabilities
  - Best practices recommendations

- Hosted link :- *http://135.232.104.57:8000*

## System Requirements

- Python >= 3.11
- Redis (for Celery)
- PostgreSQL (for result storage)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/pr-review-agent.git
cd pr-review-agent
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

3. Install Poetry:
```bash
pip install poetry
```

4. Install dependencies:
```bash
poetry install
```

5. Copy environment example and configure:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Configuration

Create a `.env` file with the following configurations:

```env

# Database
DATABASE_URL=postgresql://user:password@localhost/pr_review

# Redis
REDIS_URL=redis://localhost:6379

# OpenAI
OPENAI_API_KEY=your_api_key


```

## Running the Application

1. Start Redis:
```bash
redis-server
```

2. Start Celery worker:
```bash
celery -A app.worker worker --loglevel=info
```

3. Start the FastAPI application:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Documentation

### Endpoints

#### POST /analyze-pr
Initiate a PR review.

Request:
```json
{
    "repo_url": "https://github.com/user/repo",
    "pr_number": 123,
    "github_token": "optional_token"
}
```

Response:
```json
{
    "task_id": "abc123",
    "status": "pending"
}
```

#### GET /status/{task_id}
Check the status of a PR review.

Response:
```json
{
    "task_id": "abc123",
    "status": "processing|completed|failed",
    "progress": 75
}
```

#### GET /results/{task_id}
Get the results of a completed PR review.

Response:
```json
{
    "task_id": "abc123",
    "status": "completed",
    "results": {
        "files": [
            {
                "name": "main.py",
                "issues": [
                    {
                        "type": "style",
                        "line": 15,
                        "description": "Line too long",
                        "suggestion": "Break line into multiple lines"
                    },
                    {
                        "type": "security",
                        "line": 45,
                        "description": "Potential SQL injection vulnerability",
                        "suggestion": "Use parameterized queries"
                    },
                    {
                        "type": "bug",
                        "line": 23,
                        "description": "Potential null pointer",
                        "suggestion": "Add null check"
                    }
                ]
            }
        ],
        "summary": {
            "total_files": 1,
            "total_issues": 3,
            "critical_issues": 1
        }
    }
}
```

## Design Decisions

### Code Organization
```
pr-review-agent/
├── alembic/
├── app/
│   ├── core/
│   │   ├── config.py
│   │   └── logging_config.py
│   ├── celery.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   └── pr_review_agent.py
│ 
├── tests/
├── .env.example
├── poetry.lock
├── pyproject.toml
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
└── README.md
```

### Technology Choices

1. **LangGraph**: For orchestrating the review workflow and managing state transitions.
2. **Celery**: For handling asynchronous processing of PR reviews.
3. **PostgreSQL**: For storing review results and maintaining task history.
4. **Redis**: For Celery message broker and result backend.
5. **FastAPI**: For building a fast, modern API with automatic documentation.
6. **Docker**: For building image and deployment

# PR Analysis Strategy

## Overview
1. Use token counter to measure each file's size and determine if PR fits within model's context window (system prompt + user prompt + PR content)

## Small PRs (fits in context)
* When total tokens are within limit, process entire diff in single prompt with surrounding context lines

## Large PRs (exceeds context)
* Compress by keeping additions and consolidating all deletions into a list
* Sort files by token size within each language (larger files first for each language)
* Fill context up to a safe batch size, mark remaining as "other modified files"
* For other modified file generate small summaries of code and search for bugs
* Include deleted files list if context space remains


## Strategy Benefits
This adaptive token-aware strategy ensures we maximize the model's context window while preserving the most relevant code changes for review. Think of it like packing a suitcase - we fit the largest, most important items first (prioritized by language), then add smaller items if space permits.


![Alt text](pr_review_artitecture.png)

## Future Improvements

1. **Enhanced Analysis**
   - Add support for more programming languages
   - Improve diff management for large PR
   - Add machine learning-based code smell detection

2. **Performance Optimization**
   - Implement caching for similar code patterns
   - Add parallel processing for large PRs
   - Optimize token usage

3. **Integration Features**
   - Add GitHub Actions integration
   - Implement GitLab support
   - Add Bitbucket support

4. **UI Features**
   - Add web dashboard for monitoring
   - Implement real-time progress updates
   - Add custom rule configuration UI

5. **Security Enhancements**
   - Add vulnerability database integration
   - Implement custom security rules
   - Add compliance checking


## Endpoints

### 1. **Analyze PR**

```bash
curl -X POST "http://135.232.104.57:8000/analyze-pr" \
-H "Content-Type: application/json" \
-d '{"repo_url": "https://github.com/owner/repo", "pr_number": 123, "github_token": "your_github_token_here"}'
```

---

### 2. **Get Task Status**

```bash
curl -X GET "http://135.232.104.57:8000/status/{task_id}" \
-H "Content-Type: application/json"
```

---

### 3. **Get Task Results**

```bash
curl -X GET "http://135.232.104.57:8000/results/{task_id}" \
-H "Content-Type: application/json"
```

---

Replace `{task_id}` with the actual task ID returned by the `POST /analyze-pr` command.


## Testing

Run the test suite:
```bash
poetry run pytest
```

Run with coverage:
```bash
poetry run pytest --cov=app tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.