import os
import tempfile
from typing import Optional

from starlette.background import BackgroundTask
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services.collaborator_service import (
    add_song_credit_collaborator,
    get_song_credit_record,
    load_collaborators,
    remove_song_credit_collaborator,
    reset_song_credit_splits,
    save_collaborator_profile,
    update_song_status,
)
from services.song_service import (
    create_artist_folder,
    create_send_link,
    create_song_folder,
    delete_artist_profile,
    get_artist_profile_image_file,
    get_song_completeness,
    list_artist_profiles,
    list_songs,
    rename_artist_profile,
    upload_artist_profile_image,
    upload_file_to_drive,
)
from services.split_sheet_service import (
    build_signature_page,
    generate_split_sheet_for_song,
    save_signature_submission_for_token,
    send_split_sheet_for_song,
)
from services.status_service import calculate_song_release_status


app = FastAPI(title="Music Distribution Organizer API")

DEFAULT_CORS_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIST_DIR = os.path.join("frontend", "dist")
FRONTEND_DIST_ASSETS_DIR = os.path.join(FRONTEND_DIST_DIR, "assets")
FRONTEND_STATIC_DIR = os.path.join("frontend", "static")

if os.path.isdir(FRONTEND_DIST_ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_ASSETS_DIR), name="assets")

if os.path.isdir(FRONTEND_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_STATIC_DIR), name="static")


@app.get("/")
def health_check():
    dist_index = os.path.join(FRONTEND_DIST_DIR, "index.html")
    if os.path.exists(dist_index):
        return FileResponse(dist_index)
    return FileResponse("frontend/index.html")


@app.get("/legacy-control-panel", response_class=HTMLResponse)
def legacy_control_panel():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Music Distribution Organizer API</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, sans-serif; background: #15110d; color: #f6ead8; }
    header { padding: 20px 24px; border-bottom: 1px solid #4b2a11; background: #100b07; }
    h1 { margin: 0 0 6px; font-size: 26px; }
    h2 { margin: 0 0 12px; color: #ffad42; font-size: 17px; }
    p { margin: 0; color: #d8c7b4; }
    main { padding: 22px; display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; }
    section { border: 1px solid #5a3518; background: #1d140d; padding: 16px; }
    label { display: block; margin: 10px 0 4px; color: #c9ad8f; font-size: 12px; font-weight: 700; text-transform: uppercase; }
    input, textarea { width: 100%; padding: 10px; border: 1px solid #5a3518; background: #2b2118; color: #f6ead8; font: inherit; }
    textarea { min-height: 72px; resize: vertical; }
    button, a.button { display: inline-block; margin-top: 12px; padding: 10px 13px; border: 0; background: #ff9f2e; color: #120c07; font-weight: 700; text-decoration: none; cursor: pointer; }
    a.button { background: #2b2118; color: #f6ead8; border: 1px solid #5a3518; margin-left: 8px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .full { grid-column: 1 / -1; }
    #output { margin: 0; padding: 14px; background: #0e0b08; border: 1px solid #4b2a11; color: #d7ffd7; }
    .muted { color: #c9ad8f; font-size: 13px; margin-top: 6px; }
  </style>
</head>
<body>
  <header>
    <h1>Music Distribution Organizer API</h1>
    <p>Local backend controls for the endpoints currently exposed. <a class="button" href="/docs">Open Swagger Docs</a></p>
  </header>
  <main>
    <section>
      <h2>Create Artist</h2>
      <label for="artist-name">Artist Name</label>
      <input id="artist-name" placeholder="GUAM">
      <button onclick="createArtist()">Create Artist</button>
    </section>

    <section>
      <h2>Create Song</h2>
      <div class="row">
        <div>
          <label for="song-artist">Artist Name</label>
          <input id="song-artist" placeholder="GUAM">
        </div>
        <div>
          <label for="song-name">Song Name</label>
          <input id="song-name" placeholder="FOR MY EGO">
        </div>
      </div>
      <button onclick="createSong()">Create Song</button>
    </section>

    <section>
      <h2>Upload File</h2>
      <div class="row">
        <div>
          <label for="upload-artist">Artist Name</label>
          <input id="upload-artist" placeholder="Optional if filename is formatted">
        </div>
        <div>
          <label for="upload-song">Song Name</label>
          <input id="upload-song" placeholder="Optional if filename is formatted">
        </div>
      </div>
      <label for="upload-file">File</label>
      <input id="upload-file" type="file">
      <p class="muted">Filename format can be: Artist - Song Name (Final).wav</p>
      <button onclick="uploadFile()">Upload</button>
    </section>

    <section>
      <h2>Collaborators</h2>
      <button onclick="getCollaborators()">Load Collaborators</button>
      <label for="collab-id">Profile ID</label>
      <input id="collab-id" placeholder="Optional for update">
      <label for="collab-name">Name</label>
      <input id="collab-name" placeholder="Collaborator name">
      <label for="collab-email">Email</label>
      <input id="collab-email" type="email">
      <div class="row">
        <div>
          <label for="collab-bmi">BMI</label>
          <input id="collab-bmi">
        </div>
        <div>
          <label for="collab-ascap">ASCAP</label>
          <input id="collab-ascap">
        </div>
      </div>
      <label for="collab-pro">PRO</label>
      <input id="collab-pro">
      <label for="collab-notes">Notes</label>
      <textarea id="collab-notes"></textarea>
      <button onclick="saveCollaborator()">Save Collaborator</button>
    </section>

    <section>
      <h2>Songs & Artist Profiles</h2>
      <button onclick="getSongs()">Load Songs</button>
      <button onclick="getArtistProfiles()">Load Artist Profiles</button>
    </section>

    <section>
      <h2>Song Credits</h2>
      <label for="credit-song-id">Song Folder ID</label>
      <input id="credit-song-id" placeholder="Google Drive song folder ID">
      <button onclick="getSongCredits()">Load Song Credits</button>
      <div class="row">
        <div>
          <label for="credit-profile-id">Profile ID</label>
          <input id="credit-profile-id">
        </div>
        <div>
          <label for="credit-role">Role</label>
          <input id="credit-role" placeholder="Producer">
        </div>
      </div>
      <div class="row">
        <div>
          <label for="credit-split">Split</label>
          <input id="credit-split" type="number" step="0.01" placeholder="Optional">
        </div>
        <div>
          <label for="credit-text">Credit</label>
          <input id="credit-text">
        </div>
      </div>
      <button onclick="addSongCredit()">Add Credit</button>
      <label for="remove-index">Remove Collaborator Index</label>
      <input id="remove-index" type="number" min="0" placeholder="0">
      <button onclick="removeSongCredit()">Remove Credit</button>
      <button onclick="resetSplits()">Reset Splits</button>
    </section>

    <section>
      <h2>Song Tools</h2>
      <label for="song-tools-id">Song Folder ID</label>
      <input id="song-tools-id" placeholder="Google Drive song folder ID">
      <button onclick="getCompleteness()">Get Completeness</button>
      <label for="song-status">Status</label>
      <input id="song-status" placeholder="Ready, Needs assets, Sent, etc.">
      <button onclick="updateStatus()">Update Status</button>
      <button onclick="generateSplitSheet()">Generate Split Sheet</button>
      <button onclick="sendSplitSheet()">Send Split Sheet Emails</button>
    </section>

    <section>
      <h2>Send Link</h2>
      <div class="row">
        <div>
          <label for="send-link-artist">Artist Name</label>
          <input id="send-link-artist" placeholder="GUAM">
        </div>
        <div>
          <label for="send-link-song">Song Name</label>
          <input id="send-link-song" placeholder="FOR MY EGO">
        </div>
      </div>
      <button onclick="createSendLink()">Create Send Link</button>
      <p class="muted">Creates or reuses the Drive song folder and gives anyone writer permission.</p>
    </section>

    <section class="full">
      <h2>Response</h2>
      <div id="output">Ready.</div>
    </section>
  </main>
  <script>
    const out = document.getElementById('output');
    function value(id) { return document.getElementById(id).value.trim(); }
    function show(data) { out.textContent = data && data.ok === false ? 'Request failed.' : 'Request complete.'; }
    function showError(error) { out.textContent = error.message || String(error); }

    async function requestJson(path, options = {}) {
      const response = await fetch(path, options);
      const data = await response.json().catch(() => ({ ok: false, detail: response.statusText }));
      if (!response.ok) throw new Error(data.detail || 'Request failed.');
      return data;
    }

    async function createArtist() {
      try {
        show(await requestJson('/create-artist', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ artist_name: value('artist-name') })
        }));
      } catch (error) { showError(error); }
    }

    async function createSong() {
      try {
        show(await requestJson('/create-song', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ artist_name: value('song-artist'), song_name: value('song-name') })
        }));
      } catch (error) { showError(error); }
    }

    async function uploadFile() {
      try {
        const fileInput = document.getElementById('upload-file');
        if (!fileInput.files.length) throw new Error('Choose a file first.');
        const form = new FormData();
        form.append('file', fileInput.files[0]);
        if (value('upload-artist')) form.append('artist_name', value('upload-artist'));
        if (value('upload-song')) form.append('song_name', value('upload-song'));
        show(await requestJson('/upload', { method: 'POST', body: form }));
      } catch (error) { showError(error); }
    }

    async function getCollaborators() {
      try { show(await requestJson('/collaborators')); } catch (error) { showError(error); }
    }

    async function saveCollaborator() {
      try {
        const body = {
          name: value('collab-name'),
          email: value('collab-email'),
          bmi: value('collab-bmi'),
          ascap: value('collab-ascap'),
          pro: value('collab-pro'),
          notes: value('collab-notes')
        };
        if (value('collab-id')) body.profile_id = value('collab-id');
        show(await requestJson('/collaborators', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        }));
      } catch (error) { showError(error); }
    }

    async function getSongs() {
      try { show(await requestJson('/songs')); } catch (error) { showError(error); }
    }

    async function getArtistProfiles() {
      try { show(await requestJson('/artist-profiles')); } catch (error) { showError(error); }
    }

    async function getSongCredits() {
      try { show(await requestJson(`/song-credits/${encodeURIComponent(value('credit-song-id'))}`)); } catch (error) { showError(error); }
    }

    async function addSongCredit() {
      try {
        const body = {
          profile_id: value('credit-profile-id'),
          role: value('credit-role'),
          credit: value('credit-text')
        };
        if (value('credit-split')) body.split = Number(value('credit-split'));
        show(await requestJson(`/song-credits/${encodeURIComponent(value('credit-song-id'))}/collaborators`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        }));
      } catch (error) { showError(error); }
    }

    async function removeSongCredit() {
      try {
        show(await requestJson(`/song-credits/${encodeURIComponent(value('credit-song-id'))}/collaborators/${encodeURIComponent(value('remove-index'))}`, {
          method: 'DELETE'
        }));
      } catch (error) { showError(error); }
    }

    async function resetSplits() {
      try {
        show(await requestJson(`/song-credits/${encodeURIComponent(value('credit-song-id'))}/reset-splits`, {
          method: 'POST'
        }));
      } catch (error) { showError(error); }
    }

    async function getCompleteness() {
      try { show(await requestJson(`/songs/${encodeURIComponent(value('song-tools-id'))}/completeness`)); } catch (error) { showError(error); }
    }

    async function updateStatus() {
      try {
        show(await requestJson(`/songs/${encodeURIComponent(value('song-tools-id'))}/status`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: value('song-status') })
        }));
      } catch (error) { showError(error); }
    }

    async function generateSplitSheet() {
      try {
        show(await requestJson(`/songs/${encodeURIComponent(value('song-tools-id'))}/generate-split-sheet`, {
          method: 'POST'
        }));
      } catch (error) { showError(error); }
    }

    async function sendSplitSheet() {
      try {
        show(await requestJson(`/songs/${encodeURIComponent(value('song-tools-id'))}/send-split-sheet`, {
          method: 'POST'
        }));
      } catch (error) { showError(error); }
    }

    async function createSendLink() {
      try {
        show(await requestJson('/send-links', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ artist_name: value('send-link-artist'), song_name: value('send-link-song') })
        }));
      } catch (error) { showError(error); }
    }
  </script>
</body>
</html>"""


class CreateArtistRequest(BaseModel):
    artist_name: str = Field(..., min_length=1)


class CreateSongRequest(BaseModel):
    artist_name: str = Field(..., min_length=1)
    song_name: str = Field(..., min_length=1)


class CollaboratorRequest(BaseModel):
    profile_id: Optional[str] = None
    name: str = Field(..., min_length=1)
    email: str = ""
    bmi: str = ""
    ascap: str = ""
    pro: str = ""
    notes: str = ""


class SongCreditCollaboratorRequest(BaseModel):
    profile_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    credit: str = ""
    split: Optional[float] = None
    artist: str = ""
    song: str = ""


class SongStatusRequest(BaseModel):
    status: str = Field(..., min_length=1)


class SendLinkRequest(BaseModel):
    artist_name: str = Field(..., min_length=1)
    song_name: str = Field(..., min_length=1)


class ArtistProfileRequest(BaseModel):
    artist_name: str = Field(..., min_length=1)


@app.post("/create-artist")
def create_artist(request: CreateArtistRequest):
    try:
        result = create_artist_folder(request.artist_name)
        return {
            "ok": True,
            "artist": result["artist"],
            "artist_folder_id": result["artist_folder_id"],
            "parent_folder_id": result["parent_folder_id"],
            "created": result["created"],
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/create-song")
def create_song(request: CreateSongRequest):
    try:
        result = create_song_folder(request.artist_name, request.song_name)
        return {
            "ok": True,
            "artist": result["artist"],
            "artist_folder_id": result["artist_folder_id"],
            "song": result["song"],
            "song_folder_id": result["song_folder_id"],
            "parent_folder_id": result["parent_folder_id"],
            "created": result["created"],
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    artist_name: Optional[str] = Form(None),
    song_name: Optional[str] = Form(None),
):
    temp_path = None
    try:
        suffix = "_" + os.path.basename(file.filename or "upload")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            temp_file.write(await file.read())

        result = upload_file_to_drive(
            temp_path,
            filename=file.filename,
            artist_name=artist_name,
            song_name=song_name,
        )
        return {
            "ok": True,
            "file": result,
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


@app.get("/collaborators")
def get_collaborators():
    try:
        return {
            "ok": True,
            "collaborators": load_collaborators(),
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/collaborators")
def create_or_update_collaborator(request: CollaboratorRequest):
    try:
        result = save_collaborator_profile(request.model_dump())
        return {
            "ok": True,
            "created": result["created"],
            "collaborator": result["profile"],
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/songs")
def get_songs():
    try:
        return {
            "ok": True,
            "songs": list_songs(),
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/artist-profiles")
def get_artist_profiles():
    try:
        return {
            "ok": True,
            "artist_profiles": list_artist_profiles(),
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.patch("/artist-profiles/{artist_folder_id}")
def patch_artist_profile(artist_folder_id: str, request: ArtistProfileRequest):
    try:
        return {
            "ok": True,
            "artist_profile": rename_artist_profile(artist_folder_id, request.artist_name),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.delete("/artist-profiles/{artist_folder_id}")
def delete_artist_profile_endpoint(artist_folder_id: str):
    try:
        return {
            "ok": True,
            "artist_profile": delete_artist_profile(artist_folder_id),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/artist-profiles/{artist_folder_id}/image")
async def post_artist_profile_image(artist_folder_id: str, image: UploadFile = File(...)):
    if not (image.content_type or '').startswith('image/'):
        raise HTTPException(status_code=400, detail="Upload an image file.")

    suffix = os.path.splitext(image.filename or '')[1] or '.png'
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = temp.name
    try:
        with temp:
            temp.write(await image.read())
        return {
            "ok": True,
            "image": upload_artist_profile_image(artist_folder_id, temp_path, filename=image.filename),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/artist-profiles/{artist_folder_id}/image")
def get_artist_profile_image(artist_folder_id: str):
    try:
        image_file = get_artist_profile_image_file(artist_folder_id)
        if not image_file:
            raise HTTPException(status_code=404, detail="No profile image found.")

        suffix = os.path.splitext(image_file.get('title', 'profile.png'))[1] or '.png'
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_path = temp.name
        temp.close()
        image_file.GetContentFile(temp_path)
        return FileResponse(
            temp_path,
            media_type=image_file.get('mimeType') or 'image/*',
            background=BackgroundTask(lambda: os.path.exists(temp_path) and os.remove(temp_path)),
        )
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/song-credits/{song_folder_id}")
def get_song_credits(song_folder_id: str, artist: str = "", song: str = ""):
    try:
        record = get_song_credit_record(song_folder_id, artist=artist, song=song)
        return {
            "ok": True,
            "song_credit": record,
            "split_total": sum(float(item.get("split") or 0) for item in record.get("collaborators", [])),
            "release_status": calculate_song_release_status(song_folder_id, record=record),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/songs/{song_folder_id}/completeness")
def get_song_completeness_endpoint(song_folder_id: str):
    try:
        return {
            "ok": True,
            "completeness": get_song_completeness(song_folder_id),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.patch("/songs/{song_folder_id}/status")
def patch_song_status(song_folder_id: str, request: SongStatusRequest):
    try:
        release_status = calculate_song_release_status(song_folder_id)
        return {
            "ok": True,
            "song_credit": update_song_status(song_folder_id, release_status["label"]),
            "release_status": release_status,
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/songs/{song_folder_id}/generate-split-sheet")
def generate_song_split_sheet(song_folder_id: str):
    try:
        return {
            "ok": True,
            "split_sheet": generate_split_sheet_for_song(song_folder_id),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/songs/{song_folder_id}/send-split-sheet")
def send_song_split_sheet(song_folder_id: str, request: Request):
    try:
        return {
            "ok": True,
            "result": send_split_sheet_for_song(song_folder_id, str(request.base_url)),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/song-credits/{song_folder_id}/collaborators")
def add_song_credit(song_folder_id: str, request: SongCreditCollaboratorRequest):
    try:
        result = add_song_credit_collaborator(
            song_folder_id,
            profile_id=request.profile_id,
            role=request.role,
            split=request.split,
            credit=request.credit,
            artist=request.artist,
            song=request.song,
        )
        return {
            "ok": True,
            "song_credit": result["record"],
            "split_total": result["split_total"],
            "release_status": calculate_song_release_status(song_folder_id, record=result["record"]),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.delete("/song-credits/{song_folder_id}/collaborators/{collaborator_index}")
def remove_song_credit(song_folder_id: str, collaborator_index: int):
    try:
        result = remove_song_credit_collaborator(song_folder_id, collaborator_index)
        return {
            "ok": True,
            "removed": result["removed"],
            "song_credit": result["record"],
            "split_total": result["split_total"],
            "release_status": calculate_song_release_status(song_folder_id, record=result["record"]),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/song-credits/{song_folder_id}/reset-splits")
def reset_song_credit_split_total(song_folder_id: str):
    try:
        result = reset_song_credit_splits(song_folder_id)
        return {
            "ok": True,
            "song_credit": result["record"],
            "split_total": result["split_total"],
            "release_status": calculate_song_release_status(song_folder_id, record=result["record"]),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/send-links")
def create_song_send_link(request: SendLinkRequest):
    try:
        return {
            "ok": True,
            "send_link": create_send_link(request.artist_name, request.song_name),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/signature/{token}", response_class=HTMLResponse)
def get_signature_page(token: str):
    try:
        return build_signature_page(token)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/signature/{token}", response_class=HTMLResponse)
def submit_signature(
    token: str,
    signature_name: str = Form(...),
    email: str = Form(...),
    notes: str = Form(""),
    agreement: str = Form(""),
):
    try:
        signed_request = save_signature_submission_for_token(
            token,
            signature_name,
            email,
            notes=notes,
            agreement=agreement == "yes",
        )
        signed_url = signed_request.get("signed_document_url", "")
        return """<!doctype html><html><body>
<h1>Signature Received</h1>
<p>Thank you. Your signed confirmation was saved to the song folder.</p>
<p><a href="{url}" target="_blank" rel="noopener">Open signed confirmation</a></p>
</body></html>""".format(url=signed_url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    build_signature_page,
