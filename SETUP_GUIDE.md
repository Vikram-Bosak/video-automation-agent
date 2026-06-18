# 🎬 Video Automation Agent — Setup Guide

यह guide आपको step-by-step project setup करने में help करेगी।

---

## STEP 1: Google Cloud Project Setup

### 1.1 — Google Cloud Console खोलो
👉 https://console.cloud.google.com

### 1.2 — नया Project बनाओ
- "New Project" → Name: `video-automation`
- Create पर click करो

### 1.3 — APIs Enable करो
"APIs & Services" → "Enable APIs" → इन दोनों को enable करो:
- ✅ **Google Sheets API**
- ✅ **Google Drive API**

### 1.4 — Service Account बनाओ
1. "APIs & Services" → "Credentials"
2. "Create Credentials" → "Service Account"
3. Name: `video-agent`
4. Role: **Editor** (या minimum: Sheets Editor + Drive Editor)
5. "Done" click करो

### 1.5 — JSON Key Download करो
1. Service Account पर click करो
2. "Keys" tab → "Add Key" → "Create New Key"
3. **JSON** select करो → Download होगी
4. File save करो: `service_account.json`

---

## STEP 2: Google Sheet Setup

### 2.1 — Sheet Structure बनाओ

Column layout (exactly इस order में):
```
| A: Title      | B: Prompt 1    | C: Prompt 2    | D: Prompt 3    | E: Status | F: Drive Links |
```

**Row 1 = Header** (इसे skip किया जाएगा)
```
Title | Prompt 1 | Prompt 2 | Prompt 3 | Status | Drive Links
```

**Row 2 onwards = Data**
```
My_Video_001 | Opening scene of... | Close up of... | Aerial shot of... | pending |
My_Video_002 | A person walking... | Camera zooms... | Final scene...   | pending |
```

### 2.2 — Service Account को Access दो
1. Sheet open करो → "Share" button
2. Service Account email paste करो: `video-agent@video-automation.iam.gserviceaccount.com`
3. Role: **Editor**
4. Share

### 2.3 — Sheet ID निकालो
URL से: `https://docs.google.com/spreadsheets/d/**[SHEET_ID]**/edit`

---

## STEP 3: Google Drive Setup

### 3.1 — Folder बनाओ
Google Drive में नया folder बनाओ: `Generated Videos`

### 3.2 — Service Account को Access दो
1. Folder पर right-click → "Share"
2. Service Account email → Role: **Editor**

### 3.3 — Folder ID निकालो
URL से: `https://drive.google.com/drive/folders/**[FOLDER_ID]**`

---

## STEP 4: Credentials को Base64 Encode करो

```bash
# Linux/Mac:
base64 -w 0 service_account.json

# Output को copy करो — GitHub Secret में use होगा
```

---

## STEP 5: GitHub Repository Setup

### 5.1 — New Repository बनाओ
GitHub पर: New Repository → `video-automation-agent`

### 5.2 — Code Push करो
```bash
cd video-automation-agent
git init
git add .
git commit -m "Initial: Video Automation Agent"
git remote add origin https://github.com/YOUR_USERNAME/video-automation-agent.git
git push -u origin main
```

### 5.3 — GitHub Secrets Add करो
Repository → Settings → Secrets → Actions → "New repository secret"

| Secret Name | Value |
|---|---|
| `GOOGLE_CREDENTIALS` | Step 4 का base64 output |
| `SHEET_ID` | Step 2.3 का Sheet ID |
| `SHEET_NAME` | `Sheet1` (या आपकी tab name) |
| `DRIVE_FOLDER_ID` | Step 3.3 का Folder ID |
| `WEBSITE_URL` | जैसे `https://klingai.com` |
| `WEBSITE_EMAIL` | Video site का login email |
| `WEBSITE_PASSWORD` | Video site का login password |

---

## STEP 6: Website-Specific Configuration

`agents/browser_agent.py` में अपनी website के selectors check करो:

```python
# अपनी website inspect करो (F12 → Inspect Element)
SEL_PROMPT_INPUT   = 'textarea#prompt'   # Prompt text area
SEL_GENERATE_BTN   = 'button#generate'  # Generate button
SEL_VIDEO_READY    = 'video.result'     # Generated video
SEL_DOWNLOAD_BTN   = 'a#download'       # Download link
```

---

## STEP 7: Local Testing

```bash
# Virtual environment बनाओ
python -m venv venv
source venv/bin/activate  # Linux/Mac

# Dependencies install
pip install -r requirements.txt
playwright install chromium --with-deps

# .env file बनाओ
cp .env.example .env
# .env में values fill करो

# Test run (BROWSER_HEADLESS=false में - आप देख सकते हो)
python main.py
```

---

## STEP 8: GitHub Actions Enable करो

1. Repository → "Actions" tab
2. Workflow दिखेगा: "Video Automation Pipeline"
3. "Run workflow" → Manual test करो
4. Cron automatically हर 2 घंटे में चलेगा

---

## Schedule (IST Reference)

| IST Time | UTC Time | Cron |
|---|---|---|
| 06:00 AM | 00:30 | ✅ Run |
| 08:00 AM | 02:30 | ✅ Run |
| 10:00 AM | 04:30 | ✅ Run |
| 12:00 PM | 06:30 | ✅ Run |
| 02:00 PM | 08:30 | ✅ Run |
| 04:00 PM | 10:30 | ✅ Run |
| 06:00 PM | 12:30 | ✅ Run |
| 08:00 PM | 14:30 | ✅ Run |
| 10:00 PM | 16:30 | ✅ Run |
| 12:00 AM | 18:30 | ✅ Run |
| 02:00 AM | 20:30 | ✅ Run |
| 04:00 AM | 22:30 | ✅ Run |

**24 घंटे में 12 runs = 12 videos 🎬**

---

## Troubleshooting

### Login नहीं हो रहा?
```python
# browser_agent.py में BROWSER_HEADLESS = False करो
# देखो क्या हो रहा है
# Screenshots देखो: logs/*.png
```

### Sheet नहीं पढ़ रहा?
- Service account को Editor access मिली है?
- SHEET_ID सही है?
- Row 1 header है?

### Drive upload fail?
- Service account को folder access मिली है?
- DRIVE_FOLDER_ID सही है?

### Video generate timeout?
- `VIDEO_GEN_TIMEOUT_SEC` बढ़ाओ (default: 600 = 10 min)
- Website के selectors verify करो
