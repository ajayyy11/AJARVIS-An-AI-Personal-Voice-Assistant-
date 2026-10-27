# A.J.A.R.V.I.S. — AI Personal Assistant

![Python CI](https://github.com/ajayyy11/AJARVIS-An-AI-Personal-Voice-Assistant-/actions/workflows/ci.yml/badge.svg)

A local assistant project for Windows built with Flask, Google Gemini integration, MySQL support, and face-authentication components. The application source is located in the `A.JARVIS/` directory.

## Project Highlights

- Flask-based web interface and dashboard
- Gemini-powered command/assistant integration
- Face-authentication workflow using computer-vision libraries
- MySQL database connection layer
- Session management and system-statistics modules

## Tech Stack

Python · Flask · Google GenAI · OpenCV · face-recognition · MySQL

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/ajayyy11/AJARVIS-An-AI-Personal-Voice-Assistant-.git
cd AJARVIS-An-AI-Personal-Voice-Assistant-/A.JARVIS
```

### 2. Create a virtual environment

**Windows:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure the application

Copy `.env.example` to `.env` and fill in the required values for the database, Gemini API, and Flask secret key. Create/configure the MySQL database as described in `database/db.py`.

Never commit `.env`, API keys, database passwords, or real biometric data. Use a unique random secret key and disable debug mode in any deployment.

### 5. Run

```bash
python app.py
```

Follow any application-specific setup instructions in [the application README](A.JARVIS/README.md).

## Security and Privacy

This project handles camera input, face-related data, sessions, and API credentials. Use it only with informed consent, protect credentials, and review access controls before exposing it to a network. Face recognition can make mistakes and should not be treated as infallible identity verification.

## Automated Tests

A GitHub Actions workflow runs the session-management security tests on pushes and pull requests. To run those tests locally from the application directory:

```bash
cd A.JARVIS
python -m pip install Flask python-dotenv pytest
pytest -q tests/test_session_manager.py
```

These tests cover session creation, revocation, expiry, and malformed timestamps. They do not replace full integration testing of the camera, database, or external AI services.

## Repository Layout

```text
A.JARVIS/       Application source, configuration, templates, and dependencies
ProjectDetails/ Supporting project materials
```

## Author

Ajay Shanmuga Sundaram
