import base64
import os
import re
import tempfile
import time
import uuid
from email.message import EmailMessage
from html import escape as html_escape

try:
    from googleapiclient.discovery import build as build_google_service
    GOOGLE_API_CLIENT_AVAILABLE = True
except ImportError:
    GOOGLE_API_CLIENT_AVAILABLE = False

from .collaborator_service import (
    ensure_credits_data_folder,
    get_song_credit_total,
    load_collaborators,
    load_song_credit_assignments,
    save_song_credit_assignments,
)
from .config import SIGNATURE_REQUESTS_JSON, SIGNED_SPLIT_SHEETS_FOLDER_NAME
from .drive_service import (
    get_authenticated_drive,
    get_or_create_drive_folder,
    load_drive_json_file,
    save_drive_json_file,
)
from .song_service import get_song_context


def get_google_service_from_drive(drive, api_name, version):
    if not GOOGLE_API_CLIENT_AVAILABLE:
        raise RuntimeError("google-api-python-client is required for Docs/Gmail features.")
    if not drive or not getattr(drive, 'auth', None):
        raise RuntimeError("Google Drive is not authenticated.")
    return build_google_service(api_name, version, credentials=drive.auth.credentials, cache_discovery=False)


def build_split_sheet_html_for_song(song, contributors):
    rows = []
    seen = set()
    signatures = []
    for contributor in contributors:
        name = contributor.get('name', '').strip()
        rows.append("<tr><td>{}</td><td>{}</td><td>{}%</td></tr>".format(
            html_escape(name),
            html_escape(contributor.get('role', '').strip()),
            html_escape(str(contributor.get('split', 0))),
        ))
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            signatures.append("<p>{}<br>Signature: ____________________________ &nbsp; Date: ____________</p>".format(html_escape(name)))

    return """<!doctype html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: Arial, sans-serif; color: #111; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
th, td {{ border: 1px solid #999; padding: 8px; text-align: left; }}
th {{ background: #f1f1f1; }}
</style></head><body>
<h1>Split Sheet</h1>
<p><strong>Song:</strong> {artist} - {song}</p>
<h2>Contributors</h2>
<table><tr><th>Name</th><th>Role</th><th>Split</th></tr>{rows}</table>
<h2>Signatures</h2>{signatures}
</body></html>""".format(
        artist=html_escape(song.get('artist', '')),
        song=html_escape(song.get('song', '')),
        rows=''.join(rows),
        signatures=''.join(signatures),
    )


def generate_split_sheet_for_song(song_folder_id, drive=None):
    drive = drive or get_authenticated_drive()
    assignments = load_song_credit_assignments(drive)
    record = assignments.get(song_folder_id)
    if not record or not record.get('collaborators'):
        raise ValueError("Add collaborators before generating a split sheet.")
    split_total = get_song_credit_total(record)
    if abs(split_total - 100.0) > 0.01:
        raise ValueError("Song splits must total 100% before generating a split sheet. Current total: {}%.".format(split_total))

    profiles = {profile.get('profile_id'): profile for profile in load_collaborators(drive)}
    context = get_song_context(song_folder_id, drive)
    song = {'artist': record.get('artist') or context.get('artist', ''), 'song': record.get('song') or context.get('song', '')}
    contributors = []
    for collaborator in record.get('collaborators', []):
        profile = profiles.get(collaborator.get('profile_id'), {})
        contributors.append({
            'name': profile.get('name') or collaborator.get('profile_id', 'Collaborator'),
            'role': collaborator.get('role', ''),
            'split': collaborator.get('split', 0),
        })

    safe_name = re.sub(r'[<>:"/\\\\|?*]+', '-', "{} - {} Split Sheet".format(song.get('artist') or 'Artist', song.get('song') or 'Song')).strip() or 'Split Sheet'
    html_content = build_split_sheet_html_for_song(song, contributors)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as temp_file:
            temp_file.write(html_content)
            temp_path = temp_file.name
        drive_file = drive.CreateFile({'title': safe_name, 'parents': [{'id': song_folder_id}], 'mimeType': 'text/html'})
        drive_file.SetContentFile(temp_path)
        drive_file.Upload(param={'convert': True})
        drive_file.FetchMetadata(fields='id,title,alternateLink')
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    url = drive_file.get('alternateLink') or 'https://docs.google.com/document/d/{}/edit'.format(drive_file.get('id'))
    record['split_sheet_doc_id'] = drive_file.get('id')
    record['split_sheet_url'] = url
    record['split_sheet_title'] = drive_file.get('title') or safe_name
    record['split_sheet_generated_at'] = int(time.time())
    assignments[song_folder_id] = record
    save_song_credit_assignments(assignments, drive)
    return {'id': drive_file.get('id'), 'title': record['split_sheet_title'], 'url': url, 'song_credit': record}


def load_signature_requests(drive=None):
    drive = drive or get_authenticated_drive()
    folder = ensure_credits_data_folder(drive)
    data = load_drive_json_file(drive, SIGNATURE_REQUESTS_JSON, {'requests': {}}, folder['id'])
    return data.get('requests', {})


def save_signature_requests(requests, drive=None):
    drive = drive or get_authenticated_drive()
    folder = ensure_credits_data_folder(drive)
    save_drive_json_file(drive, SIGNATURE_REQUESTS_JSON, {'requests': requests}, folder['id'])
    return requests


def find_existing_split_sheet_for_song(song_folder_id, drive=None):
    drive = drive or get_authenticated_drive()
    assignments = load_song_credit_assignments(drive)
    record = assignments.get(song_folder_id, {})
    if record.get('split_sheet_doc_id') or record.get('split_sheet_url'):
        return {'id': record.get('split_sheet_doc_id'), 'url': record.get('split_sheet_url', ''), 'title': record.get('split_sheet_title', 'Split Sheet')}
    query = "mimeType='application/vnd.google-apps.document' and trashed=false and '{}' in parents and title contains 'Split Sheet'".format(song_folder_id)
    docs = drive.ListFile({'q': query, 'orderBy': 'modifiedDate desc'}).GetList()
    if not docs:
        return None
    doc = docs[0]
    doc_id = doc.get('id')
    return {'id': doc_id, 'url': doc.get('alternateLink') or 'https://docs.google.com/document/d/{}/edit'.format(doc_id), 'title': doc.get('title', 'Split Sheet')}


def create_signature_requests_for_song(song_folder_id, base_url, drive=None):
    drive = drive or get_authenticated_drive()
    split_sheet = find_existing_split_sheet_for_song(song_folder_id, drive)
    if not split_sheet:
        raise ValueError("No split sheet was found for this song. Generate one first.")
    assignments = load_song_credit_assignments(drive)
    record = assignments.get(song_folder_id)
    if not record or not record.get('collaborators'):
        raise ValueError("Add collaborators before sending a split sheet.")

    profiles = {profile.get('profile_id'): profile for profile in load_collaborators(drive)}
    context = get_song_context(song_folder_id, drive)
    signed_folder = get_or_create_drive_folder(drive, SIGNED_SPLIT_SHEETS_FOLDER_NAME, song_folder_id)
    all_requests = load_signature_requests(drive)
    created = []
    seen = set()
    clean_base = base_url.rstrip('/')
    for collaborator in record.get('collaborators', []):
        profile = profiles.get(collaborator.get('profile_id'), {})
        name = (profile.get('name') or collaborator.get('profile_id') or '').strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        token = str(uuid.uuid4())
        request = {
            'token': token,
            'song_folder_id': song_folder_id,
            'signatures_folder_id': signed_folder['id'],
            'split_sheet_doc_id': split_sheet.get('id'),
            'split_sheet_url': split_sheet.get('url', ''),
            'artist': record.get('artist') or context.get('artist', ''),
            'song': record.get('song') or context.get('song', ''),
            'profile_id': collaborator.get('profile_id', ''),
            'name': name,
            'email': profile.get('email', ''),
            'status': 'pending',
            'signature_link': '{}/signature/{}'.format(clean_base, token),
            'created_at': int(time.time()),
        }
        all_requests[token] = request
        created.append(request)
    save_signature_requests(all_requests, drive)
    return created


def send_signature_email_request(drive, request):
    if not request.get('email'):
        return False, "No email on collaborator profile."
    gmail = get_google_service_from_drive(drive, 'gmail', 'v1')
    message = EmailMessage()
    message['To'] = request['email']
    message['Subject'] = "Split sheet signature: {} - {}".format(request.get('artist', ''), request.get('song', ''))
    message.set_content("Hi {},\n\nPlease review and sign the split sheet for {} - {}.\n\nGoogle Doc:\n{}\n\nSignature link:\n{}\n\nThank you.".format(
        request.get('name', ''),
        request.get('artist', ''),
        request.get('song', ''),
        request.get('split_sheet_url', ''),
        request.get('signature_link', ''),
    ))
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    gmail.users().messages().send(userId='me', body={'raw': encoded}).execute()
    return True, request.get('signature_link', '')


def send_split_sheet_for_song(song_folder_id, base_url, drive=None):
    drive = drive or get_authenticated_drive()
    requests = create_signature_requests_for_song(song_folder_id, base_url, drive)
    all_requests = load_signature_requests(drive)
    sent = []
    skipped = []
    for request in requests:
        try:
            ok, detail = send_signature_email_request(drive, request)
            if ok:
                request['email_sent_at'] = int(time.time())
                sent.append(request)
            else:
                skipped.append({'name': request.get('name', ''), 'reason': detail})
        except Exception as error:
            skipped.append({'name': request.get('name', ''), 'reason': str(error)})
        all_requests[request['token']] = request
    save_signature_requests(all_requests, drive)
    return {'created_requests': requests, 'sent': sent, 'skipped': skipped}


def build_signature_page(token, drive=None):
    drive = drive or get_authenticated_drive()
    request = load_signature_requests(drive).get(token)
    if not request:
        raise ValueError("Signature request not found.")
    if request.get('status') == 'signed':
        return "<!doctype html><html><body><h1>Already Signed</h1><p>This split sheet has already been signed and received.</p></body></html>"
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Split Sheet Signature</title>
<style>
body {{ margin: 0; font-family: Arial, sans-serif; background: #20140c; color: #f6ead8; }}
main {{ max-width: 760px; margin: 0 auto; padding: 42px 22px; }}
form {{ margin-top: 22px; padding: 22px; background: #17100a; border: 1px solid #5a3518; }}
label {{ display:block; margin:14px 0 6px; color:#ffb45a; font-weight:700; }}
input, textarea {{ width:100%; box-sizing:border-box; background:#2b2118; color:#f6ead8; border:1px solid #5a3518; padding:11px; font:inherit; }}
button, a {{ display:inline-block; margin-top:18px; background:#ff9f2e; color:#120c07; border:0; padding:12px 16px; font-weight:700; text-decoration:none; }}
</style></head><body><main>
<h1>Review and Sign Split Sheet</h1>
<p><strong>Song:</strong> {artist} - {song}<br><strong>Contributor:</strong> {name}</p>
<a href="{split_sheet_url}" target="_blank" rel="noopener">Open Split Sheet</a>
<form action="/signature/{token}" method="post">
<label for="signature_name">Typed Signature</label>
<input id="signature_name" name="signature_name" value="{name}" required>
<label for="email">Email</label>
<input id="email" name="email" type="email" value="{email}" required>
<label for="notes">Notes</label>
<textarea id="notes" name="notes"></textarea>
<label><input name="agreement" type="checkbox" value="yes" required style="width:auto;margin-right:8px;">I reviewed and approve this split sheet.</label>
<button type="submit">Submit Signature</button>
</form></main></body></html>""".format(
        artist=html_escape(request.get('artist', '')),
        song=html_escape(request.get('song', '')),
        name=html_escape(request.get('name', '')),
        email=html_escape(request.get('email', '')),
        split_sheet_url=html_escape(request.get('split_sheet_url', '#')),
        token=html_escape(token),
    )


def save_signature_submission_for_token(token, signature_name, email, notes='', agreement=False, drive=None):
    if not agreement:
        raise ValueError("Signature agreement is required.")
    signature_name = signature_name.strip()
    email = email.strip()
    if not signature_name or not email:
        raise ValueError("Name and email are required.")

    drive = drive or get_authenticated_drive()
    all_requests = load_signature_requests(drive)
    request = all_requests.get(token)
    if not request:
        raise ValueError("Signature request not found.")

    signed_at = time.strftime('%Y-%m-%d %H:%M:%S')
    html_content = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<h1>Signed Split Sheet Confirmation</h1>
<p><strong>Song:</strong> {artist} - {song}</p>
<p><strong>Contributor:</strong> {name}</p>
<p><strong>Email:</strong> {email}</p>
<p><strong>Signed At:</strong> {signed_at}</p>
<p><strong>Agreement:</strong> I reviewed and approve this split sheet.</p>
<p><strong>Split Sheet:</strong> <a href="{split_sheet_url}">{split_sheet_url}</a></p>
<h2>Notes</h2><p>{notes}</p>
</body></html>""".format(
        artist=html_escape(request.get('artist', '')),
        song=html_escape(request.get('song', '')),
        name=html_escape(signature_name),
        email=html_escape(email),
        signed_at=html_escape(signed_at),
        split_sheet_url=html_escape(request.get('split_sheet_url', '')),
        notes=html_escape(notes).replace('\n', '<br>'),
    )
    signatures_folder_id = request.get('signatures_folder_id')
    if not signatures_folder_id:
        signatures_folder_id = get_or_create_drive_folder(drive, SIGNED_SPLIT_SHEETS_FOLDER_NAME, request.get('song_folder_id'))['id']
        request['signatures_folder_id'] = signatures_folder_id

    safe_title = re.sub(r'[<>:"/\\\\|?*]+', '-', "{} - {} Signature".format(request.get('song', 'Song'), signature_name)).strip()
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as temp_file:
            temp_file.write(html_content)
            temp_path = temp_file.name
        drive_file = drive.CreateFile({'title': safe_title, 'parents': [{'id': signatures_folder_id}], 'mimeType': 'text/html'})
        drive_file.SetContentFile(temp_path)
        drive_file.Upload(param={'convert': True})
        drive_file.FetchMetadata(fields='id,title,alternateLink')
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    request['status'] = 'signed'
    request['signed_at'] = int(time.time())
    request['signed_name'] = signature_name
    request['signed_email'] = email
    request['signed_document_id'] = drive_file.get('id')
    request['signed_document_url'] = drive_file.get('alternateLink') or 'https://docs.google.com/document/d/{}/edit'.format(drive_file.get('id'))
    all_requests[token] = request
    save_signature_requests(all_requests, drive)
    return request
