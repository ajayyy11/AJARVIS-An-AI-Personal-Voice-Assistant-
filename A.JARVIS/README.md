# A.JARVIS

A.JARVIS is an advanced, local AI System tailored to operate as a central assistant on Windows, utilizing the Google Generative AI (Gemini 2.5 Flash), built on Flask with Biometric authentication (Face Recognition).

## Project Structure

```text
A.JARVIS/
├── .env                # Environment keys (DO NOT COMMIT)
├── .env.example        # Template for fresh installations
├── .gitignore          # Excludes __pycache__, .env, and local artifacts
├── app.py              # Main Flask router and application launch point
├── config.py           # Configuration object builder mapped to .env
├── notes.txt           # Artifact file: Local notes saved by Jarvis via voice
├── requirements.txt    # Python module dependencies for pip installation
├── run_hidden.vbs      # VBScript to launch JARVIS in the background
├── start_jarvis.bat    # Application bootstrapper batch file
├── README.md           # This file
|
├── database/
│   └── db.py                 # MySQL Setup & connection wrappers
|
├── intelligence/
│   ├── command_router.py     # NLP logic, hardcoded triggers & Gemini API Hub
│   └── memory.py             # Memory persistence logic for AI context
|
├── scripts/
│   └── test_camera.py        # Development utilities and hardware tests
|
├── security/
│   ├── camera.py             # Handlers for OpenCV video streaming
│   ├── face_auth.py          # Biometric logic utilizing face_recognition
│   └── session_manager.py    # Login/logout authentication states
|
├── system/
│   └── stats.py              # Harware monitoring module (CPU/RAM wrapper)
|
├── static/                   # Static web assets (CSS/JS/Images if decoupled)
└── templates/
    ├── dashboard.html        # Primary authenticated control hub UI
    ├── home.html             # Landing page
    ├── index.html            # Core routing template
    ├── login.html            # Session login interface
    └── register.html         # On-boarding Interface & Facial capture
```

## Quick Start
1. Create your database outlined in `database/db.py`.
2. Apply your configuration into `.env`.
3. Install dependencies: `pip install -r requirements.txt`.
4. Boot the system: `python app.py` or double-click `start_jarvis.bat`.
