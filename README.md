# Chrome Session Manager (RM FB Chrome)

A desktop application built with Python (Flask + PyWebView) to manage multiple isolated Chrome sessions with custom configurations (e.g., iPhone emulation for Facebook).

## Features

- Isolated profiles for each session.
- Mobile device emulation (iPhone).
- Persistent session storage.
- Real-time window status tracking.

## Prerequisites

- **Python 3.11+**
- **Google Chrome / Chromium Binaries**: Required for the local execution.

## Installation

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd RM_FB_chrome
   ```

2. **Create and activate a virtual environment**:

   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Critical Setup: Local Chrome Binaries

Because the Chrome binaries are ignored by Git (see `.gitignore`), each team member must set up the `bin/` folder manually:

1. Create a folder named `bin` in the project root.
2. Go to your local Chrome installation (usually `C:\Program Files\Google\Chrome\Application\`).
3. Copy **all files and subfolders** (including `chrome.exe`, `chrome.dll`, and the versioned folder like `124.0.x.x`) into your project's `bin/` folder.

**Folder Structure should look like this:**

```text
RM_FB_chrome/
├── bin/
│   ├── chrome.exe
│   ├── chrome.dll
│   └── [Version Folder]/
├── core/
├── web/
└── app.py
```

## Running the Application

### Standard Desktop Mode

To run the application as a standalone desktop window:

```bash
python app.py
```

### Development Mode

To run with Flask debug mode enabled (accessible at `http://127.0.0.1:5000`):

```bash
python app.py dev
```

## Project Structure

- `app.py`: Main entry point and Flask routes.
- `core/`: Backend logic (Chrome management, session storage).
- `web/`: Frontend templates (HTML) and static assets (JS/CSS).
- `profiles/`: (Ignored) Stores isolated Chrome user data.
- `data/`: Stores session metadata in `sessions.json`.
- `vpn_configs/`: (Ignored) Stores VPN configurations and credentials.
