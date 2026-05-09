# Music Distribution Organizer

Windows desktop app for organizing music delivery files, uploading them to Google Drive, checking song-folder completeness, and creating a public sender upload link.

## Intended User Flow

The ideal G-DAM experience is simple:

1. The user goes to the G-DAM website.
2. The user signs in with Google.
3. The user grants Drive, Docs, and Gmail permissions.
4. G-DAM automatically creates this folder in the user's own Google Drive:

```text
My Drive / G-DAM
```

5. The user manages everything inside their own Drive:

- Artists
- Songs
- Uploads
- Collaborators
- Song splits
- Split sheets
- Signature requests
- Signed confirmations

This keeps each user's catalog, files, credits, and signatures inside their own Google account. G-DAM acts as the interface and workflow layer on top of the user's Drive.

The current local development setup runs the backend and frontend on the user's computer. The product direction is a clean hosted website where each user signs in and manages their own `G-DAM` Drive workspace.

## What The App Does

- Parses files named `Artist - Song Name (Tag).ext`
- Organizes local files into `Artist/Song/Tag/`
- Uploads organized files to Google Drive
- Creates missing Google Drive folders as needed
- Uses one app parent folder in Drive: `G-DAM`
- Skips duplicate Drive files instead of re-uploading them
- Tracks required song assets: Clean, Final, Instrumental, Acapella, Lyrics, Artwork
- Accepts optional Session Files without affecting required completion progress
- Builds artist profiles from `Artist/Song/Tag` Drive folders
- Monitors each song drop plus overall artist progress
- Shows a Songs screen with every Drive song folder and its completion status
- Stores global collaborator profiles in Drive as JSON
- Assigns collaborators, roles, and song splits per song
- Generates split sheet Google Docs with contributor and signature sections
- Sends split sheet signature links to collaborators by email
- Receives signed split sheet confirmations back into each song folder
- Stores manager-assigned artist profile images in each artist's Drive folder
- Creates a sender upload portal on HTTP port `3000`
- Starts ngrok automatically and uses this public sender link:
  `https://ferris-yonder-cyclist.ngrok-free.dev`
- Keeps each send link open for 7 days, unless you close it manually
- Collects sender email and optional phone number before accepting uploads
- Notifies the manager app when a sender submits files

## Important

The public sender link only works while your computer is on, the app is open, and ngrok is running. The app keeps the link active for 7 days, but it cannot receive uploads if the computer sleeps, shuts down, loses internet, or the app is closed.

## Requirements

- Windows 10 or newer
- Python 3.8+
- Google Drive account/API credentials
- Internet connection
- ngrok configured with your account token

## Daily Launch

Use this after the one-time setup is complete.

1. Open PowerShell.
2. Run:

```powershell
cd "C:\Users\Head Huncho Guam\Desktop\MUSIC DISTRO PROGRAM"
.\Start-Web-Dashboard.ps1
```

3. Keep the two PowerShell windows open:

- Backend API window: `http://127.0.0.1:8000/docs`
- Frontend dashboard window: `http://127.0.0.1:5173/`

4. Use the web dashboard here:

```text
http://127.0.0.1:5173/
```

Close the backend and frontend PowerShell windows when you are done.

If PowerShell blocks the launch script, run this once, then try the launch command again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Manual Web Launch

Use this only if you want to start the backend and frontend yourself.

Open PowerShell window 1 for the backend:

```powershell
cd "C:\Users\Head Huncho Guam\Desktop\MUSIC DISTRO PROGRAM"
.\Start-Backend.ps1
```

Open PowerShell window 2 for the frontend:

```powershell
cd "C:\Users\Head Huncho Guam\Desktop\MUSIC DISTRO PROGRAM"
.\Start-Frontend.ps1
```

Then open:

```text
http://127.0.0.1:5173/
```

## First-Time Initialization

Run these from the project folder in PowerShell:

```powershell
cd "C:\Users\Head Huncho Guam\Desktop\MUSIC DISTRO PROGRAM"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the virtual environment activation script, run this once for your Windows user, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Then finish the one-time app setup:

1. Put your Google OAuth desktop credentials in this folder as `client_secrets.json`.
2. Configure ngrok with your account token.
3. Start the desktop app with `python music_organizer.py`.
4. Complete the Google sign-in that opens in your browser.

After that first sign-in, the app saves the manager token at:

```text
%LOCALAPPDATA%\Music Distribution Organizer\google_drive_token.pickle
```

For the web dashboard, initialize the frontend after the Python setup:

```powershell
cd frontend
npm install
```

Optional local frontend environment file:

```powershell
Copy-Item .env.example .env
```

The frontend reads `VITE_API_BASE_URL` from `frontend/.env`. If no value is set, local development uses:

```text
http://127.0.0.1:8000
```

Production builds default to:

```text
https://g-dam.onrender.com
```

After `npm install` finishes, launch the dashboard with:

```powershell
cd "C:\Users\Head Huncho Guam\Desktop\MUSIC DISTRO PROGRAM"
.\Start-Web-Dashboard.ps1
```

## Common Launch Problems

If you see `No module named 'backend'`, you started the backend from the wrong folder. Run `.\Start-Backend.ps1` from the project folder, or use:

```powershell
python -m uvicorn backend.main:app --app-dir "C:\Users\Head Huncho Guam\Desktop\MUSIC DISTRO PROGRAM" --host 127.0.0.1 --port 8000
```

If the frontend opens but data does not load, make sure the backend window is also running on:

```text
http://127.0.0.1:8000
```

If a port is already in use, close the old backend/frontend PowerShell window and run `.\Start-Web-Dashboard.ps1` again.

## Install

Install the Python dependencies:

```powershell
pip install -r requirements.txt
```

Optional drag-and-drop support:

```powershell
pip install tkinterdnd2
```

## Google Drive Setup

1. Go to Google Cloud Console.
2. Enable the Google Drive API.
3. Enable the Google Docs API.
4. Enable the Gmail API.
5. Create an OAuth 2.0 Client ID for a desktop app.
6. Download the credentials file.
7. Save it in this app folder as `client_secrets.json`.
8. Run the app once and complete the browser sign-in.

The desktop app opens Google sign-in automatically when no saved manager token exists. This login is for the manager running the app, not for senders using the upload link. Each Windows user gets their own token at:

```text
%LOCALAPPDATA%\Music Distribution Organizer\google_drive_token.pickle
```

Do not ship `token.pickle` or `google_drive_token.pickle` with the app. Those files belong to one signed-in manager Google account. Use the **Reconnect** button if the manager needs to switch Google accounts or create a fresh token.

The app requests Drive access for uploads and library management, Google Docs access for split sheet templates, and Gmail send access for emailing split sheet signature links from the manager's signed-in Google account.

If Gmail sending fails after an update, refresh the cached Google permissions. This app does not use `token.json`; it saves credentials here:

```text
%LOCALAPPDATA%\Music Distribution Organizer\google_drive_token.pickle
```

Use **Reconnect** in the app to delete that saved token and sign in again. The browser consent screen should ask for permission to send email on your behalf. Click **Allow**.

After login, the app creates or reuses this parent folder in the manager's Drive:

```text
My Drive / G-DAM
```

All artist folders, song folders, profile images, credits JSON files, manager uploads, and sender uploads go inside `G-DAM`.

## ngrok Setup

Run this once in PowerShell, replacing `YOUR_TOKEN` with your ngrok authtoken:

```powershell
& "$env:USERPROFILE\Downloads\ngrok-v3-stable-windows-amd64\ngrok.exe" config add-authtoken YOUR_TOKEN
```

Confirm ngrok is configured:

```powershell
& "$env:USERPROFILE\Downloads\ngrok-v3-stable-windows-amd64\ngrok.exe" config check
```

The app looks for `ngrok.exe` on PATH, next to the app, on your Desktop, or in your Downloads/ngrok folder.

## Run The App

```powershell
python music_organizer.py
```

## Run The API Backend

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open the API docs at:

```text
http://127.0.0.1:8000/docs
```

## Run The Web Frontend

In another PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Open the standalone web app at:

```text
http://127.0.0.1:5173/
```

After running `npm run build`, FastAPI can also serve the built dashboard at:

```text
http://127.0.0.1:8000/
```

Current backend endpoints:

- `POST /create-artist`
- `POST /create-song`
- `POST /upload`
- `GET /collaborators`
- `POST /collaborators`
- `GET /songs`
- `GET /artist-profiles`
- `GET /songs/{song_folder_id}/completeness`
- `PATCH /songs/{song_folder_id}/status`
- `POST /songs/{song_folder_id}/generate-split-sheet`
- `POST /songs/{song_folder_id}/send-split-sheet`
- `GET /song-credits/{song_folder_id}`
- `POST /song-credits/{song_folder_id}/collaborators`
- `DELETE /song-credits/{song_folder_id}/collaborators/{collaborator_index}`
- `POST /song-credits/{song_folder_id}/reset-splits`
- `POST /send-links`
- `GET /signature/{token}`
- `POST /signature/{token}`

## Service Layer

Reusable backend logic lives in:

```text
services/
```

The goal is one shared engine with multiple interfaces:

```text
Tkinter desktop UI -> services -> Google Drive / Docs / Gmail
FastAPI web UI    -> services -> Google Drive / Docs / Gmail
```

Current service modules:

- `services/drive_service.py` handles Google auth, Drive folders, metadata, and JSON file helpers.
- `services/song_service.py` handles artist/song folders, uploads, filename parsing, song lists, completeness, and send-link Drive permissions.
- `services/collaborator_service.py` handles collaborator profiles, song credits, split reset logic, and status updates.
- `services/split_sheet_service.py` handles split sheet generation, Gmail signature emails, signature pages, and signed confirmation documents.

## Files Screen

Use this screen when you already have files on your computer.

1. Choose a local destination folder.
2. Confirm the app Drive folder is `G-DAM`.
3. Click **Add Files**.
4. Review the detected song progress and missing tags.
5. Click **Organize + Upload**.

The app copies valid files into your local organized folder, then uploads them to Google Drive.

The required completion tags are:

- Clean
- Final
- Instrumental
- Acapella
- Lyrics
- Artwork

Optional accepted tag:

- Session Files

Session Files are organized and uploaded, but they do not affect the ready-to-upload progress meter or missing required asset list.

## Artist Profiles Screen

Use this screen to monitor artist folders and song-drop progress.

1. Choose the Drive folder that contains your artist folders, or choose one artist folder directly.
2. Select **Artist Profiles** in the sidebar.
3. Click **Refresh Profiles**.

The app expects this Drive shape:

```text
G-DAM / Artist / Song / Clean, Final, Instrumental, Acapella, Lyrics, Artwork
G-DAM / Artist / Song / Session Files
```

Each artist profile shows overall artist progress, total song drops, completed drops, each song's percent complete, and the missing required assets. `Session Files` is optional and does not change completion progress.

Select an artist profile icon to open a popup with that artist's song drops and progress. Use **Assign Image** to choose an image from your computer; the app uploads it to this Drive folder inside the artist folder:

```text
G-DAM / Artist / Profile Image / profile.png
```

The manager assigns these images from the desktop app. Senders do not manage profile images.

Use **Delete Artist** to remove an artist profile and all of that artist's song folders from Drive. Use **Delete Song** to remove one song folder and its tag folders/files.

## Songs Screen

Use this screen to see every song folder in the manager's `G-DAM` Drive library.

1. Select **Songs** in the sidebar.
2. Click **Refresh Songs** if you need to reload the Drive list.
3. Double-click a song to open its **Song Credits** window.

The Songs screen shows:

- Artist
- Song
- Completion progress
- Number of assigned credits
- Total split percentage

The app stores global collaborator and credit data in this Drive folder:

```text
G-DAM / Credits & Collaborators
```

The JSON files are:

```text
collaborator_profiles.json
song_credits.json
signature_requests.json
```

`collaborator_profiles.json` stores reusable collaborator profiles. Each profile can include:

- Name
- Email
- BMI
- ASCAP
- PRO
- Notes

`song_credits.json` stores each song's collaborator assignments by Drive song folder ID.

`signature_requests.json` stores split sheet signature links, email status, and signed document references.

## Collaborators Screen

Use this screen to edit the global collaborator profile library.

1. Select **Collaborators** in the sidebar.
2. Select an existing collaborator profile from the table.
3. Edit the name, email, BMI, ASCAP, PRO, or notes.
4. Click **Save**.

Use **New** to clear the editor and create a new collaborator profile. Use **Refresh** to reload profiles from Drive.

## Song Credits Window

Open this window by double-clicking a song in the Songs screen.

Use **Create Collaborator** to create a global collaborator profile. This opens a separate popup with a **Done** button at the bottom. Saving here adds the profile to `collaborator_profiles.json`.

Use **Add Collaborator** to assign an existing collaborator to the selected song. The Add Collaborator menu includes grouped roles:

- Ownership: Songwriter, Composer, Topliner
- Production: Producer, Co-Producer, Additional Producer
- Engineering: Recording Engineer, Mix Engineer, Mastering Engineer
- Performance: Primary Artist, Featured Artist
- Business: Publisher

Use **Remove Collaborator** to remove the selected collaborator credit from the current song. After removal, the app resets the remaining split percentages using the default role pools.

Every collaborator role can have a song split. Split rules:

- Multiple primary/featured artists default to sharing a 50% artist pool.
- Producers and engineers default to sharing a 50% production/engineering pool.
- Splits can always be changed per song.
- The app blocks a save if the song's total splits would go above 100%.
- If the song total is below 100%, the app warns you so you can keep adjusting until the total equals 100%.

Use **Generate Split Sheet** after the song's split total equals 100%. The app creates a Google Docs split sheet in the selected song's Drive folder without emailing collaborators.

Use **View Split Sheet** to open the newest split sheet Google Doc found in the selected song's Drive folder.

If you have a Google Doc template inside `G-DAM`, title it with words like `split template` or `signature template`. The app copies that template and replaces these placeholders:

```text
{{ARTIST}}
{{SONG}}
{{CONTRIBUTORS}}
{{SIGNATURES}}
```

Place `{{SIGNATURES}}` under your contributors/signatures section in the template. If no template is found, the app generates a basic split sheet document.

The generated split sheet includes:

- Song title and artist
- Contributor table with name, role, and split
- Signature section with one signature line per unique collaborator
- Date line for each signature

If a collaborator appears more than once on the same song, the signature section only creates one signature line for that name.

Use **Send Split Sheet** after a split sheet has already been generated. The app finds the selected song's split sheet and emails signature links to collaborators. After sending, the app:

- Creates or reuses `Signed Split Sheets` inside the song folder
- Creates a signature request for each unique collaborator
- Sends each collaborator an email from the manager's signed-in Google account when their collaborator profile has an email address
- Includes both the Google Doc link and a signature portal link in the email
- Uses the same local/ngrok sender portal to receive signature submissions
- Saves each submitted signature confirmation as a Google Doc inside `Signed Split Sheets`

If a collaborator has no email address, the request is created but the email is skipped.

## Send Link Screen

Use this screen when someone else needs to send files to your active song folder.

1. Enter the artist name.
2. Choose an existing song from the dropdown, or type a new song name.
3. Click **Create Send Link**.
4. Send this public link to the sender:
   `https://ferris-yonder-cyclist.ngrok-free.dev`
5. Keep your computer awake, the app open, and internet connected.
6. Click **Close Send Link** when you are done, or let it expire after 7 days.

The app runs the upload portal at:

```text
http://127.0.0.1:3000/
```

ngrok forwards the public sender link to that local portal.

Before uploading, the sender must enter:

- Email
- Phone, optional

The sender portal also includes **Create Collaborator Profile**. Senders can enter their name, email, BMI, ASCAP, PRO, and notes, and the app saves that information to the manager's global collaborator profile library in:

```text
G-DAM / Credits & Collaborators / collaborator_profiles.json
```

Before the sender uploads, the portal shows:

- What required assets are already submitted
- What required assets are still missing
- Whether optional Session Files are present or selected
- Which selected files have wrong names or wrong artist/song/tag values

Wrong filenames are blocked until they are fixed.

Senders do not log in to Google Drive. Uploaded files go through the manager's already-authenticated desktop app.

When a sender submits files, the manager app logs the sender email/phone and shows a **Sender Upload Received** notification with the sender info and uploaded filenames.

## Sender File Naming

Senders should upload files using this format:

```text
Artist - Song Name (Tag).ext
```

Examples:

```text
Guam - My Song (Final).wav
Guam - My Song (Clean).wav
Guam - My Song (Instrumental).wav
Guam - My Song (Acapella).wav
Guam - My Song (Lyrics).txt
Guam - My Song (Artwork).jpg
Guam - My Song (Session Files).zip
```

## Tag Mapping

- `Clean` goes to the Clean folder
- `Final` goes to the Final folder
- `Instrumental` goes to the Instrumental folder
- `Acapella` goes to the Acapella folder
- `Lyrics` goes to the Lyrics folder
- `Cover` or `Artwork` goes to the Artwork folder
- `Session`, `Sessions`, `Session File`, or `Session Files` goes to the Session Files folder and is optional
- Any other tag goes to the Other folder for local/manager organization. Sender upload links only accept required tags and optional Session Files.

## Troubleshooting

If the public sender link does not open, make sure the app is open and ngrok is configured.

If port `3000` is already in use, close the other app using that port and create the send link again.

If Google Drive upload fails, confirm the app is authenticated and `client_secrets.json` is bundled with the app or next to the executable.

If split sheet documents generate but signature emails show `Signature emails sent: 0`, confirm the Gmail API is enabled in Google Cloud, then use **Reconnect** in the app to refresh the saved token with the Gmail send permission. The saved token path is:

```text
%LOCALAPPDATA%\Music Distribution Organizer\google_drive_token.pickle
```

If a file is skipped, check that its filename matches `Artist - Song Name (Tag).ext`.
