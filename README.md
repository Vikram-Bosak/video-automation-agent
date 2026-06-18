# 🎬 Video Automation Agent

> Google Sheet → AI Video Website → Google Drive | Automated Pipeline

[![GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-blue)](https://github.com)
[![Python](https://img.shields.io/badge/Python-3.11-green)](https://python.org)
[![Playwright](https://img.shields.io/badge/Browser-Playwright-orange)](https://playwright.dev)

---

## क्या करता है?

हर **2 घंटे** में automatically:

```
Google Sheet (pending row)
    ↓ Title + 3 Prompts पढ़ो
AI Video Website
    ↓ 3 Videos generate करो
    ↓ Download करो
    ↓ Title के अनुसार rename करो
Google Drive
    ↓ Upload करो
Google Sheet
    ↓ "done" mark करो
```

**24 घंटे में 12 videos automatically तैयार!**

---

## Architecture

```
video-automation-agent/
├── agents/
│   ├── browser_agent.py   # Playwright automation (Kling/Runway/Custom)
│   ├── sheet_reader.py    # Google Sheets API
│   ├── drive_uploader.py  # Google Drive API
│   └── state_manager.py   # Progress tracking
├── config/
│   └── settings.py        # Environment variables
├── .github/workflows/
│   └── automation.yml     # Cron: हर 2 घंटे
├── main.py                # Orchestrator
└── requirements.txt
```

---

## Quick Start

```bash
# 1. Clone करो
git clone https://github.com/YOUR_USERNAME/video-automation-agent.git
cd video-automation-agent

# 2. Install करो
pip install -r requirements.txt
playwright install chromium --with-deps

# 3. .env बनाओ
cp .env.example .env
# .env में values fill करो

# 4. Run करो
python main.py
```

**Full setup के लिए:** [SETUP_GUIDE.md](SETUP_GUIDE.md)

---

## Google Sheet Format

| A: Title | B: Prompt 1 | C: Prompt 2 | D: Prompt 3 | E: Status | F: Drive Links |
|---|---|---|---|---|---|
| Video_001 | Opening scene... | Close up... | Final shot... | pending | |

---

## Supported Websites

| Website | Status |
|---|---|
| Kling AI (klingai.com) | ✅ Built-in |
| Runway ML (runwayml.com) | ✅ Built-in |
| Any website | ✅ Custom Agent |

---

## GitHub Secrets Required

| Secret | Description |
|---|---|
| `GOOGLE_CREDENTIALS` | Service Account JSON (base64) |
| `SHEET_ID` | Google Sheet ID |
| `DRIVE_FOLDER_ID` | Google Drive Folder ID |
| `WEBSITE_URL` | Video generation website URL |
| `WEBSITE_EMAIL` | Login email |
| `WEBSITE_PASSWORD` | Login password |
