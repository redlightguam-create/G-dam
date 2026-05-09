import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default as email_policy
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import socket
import subprocess
import sys
import time
import json
import uuid
import base64
from urllib.request import Request, urlopen
from urllib.parse import unquote, parse_qs, urlparse
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    TKINTER_DND_AVAILABLE = True
except ImportError:
    TKINTER_DND_AVAILABLE = False
    print("tkinterdnd2 not available, drag-drop disabled")
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
try:
    from googleapiclient.discovery import build as build_google_service
    GOOGLE_API_CLIENT_AVAILABLE = True
except ImportError:
    GOOGLE_API_CLIENT_AVAILABLE = False
import threading
import webbrowser
try:
    from PIL import Image, ImageDraw, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

SENDER_PORTAL_PORT = 3000
NGROK_SENDER_URL = 'https://ferris-yonder-cyclist.ngrok-free.dev'
SEND_LINK_LIFETIME_SECONDS = 7 * 24 * 60 * 60
APP_NAME = 'Music Distribution Organizer'
TOKEN_FILENAME = 'google_drive_token.pickle'
PROFILE_IMAGE_FOLDER_NAME = 'Profile Image'
APP_DRIVE_ROOT_FOLDER_NAME = 'G-DAM'
CREDITS_DATA_FOLDER_NAME = 'Credits & Collaborators'
COLLABORATOR_PROFILES_JSON = 'collaborator_profiles.json'
SONG_CREDITS_JSON = 'song_credits.json'
SIGNATURE_REQUESTS_JSON = 'signature_requests.json'
SIGNED_SPLIT_SHEETS_FOLDER_NAME = 'Signed Split Sheets'

def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.abspath('.'))
    return os.path.join(base_path, relative_path)

def get_app_data_dir():
    """Return a per-user writable app directory for tokens and local state."""
    candidates = []
    if sys.platform.startswith('win'):
        for base_dir in [os.environ.get('LOCALAPPDATA'), os.environ.get('APPDATA'), os.path.expanduser('~')]:
            if base_dir:
                candidates.append(os.path.join(base_dir, APP_NAME))
    else:
        candidates.append(os.path.join(os.path.expanduser('~'), '.music_distribution_organizer'))

    candidates.extend([
        os.path.join(tempfile.gettempdir(), APP_NAME),
        os.path.abspath('.app_data'),
    ])

    for app_data_dir in candidates:
        try:
            os.makedirs(app_data_dir, exist_ok=True)
            return app_data_dir
        except OSError:
            continue

    return os.path.abspath('.')

def get_token_path():
    return os.path.join(get_app_data_dir(), TOKEN_FILENAME)

def get_client_secrets_path():
    """Find OAuth client configuration in dev, bundled, or next to the exe."""
    if getattr(sys, 'frozen', False):
        candidates = [
            os.path.join(os.path.dirname(sys.executable), 'client_secrets.json'),
            resource_path('client_secrets.json'),
            os.path.abspath('client_secrets.json'),
        ]
    else:
        candidates = [
            os.path.abspath('client_secrets.json'),
            resource_path('client_secrets.json'),
        ]

    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]

def build_google_auth_settings(client_secrets_path, token_path):
    return {
        'client_config_backend': 'file',
        'client_config_file': client_secrets_path,
        'save_credentials': True,
        'save_credentials_backend': 'file',
        'save_credentials_file': token_path,
        'get_refresh_token': True,
        'oauth_scope': [
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/gmail.send'
        ],
    }

def escape_drive_query_value(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'")

def get_authenticated_drive(force_new_token=False):
    client_secrets_path = get_client_secrets_path()
    token_path = get_token_path()
    gauth = GoogleAuth(settings=build_google_auth_settings(client_secrets_path, token_path))

    if force_new_token and os.path.exists(token_path):
        os.remove(token_path)

    if os.path.exists(token_path) and not force_new_token:
        gauth.LoadCredentialsFile(token_path)

    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()

    gauth.SaveCredentialsFile(token_path)
    return GoogleDrive(gauth)

def find_drive_child_folder_case_insensitive(drive, title, parent_id='root'):
    wanted = title.strip().casefold()
    if not wanted:
        return None

    if parent_id == 'root':
        query = "mimeType='application/vnd.google-apps.folder' and trashed=false and 'root' in parents"
    else:
        query = "mimeType='application/vnd.google-apps.folder' and trashed=false and '{}' in parents".format(parent_id)

    folders = drive.ListFile({'q': query}).GetList()
    for folder in folders:
        if folder.get('title', '').strip().casefold() == wanted:
            return folder
    return None

def get_or_create_drive_folder(drive, title, parent_id='root'):
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Folder title is required.")

    existing_folder = find_drive_child_folder_case_insensitive(drive, clean_title, parent_id)
    if existing_folder:
        return {
            'id': existing_folder['id'],
            'title': existing_folder.get('title', clean_title),
            'created': False
        }

    query = "title='{}' and mimeType='application/vnd.google-apps.folder' and '{}' in parents and trashed=false".format(
        escape_drive_query_value(clean_title),
        parent_id
    )
    existing = drive.ListFile({'q': query}).GetList()
    if existing:
        return {
            'id': existing[0]['id'],
            'title': existing[0].get('title', clean_title),
            'created': False
        }

    folder = drive.CreateFile({
        'title': clean_title,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [{'id': parent_id}]
    })
    folder.Upload()
    return {
        'id': folder['id'],
        'title': clean_title,
        'created': True
    }

def ensure_app_drive_root_folder(drive):
    return get_or_create_drive_folder(drive, APP_DRIVE_ROOT_FOLDER_NAME, 'root')

def create_artist_folder(artist_name, drive=None, parent_id=None):
    clean_artist = artist_name.strip()
    if not clean_artist:
        raise ValueError("artist_name is required.")

    drive = drive or get_authenticated_drive()
    root_folder = {'id': parent_id} if parent_id else ensure_app_drive_root_folder(drive)
    artist_folder = get_or_create_drive_folder(drive, clean_artist, root_folder['id'])
    return {
        'artist': artist_folder['title'],
        'artist_folder_id': artist_folder['id'],
        'parent_folder_id': root_folder['id'],
        'parent_folder_name': APP_DRIVE_ROOT_FOLDER_NAME if not parent_id else '',
        'created': artist_folder['created']
    }

def create_song_folder(artist_name, song_name, drive=None, parent_id=None):
    clean_artist = artist_name.strip()
    clean_song = song_name.strip()
    if not clean_artist:
        raise ValueError("artist_name is required.")
    if not clean_song:
        raise ValueError("song_name is required.")

    drive = drive or get_authenticated_drive()
    artist_folder = create_artist_folder(clean_artist, drive=drive, parent_id=parent_id)
    song_folder = get_or_create_drive_folder(drive, clean_song, artist_folder['artist_folder_id'])
    return {
        'artist': artist_folder['artist'],
        'artist_folder_id': artist_folder['artist_folder_id'],
        'song': song_folder['title'],
        'song_folder_id': song_folder['id'],
        'parent_folder_id': artist_folder['parent_folder_id'],
        'created': song_folder['created']
    }

def find_drive_file_by_title(drive, title, parent_id):
    query = "title='{}' and '{}' in parents and trashed=false".format(
        escape_drive_query_value(title),
        parent_id
    )
    matches = drive.ListFile({'q': query}).GetList()
    return matches[0] if matches else None

def ensure_credits_data_folder(drive):
    app_root = ensure_app_drive_root_folder(drive)
    return get_or_create_drive_folder(drive, CREDITS_DATA_FOLDER_NAME, app_root['id'])

def load_drive_json_file(drive, title, default_value):
    folder = ensure_credits_data_folder(drive)
    existing = find_drive_file_by_title(drive, title, folder['id'])
    if not existing:
        return default_value
    raw = drive.CreateFile({'id': existing['id']}).GetContentString()
    return json.loads(raw) if raw.strip() else default_value

def save_drive_json_file(drive, title, data):
    folder = ensure_credits_data_folder(drive)
    existing = find_drive_file_by_title(drive, title, folder['id'])
    metadata = {'id': existing['id']} if existing else {'title': title, 'parents': [{'id': folder['id']}]}
    drive_file = drive.CreateFile(metadata)
    drive_file.SetContentString(json.dumps(data, indent=2, sort_keys=True))
    drive_file.Upload()
    return {
        'id': drive_file.get('id'),
        'title': title
    }

def load_collaborators(drive=None):
    drive = drive or get_authenticated_drive()
    data = load_drive_json_file(drive, COLLABORATOR_PROFILES_JSON, {'profiles': []})
    return data.get('profiles', [])

def save_collaborator_profile(profile_data, drive=None):
    drive = drive or get_authenticated_drive()
    name = (profile_data.get('name') or '').strip()
    if not name:
        raise ValueError("name is required.")

    profiles = load_collaborators(drive)
    existing = None
    profile_id = (profile_data.get('profile_id') or '').strip()
    for profile in profiles:
        if profile_id and profile.get('profile_id') == profile_id:
            existing = profile
            break
        if not profile_id and profile.get('name', '').strip().casefold() == name.casefold():
            existing = profile
            break

    payload = {
        'name': name,
        'email': (profile_data.get('email') or '').strip(),
        'bmi': (profile_data.get('bmi') or '').strip(),
        'ascap': (profile_data.get('ascap') or '').strip(),
        'pro': (profile_data.get('pro') or '').strip(),
        'notes': (profile_data.get('notes') or '').strip(),
    }
    if existing:
        existing.update(payload)
        existing.pop('phone', None)
        existing.pop('publisher', None)
        existing['updated_at'] = int(time.time())
        saved = existing
        created = False
    else:
        saved = {
            'profile_id': profile_id or str(uuid.uuid4()),
            **payload,
            'created_at': int(time.time())
        }
        profiles.append(saved)
        created = True

    profiles.sort(key=lambda item: item.get('name', '').casefold())
    save_drive_json_file(drive, COLLABORATOR_PROFILES_JSON, {'profiles': profiles})
    return {
        'profile': saved,
        'created': created
    }

def get_drive_folder_contents(drive, folder_id):
    query = "trashed=false and '{}' in parents".format(folder_id if folder_id != 'root' else 'root')
    return drive.ListFile({'q': query}).GetList()

def is_drive_folder(item):
    return item.get('mimeType') == 'application/vnd.google-apps.folder'

def get_required_tags():
    return ['Clean', 'Final', 'Instrumental', 'Acapella', 'Lyrics', 'Artwork']

def get_optional_tags():
    return ['Session Files']

def normalize_tag(tag):
    normalized = tag.strip().capitalize()
    if normalized.lower() == 'acapella':
        return 'Acapella'
    if normalized.lower() == 'instrumental':
        return 'Instrumental'
    if normalized.lower() == 'clean':
        return 'Clean'
    if normalized.lower() == 'final':
        return 'Final'
    if normalized.lower() == 'lyrics':
        return 'Lyrics'
    if normalized.lower() in ['cover', 'artwork']:
        return 'Artwork'
    if normalized.lower() in ['session', 'sessions', 'session file', 'session files', 'sessionfiles']:
        return 'Session Files'
    return normalized

def title_matches_required_tag(title):
    title_key = title.strip().casefold()
    return any(title_key == tag.casefold() for tag in get_required_tags())

def parse_filename(filename):
    name_without_ext = os.path.splitext(filename)[0]
    match = re.match(r'^(.+?)\s*-\s*(.+?)\s*\((.+?)\)$', name_without_ext)
    if not match:
        return None, None, None
    return match.group(1).strip(), match.group(2).strip(), match.group(3).strip()

def get_folder_for_tag(tag):
    tag_lower = tag.lower()
    if tag_lower in ['final', 'clean', 'instrumental', 'acapella']:
        return tag.capitalize()
    if tag_lower == 'lyrics':
        return 'Lyrics'
    if tag_lower in ['cover', 'artwork']:
        return 'Artwork'
    if tag_lower in ['session', 'sessions', 'session file', 'session files', 'sessionfiles']:
        return 'Session Files'
    return 'Other'

def build_drive_folder_status(items, folder_name=None):
    required = get_required_tags()
    optional = get_optional_tags()
    present_tags = set()
    optional_tags = set()

    def tag_from_title(title):
        title_lower = title.lower()
        for tag in required + optional:
            if tag.lower() in title_lower:
                return tag
        return None

    if folder_name:
        folder_tag = tag_from_title(folder_name)
        if folder_tag in required:
            present_tags.add(folder_tag)
        elif folder_tag in optional:
            optional_tags.add(folder_tag)

    for item in items:
        if is_drive_folder(item):
            folder_tag = tag_from_title(item.get('title', ''))
            if folder_tag in required:
                present_tags.add(folder_tag)
            elif folder_tag in optional:
                optional_tags.add(folder_tag)
        else:
            _, _, tag = parse_filename(item.get('title', ''))
            if tag:
                normalized_tag = normalize_tag(tag)
                if normalized_tag in required:
                    present_tags.add(normalized_tag)
                elif normalized_tag in optional:
                    optional_tags.add(normalized_tag)

    missing = [tag for tag in required if tag not in present_tags]
    return {
        'present': sorted(present_tags),
        'optional_present': sorted(optional_tags),
        'missing': missing,
        'percent': int(len(present_tags) / len(required) * 100) if required else 0
    }

def drive_folder_looks_like_song_drop(drive, folder, items=None):
    if title_matches_required_tag(folder.get('title', '')):
        return False
    items = items if items is not None else get_drive_folder_contents(drive, folder['id'])
    if not items:
        return False
    for item in items:
        if is_drive_folder(item) and title_matches_required_tag(item.get('title', '')):
            return True
        artist, song, tag = parse_filename(item.get('title', ''))
        if artist and song and tag and normalize_tag(tag) in get_required_tags():
            return True
    return False

def list_songs(drive=None, root_folder_id=None):
    drive = drive or get_authenticated_drive()
    root = {'id': root_folder_id} if root_folder_id else ensure_app_drive_root_folder(drive)
    songs = []
    artist_folders = [
        item for item in get_drive_folder_contents(drive, root['id'])
        if is_drive_folder(item) and item.get('title') not in [CREDITS_DATA_FOLDER_NAME, PROFILE_IMAGE_FOLDER_NAME]
    ]
    for artist_folder in artist_folders:
        song_folders = [item for item in get_drive_folder_contents(drive, artist_folder['id']) if is_drive_folder(item)]
        for song_folder in song_folders:
            song_items = get_drive_folder_contents(drive, song_folder['id'])
            if not drive_folder_looks_like_song_drop(drive, song_folder, song_items):
                continue
            status = build_drive_folder_status(song_items, song_folder.get('title', ''))
            songs.append({
                'artist': artist_folder.get('title', ''),
                'artist_folder_id': artist_folder.get('id'),
                'song': song_folder.get('title', ''),
                'song_folder_id': song_folder.get('id'),
                'present': status['present'],
                'optional_present': status['optional_present'],
                'missing': status['missing'],
                'percent': status['percent'],
                'item_count': len(song_items),
            })
    return sorted(songs, key=lambda item: (item.get('artist', '').casefold(), item.get('song', '').casefold()))

def upload_file_to_drive(file_path, filename=None, artist_name=None, song_name=None, drive=None):
    drive = drive or get_authenticated_drive()
    clean_filename = os.path.basename(filename or file_path).replace('\x00', '').strip()
    if not clean_filename:
        raise ValueError("filename is required.")

    parsed_artist, parsed_song, parsed_tag = parse_filename(clean_filename)
    artist = (artist_name or parsed_artist or '').strip()
    song = (song_name or parsed_song or '').strip()
    if not artist or not song:
        raise ValueError("artist_name and song_name are required unless filename is formatted as Artist - Song (Tag).ext.")

    song_folder = create_song_folder(artist, song, drive=drive)
    target_folder_id = song_folder['song_folder_id']
    if parsed_tag:
        tag_folder_name = get_folder_for_tag(parsed_tag)
        target_folder = get_or_create_drive_folder(drive, tag_folder_name, target_folder_id)
        target_folder_id = target_folder['id']

    existing_file = find_drive_file_by_title(drive, clean_filename, target_folder_id)
    if existing_file:
        existing_id = existing_file.get('id')
        return {
            'name': clean_filename,
            'id': existing_id,
            'url': existing_file.get('alternateLink') or 'https://drive.google.com/file/d/{}/view'.format(existing_id),
            'skipped': True,
            'verified': True
        }

    drive_file = drive.CreateFile({
        'title': clean_filename,
        'parents': [{'id': target_folder_id}]
    })
    drive_file.SetContentFile(file_path)
    drive_file.Upload()
    drive_file.FetchMetadata(fields='id,title,alternateLink')
    drive_file_id = drive_file.get('id')
    return {
        'name': clean_filename,
        'id': drive_file_id,
        'url': drive_file.get('alternateLink') or 'https://drive.google.com/file/d/{}/view'.format(drive_file_id),
        'skipped': False,
        'verified': True
    }

def load_song_credit_assignments(drive=None):
    drive = drive or get_authenticated_drive()
    data = load_drive_json_file(drive, SONG_CREDITS_JSON, {'songs': {}})
    return data.get('songs', {})

def save_song_credit_assignments(assignments, drive=None):
    drive = drive or get_authenticated_drive()
    save_drive_json_file(drive, SONG_CREDITS_JSON, {'songs': assignments})
    return assignments

def get_song_credit_record(song_folder_id, artist='', song='', drive=None):
    if not song_folder_id:
        raise ValueError("song_folder_id is required.")
    assignments = load_song_credit_assignments(drive)
    record = assignments.setdefault(song_folder_id, {
        'artist': artist,
        'song': song,
        'song_folder_id': song_folder_id,
        'collaborators': []
    })
    if artist:
        record['artist'] = artist
    if song:
        record['song'] = song
    return record

def get_role_split_pool(role):
    performance_roles = {'Primary Artist', 'Featured Artist'}
    production_engineering_roles = {
        'Producer',
        'Co-Producer',
        'Additional Producer',
        'Recording Engineer',
        'Mix Engineer',
        'Mastering Engineer'
    }
    if role in performance_roles:
        return 'artist', 50.0
    if role in production_engineering_roles:
        return 'production_engineering', 50.0
    return None, None

def reset_song_split_percentages(record):
    collaborators = record.get('collaborators', [])
    if not collaborators:
        return record

    pooled_collaborators = {}
    unpooled_collaborators = []
    used_pool_total = 0.0
    for collaborator in collaborators:
        pool_name, pool_total = get_role_split_pool(collaborator.get('role', ''))
        if pool_name:
            if pool_name not in pooled_collaborators:
                pooled_collaborators[pool_name] = {
                    'total': pool_total,
                    'collaborators': []
                }
                used_pool_total += pool_total
            pooled_collaborators[pool_name]['collaborators'].append(collaborator)
        else:
            unpooled_collaborators.append(collaborator)

    for pool in pooled_collaborators.values():
        pool_collaborators = pool['collaborators']
        split = pool['total'] / len(pool_collaborators)
        for collaborator in pool_collaborators:
            collaborator['split'] = split

    if unpooled_collaborators:
        remaining = max(0.0, 100.0 - used_pool_total)
        split = remaining / len(unpooled_collaborators)
        for collaborator in unpooled_collaborators:
            collaborator['split'] = split

    return record

def get_song_credit_total(record):
    return sum(float(item.get('split') or 0) for item in record.get('collaborators', []))

def add_song_credit_collaborator(song_folder_id, profile_id, role, split=None, credit='', artist='', song='', drive=None):
    drive = drive or get_authenticated_drive()
    if not profile_id:
        raise ValueError("profile_id is required.")
    if not role:
        raise ValueError("role is required.")

    profiles = load_collaborators(drive)
    if not any(profile.get('profile_id') == profile_id for profile in profiles):
        raise ValueError("Collaborator profile was not found.")

    assignments = load_song_credit_assignments(drive)
    record = assignments.setdefault(song_folder_id, {
        'artist': artist,
        'song': song,
        'song_folder_id': song_folder_id,
        'collaborators': []
    })
    if artist:
        record['artist'] = artist
    if song:
        record['song'] = song

    collaborator = {
        'profile_id': profile_id,
        'role': role,
        'credit': credit or '',
        'split': float(split) if split is not None else 0.0
    }
    record.setdefault('collaborators', []).append(collaborator)
    reset_song_split_percentages(record)
    save_song_credit_assignments(assignments, drive)
    return {
        'record': record,
        'split_total': get_song_credit_total(record)
    }

def remove_song_credit_collaborator(song_folder_id, collaborator_index, drive=None):
    drive = drive or get_authenticated_drive()
    assignments = load_song_credit_assignments(drive)
    record = assignments.get(song_folder_id)
    if not record:
        raise ValueError("Song credit record was not found.")

    collaborators = record.get('collaborators', [])
    if collaborator_index < 0 or collaborator_index >= len(collaborators):
        raise ValueError("Collaborator index is out of range.")

    removed = collaborators.pop(collaborator_index)
    reset_song_split_percentages(record)
    save_song_credit_assignments(assignments, drive)
    return {
        'removed': removed,
        'record': record,
        'split_total': get_song_credit_total(record)
    }

def reset_song_credit_splits(song_folder_id, drive=None):
    drive = drive or get_authenticated_drive()
    assignments = load_song_credit_assignments(drive)
    record = assignments.get(song_folder_id)
    if not record:
        raise ValueError("Song credit record was not found.")
    reset_song_split_percentages(record)
    save_song_credit_assignments(assignments, drive)
    return {
        'record': record,
        'split_total': get_song_credit_total(record)
    }

def get_drive_folder_metadata(drive, folder_id):
    if folder_id == 'root':
        return {'id': 'root', 'title': 'My Drive', 'parents': []}
    folder = drive.CreateFile({'id': folder_id})
    folder.FetchMetadata(fields='id,title,parents,mimeType')
    return folder

def get_song_context(song_folder_id, drive=None):
    drive = drive or get_authenticated_drive()
    song_folder = get_drive_folder_metadata(drive, song_folder_id)
    artist_name = ''
    artist_folder_id = ''
    parents = song_folder.get('parents') or []
    if parents:
        artist_folder_id = parents[0].get('id', '')
        if artist_folder_id:
            artist_folder = get_drive_folder_metadata(drive, artist_folder_id)
            artist_name = artist_folder.get('title', '')
    return {
        'artist': artist_name,
        'artist_folder_id': artist_folder_id,
        'song': song_folder.get('title', ''),
        'song_folder_id': song_folder_id
    }

def get_song_completeness(song_folder_id, drive=None):
    drive = drive or get_authenticated_drive()
    context = get_song_context(song_folder_id, drive)
    items = get_drive_folder_contents(drive, song_folder_id)
    status = build_drive_folder_status(items, context.get('song', ''))
    return {
        **context,
        'required': get_required_tags(),
        'optional': get_optional_tags(),
        'present': status['present'],
        'optional_present': status['optional_present'],
        'missing': status['missing'],
        'percent': status['percent'],
        'complete': status['percent'] == 100
    }

def update_song_status(song_folder_id, status, drive=None):
    clean_status = status.strip()
    if not clean_status:
        raise ValueError("status is required.")
    drive = drive or get_authenticated_drive()
    assignments = load_song_credit_assignments(drive)
    context = get_song_context(song_folder_id, drive)
    record = assignments.setdefault(song_folder_id, {
        'artist': context.get('artist', ''),
        'song': context.get('song', ''),
        'song_folder_id': song_folder_id,
        'collaborators': []
    })
    record['artist'] = record.get('artist') or context.get('artist', '')
    record['song'] = record.get('song') or context.get('song', '')
    record['status'] = clean_status
    record['status_updated_at'] = int(time.time())
    save_song_credit_assignments(assignments, drive)
    return record

def build_split_sheet_html_for_song(song, contributors):
    rows = []
    seen = set()
    signatures = []
    for contributor in contributors:
        name = contributor.get('name', '').strip()
        role = contributor.get('role', '').strip()
        split = contributor.get('split', 0)
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}%</td></tr>".format(
                html_escape(name),
                html_escape(role),
                html_escape(str(split))
            )
        )
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            signatures.append(
                "<p>{}<br>Signature: ____________________________ &nbsp; Date: ____________</p>".format(
                    html_escape(name)
                )
            )

    return """<!doctype html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: Arial, sans-serif; color: #111; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
th, td {{ border: 1px solid #999; padding: 8px; text-align: left; }}
th {{ background: #f1f1f1; }}
</style></head><body>
<h1>Split Sheet</h1>
<p><strong>Song:</strong> {artist} - {song}</p>
<h2>Contributors</h2>
<table><tr><th>Name</th><th>Role</th><th>Split</th></tr>{rows}</table>
<h2>Signatures</h2>
{signatures}
</body></html>""".format(
        artist=html_escape(song.get('artist', '')),
        song=html_escape(song.get('song', '')),
        rows=''.join(rows),
        signatures=''.join(signatures)
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
    song = {
        'artist': record.get('artist') or context.get('artist', ''),
        'song': record.get('song') or context.get('song', '')
    }
    contributors = []
    for collaborator in record.get('collaborators', []):
        profile = profiles.get(collaborator.get('profile_id'), {})
        contributors.append({
            'name': profile.get('name') or collaborator.get('profile_id', 'Collaborator'),
            'role': collaborator.get('role', ''),
            'split': collaborator.get('split', 0)
        })

    safe_name = re.sub(r'[<>:"/\\\\|?*]+', '-', "{} - {} Split Sheet".format(
        song.get('artist') or 'Artist',
        song.get('song') or 'Song'
    )).strip() or 'Split Sheet'
    html_content = build_split_sheet_html_for_song(song, contributors)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as temp_file:
            temp_file.write(html_content)
            temp_path = temp_file.name

        drive_file = drive.CreateFile({
            'title': safe_name,
            'parents': [{'id': song_folder_id}],
            'mimeType': 'text/html'
        })
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
    record['split_sheet_generated_at'] = int(time.time())
    assignments[song_folder_id] = record
    save_song_credit_assignments(assignments, drive)
    return {
        'id': drive_file.get('id'),
        'title': drive_file.get('title') or safe_name,
        'url': url,
        'song_credit': record
    }

def create_send_link(artist_name, song_name, drive=None):
    drive = drive or get_authenticated_drive()
    song_folder = create_song_folder(artist_name, song_name, drive=drive)
    folder = drive.CreateFile({'id': song_folder['song_folder_id']})
    folder.FetchMetadata(fields='id,title')
    folder.InsertPermission({'type': 'anyone', 'role': 'writer'})
    return {
        **song_folder,
        'drive_folder_url': 'https://drive.google.com/drive/folders/{}'.format(song_folder['song_folder_id']),
        'permission': 'anyone_writer'
    }

def get_google_service_from_drive(drive, api_name, version):
    if not GOOGLE_API_CLIENT_AVAILABLE:
        raise RuntimeError("google-api-python-client is required for Docs/Gmail features.")
    if not drive or not getattr(drive, 'auth', None):
        raise RuntimeError("Google Drive is not authenticated.")
    return build_google_service(api_name, version, credentials=drive.auth.credentials, cache_discovery=False)

def load_signature_requests(drive=None):
    drive = drive or get_authenticated_drive()
    data = load_drive_json_file(drive, SIGNATURE_REQUESTS_JSON, {'requests': {}})
    return data.get('requests', {})

def save_signature_requests(requests, drive=None):
    drive = drive or get_authenticated_drive()
    save_drive_json_file(drive, SIGNATURE_REQUESTS_JSON, {'requests': requests})
    return requests

def find_existing_split_sheet_for_song(song_folder_id, drive=None):
    drive = drive or get_authenticated_drive()
    assignments = load_song_credit_assignments(drive)
    record = assignments.get(song_folder_id, {})
    if record.get('split_sheet_doc_id') or record.get('split_sheet_url'):
        return {
            'id': record.get('split_sheet_doc_id'),
            'url': record.get('split_sheet_url', ''),
            'title': record.get('split_sheet_title', 'Split Sheet')
        }

    query = (
        "mimeType='application/vnd.google-apps.document' and trashed=false "
        "and '{}' in parents and title contains 'Split Sheet'"
    ).format(song_folder_id)
    docs = drive.ListFile({'q': query, 'orderBy': 'modifiedDate desc'}).GetList()
    if not docs:
        return None
    doc = docs[0]
    doc_id = doc.get('id')
    return {
        'id': doc_id,
        'url': doc.get('alternateLink') or 'https://docs.google.com/document/d/{}/edit'.format(doc_id),
        'title': doc.get('title', 'Split Sheet')
    }

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
            'created_at': int(time.time())
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
    message.set_content(
        "Hi {},\n\nPlease review and sign the split sheet for {} - {}.\n\nGoogle Doc:\n{}\n\nSignature link:\n{}\n\nThank you.".format(
            request.get('name', ''),
            request.get('artist', ''),
            request.get('song', ''),
            request.get('split_sheet_url', ''),
            request.get('signature_link', '')
        )
    )
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
    return {
        'created_requests': requests,
        'sent': sent,
        'skipped': skipped
    }

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
        token=html_escape(token)
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
        notes=html_escape(notes).replace('\n', '<br>')
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
        drive_file = drive.CreateFile({
            'title': safe_title,
            'parents': [{'id': signatures_folder_id}],
            'mimeType': 'text/html'
        })
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

def draw_rounded_rect(canvas, x1, y1, x2, y2, radius=16, **kwargs):
    """Draw a rounded rectangle on a Canvas."""
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)

def brighten_hex_color(hex_color, percent=20):
    """Return a color brightened toward white by percent."""
    value = hex_color.lstrip('#')
    if len(value) != 6:
        return hex_color
    try:
        channels = [int(value[index:index + 2], 16) for index in (0, 2, 4)]
    except ValueError:
        return hex_color
    factor = max(0, min(100, percent)) / 100
    brightened = [int(channel + (255 - channel) * factor) for channel in channels]
    return '#{:02x}{:02x}{:02x}'.format(*brightened)

class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent,
        text,
        command,
        width=120,
        height=34,
        bg='#24170d',
        fg='#f6ead8',
        accent='#ff9f2e',
        active_bg='#3a2514',
        radius=12,
        danger=False,
        font=('Arial', 9, 'bold')
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent.cget('bg'),
            highlightthickness=0,
            bd=0,
            cursor='hand2'
        )
        self.text = text
        self.command = command
        self.normal_bg = bg
        self.active_bg = active_bg
        self.fg = fg
        self.accent = accent
        self.hover_accent = brighten_hex_color(accent, 20)
        self.radius = radius
        self.font = font
        self.is_disabled = False
        self.danger = danger
        self.bind('<Button-1>', self._click)
        self.bind('<Enter>', lambda event: self._draw(self.active_bg, hover=True))
        self.bind('<Leave>', lambda event: self._draw(self.normal_bg))
        self._draw(self.normal_bg)

    def _draw(self, fill, hover=False):
        self.delete('all')
        width = int(self['width'])
        height = int(self['height'])
        accent = self.hover_accent if hover else self.accent
        if not self.is_disabled:
            if hover:
                draw_rounded_rect(self, 0, 0, width, height, self.radius + 4, outline=accent, fill='', width=1)
            draw_rounded_rect(self, 2, 2, width - 2, height - 2, self.radius + 2, outline=accent, fill='', width=1)
            draw_rounded_rect(self, 4, 4, width - 4, height - 4, self.radius, outline=accent, fill=fill, width=1)
        else:
            draw_rounded_rect(self, 4, 4, width - 4, height - 4, self.radius, outline='#4b3524', fill='#1c1510', width=1)
        self.create_text(
            width // 2,
            height // 2,
            text=self.text,
            fill='#8f8273' if self.is_disabled else self.fg,
            font=self.font
        )

    def _click(self, event):
        if not self.is_disabled and self.command:
            self.command()

    def config(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        if 'text' in kwargs:
            self.text = kwargs.pop('text')
        if 'state' in kwargs:
            self.is_disabled = kwargs.pop('state') == tk.DISABLED
        if 'bg' in kwargs:
            self.normal_bg = kwargs.pop('bg')
        if kwargs:
            super().config(**kwargs)
        self._draw(self.normal_bg)

    configure = config

class MusicOrganizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Music Distribution Organizer")
        self.root.geometry("1120x720")
        self.root.configure(bg='#0d0905')
        self.set_window_icon()

        # Warm dark dashboard theme
        self.bg_color = '#0d0905'
        self.panel_bg = '#17100a'
        self.card_bg = '#21160d'
        self.field_bg = '#2b2118'
        self.border_color = '#5a3518'
        self.accent_color = '#ff9f2e'
        self.accent_hover = '#ffb45a'
        self.danger_color = '#ff4d32'
        self.success_color = '#6cc24a'
        self.muted_fg = '#c9b8a4'
        self.fg_color = '#f6ead8'
        self.button_bg = '#24170d'
        self.button_fg = '#f6ead8'

        # File list to hold dropped/selected files
        self.files = []
        self.dnd_available = TKINTER_DND_AVAILABLE
        self.last_sent_song_status = []
        self.last_uploaded_drive_folder_id = None
        self.current_share_folder_id = None
        self.share_link_url = None
        self.sender_portal_url = None
        self.sender_portal_local_url = None
        self.sender_portal_lan_url = None
        self.sender_portal_server = None
        self.sender_portal_thread = None
        self.sender_portal_port = None
        self.ngrok_process = None
        self.ngrok_public_url = None
        self.ngrok_error = None
        self.sender_link_created_at = None
        self.sender_link_expires_at = None
        self.sender_link_expire_after_id = None
        self.messenger_webhook_url = os.environ.get('MESSENGER_WEBHOOK_URL', '').strip()
        self.sender_upload_lock = threading.RLock()
        self.shared_folder_item_ids = set()
        self.drive = None
        self.app_drive_root_folder_id = None
        self.current_artist_profiles = []
        self.current_song_profiles = []
        self.collaborator_profiles = []
        self.song_credit_assignments = {}
        self.signature_requests = {}
        self.credits_data_folder_id = None
        self.google_docs_service = None
        self.google_drive_v3_service = None
        self.gmail_service = None
        self.drive_folder_contents_cache = {}
        self.drive_metadata_cache = {}
        self.drive_path_cache = {}
        self.artist_profile_images = {}
        self.send_link_artist_options = {}
        self.send_link_song_options = {}
        self.artist_hover_popup = None
        self.artist_hover_after_id = None
        
        # Default directories
        self.local_dest_dir = os.path.join(os.getcwd(), 'Organized_Music')
        self.drive_dest_folder = 'root'  # Set to the app Drive root after authentication.
        
        # Load saved settings
        self.load_settings()

        # Create UI elements
        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Google Drive setup
        self.authenticate_drive()

    def set_window_icon(self):
        ico_path = resource_path(os.path.join('assets', 'app_icon.ico'))
        png_path = resource_path(os.path.join('assets', 'app_icon.png'))

        try:
            if os.path.exists(ico_path):
                self.root.iconbitmap(ico_path)
        except tk.TclError:
            pass

        try:
            if os.path.exists(png_path):
                self.app_icon_image = tk.PhotoImage(file=png_path)
                self.root.iconphoto(True, self.app_icon_image)
        except tk.TclError:
            pass

    def load_settings(self):
        """Load saved directory preferences"""
        try:
            if os.path.exists('settings.json'):
                import json
                with open('settings.json', 'r') as f:
                    settings = json.load(f)
                    self.local_dest_dir = settings.get('local_dest_dir', self.local_dest_dir)
                    self.drive_dest_folder = settings.get('drive_dest_folder', self.drive_dest_folder)
                    if not self.messenger_webhook_url:
                        self.messenger_webhook_url = settings.get('messenger_webhook_url', '').strip()
        except:
            pass  # Use defaults if settings file is corrupted

    def save_settings(self):
        """Save directory preferences"""
        try:
            import json
            settings = {
                'local_dest_dir': self.local_dest_dir,
                'drive_dest_folder': self.drive_dest_folder,
                'messenger_webhook_url': self.messenger_webhook_url
            }
            with open('settings.json', 'w') as f:
                json.dump(settings, f, indent=2)
        except:
            pass

    def create_button(self, parent, text, command, width=None, danger=False):
        bg = '#35130d' if danger else self.button_bg
        fg = self.danger_color if danger else self.button_fg
        active_bg = '#4a1a12' if danger else '#3a2514'
        pixel_width = max(92, (width or 10) * 9 + 26)
        button = RoundedButton(
            parent,
            text=text,
            command=command,
            width=pixel_width,
            height=36,
            bg=bg,
            fg=fg,
            accent=self.danger_color if danger else self.accent_color,
            active_bg=active_bg,
            radius=13,
            danger=danger
        )
        return button

    def create_nav_button(self, label, tab):
        button = tk.Button(
            self.nav_container,
            text=label,
            command=lambda: self.select_app_tab(tab),
            bg=self.panel_bg,
            fg=self.fg_color,
            activebackground=self.card_bg,
            activeforeground=self.fg_color,
            relief=tk.FLAT,
            anchor='w',
            font=('Arial', 12, 'bold'),
            padx=18,
            pady=16
        )
        button.pack(fill=tk.X, pady=4)
        self.nav_buttons[tab] = button

    def select_app_tab(self, tab):
        # Update button styles first
        for tab_frame, button in getattr(self, 'nav_buttons', {}).items():
            if tab_frame is tab:
                button.config(bg='#3b210f', fg=self.accent_color, highlightbackground=self.accent_color, highlightthickness=1)
            else:
                button.config(bg=self.panel_bg, fg=self.fg_color, highlightthickness=0)
        
        if hasattr(self, 'notebook'):
            self.notebook.place(x=0, y=0, relwidth=1, relheight=1)
            self.notebook.select(tab)

    def configure_ttk_styles(self):
        """Keep ttk widgets legible on the app's dark background."""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        style.configure(
            'TNotebook',
            background=self.bg_color,
            borderwidth=0
        )
        style.configure(
            'TNotebook.Tab',
            background=self.panel_bg,
            foreground=self.fg_color,
            padding=(10, 4)
        )
        style.map(
            'TNotebook.Tab',
            background=[('selected', self.card_bg), ('active', self.field_bg)],
            foreground=[('selected', self.fg_color), ('active', self.fg_color)]
        )
        style.layout('Sidebar.TNotebook.Tab', [])
        style.configure('Sidebar.TNotebook', background=self.bg_color, borderwidth=0)
        style.configure(
            'Dark.Horizontal.TProgressbar',
            background=self.accent_color,
            troughcolor='#2a1d12',
            bordercolor=self.bg_color,
            lightcolor=self.accent_color,
            darkcolor=self.accent_color
        )
        style.configure(
            'Treeview',
            background='#1e1e1e',
            foreground=self.fg_color,
            fieldbackground='#1e1e1e',
            rowheight=26,
            bordercolor=self.border_color
        )
        style.configure(
            'Treeview.Heading',
            background=self.button_bg,
            foreground=self.fg_color,
            font=('Arial', 9, 'bold')
        )
        style.map(
            'Treeview',
            background=[('selected', self.button_bg)],
            foreground=[('selected', self.fg_color)]
        )

    def create_widgets(self):
        self.configure_ttk_styles()

        self.top_bar = tk.Frame(self.root, bg='#100b07', highlightbackground=self.border_color, highlightthickness=1)
        self.top_bar.pack(fill=tk.X, padx=12, pady=(12, 0))
        tk.Label(
            self.top_bar,
            text="Music Distribution Organizer",
            bg='#100b07',
            fg=self.fg_color,
            font=('Arial', 13, 'bold'),
            padx=18,
            pady=14
        ).pack(side=tk.LEFT)

        drive_frame = tk.Frame(self.top_bar, bg='#100b07')
        drive_frame.pack(side=tk.RIGHT, padx=14, pady=8)
        self.drive_folder_label = tk.Label(
            drive_frame,
            text=self.get_drive_folder_display(),
            bg=self.button_bg,
            fg=self.fg_color,
            font=('Arial', 9, 'bold'),
            anchor='w',
            padx=12,
            pady=7,
            highlightbackground=self.border_color,
            highlightthickness=1
        )
        self.drive_folder_label.pack(side=tk.LEFT, padx=(0,8))
        self.create_button(drive_frame, "Use G-DAM", self.use_app_drive_root_folder, width=9).pack(side=tk.LEFT, padx=(0,5))
        self.create_button(drive_frame, "Reconnect", self.reconnect_drive, width=10).pack(side=tk.LEFT, padx=(0,5))
        self.create_button(drive_frame, "Open Drive", self.open_drive_folder_in_browser, width=10).pack(side=tk.LEFT, padx=(0,5))
        self.create_button(drive_frame, "View Contents", self.show_drive_folder_contents, width=12).pack(side=tk.LEFT)

        self.body_frame = tk.Frame(self.root, bg=self.bg_color)
        self.body_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.sidebar_frame = tk.Frame(self.body_frame, bg=self.panel_bg, width=210, highlightbackground=self.border_color, highlightthickness=1)
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, pady=(0, 0))
        self.sidebar_frame.pack_propagate(False)

        self.content_frame = tk.Frame(self.body_frame, bg=self.bg_color)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(12, 0))

        tk.Label(
            self.sidebar_frame,
            text="G-DAM",
            bg=self.panel_bg,
            fg=self.accent_color,
            font=('Arial', 16, 'bold'),
            anchor='w',
            padx=18,
            pady=18
        ).pack(fill=tk.X)
        self.nav_buttons = {}
        self.nav_container = tk.Frame(self.sidebar_frame, bg=self.panel_bg)
        self.nav_container.pack(fill=tk.X, padx=10, pady=(10, 0))

        bottom_controls = tk.Frame(self.sidebar_frame, bg=self.panel_bg)
        bottom_controls.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=14)
        self.create_button(bottom_controls, "Reconnect Google", self.reconnect_drive, width=18).pack(fill=tk.X, pady=(0, 8))
        self.create_button(bottom_controls, "Close Send Link", self.close_share_link, width=18, danger=True).pack(fill=tk.X, pady=(0, 8))
        self.share_link_label = tk.Label(bottom_controls, text="", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 8), anchor='w', wraplength=170)
        self.share_link_label.pack(fill=tk.X)

        self.notebook = ttk.Notebook(self.content_frame, style='Sidebar.TNotebook')
        self.notebook.place(x=0, y=0, relwidth=1, relheight=1)
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)

        # Artist Profiles tab
        self.artist_profiles_tab = tk.Frame(self.notebook, bg=self.bg_color)
        self.notebook.add(self.artist_profiles_tab, text='Artist Profiles')

        artist_profiles_header = tk.Frame(self.artist_profiles_tab, bg=self.bg_color)
        artist_profiles_header.pack(fill=tk.X, pady=(18, 12), padx=18)
        tk.Label(artist_profiles_header, text="Artist Profiles", bg=self.bg_color, fg=self.fg_color, font=('Arial', 22, 'bold')).pack(anchor='w')
        tk.Label(artist_profiles_header, text="View and manage artist profiles from G-DAM", bg=self.bg_color, fg=self.muted_fg, font=('Arial', 10)).pack(anchor='w', pady=(4, 0))

        # Artist profiles content area
        artist_profiles_content = tk.Frame(self.artist_profiles_tab, bg=self.bg_color)
        artist_profiles_content.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))

        # Source folder selector
        source_frame = tk.Frame(artist_profiles_content, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
        source_frame.pack(fill=tk.X, pady=(0, 12))
        tk.Label(source_frame, text="Source Folder", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 9, 'bold'), padx=12, pady=10).pack(side=tk.LEFT)
        self.artist_profiles_source_label = tk.Label(source_frame, text="Loading...", bg=self.field_bg, fg=self.fg_color, font=('Arial', 8), anchor='w', padx=8, pady=6)
        self.artist_profiles_source_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.create_button(source_frame, "Change", self.select_artist_profiles_source_folder, width=8).pack(side=tk.RIGHT, padx=(0, 8), pady=7)

        # Progress bar
        progress_frame = tk.Frame(artist_profiles_content, bg=self.bg_color)
        progress_frame.pack(fill=tk.X, pady=(0, 12))
        self.artist_profiles_progress_label = tk.Label(progress_frame, text="Overall Progress: 0%", bg=self.bg_color, fg=self.muted_fg, font=('Arial', 8), anchor='w')
        self.artist_profiles_progress_label.pack(side=tk.LEFT)
        self.artist_profiles_progress_bar = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, length=300, mode='determinate', maximum=100, style='Dark.Horizontal.TProgressbar')
        self.artist_profiles_progress_bar.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

        # Artist profiles display area
        profiles_frame = tk.Frame(artist_profiles_content, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
        profiles_frame.pack(fill=tk.BOTH, expand=True)

        # Icons area
        self.artist_icon_frame = tk.Frame(profiles_frame, bg=self.panel_bg, height=120)
        self.artist_icon_frame.pack(fill=tk.X, padx=12, pady=(12, 0))
        self.artist_icon_frame.pack_propagate(False)

        # Text area
        self.artist_profiles_text = tk.Text(
            profiles_frame,
            bg='#1e1e1e',
            fg=self.fg_color,
            font=('Arial', 10),
            wrap=tk.WORD,
            padx=15,
            pady=15
        )
        self.artist_profiles_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 12))
        self.artist_profiles_text.tag_config('header', foreground=self.accent_color, font=('Arial', 11, 'bold'))
        self.artist_profiles_text.tag_config('green', foreground='#7CFC00')
        self.artist_profiles_text.tag_config('yellow', foreground='#FFD700')
        self.artist_profiles_text.tag_config('red', foreground='#FF6347')
        self.artist_profiles_text.config(state=tk.DISABLED)

        # Songs tab
        self.songs_tab = tk.Frame(self.notebook, bg=self.bg_color)
        self.notebook.add(self.songs_tab, text='Songs')

        songs_header = tk.Frame(self.songs_tab, bg=self.bg_color)
        songs_header.pack(fill=tk.X, pady=(18, 12), padx=18)
        tk.Label(songs_header, text="Songs", bg=self.bg_color, fg=self.fg_color, font=('Arial', 22, 'bold')).pack(anchor='w')
        tk.Label(songs_header, text="Browse every G-DAM song folder and manage global collaborator credits", bg=self.bg_color, fg=self.muted_fg, font=('Arial', 10)).pack(anchor='w', pady=(4, 0))

        songs_source_frame = tk.Frame(self.songs_tab, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
        songs_source_frame.pack(fill=tk.X, padx=18, pady=(0, 12))
        tk.Label(songs_source_frame, text="Drive Library", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 9, 'bold'), padx=12, pady=10).pack(side=tk.LEFT)
        self.songs_source_label = tk.Label(songs_source_frame, text="Loading...", bg=self.field_bg, fg=self.fg_color, font=('Arial', 8), anchor='w', padx=8, pady=6)
        self.songs_source_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.create_button(songs_source_frame, "Refresh Songs", self.refresh_songs_tab, width=13).pack(side=tk.RIGHT, padx=(0, 8), pady=7)

        self.songs_summary_label = tk.Label(self.songs_tab, text="Songs: 0", bg=self.bg_color, fg=self.muted_fg, font=('Arial', 8), anchor='w')
        self.songs_summary_label.pack(fill=tk.X, padx=18, pady=(0, 8))

        songs_table_frame = tk.Frame(self.songs_tab, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
        songs_table_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))
        self.songs_tree = ttk.Treeview(
            songs_table_frame,
            columns=('artist', 'song', 'progress', 'credits', 'split'),
            show='headings',
            selectmode='browse'
        )
        self.songs_tree.heading('artist', text='Artist')
        self.songs_tree.heading('song', text='Song')
        self.songs_tree.heading('progress', text='Progress')
        self.songs_tree.heading('credits', text='Credits')
        self.songs_tree.heading('split', text='Split Total')
        self.songs_tree.column('artist', width=180, anchor='w')
        self.songs_tree.column('song', width=260, anchor='w')
        self.songs_tree.column('progress', width=90, anchor='center')
        self.songs_tree.column('credits', width=90, anchor='center')
        self.songs_tree.column('split', width=90, anchor='center')
        self.songs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        songs_scroll = ttk.Scrollbar(songs_table_frame, orient=tk.VERTICAL, command=self.songs_tree.yview)
        songs_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=10, padx=(0, 10))
        self.songs_tree.configure(yscrollcommand=songs_scroll.set)
        self.songs_tree.bind('<Double-1>', self.open_selected_song_window)
        self.songs_tree.bind('<Return>', self.open_selected_song_window)

        # Files tab
        self.files_tab = tk.Frame(self.notebook, bg=self.bg_color)
        self.notebook.add(self.files_tab, text='Files')

        files_header = tk.Frame(self.files_tab, bg=self.bg_color)
        files_header.pack(fill=tk.X, pady=(18, 12), padx=18)
        tk.Label(files_header, text="Files", bg=self.bg_color, fg=self.fg_color, font=('Arial', 22, 'bold')).pack(anchor='w')
        tk.Label(files_header, text="Organize local music files into G-DAM artist/song folders", bg=self.bg_color, fg=self.muted_fg, font=('Arial', 10)).pack(anchor='w', pady=(4, 0))

        local_frame = tk.Frame(self.files_tab, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
        local_frame.pack(fill=tk.X, padx=18, pady=(0, 12))
        tk.Label(local_frame, text="Local Destination", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 9, 'bold'), padx=12, pady=10).pack(side=tk.LEFT)
        self.local_dir_label = tk.Label(local_frame, text=self.local_dest_dir, bg=self.field_bg, fg=self.fg_color,
                                       font=('Arial', 8), anchor='w', padx=8, pady=6)
        self.local_dir_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.create_button(local_frame, "Choose", self.choose_local_dir, width=8).pack(side=tk.RIGHT, padx=(0, 8), pady=7)

        button_frame = tk.Frame(self.files_tab, bg=self.bg_color)
        button_frame.pack(fill=tk.X, pady=(0,8), padx=18)

        self.select_button = tk.Button(
            button_frame,
            text="Add Files",
            command=self.select_files,
            bg=self.card_bg,
            fg=self.button_fg,
            activebackground='#3a2514',
            activeforeground=self.button_fg,
            font=('Arial', 12, 'bold'),
            height=2
        )
        self.select_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))

        self.organize_button = tk.Button(
            button_frame,
            text="Organize + Upload",
            command=self.organize_and_upload,
            bg=self.card_bg,
            fg=self.button_fg,
            activebackground='#3a2514',
            activeforeground=self.button_fg,
            disabledforeground='#bdbdbd',
            font=('Arial', 10, 'bold'),
            height=2,
            state=tk.DISABLED
        )
        self.organize_button.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        self.operation_progress_frame = tk.Frame(self.files_tab, bg=self.bg_color)
        self.operation_progress_frame.pack(fill=tk.X, pady=(8,0), padx=18)
        self.operation_progress_label = tk.Label(
            self.operation_progress_frame,
            text="Progress: Ready",
            bg=self.bg_color,
            fg=self.muted_fg,
            font=('Arial', 8),
            anchor='w'
        )
        self.operation_progress_label.pack(side=tk.LEFT)
        self.operation_progress_bar = ttk.Progressbar(
            self.operation_progress_frame,
            orient=tk.HORIZONTAL,
            length=300,
            mode='determinate',
            maximum=100,
            style='Dark.Horizontal.TProgressbar'
        )
        self.operation_progress_bar.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10,0))

        self.main_text = tk.Text(
            self.files_tab,
            bg=self.panel_bg,
            fg=self.fg_color,
            font=('Arial', 10),
            wrap=tk.WORD,
            padx=20,
            pady=20
        )
        self.main_text.pack(fill=tk.BOTH, expand=True, pady=(8,18), padx=18)
        self.main_text.tag_config('green', foreground=self.success_color)
        self.main_text.tag_config('yellow', foreground=self.accent_color)
        self.main_text.tag_config('red', foreground=self.danger_color)

        self.update_main_display()

        # Hidden Drive preview widgets retained for logging/status methods.
        self.drive_preview_frame = tk.Frame(self.root, bg=self.bg_color)
        self.drive_preview_text = tk.Text(
            self.drive_preview_frame,
            bg='#1e1e1e',
            fg=self.fg_color,
            font=('Arial', 8),
            height=6,
            wrap=tk.WORD,
            padx=10,
            pady=10
        )
        self.drive_preview_text.tag_config('folder', foreground='#7CFC00')
        self.drive_preview_text.tag_config('file', foreground='#FFD700')
        self.drive_preview_text.config(state=tk.DISABLED)

        self.drive_progress_frame = tk.Frame(self.drive_preview_frame, bg=self.bg_color)
        self.drive_progress_label = tk.Label(self.drive_progress_frame, text="Progress: 0%", bg=self.bg_color, fg=self.fg_color, font=('Arial', 8))
        self.drive_progress_bar = ttk.Progressbar(
            self.drive_progress_frame,
            orient=tk.HORIZONTAL,
            length=300,
            mode='determinate',
            maximum=100,
            style='Dark.Horizontal.TProgressbar'
        )

        # Send Link tab
        self.send_link_tab = tk.Frame(self.notebook, bg=self.bg_color)
        self.notebook.add(self.send_link_tab, text='Send Link')

        send_link_header = tk.Frame(self.send_link_tab, bg=self.bg_color)
        send_link_header.pack(fill=tk.X, padx=18, pady=(18, 12))

        send_title = tk.Frame(send_link_header, bg=self.bg_color)
        send_title.pack(fill=tk.X, pady=(0, 12))
        tk.Label(send_title, text="Send Link", bg=self.bg_color, fg=self.fg_color, font=('Arial', 22, 'bold')).pack(anchor='w')
        tk.Label(send_title, text="Create a sender portal for one G-DAM song folder", bg=self.bg_color, fg=self.muted_fg, font=('Arial', 10)).pack(anchor='w', pady=(4,0))

        send_controls = tk.Frame(send_link_header, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
        send_controls.pack(fill=tk.X)

        tk.Label(send_controls, text="Artist", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 9, 'bold'), padx=12, pady=12).pack(side=tk.LEFT)
        self.send_link_artist_var = tk.StringVar()
        self.send_link_artist_combo = ttk.Combobox(
            send_controls,
            textvariable=self.send_link_artist_var,
            font=('Arial', 9),
            width=22
        )
        self.send_link_artist_combo.pack(side=tk.LEFT, padx=(5, 20))
        self.send_link_artist_combo.bind('<<ComboboxSelected>>', self.on_send_link_artist_selected)
        self.send_link_artist_combo.bind('<FocusOut>', self.on_send_link_artist_typed)
        self.send_link_artist_combo.bind('<Enter>', lambda e: self.open_combobox(self.send_link_artist_combo))

        tk.Label(send_controls, text="Song", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 9, 'bold'), padx=12, pady=12).pack(side=tk.LEFT)
        self.send_link_song_var = tk.StringVar()
        self.send_link_song_combo = ttk.Combobox(
            send_controls,
            textvariable=self.send_link_song_var,
            font=('Arial', 9),
            width=22
        )
        self.send_link_song_combo.pack(side=tk.LEFT, padx=(5, 10))
        self.send_link_song_combo.bind('<Enter>', lambda e: self.open_combobox(self.send_link_song_combo))

        self.create_button(send_controls, "Create Send Link", self.create_send_link_from_tab, width=15).pack(side=tk.LEFT, padx=(0, 5))
        self.create_button(send_controls, "Refresh Lists", self.refresh_send_link_dropdowns, width=12).pack(side=tk.LEFT, padx=(0, 8))

        self.send_link_info_text = tk.Text(
            self.send_link_tab,
            bg=self.panel_bg,
            fg=self.fg_color,
            font=('Arial', 10),
            wrap=tk.WORD,
            padx=20,
            pady=20,
            height=25
        )
        self.send_link_info_text.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))
        self.send_link_info_text.tag_config('green', foreground=self.success_color)
        self.send_link_info_text.tag_config('yellow', foreground=self.accent_color)
        self.send_link_info_text.tag_config('red', foreground=self.danger_color)
        self.send_link_info_text.tag_config('header', foreground=self.accent_hover, font=('Arial', 11, 'bold'))
        self.send_link_info_text.config(state=tk.DISABLED)

        self.create_collaborators_tab()

        self.update_send_link_display()
        self.refresh_send_link_dropdowns()
        self.create_nav_button("Artist Profiles", self.artist_profiles_tab)
        self.create_nav_button("Songs", self.songs_tab)
        self.create_nav_button("Files", self.files_tab)
        self.create_nav_button("Send Link", self.send_link_tab)
        self.create_nav_button("Collaborators", self.collaborators_tab)
        self.select_app_tab(self.artist_profiles_tab)

    def create_collaborators_tab(self):
        self.collaborators_tab = tk.Frame(self.notebook, bg=self.bg_color)
        self.notebook.add(self.collaborators_tab, text='Collaborators')
        self.selected_collaborator_profile_id = None

        header = tk.Frame(self.collaborators_tab, bg=self.bg_color)
        header.pack(fill=tk.X, pady=(18, 12), padx=18)
        tk.Label(header, text="Collaborators", bg=self.bg_color, fg=self.fg_color, font=('Arial', 22, 'bold')).pack(anchor='w')
        tk.Label(header, text="Edit global collaborator profiles saved in G-DAM", bg=self.bg_color, fg=self.muted_fg, font=('Arial', 10)).pack(anchor='w', pady=(4, 0))

        summary_frame = tk.Frame(self.collaborators_tab, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
        summary_frame.pack(fill=tk.X, padx=18, pady=(0, 12))
        tk.Label(summary_frame, text="Profile Library", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 9, 'bold'), padx=12, pady=10).pack(side=tk.LEFT)
        self.collaborators_summary_label = tk.Label(summary_frame, text="Loading...", bg=self.field_bg, fg=self.fg_color, font=('Arial', 8), anchor='w', padx=8, pady=6)
        self.collaborators_summary_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.create_button(summary_frame, "Refresh", self.refresh_collaborators_tab, width=9).pack(side=tk.RIGHT, padx=(0, 8), pady=7)

        body = tk.Frame(self.collaborators_tab, bg=self.bg_color)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))

        list_panel = tk.Frame(body, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
        list_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        self.collaborators_tree = ttk.Treeview(
            list_panel,
            columns=('name', 'email'),
            show='headings',
            selectmode='browse'
        )
        self.collaborators_tree.heading('name', text='Name')
        self.collaborators_tree.heading('email', text='Email')
        self.collaborators_tree.column('name', width=180, anchor='w')
        self.collaborators_tree.column('email', width=240, anchor='w')
        self.collaborators_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        collaborators_scroll = ttk.Scrollbar(list_panel, orient=tk.VERTICAL, command=self.collaborators_tree.yview)
        collaborators_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=10, padx=(0, 10))
        self.collaborators_tree.configure(yscrollcommand=collaborators_scroll.set)
        self.collaborators_tree.bind('<<TreeviewSelect>>', self.load_selected_collaborator_profile)

        editor = tk.Frame(body, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1, width=360)
        editor.pack(side=tk.RIGHT, fill=tk.BOTH)
        editor.pack_propagate(False)
        tk.Label(editor, text="Collaborator Info", bg=self.panel_bg, fg=self.accent_color, font=('Arial', 13, 'bold')).pack(anchor='w', padx=14, pady=(14, 8))

        self.collaborator_name_var = tk.StringVar()
        self.collaborator_email_var = tk.StringVar()
        self.collaborator_bmi_var = tk.StringVar()
        self.collaborator_ascap_var = tk.StringVar()
        self.collaborator_pro_var = tk.StringVar()

        def add_editor_entry(label, variable):
            tk.Label(editor, text=label, bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 8, 'bold')).pack(anchor='w', padx=14, pady=(8, 3))
            entry = tk.Entry(editor, textvariable=variable, bg=self.field_bg, fg=self.fg_color, insertbackground=self.fg_color)
            entry.pack(fill=tk.X, padx=14)
            return entry

        add_editor_entry("Name", self.collaborator_name_var)
        add_editor_entry("Email", self.collaborator_email_var)
        add_editor_entry("BMI", self.collaborator_bmi_var)
        add_editor_entry("ASCAP", self.collaborator_ascap_var)
        add_editor_entry("PRO", self.collaborator_pro_var)
        tk.Label(editor, text="Notes", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 8, 'bold')).pack(anchor='w', padx=14, pady=(8, 3))
        self.collaborator_notes_text = tk.Text(
            editor,
            bg=self.field_bg,
            fg=self.fg_color,
            insertbackground=self.fg_color,
            height=7,
            wrap=tk.WORD,
            padx=8,
            pady=6
        )
        self.collaborator_notes_text.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))

        actions = tk.Frame(editor, bg=self.panel_bg)
        actions.pack(fill=tk.X, padx=14, pady=(0, 14))
        self.create_button(actions, "New", self.clear_collaborator_editor, width=7).pack(side=tk.LEFT)
        self.create_button(actions, "Save", self.save_collaborator_profile_from_tab, width=8).pack(side=tk.RIGHT)

    def clear_collaborator_editor(self):
        self.selected_collaborator_profile_id = None
        if hasattr(self, 'collaborators_tree'):
            for item in self.collaborators_tree.selection():
                self.collaborators_tree.selection_remove(item)
        self.collaborator_name_var.set('')
        self.collaborator_email_var.set('')
        self.collaborator_bmi_var.set('')
        self.collaborator_ascap_var.set('')
        self.collaborator_pro_var.set('')
        self.collaborator_notes_text.delete(1.0, tk.END)

    def refresh_collaborators_tab(self):
        if not hasattr(self, 'collaborators_tree'):
            return

        for item in self.collaborators_tree.get_children():
            self.collaborators_tree.delete(item)

        if not self.drive:
            self.collaborators_summary_label.config(text="Manager Google Drive is not authenticated yet.")
            return

        try:
            self.load_credit_data()
            for profile in self.collaborator_profiles:
                profile_id = profile.get('profile_id')
                if not profile_id:
                    continue
                self.collaborators_tree.insert(
                    '',
                    tk.END,
                    iid=profile_id,
                    values=(profile.get('name', ''), profile.get('email', ''))
                )
            self.collaborators_summary_label.config(
                text="{} profile(s) in {}".format(len(self.collaborator_profiles), CREDITS_DATA_FOLDER_NAME)
            )
        except Exception as e:
            self.collaborators_summary_label.config(text="Could not load collaborators.")
            self.log("Could not refresh collaborators tab: {}".format(str(e)))

    def load_selected_collaborator_profile(self, event=None):
        selection = self.collaborators_tree.selection()
        if not selection:
            return

        profile_id = selection[0]
        profile = self.get_collaborator_profile_by_id(profile_id)
        if not profile:
            return

        self.selected_collaborator_profile_id = profile_id
        self.collaborator_name_var.set(profile.get('name', ''))
        self.collaborator_email_var.set(profile.get('email', ''))
        self.collaborator_bmi_var.set(profile.get('bmi', ''))
        self.collaborator_ascap_var.set(profile.get('ascap', ''))
        self.collaborator_pro_var.set(profile.get('pro', ''))
        self.collaborator_notes_text.delete(1.0, tk.END)
        self.collaborator_notes_text.insert(tk.END, profile.get('notes', ''))

    def save_collaborator_profile_from_tab(self):
        if not self.drive:
            messagebox.showerror("Collaborators", "Google Drive is not authenticated.")
            return

        name = self.collaborator_name_var.get().strip()
        if not name:
            messagebox.showwarning("Collaborators", "Enter a collaborator name.")
            return

        profile_info = {
            'email': self.collaborator_email_var.get().strip(),
            'bmi': self.collaborator_bmi_var.get().strip(),
            'ascap': self.collaborator_ascap_var.get().strip(),
            'pro': self.collaborator_pro_var.get().strip(),
            'notes': self.collaborator_notes_text.get(1.0, tk.END).strip()
        }

        try:
            self.load_credit_data()
            profile = self.get_collaborator_profile_by_id(self.selected_collaborator_profile_id) if self.selected_collaborator_profile_id else None
            if profile:
                profile['name'] = name
                profile['email'] = profile_info['email']
                profile['bmi'] = profile_info['bmi']
                profile['ascap'] = profile_info['ascap']
                profile['pro'] = profile_info['pro']
                profile['notes'] = profile_info['notes']
                profile.pop('phone', None)
                profile.pop('publisher', None)
                profile['updated_at'] = int(time.time())
                self.collaborator_profiles.sort(key=lambda item: item.get('name', '').casefold())
            else:
                profile = self.get_or_create_collaborator_profile(name, profile_info)

            self.save_drive_json_file(COLLABORATOR_PROFILES_JSON, {'profiles': self.collaborator_profiles})
            self.selected_collaborator_profile_id = profile.get('profile_id')
            self.refresh_collaborators_tab()
            if self.selected_collaborator_profile_id in self.collaborators_tree.get_children():
                self.collaborators_tree.selection_set(self.selected_collaborator_profile_id)
                self.collaborators_tree.see(self.selected_collaborator_profile_id)
            self.refresh_songs_tab()
            messagebox.showinfo("Collaborators", "Collaborator profile saved.")
        except Exception as e:
            messagebox.showerror("Collaborators", "Unable to save collaborator profile:\n{}".format(str(e)))

    def create_send_link_from_tab(self):
        """Create send link from the Send Link tab input fields."""
        artist = self.send_link_artist_var.get().strip()
        song = self.send_link_song_var.get().strip()
        if not artist or not song:
            messagebox.showwarning("Input Required", "Please enter both artist and song name.")
            return
        self.create_share_link_folder(artist, song)
        self.update_send_link_display()

    def refresh_send_link_dropdowns(self):
        """Populate send-link artist/song dropdowns from the G-DAM Drive folder."""
        if not hasattr(self, 'send_link_artist_combo'):
            return

        self.send_link_artist_options = {}
        self.send_link_song_options = {}
        self.send_link_artist_combo['values'] = []
        self.send_link_song_combo['values'] = []

        if not self.drive:
            return

        try:
            app_root_id = self.ensure_app_drive_root_folder()
            artist_folders = self.get_drive_child_folders(app_root_id)
            artist_folders = [
                folder for folder in artist_folders
                if folder.get('title') != PROFILE_IMAGE_FOLDER_NAME
            ]
            artist_names = sorted([folder.get('title', '') for folder in artist_folders if folder.get('title')], key=str.casefold)
            self.send_link_artist_options = {
                folder.get('title', '').strip().casefold(): folder
                for folder in artist_folders
                if folder.get('title')
            }
            self.send_link_artist_combo['values'] = artist_names

            if self.send_link_artist_var.get().strip():
                self.refresh_send_link_song_dropdown(self.send_link_artist_var.get().strip())
        except Exception as e:
            self.log("Could not refresh send-link artist list: {}".format(str(e)))

    def refresh_send_link_song_dropdown(self, artist_name):
        """Populate song dropdown for the selected or typed artist."""
        if not hasattr(self, 'send_link_song_combo'):
            return

        self.send_link_song_options = {}
        self.send_link_song_combo['values'] = []
        artist_key = artist_name.strip().casefold()
        artist_folder = self.send_link_artist_options.get(artist_key)
        if not artist_folder:
            return

        try:
            song_folders = [
                folder for folder in self.get_drive_child_folders(artist_folder['id'])
                if self.drive_folder_looks_like_song_drop(folder)
            ]
            song_names = sorted([folder.get('title', '') for folder in song_folders if folder.get('title')], key=str.casefold)
            self.send_link_song_options = {
                folder.get('title', '').strip().casefold(): folder
                for folder in song_folders
                if folder.get('title')
            }
            self.send_link_song_combo['values'] = song_names
        except Exception as e:
            self.log("Could not refresh song list for {}: {}".format(artist_name, str(e)))

    def on_send_link_artist_selected(self, event=None):
        self.send_link_song_var.set('')
        self.refresh_send_link_song_dropdown(self.send_link_artist_var.get().strip())

    def on_send_link_artist_typed(self, event=None):
        self.refresh_send_link_song_dropdown(self.send_link_artist_var.get().strip())

    def open_combobox(self, combobox):
        """Open a combobox dropdown on hover."""
        if combobox['values']:
            combobox.focus()
            combobox.event_generate('<Down>')

    def get_selected_send_link_song_folder_id(self, artist, song):
        artist_folder = self.send_link_artist_options.get(artist.strip().casefold())
        song_folder = self.send_link_song_options.get(song.strip().casefold())
        if artist_folder and song_folder:
            return song_folder.get('id')
        return None

    def update_send_link_display(self):
        """Update the Send Link tab display."""
        self.send_link_info_text.config(state=tk.NORMAL)
        self.send_link_info_text.delete(1.0, tk.END)

        if self.current_share_folder_id and self.share_link_url:
            self.send_link_info_text.insert(tk.END, "ACTIVE SEND LINK\n", 'header')
            self.send_link_info_text.insert(tk.END, "{}\n\n".format('-'*60))
            if self.sender_link_expires_at:
                self.send_link_info_text.insert(tk.END, "Expires:\n")
                self.send_link_info_text.insert(tk.END, "{}\n".format(self.format_sender_link_expiration()))
                self.send_link_info_text.insert(tk.END, "Remaining: {}\n\n".format(self.format_sender_link_time_remaining()))
            if self.sender_portal_url:
                if self.ngrok_public_url:
                    self.send_link_info_text.insert(tk.END, "Public sender portal link:\n")
                else:
                    self.send_link_info_text.insert(tk.END, "Sender portal link for same-network sharing:\n")
                self.send_link_info_text.insert(tk.END, "{}\n\n".format(self.sender_portal_url))
                if self.ngrok_public_url and self.sender_portal_lan_url:
                    self.send_link_info_text.insert(tk.END, "Same-network backup link:\n")
                    self.send_link_info_text.insert(tk.END, "{}\n\n".format(self.sender_portal_lan_url))
                if self.sender_portal_local_url:
                    self.send_link_info_text.insert(tk.END, "Local link for this computer:\n")
                    self.send_link_info_text.insert(tk.END, "{}\n\n".format(self.sender_portal_local_url))
                if self.ngrok_public_url:
                    self.send_link_info_text.insert(tk.END, "ngrok tunnel is active. Keep this app and ngrok running while senders upload.\n\n", 'green')
                else:
                    note = (
                        "Note: senders must be on the same network, and Windows Firewall may ask to allow Python. "
                        "For outside-network sharing, start an ngrok tunnel for this port.\n\n"
                    )
                    if self.ngrok_error:
                        note = "ngrok was not started: {}\n\n{}".format(self.ngrok_error, note)
                    self.send_link_info_text.insert(tk.END, note, 'yellow')
            self.send_link_info_text.insert(tk.END, "Google Drive folder:\n")
            self.send_link_info_text.insert(tk.END, "{}\n\n".format(self.share_link_url))

            try:
                items = self.get_drive_folder_contents(self.current_share_folder_id)
                folder_status = self.build_drive_folder_status(items, self.get_drive_folder_display())

                self.send_link_info_text.insert(tk.END, "REQUIREMENTS\n", 'header')
                self.send_link_info_text.insert(tk.END, "{}\n".format('-'*60))
                if folder_status['missing']:
                    self.send_link_info_text.insert(tk.END, "Missing required tags:\n")
                    for tag in folder_status['missing']:
                        self.send_link_info_text.insert(tk.END, "  - {}\n".format(tag), 'red')
                    self.send_link_info_text.insert(tk.END, "\n")
                else:
                    self.send_link_info_text.insert(tk.END, "All required tags are present! [OK]\n", 'green')
                    self.send_link_info_text.insert(tk.END, "The send link will stay open until the 7-day expiration or until you close it.\n\n")

                self.send_link_info_text.insert(tk.END, "Present tags: {}\n\n".format(', '.join(folder_status['present']) if folder_status['present'] else 'None'))
                if folder_status.get('optional_present'):
                    self.send_link_info_text.insert(
                        tk.END,
                        "Optional tags present: {} (not required for progress)\n\n".format(', '.join(folder_status['optional_present'])),
                        'green'
                    )

                if items:
                    self.send_link_info_text.insert(tk.END, "RECEIVED FILES\n", 'header')
                    self.send_link_info_text.insert(tk.END, "{}\n".format('-'*60))
                    for item in items[:50]:
                        icon = '[Folder]' if item['mimeType'] == 'application/vnd.google-apps.folder' else '[File]'
                        self.send_link_info_text.insert(tk.END, "{} {}\n".format(icon, item['title']))
                    if len(items) > 50:
                        self.send_link_info_text.insert(tk.END, "...and {} more items\n".format(len(items) - 50))
                else:
                    self.send_link_info_text.insert(tk.END, "No files received yet.\n")
            except Exception as e:
                self.send_link_info_text.insert(tk.END, "Error loading send link status: {}\n".format(str(e)), 'red')
        else:
            self.send_link_info_text.insert(tk.END, "NO ACTIVE SEND LINK\n", 'header')
            self.send_link_info_text.insert(tk.END, "{}\n\n".format('-'*60))
            self.send_link_info_text.insert(tk.END, "Choose an artist and song from the dropdowns, or type new names, then click 'Create Send Link' to generate a shareable folder for senders.\n\n")
            self.send_link_info_text.insert(tk.END, "Once created:\n")
            self.send_link_info_text.insert(tk.END, "1. A local browser portal opens\n")
            self.send_link_info_text.insert(tk.END, "2. Senders upload files with proper naming\n")
            self.send_link_info_text.insert(tk.END, "3. The app uploads those files to the active Drive song folder\n")
            self.send_link_info_text.insert(tk.END, "4. You receive notifications of new uploads\n")
            self.send_link_info_text.insert(tk.END, "5. The link stays alive for 7 days while this app and ngrok keep running\n")
            self.send_link_info_text.insert(tk.END, "Optional tag accepted: Session Files. It does not affect completion progress.\n")

        self.send_link_info_text.config(state=tk.DISABLED)

    def on_tab_changed(self, event=None):
        """Handle tab changes"""
        current_tab = self.notebook.select()
        if current_tab == str(self.artist_profiles_tab):
            self.update_artist_profiles_display()
        elif current_tab == str(self.songs_tab):
            self.refresh_songs_tab()
        elif hasattr(self, 'collaborators_tab') and current_tab == str(self.collaborators_tab):
            self.refresh_collaborators_tab()

    def choose_local_dir(self):
        """Choose local destination directory"""
        from tkinter import filedialog
        dir_path = filedialog.askdirectory(title="Choose local destination folder")
        if dir_path:
            self.local_dest_dir = dir_path
            self.local_dir_label.config(text=dir_path)
            self.save_settings()
            self.log("Local destination changed to: {}".format(dir_path))

    def choose_drive_folder(self):
        """Choose Google Drive destination folder"""
        if not self.drive:
            messagebox.showerror("Error", "Google Drive not authenticated")
            return
        self.show_drive_folder_picker()

    def select_artist_profiles_source_folder(self):
        """Choose source folder for artist profiles"""
        if not self.drive:
            messagebox.showerror("Error", "Google Drive not authenticated")
            return
        self.show_drive_folder_picker(callback=self.set_artist_profiles_source_folder)

    def set_artist_profiles_source_folder(self, folder_id):
        """Set the source folder for artist profiles"""
        self.artist_profiles_source_folder = folder_id
        self.save_settings()
        self.update_artist_profiles_display()

    def use_app_drive_root_folder(self):
        """Reset the visible Drive folder to the app-owned parent folder."""
        if not self.drive:
            messagebox.showerror("Error", "Google Drive not authenticated")
            return
        app_root_id = self.ensure_app_drive_root_folder()
        if not app_root_id:
            messagebox.showerror("Drive Error", "Unable to create or find the G-DAM folder.")
            return
        self.drive_dest_folder = app_root_id
        self.artist_profiles_source_folder = app_root_id
        self.drive_folder_label.config(text=self.get_drive_folder_display())
        self.save_settings()
        self.update_drive_preview_display()
        self.update_artist_profiles_display()
        self.refresh_songs_tab()
        self.refresh_collaborators_tab()
        self.refresh_send_link_dropdowns()
        self.log("Using app Drive parent folder: {}".format(self.get_drive_folder_path(app_root_id)))

    def get_drive_folder_display(self):
        """Get display text for current Google Drive folder"""
        if self.drive_dest_folder == 'root':
            return "Root Folder"
        else:
            # Try to get folder name from cache or Drive
            try:
                folder = self.drive.CreateFile({'id': self.drive_dest_folder})
                folder.FetchMetadata(fields='title')
                return folder['title']
            except:
                return "Custom Folder"

    def clear_drive_cache(self):
        self.drive_folder_contents_cache = {}
        self.drive_metadata_cache = {}
        self.drive_path_cache = {}

    def get_drive_folder_contents(self, folder_id, use_cache=True):
        """Get child items for a Google Drive folder."""
        if use_cache and folder_id in self.drive_folder_contents_cache:
            return self.drive_folder_contents_cache[folder_id]

        if folder_id == 'root':
            query = "trashed=false and 'root' in parents"
        else:
            query = "trashed=false and '{}' in parents".format(folder_id)
        try:
            items = self.drive.ListFile({'q': query}).GetList()
            if use_cache:
                self.drive_folder_contents_cache[folder_id] = items
            return items
        except Exception:
            return []

    def get_drive_folder_metadata(self, folder_id, use_cache=True):
        """Return basic metadata for a Drive folder."""
        if folder_id == 'root':
            return {'id': 'root', 'title': 'My Drive', 'parents': []}
        if use_cache and folder_id in self.drive_metadata_cache:
            return self.drive_metadata_cache[folder_id]

        folder = self.drive.CreateFile({'id': folder_id})
        folder.FetchMetadata(fields='id,title,parents,mimeType')
        if use_cache:
            self.drive_metadata_cache[folder_id] = folder
        return folder

    def get_drive_parent_id(self, folder_id):
        if not folder_id or folder_id == 'root':
            return 'root'
        try:
            metadata = self.get_drive_folder_metadata(folder_id)
            parents = metadata.get('parents') or []
            return parents[0].get('id') if parents else 'root'
        except Exception:
            return 'root'

    def get_artist_library_root_for_upload(self, artist=None, song=None):
        """
        Return the folder that should contain artist folders.

        All manager and sender uploads live under the app-owned Drive folder,
        so new artists never depend on whatever folder the manager is previewing.
        """
        return self.ensure_app_drive_root_folder() or 'root'

    def find_drive_child_folder_case_insensitive(self, title, parent_id='root'):
        """Find a child folder by title without treating case differences as new folders."""
        wanted = title.strip().casefold()
        if not wanted:
            return None

        if parent_id == 'root':
            query = "mimeType='application/vnd.google-apps.folder' and trashed=false and 'root' in parents"
        else:
            query = "mimeType='application/vnd.google-apps.folder' and trashed=false and '{}' in parents".format(parent_id)

        folders = self.drive.ListFile({'q': query}).GetList()
        for folder in folders:
            if folder.get('title', '').strip().casefold() == wanted:
                return folder
        return None

    def get_drive_folder_path(self, folder_id):
        """Resolve a Drive folder path from the given folder ID."""
        if folder_id == 'root':
            return 'My Drive'
        if folder_id in self.drive_path_cache:
            return self.drive_path_cache[folder_id]

        try:
            folder = self.drive.CreateFile({'id': folder_id})
            folder.FetchMetadata(fields='title,parents')
            titles = [folder['title']]
            parents = folder.get('parents') or []
            while parents:
                parent_id = parents[0].get('id')
                if not parent_id or parent_id == 'root':
                    titles.insert(0, 'My Drive')
                    break
                parent_folder = self.drive.CreateFile({'id': parent_id})
                parent_folder.FetchMetadata(fields='title,parents')
                titles.insert(0, parent_folder['title'])
                parents = parent_folder.get('parents') or []
            path = '/'.join(titles)
            self.drive_path_cache[folder_id] = path
            return path
        except Exception:
            return self.get_drive_folder_display()

    def build_drive_folder_status(self, items, folder_name=None):
        """Build missing tag status from Drive folder contents."""
        required = self.get_required_tags()
        optional = self.get_optional_tags()
        present_tags = set()
        optional_tags = set()

        def tag_from_title(title):
            title_lower = title.lower()
            for tag in required + optional:
                if tag.lower() in title_lower:
                    return tag
            return None

        # If the current folder title contains a tag, count it.
        if folder_name:
            folder_tag = tag_from_title(folder_name)
            if folder_tag in required:
                present_tags.add(folder_tag)
            elif folder_tag in optional:
                optional_tags.add(folder_tag)

        for item in items:
            if item.get('mimeType') == 'application/vnd.google-apps.folder':
                folder_title = item.get('title', '')
                folder_tag = tag_from_title(folder_title)
                if folder_tag in required:
                    present_tags.add(folder_tag)
                elif folder_tag in optional:
                    optional_tags.add(folder_tag)
            else:
                artist, song, tag = self.parse_filename(item.get('title', ''))
                if tag:
                    normalized_tag = self.normalize_tag(tag)
                    if normalized_tag in required:
                        present_tags.add(normalized_tag)
                    elif normalized_tag in optional:
                        optional_tags.add(normalized_tag)

        missing = [t for t in required if t not in present_tags]
        percent = int(len(present_tags) / len(required) * 100) if required else 0
        return {
            'present': sorted(present_tags),
            'optional_present': sorted(optional_tags),
            'missing': missing,
            'percent': percent
        }

    def is_drive_folder(self, item):
        return item.get('mimeType') == 'application/vnd.google-apps.folder'

    def title_matches_required_tag(self, title):
        title_key = title.strip().casefold()
        return any(title_key == tag.casefold() for tag in self.get_required_tags())

    def get_drive_child_folders(self, parent_id):
        return [
            item for item in self.get_drive_folder_contents(parent_id)
            if self.is_drive_folder(item)
        ]

    def get_artist_profile_image_folder(self, artist_folder_id, create=False):
        if create:
            return self.get_or_create_drive_folder(PROFILE_IMAGE_FOLDER_NAME, artist_folder_id)

        folder = self.find_drive_child_folder_case_insensitive(PROFILE_IMAGE_FOLDER_NAME, artist_folder_id)
        return folder['id'] if folder else None

    def get_artist_profile_image_file(self, artist_folder_id):
        image_folder_id = self.get_artist_profile_image_folder(artist_folder_id, create=False)
        if not image_folder_id:
            return None

        items = self.get_drive_folder_contents(image_folder_id)
        image_items = [
            item for item in items
            if not self.is_drive_folder(item) and item.get('mimeType', '').startswith('image/')
        ]
        if not image_items:
            return None
        return image_items[0]

    def get_artist_initials(self, artist_name):
        parts = [part for part in re.split(r'\s+', artist_name.strip()) if part]
        if not parts:
            return '?'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return ''.join(part[0].upper() for part in parts[:2])

    def load_artist_profile_photo(self, profile, size=72):
        """Return a circular PhotoImage for an artist profile, if Pillow and image data are available."""
        if not PIL_AVAILABLE or not profile.get('image_file_id'):
            return None

        cache_key = (profile['id'], profile.get('image_file_id'), size)
        if cache_key in self.artist_profile_images:
            return self.artist_profile_images[cache_key]

        try:
            cache_dir = os.path.join(get_app_data_dir(), 'profile_image_cache')
            os.makedirs(cache_dir, exist_ok=True)
            image_path = os.path.join(cache_dir, '{}_{}'.format(profile['id'], profile.get('image_title', 'profile_image')))

            drive_file = self.drive.CreateFile({'id': profile['image_file_id']})
            drive_file.GetContentFile(image_path)

            image = Image.open(image_path).convert('RGBA')
            image.thumbnail((size, size), Image.LANCZOS)

            square = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            x = (size - image.width) // 2
            y = (size - image.height) // 2
            square.paste(image, (x, y))

            mask = Image.new('L', (size, size), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, size - 1, size - 1), fill=255)
            square.putalpha(mask)

            photo = ImageTk.PhotoImage(square)
            self.artist_profile_images[cache_key] = photo
            return photo
        except Exception as e:
            self.log("Could not load profile image for {}: {}".format(profile.get('artist', 'artist'), str(e)))
            return None

    def render_artist_profile_icons(self, profiles):
        if not hasattr(self, 'artist_icon_frame'):
            return

        for child in self.artist_icon_frame.winfo_children():
            child.destroy()

        self.artist_profile_images = {}
        if not profiles:
            return

        def draw_card(card, profile, highlighted=False):
            card.delete('all')
            glow_color = self.accent_hover if highlighted else self.border_color
            border_color = self.accent_color if highlighted else '#6b3b15'
            draw_rounded_rect(card, 3, 3, 227, 159, 16, outline='#3b210f', fill=self.card_bg, width=1)
            if highlighted:
                draw_rounded_rect(card, 0, 0, 230, 162, 19, outline=self.accent_hover, fill='', width=1)
                draw_rounded_rect(card, 1, 1, 229, 161, 18, outline=glow_color, fill='', width=1)
            draw_rounded_rect(card, 5, 5, 225, 157, 15, outline=border_color, fill='', width=1)

            photo = self.load_artist_profile_photo(profile, size=72)
            if photo:
                card.create_image(56, 52, image=photo)
                self.artist_profile_images[('card', profile['id'])] = photo
            else:
                card.create_oval(20, 16, 92, 88, fill='#3a2514', outline=self.accent_color if highlighted else self.border_color, width=2)
                card.create_text(
                    56,
                    52,
                    text=self.get_artist_initials(profile['artist']),
                    fill=self.fg_color,
                    font=('Arial', 16, 'bold')
                )

            percent_color = self.success_color if profile['percent'] >= 80 else self.accent_color if profile['percent'] >= 50 else self.danger_color
            card.create_oval(150, 30, 204, 84, outline='#4b3524', width=6)
            card.create_arc(150, 30, 204, 84, start=90, extent=-int(360 * profile['percent'] / 100), style=tk.ARC, outline=percent_color, width=6)
            card.create_text(177, 57, text="{}%".format(profile['percent']), fill=self.fg_color, font=('Arial', 13, 'bold'))
            card.create_text(22, 106, text=profile['artist'][:22], fill=self.fg_color, font=('Arial', 14, 'bold'), anchor='w')
            card.create_text(
                22,
                130,
                text="{} Songs  -  {} Complete".format(profile['total_songs'], profile['completed_songs']),
                fill=self.muted_fg,
                font=('Arial', 9),
                anchor='w'
            )
            card.create_line(22, 146, 202, 146, fill='#4b3524', width=5)
            card.create_line(22, 146, 22 + int(180 * profile['percent'] / 100), 146, fill=percent_color, width=5)

        for profile in profiles:
            card = tk.Canvas(
                self.artist_icon_frame,
                width=230,
                height=162,
                bg=self.bg_color,
                highlightthickness=0,
                bd=0,
                cursor='hand2'
            )
            card.pack(side=tk.LEFT, padx=(0, 16), pady=2)
            draw_card(card, profile, highlighted=False)
            card.bind('<Button-1>', lambda event, item=profile: self.open_artist_profile_popup(item))
            card.bind('<Enter>', lambda event, item=profile, card=card: self.on_artist_card_enter(event, card, item, draw_card))
            card.bind('<Motion>', lambda event, item=profile: self.move_artist_hover_popup(event, item))
            card.bind('<Leave>', lambda event, item=profile, card=card: self.on_artist_card_leave(card, item, draw_card))

    def drive_folder_looks_like_song_drop(self, folder, items=None):
        """Return True when a folder appears to be a Song folder in Artist/Song/Tag."""
        if self.title_matches_required_tag(folder.get('title', '')):
            return False

        items = items if items is not None else self.get_drive_folder_contents(folder['id'])
        if not items:
            return False

        required = self.get_required_tags()
        for item in items:
            if self.is_drive_folder(item):
                if self.title_matches_required_tag(item.get('title', '')):
                    return True
            else:
                artist, song, tag = self.parse_filename(item.get('title', ''))
                if artist and song and tag and self.normalize_tag(tag) in required:
                    return True
        return False

    def on_artist_card_enter(self, event, card, profile, draw_card):
        draw_card(card, profile, highlighted=True)
        if self.artist_hover_after_id:
            try:
                self.root.after_cancel(self.artist_hover_after_id)
            except Exception:
                pass
        self.artist_hover_after_id = None
        self.show_artist_hover_popup(event, profile)

    def on_artist_card_leave(self, card, profile, draw_card):
        draw_card(card, profile, highlighted=False)
        if self.artist_hover_after_id:
            try:
                self.root.after_cancel(self.artist_hover_after_id)
            except Exception:
                pass
            self.artist_hover_after_id = None
        self.hide_artist_hover_popup()

    def move_artist_hover_popup(self, event, profile):
        if self.artist_hover_popup:
            self.artist_hover_popup.geometry("+{}+{}".format(event.x_root + 18, event.y_root + 16))

    def hide_artist_hover_popup(self):
        if self.artist_hover_popup:
            try:
                self.artist_hover_popup.destroy()
            except Exception:
                pass
            self.artist_hover_popup = None

    def show_artist_hover_popup(self, event, profile):
        self.hide_artist_hover_popup()
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.configure(bg=self.bg_color)
        popup.attributes('-topmost', True)
        x = event.x_root + 18
        y = event.y_root + 16

        panel = tk.Frame(
            popup,
            bg=self.panel_bg,
            highlightbackground=self.accent_hover,
            highlightthickness=1,
            padx=14,
            pady=12
        )
        panel.pack()
        tk.Label(panel, text=profile['artist'], bg=self.panel_bg, fg=self.fg_color, font=('Arial', 12, 'bold')).pack(anchor='w')
        tk.Label(
            panel,
            text="Overall: {}%   {} of {} complete".format(profile['percent'], profile['completed_songs'], profile['total_songs']),
            bg=self.panel_bg,
            fg=self.muted_fg,
            font=('Arial', 9)
        ).pack(anchor='w', pady=(2, 8))

        songs = profile.get('songs', [])[:6]
        if not songs:
            tk.Label(panel, text="No song drops yet.", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 9)).pack(anchor='w')
        for song in songs:
            row = tk.Frame(panel, bg=self.panel_bg)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=song['song'][:24], bg=self.panel_bg, fg=self.fg_color, font=('Arial', 9), width=24, anchor='w').pack(side=tk.LEFT)
            color = self.success_color if song['percent'] >= 80 else self.accent_color if song['percent'] >= 50 else self.danger_color
            tk.Label(row, text="{}%".format(song['percent']), bg=self.panel_bg, fg=color, font=('Arial', 9, 'bold'), width=5, anchor='e').pack(side=tk.LEFT)
            missing = ', '.join(song['missing']) if song['missing'] else 'Complete'
            tk.Label(row, text=missing[:28], bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 8), anchor='w').pack(side=tk.LEFT, padx=(8,0))
        if len(profile.get('songs', [])) > 6:
            tk.Label(panel, text="Click card to view all songs.", bg=self.panel_bg, fg=self.accent_color, font=('Arial', 8, 'bold')).pack(anchor='w', pady=(8, 0))

        self.artist_hover_popup = popup
        popup.update_idletasks()
        target_width = max(280, panel.winfo_reqwidth())
        target_height = max(90, panel.winfo_reqheight())
        popup.geometry("{}x{}+{}+{}".format(target_width, target_height, x, y))

    def build_artist_profile_for_single_song_folder(self, song_folder):
        """Build an artist profile when the selected Drive folder is already one song drop."""
        song_profile = self.build_song_profile_from_drive_folder(song_folder)
        artist_name = 'Artist'
        artist_folder_id = None

        try:
            song_metadata = self.get_drive_folder_metadata(song_folder['id'])
            parents = song_metadata.get('parents') or []
            parent_id = parents[0].get('id') if parents else None
            if parent_id:
                artist_folder_id = parent_id
                artist_name = self.get_drive_folder_metadata(parent_id).get('title', artist_name)
        except Exception:
            pass

        required_count = len(self.get_required_tags())
        total_present = len(song_profile['present'])
        artist_percent = int((total_present / required_count) * 100) if required_count else 0
        color = 'green' if artist_percent >= 80 else 'yellow' if artist_percent >= 50 else 'red'

        image_file = self.get_artist_profile_image_file(artist_folder_id) if artist_folder_id else None
        return {
            'id': song_folder['id'],
            'artist_folder_id': artist_folder_id,
            'artist': artist_name,
            'songs': [song_profile],
            'percent': artist_percent,
            'completed_songs': 1 if song_profile['percent'] == 100 else 0,
            'total_songs': 1,
            'total_present': total_present,
            'total_required': required_count,
            'color': color,
            'image_file_id': image_file.get('id') if image_file else None,
            'image_title': image_file.get('title') if image_file else None
        }

    def build_song_profile_from_drive_folder(self, song_folder, song_items=None):
        """Build progress data for one song/drop folder."""
        song_items = song_items if song_items is not None else self.get_drive_folder_contents(song_folder['id'])
        status = self.build_drive_folder_status(song_items, song_folder.get('title', ''))
        color = 'green' if status['percent'] >= 80 else 'yellow' if status['percent'] >= 50 else 'red'
        return {
            'id': song_folder['id'],
            'song_folder_id': song_folder['id'],
            'song': song_folder.get('title', 'Untitled Song'),
            'present': status['present'],
            'missing': status['missing'],
            'percent': status['percent'],
            'color': color,
            'item_count': len(song_items)
        }

    def build_artist_profile_from_drive_folder(self, artist_folder):
        """Build one artist profile from an Artist/Song/Tag Drive folder structure."""
        song_profiles = []
        for song_folder in self.get_drive_child_folders(artist_folder['id']):
            song_items = self.get_drive_folder_contents(song_folder['id'])
            if not self.drive_folder_looks_like_song_drop(song_folder, song_items):
                continue
            song_profile = self.build_song_profile_from_drive_folder(song_folder, song_items)
            song_profiles.append(song_profile)

        required_count = len(self.get_required_tags())
        total_required = len(song_profiles) * required_count
        total_present = sum(len(song['present']) for song in song_profiles)
        artist_percent = int((total_present / total_required) * 100) if total_required else 0
        completed_songs = sum(1 for song in song_profiles if song['percent'] == 100)
        color = 'green' if artist_percent >= 80 else 'yellow' if artist_percent >= 50 else 'red'

        image_file = self.get_artist_profile_image_file(artist_folder['id'])
        return {
            'id': artist_folder['id'],
            'artist_folder_id': artist_folder['id'],
            'artist': artist_folder.get('title', 'Untitled Artist'),
            'songs': sorted(song_profiles, key=lambda item: item['song'].casefold()),
            'percent': artist_percent,
            'completed_songs': completed_songs,
            'total_songs': len(song_profiles),
            'total_present': total_present,
            'total_required': total_required,
            'color': color,
            'image_file_id': image_file.get('id') if image_file else None,
            'image_title': image_file.get('title') if image_file else None
        }

    def build_artist_profiles_from_drive_folder(self, root_folder_id):
        """Return artist profiles for the selected folder or its child artist folders."""
        if not self.drive:
            return []

        root_metadata = self.get_drive_folder_metadata(root_folder_id)
        root_folder = {
            'id': root_folder_id,
            'title': root_metadata.get('title', 'My Drive')
        }

        if self.drive_folder_looks_like_song_drop(root_folder):
            return [self.build_artist_profile_for_single_song_folder(root_folder)]

        direct_child_folders = self.get_drive_child_folders(root_folder_id)
        if any(self.drive_folder_looks_like_song_drop(folder) for folder in direct_child_folders):
            selected_as_artist = self.build_artist_profile_from_drive_folder(root_folder)
            return [selected_as_artist] if selected_as_artist['total_songs'] > 0 else []

        profiles = []
        for artist_folder in direct_child_folders:
            profile = self.build_artist_profile_from_drive_folder(artist_folder)
            if profile['total_songs'] > 0:
                profiles.append(profile)

        unique_profiles = {}
        for profile in profiles:
            unique_profiles[profile['id']] = profile
        return sorted(unique_profiles.values(), key=lambda item: item['artist'].casefold())

    def get_all_song_profiles(self, root_folder_id=None):
        """Flatten all Drive artist profiles into one song list."""
        source_folder = root_folder_id or self.ensure_app_drive_root_folder() or self.drive_dest_folder or 'root'
        songs = []
        for profile in self.build_artist_profiles_from_drive_folder(source_folder):
            for song in profile.get('songs', []):
                song_copy = dict(song)
                song_copy['artist'] = profile.get('artist', 'Untitled Artist')
                song_copy['artist_folder_id'] = profile.get('artist_folder_id')
                songs.append(song_copy)
        return sorted(songs, key=lambda item: (item.get('artist', '').casefold(), item.get('song', '').casefold()))

    def ensure_credits_data_folder(self):
        """Create or find the global JSON folder inside G-DAM."""
        if not self.drive:
            return None
        if self.credits_data_folder_id:
            return self.credits_data_folder_id
        app_root_id = self.ensure_app_drive_root_folder()
        self.credits_data_folder_id = self.get_or_create_drive_folder(CREDITS_DATA_FOLDER_NAME, app_root_id)
        return self.credits_data_folder_id

    def get_google_service(self, api_name, version):
        if not GOOGLE_API_CLIENT_AVAILABLE:
            raise RuntimeError("google-api-python-client is required for Docs/Gmail features.")
        if not self.drive or not getattr(self.drive, 'auth', None):
            raise RuntimeError("Google Drive is not authenticated.")

        cache_attr = {
            ('docs', 'v1'): 'google_docs_service',
            ('drive', 'v3'): 'google_drive_v3_service',
            ('gmail', 'v1'): 'gmail_service'
        }.get((api_name, version))
        if cache_attr and getattr(self, cache_attr, None):
            return getattr(self, cache_attr)

        credentials = self.drive.auth.credentials
        service = build_google_service(api_name, version, credentials=credentials, cache_discovery=False)
        if cache_attr:
            setattr(self, cache_attr, service)
        return service

    def find_drive_file_by_title(self, title, parent_id):
        query = "title='{}' and '{}' in parents and trashed=false".format(
            self.escape_drive_query_value(title),
            parent_id
        )
        matches = self.drive.ListFile({'q': query}).GetList()
        return matches[0] if matches else None

    def load_drive_json_file(self, title, default_value):
        folder_id = self.ensure_credits_data_folder()
        if not folder_id:
            return default_value
        existing = self.find_drive_file_by_title(title, folder_id)
        if not existing:
            return default_value
        try:
            raw = self.drive.CreateFile({'id': existing['id']}).GetContentString()
            return json.loads(raw) if raw.strip() else default_value
        except Exception as e:
            self.log("Could not read {}: {}".format(title, str(e)))
            return default_value

    def save_drive_json_file(self, title, data):
        folder_id = self.ensure_credits_data_folder()
        if not folder_id:
            raise RuntimeError("Credits data folder is not available.")
        existing = self.find_drive_file_by_title(title, folder_id)
        metadata = {'id': existing['id']} if existing else {'title': title, 'parents': [{'id': folder_id}]}
        drive_file = self.drive.CreateFile(metadata)
        drive_file.SetContentString(json.dumps(data, indent=2, sort_keys=True))
        drive_file.Upload()
        self.clear_drive_cache()

    def load_credit_data(self):
        profiles_data = self.load_drive_json_file(COLLABORATOR_PROFILES_JSON, {'profiles': []})
        credits_data = self.load_drive_json_file(SONG_CREDITS_JSON, {'songs': {}})
        signature_data = self.load_drive_json_file(SIGNATURE_REQUESTS_JSON, {'requests': {}})
        self.collaborator_profiles = profiles_data.get('profiles', [])
        self.song_credit_assignments = credits_data.get('songs', {})
        self.signature_requests = signature_data.get('requests', {})
        return self.collaborator_profiles, self.song_credit_assignments

    def save_credit_data(self):
        self.save_drive_json_file(COLLABORATOR_PROFILES_JSON, {'profiles': self.collaborator_profiles})
        self.save_drive_json_file(SONG_CREDITS_JSON, {'songs': self.song_credit_assignments})
        self.save_drive_json_file(SIGNATURE_REQUESTS_JSON, {'requests': self.signature_requests})

    def get_credit_profile_name(self, profile_id):
        for profile in self.collaborator_profiles:
            if profile.get('profile_id') == profile_id:
                return profile.get('name') or profile_id
        return profile_id

    def get_collaborator_profile_by_name(self, name):
        clean_name = name.strip().casefold()
        for profile in self.collaborator_profiles:
            if profile.get('name', '').strip().casefold() == clean_name:
                return profile
        return None

    def get_collaborator_profile_by_id(self, profile_id):
        for profile in self.collaborator_profiles:
            if profile.get('profile_id') == profile_id:
                return profile
        return None

    def get_or_create_collaborator_profile(self, name, profile_info=None):
        clean_name = name.strip()
        if not clean_name:
            return None
        profile_info = profile_info or {}
        profile = self.get_collaborator_profile_by_name(clean_name)
        if profile:
            profile['name'] = clean_name
            profile.pop('phone', None)
            profile.pop('publisher', None)
            for key, value in profile_info.items():
                if value is not None:
                    profile[key] = value.strip() if isinstance(value, str) else value
            profile['updated_at'] = int(time.time())
            self.collaborator_profiles.sort(key=lambda item: item.get('name', '').casefold())
            return profile
        profile = {
            'profile_id': str(uuid.uuid4()),
            'name': clean_name,
            'email': profile_info.get('email', '').strip(),
            'bmi': profile_info.get('bmi', '').strip(),
            'ascap': profile_info.get('ascap', '').strip(),
            'pro': profile_info.get('pro', '').strip(),
            'notes': profile_info.get('notes', '').strip(),
            'created_at': int(time.time())
        }
        self.collaborator_profiles.append(profile)
        self.collaborator_profiles.sort(key=lambda item: item.get('name', '').casefold())
        return profile

    def save_sender_collaborator_profile(self, form_data):
        name = (form_data.get('collaborator_name', [''])[0] or '').strip()
        email = (form_data.get('collaborator_email', [''])[0] or '').strip()
        if not name or not email:
            raise RuntimeError("Name and email are required.")

        profile_info = {
            'email': email,
            'bmi': (form_data.get('collaborator_bmi', [''])[0] or '').strip(),
            'ascap': (form_data.get('collaborator_ascap', [''])[0] or '').strip(),
            'pro': (form_data.get('collaborator_pro', [''])[0] or '').strip(),
            'notes': (form_data.get('collaborator_notes', [''])[0] or '').strip()
        }
        self.load_credit_data()
        profile = self.get_or_create_collaborator_profile(name, profile_info)
        self.save_drive_json_file(COLLABORATOR_PROFILES_JSON, {'profiles': self.collaborator_profiles})
        if hasattr(self, 'root'):
            self.root.after(0, self.refresh_collaborators_tab)
        return profile

    def get_song_credit_record(self, song):
        song_id = song.get('song_folder_id') or song.get('id')
        if not song_id:
            return {'collaborators': []}
        return self.song_credit_assignments.setdefault(song_id, {
            'artist': song.get('artist', ''),
            'song': song.get('song', ''),
            'song_folder_id': song_id,
            'collaborators': []
        })

    def get_song_credit_summary(self, song):
        song_id = song.get('song_folder_id') or song.get('id')
        record = self.song_credit_assignments.get(song_id, {})
        collaborators = record.get('collaborators', [])
        split_total = sum(self.safe_float(item.get('split', 0)) for item in collaborators)
        return len(collaborators), split_total

    def safe_float(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def format_split(self, value):
        number = self.safe_float(value)
        return str(int(number)) if number.is_integer() else "{:.2f}".format(number).rstrip('0').rstrip('.')

    def get_role_split_pool(self, role):
        performance_roles = {'Primary Artist', 'Featured Artist'}
        production_engineering_roles = {
            'Producer',
            'Co-Producer',
            'Additional Producer',
            'Recording Engineer',
            'Mix Engineer',
            'Mastering Engineer'
        }
        if role in performance_roles:
            return 'artist', 50.0
        if role in production_engineering_roles:
            return 'production_engineering', 50.0
        return None, None

    def get_song_split_total_from_record(self, record):
        return sum(self.safe_float(item.get('split', 0)) for item in record.get('collaborators', []))

    def apply_default_split_pool(self, record, new_collaborator):
        role = new_collaborator.get('role', '')
        pool_name, pool_total = self.get_role_split_pool(role)
        if not pool_name:
            if not new_collaborator.get('split'):
                remaining = max(0.0, 100.0 - self.get_song_split_total_from_record(record))
                new_collaborator['split'] = remaining
            return

        collaborators = record.setdefault('collaborators', [])
        pooled = []
        for collaborator in collaborators:
            collaborator_pool, _ = self.get_role_split_pool(collaborator.get('role', ''))
            if collaborator_pool == pool_name:
                pooled.append(collaborator)

        previous_default = pool_total / len(pooled) if pooled else None
        can_rebalance_existing = (
            not pooled or
            all(abs(self.safe_float(item.get('split', 0)) - previous_default) < 0.01 for item in pooled)
        )
        next_default = pool_total / (len(pooled) + 1)
        if not new_collaborator.get('split'):
            new_collaborator['split'] = next_default
        if can_rebalance_existing:
            for collaborator in pooled:
                collaborator['split'] = next_default

    def reset_song_split_percentages(self, record):
        collaborators = record.get('collaborators', [])
        if not collaborators:
            return

        pooled_collaborators = {}
        unpooled_collaborators = []
        used_pool_total = 0.0
        for collaborator in collaborators:
            pool_name, pool_total = self.get_role_split_pool(collaborator.get('role', ''))
            if pool_name:
                if pool_name not in pooled_collaborators:
                    pooled_collaborators[pool_name] = {
                        'total': pool_total,
                        'collaborators': []
                    }
                    used_pool_total += pool_total
                pooled_collaborators[pool_name]['collaborators'].append(collaborator)
            else:
                unpooled_collaborators.append(collaborator)

        for pool in pooled_collaborators.values():
            pool_collaborators = pool['collaborators']
            split = pool['total'] / len(pool_collaborators)
            for collaborator in pool_collaborators:
                collaborator['split'] = split

        if unpooled_collaborators:
            remaining = max(0.0, 100.0 - used_pool_total)
            split = remaining / len(unpooled_collaborators)
            for collaborator in unpooled_collaborators:
                collaborator['split'] = split

    def build_song_contributors(self, record):
        contributors = []
        for collaborator in record.get('collaborators', []):
            profile = self.get_collaborator_profile_by_id(collaborator.get('profile_id'))
            contributors.append({
                'profile_id': collaborator.get('profile_id', ''),
                'name': profile.get('name', collaborator.get('profile_id', 'Collaborator')) if profile else collaborator.get('profile_id', 'Collaborator'),
                'role': collaborator.get('role', ''),
                'split': self.format_split(collaborator.get('split', 0))
            })
        return contributors

    def build_signature_block(self, contributors):
        seen = set()
        lines = []
        for contributor in contributors:
            name = contributor.get('name', '').strip()
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            lines.append("{}\nSignature: ____________________________    Date: ____________".format(name))
        return "\n\n".join(lines)

    def build_contributors_block(self, contributors):
        lines = []
        for contributor in contributors:
            lines.append("{} - {} - {}%".format(
                contributor.get('name', ''),
                contributor.get('role', ''),
                contributor.get('split', '0')
            ))
        return "\n".join(lines)

    def find_split_sheet_template_doc(self):
        app_root_id = self.ensure_app_drive_root_folder()
        query = (
            "mimeType='application/vnd.google-apps.document' and trashed=false "
            "and '{}' in parents"
        ).format(app_root_id)
        docs = self.drive.ListFile({'q': query}).GetList()
        preferred = []
        fallback = []
        for doc in docs:
            title = doc.get('title', '')
            title_key = title.casefold()
            if 'template' in title_key and ('split' in title_key or 'signature' in title_key):
                preferred.append(doc)
            elif 'template' in title_key:
                fallback.append(doc)
        return (preferred or fallback or [None])[0]

    def copy_template_and_replace_text(self, template_id, title, replacements, parent_id):
        drive_service = self.get_google_service('drive', 'v3')
        docs_service = self.get_google_service('docs', 'v1')
        copied = drive_service.files().copy(
            fileId=template_id,
            body={
                'name': title,
                'parents': [parent_id] if parent_id else [self.ensure_app_drive_root_folder()]
            },
            fields='id,name,webViewLink'
        ).execute()

        requests = []
        for placeholder, value in replacements.items():
            requests.append({
                'replaceAllText': {
                    'containsText': {
                        'text': placeholder,
                        'matchCase': True
                    },
                    'replaceText': value
                }
            })
        docs_service.documents().batchUpdate(
            documentId=copied['id'],
            body={'requests': requests}
        ).execute()
        self.clear_drive_cache()
        return copied

    def create_signature_requests_for_song(self, song, contributors, split_sheet_doc):
        song_folder_id = song.get('song_folder_id') or song.get('id')
        signatures_folder_id = self.get_or_create_drive_folder(SIGNED_SPLIT_SHEETS_FOLDER_NAME, song_folder_id)
        request_rows = []
        seen = set()
        for contributor in contributors:
            profile = self.get_collaborator_profile_by_id(contributor.get('profile_id'))
            name = contributor.get('name', '').strip()
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            token = str(uuid.uuid4())
            request = {
                'token': token,
                'song_folder_id': song_folder_id,
                'signatures_folder_id': signatures_folder_id,
                'split_sheet_doc_id': split_sheet_doc.get('id'),
                'split_sheet_url': split_sheet_doc.get('webViewLink') or split_sheet_doc.get('alternateLink') or '',
                'artist': song.get('artist', ''),
                'song': song.get('song', ''),
                'profile_id': contributor.get('profile_id', ''),
                'name': name,
                'email': profile.get('email', '') if profile else '',
                'status': 'pending',
                'created_at': int(time.time())
            }
            self.signature_requests[token] = request
            request_rows.append(request)
        self.save_drive_json_file(SIGNATURE_REQUESTS_JSON, {'requests': self.signature_requests})
        return request_rows

    def get_signature_request(self, token):
        if not self.signature_requests:
            self.load_credit_data()
        return self.signature_requests.get(token)

    def get_signature_link(self, token):
        portal_url = self.start_sender_portal()
        base_url = portal_url.rstrip('/')
        return "{}/signature/{}".format(base_url, token)

    def send_signature_email(self, request):
        if not request.get('email'):
            return False, "No email on collaborator profile."
        gmail = self.get_google_service('gmail', 'v1')
        link = self.get_signature_link(request['token'])
        message = EmailMessage()
        message['To'] = request['email']
        message['Subject'] = "Split sheet signature: {} - {}".format(request.get('artist', ''), request.get('song', ''))
        message.set_content(
            "Hi {},\n\nPlease review and sign the split sheet for {} - {}.\n\nGoogle Doc:\n{}\n\nSignature link:\n{}\n\nThank you.".format(
                request.get('name', ''),
                request.get('artist', ''),
                request.get('song', ''),
                request.get('split_sheet_url', ''),
                link
            )
        )
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        gmail.users().messages().send(userId='me', body={'raw': encoded}).execute()
        return True, link

    def send_signature_emails(self, requests):
        sent = []
        skipped = []
        for request in requests:
            try:
                ok, detail = self.send_signature_email(request)
                if ok:
                    request['email_sent_at'] = int(time.time())
                    request['signature_link'] = detail
                    sent.append(request)
                else:
                    skipped.append("{}: {}".format(request.get('name', 'Collaborator'), detail))
            except Exception as e:
                skipped.append("{}: {}".format(request.get('name', 'Collaborator'), str(e)))
        self.save_drive_json_file(SIGNATURE_REQUESTS_JSON, {'requests': self.signature_requests})
        return sent, skipped

    def build_split_sheet_html(self, song, contributors, signature_block):
        contributor_rows = []
        for contributor in contributors:
            contributor_rows.append(
                "<tr><td>{}</td><td>{}</td><td>{}%</td></tr>".format(
                    html_escape(contributor.get('name', '')),
                    html_escape(contributor.get('role', '')),
                    html_escape(str(contributor.get('split', '0')))
                )
            )

        signature_html = "<br><br>".join(
            html_escape(block).replace("\n", "<br>")
            for block in signature_block.split("\n\n")
            if block.strip()
        )

        return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; color: #111; }}
    h1 {{ font-size: 24px; margin-bottom: 4px; }}
    h2 {{ font-size: 16px; margin-top: 28px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border: 1px solid #999; padding: 8px; text-align: left; }}
    th {{ background: #f1f1f1; }}
    .meta {{ color: #444; margin-bottom: 18px; }}
    .signatures {{ line-height: 1.8; margin-top: 12px; }}
  </style>
</head>
<body>
  <h1>Split Sheet</h1>
  <div class="meta"><strong>Song:</strong> {artist} - {song}</div>
  <h2>Contributors</h2>
  <table>
    <tr><th>Name</th><th>Role</th><th>Split</th></tr>
    {rows}
  </table>
  <h2>Signatures</h2>
  <div class="signatures">{signatures}</div>
</body>
</html>""".format(
            artist=html_escape(song.get('artist', '')),
            song=html_escape(song.get('song', '')),
            rows="\n".join(contributor_rows),
            signatures=signature_html
        )

    def get_split_sheet_safe_name(self, song):
        title = "{} - {} Split Sheet".format(song.get('artist', 'Artist'), song.get('song', 'Song'))
        return re.sub(r'[<>:"/\\\\|?*]+', '-', title).strip() or 'Split Sheet'

    def find_existing_split_sheet_document(self, song):
        song_folder_id = song.get('song_folder_id') or song.get('id')
        if not song_folder_id:
            return None

        safe_name = self.get_split_sheet_safe_name(song)
        escaped_name = safe_name.replace("'", "\\'")
        query = (
            "mimeType='application/vnd.google-apps.document' and trashed=false "
            "and '{}' in parents and title='{}'"
        ).format(song_folder_id, escaped_name)
        docs = self.drive.ListFile({'q': query, 'orderBy': 'modifiedDate desc'}).GetList()
        if docs:
            return docs[0]

        fallback_query = (
            "mimeType='application/vnd.google-apps.document' and trashed=false "
            "and '{}' in parents and title contains 'Split Sheet'"
        ).format(song_folder_id)
        docs = self.drive.ListFile({'q': fallback_query, 'orderBy': 'modifiedDate desc'}).GetList()
        return (docs or [None])[0]

    def view_split_sheet_document(self, song):
        try:
            split_sheet_doc = self.find_existing_split_sheet_document(song)
            if not split_sheet_doc:
                messagebox.showinfo(
                    "View Split Sheet",
                    "No split sheet was found for this song. Generate one first."
                )
                return
            url = (
                split_sheet_doc.get('alternateLink') or
                split_sheet_doc.get('webViewLink') or
                'https://docs.google.com/document/d/{}/edit'.format(split_sheet_doc.get('id'))
            )
            webbrowser.open(url)
            self.log("Opened split sheet: {}".format(url))
        except Exception as e:
            messagebox.showerror("View Split Sheet Error", "Unable to open split sheet:\n{}".format(str(e)))

    def send_existing_split_sheet_document(self, song, record):
        contributors = self.build_song_contributors(record)
        if not contributors:
            messagebox.showwarning("Send Split Sheet", "Add collaborators before sending a split sheet.")
            return

        split_total = self.get_song_split_total_from_record(record)
        if abs(split_total - 100.0) > 0.01:
            messagebox.showwarning(
                "Send Split Sheet",
                "Song splits must total 100% before sending a split sheet. Current total: {}%.".format(
                    self.format_split(split_total)
                )
            )
            return

        try:
            split_sheet_doc = self.find_existing_split_sheet_document(song)
            if not split_sheet_doc:
                messagebox.showinfo(
                    "Send Split Sheet",
                    "No split sheet was found for this song. Generate one first."
                )
                return

            url = (
                split_sheet_doc.get('alternateLink') or
                split_sheet_doc.get('webViewLink') or
                'https://docs.google.com/document/d/{}/edit'.format(split_sheet_doc.get('id'))
            )
            split_sheet_ref = {'id': split_sheet_doc.get('id'), 'webViewLink': url}
            signature_requests = self.create_signature_requests_for_song(song, contributors, split_sheet_ref)
            sent, skipped = self.send_signature_emails(signature_requests)

            message = "Sent split sheet signature emails: {}".format(len(sent))
            message += "\n\nSplit sheet:\n{}".format(url)
            if skipped:
                message += "\n\nSkipped/failed:\n{}".format("\n".join(skipped[:8]))
            messagebox.showinfo("Split Sheet Sent", message)
            self.log("Sent split sheet emails for: {}".format(url))
        except Exception as e:
            messagebox.showerror("Send Split Sheet Error", "Unable to send split sheet:\n{}".format(str(e)))

    def generate_split_sheet_document(self, song, record, send_signature_requests=False):
        contributors = self.build_song_contributors(record)
        if not contributors:
            messagebox.showwarning("Split Sheet", "Add collaborators before generating a split sheet.")
            return

        split_total = self.get_song_split_total_from_record(record)
        if abs(split_total - 100.0) > 0.01:
            messagebox.showwarning(
                "Split Sheet",
                "Song splits must total 100% before generating a split sheet. Current total: {}%.".format(
                    self.format_split(split_total)
                )
            )
            return

        signature_block = self.build_signature_block(contributors)
        contributors_block = self.build_contributors_block(contributors)
        safe_name = self.get_split_sheet_safe_name(song)
        song_folder_id = song.get('song_folder_id') or song.get('id')

        try:
            template_doc = self.find_split_sheet_template_doc()
            if template_doc:
                created_doc = self.copy_template_and_replace_text(
                    template_doc.get('id'),
                    safe_name,
                    {
                        '{{ARTIST}}': song.get('artist', ''),
                        '{{SONG}}': song.get('song', ''),
                        '{{CONTRIBUTORS}}': contributors_block,
                        '{{SIGNATURES}}': signature_block
                    },
                    song_folder_id
                )
                url = created_doc.get('webViewLink') or 'https://docs.google.com/document/d/{}/edit'.format(created_doc.get('id'))
                split_sheet_doc = {'id': created_doc.get('id'), 'webViewLink': url}
            else:
                html_content = self.build_split_sheet_html(song, contributors, signature_block)
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as temp_file:
                        temp_file.write(html_content)
                        temp_path = temp_file.name

                    drive_file = self.drive.CreateFile({
                        'title': safe_name,
                        'parents': [{'id': song_folder_id}] if song_folder_id else [{'id': self.ensure_app_drive_root_folder()}],
                        'mimeType': 'text/html'
                    })
                    drive_file.SetContentFile(temp_path)
                    drive_file.Upload(param={'convert': True})
                    self.clear_drive_cache()
                    drive_file.FetchMetadata(fields='id,title,alternateLink')
                    url = drive_file.get('alternateLink') or 'https://docs.google.com/document/d/{}/edit'.format(drive_file.get('id'))
                    split_sheet_doc = {'id': drive_file.get('id'), 'webViewLink': url}
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass

            self.log("Generated split sheet: {}".format(url))
            message = "Created split sheet:\n{}".format(url)
            if send_signature_requests:
                signature_requests = self.create_signature_requests_for_song(song, contributors, split_sheet_doc)
                sent, skipped = self.send_signature_emails(signature_requests)
                message += "\n\nSignature emails sent: {}".format(len(sent))
                if skipped:
                    message += "\n\nSkipped/failed:\n{}".format("\n".join(skipped[:8]))
            messagebox.showinfo("Split Sheet Generated", message)
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Split Sheet Error", "Unable to generate split sheet:\n{}".format(str(e)))

    def refresh_songs_tab(self):
        if not hasattr(self, 'songs_tree'):
            return
        self.clear_drive_cache()

        for item in self.songs_tree.get_children():
            self.songs_tree.delete(item)

        if not self.drive:
            self.songs_source_label.config(text="Manager Google Drive is not authenticated yet.")
            self.songs_summary_label.config(text="Songs: 0")
            self.current_song_profiles = []
            return

        try:
            app_root_id = self.ensure_app_drive_root_folder()
            self.songs_source_label.config(text=self.get_drive_folder_path(app_root_id))
            self.load_credit_data()
            songs = self.get_all_song_profiles(app_root_id)
            self.current_song_profiles = songs
            complete_count = sum(1 for song in songs if song.get('percent') == 100)
            self.songs_summary_label.config(
                text="Songs: {}   Complete: {}   Credits Folder: {}".format(
                    len(songs),
                    complete_count,
                    CREDITS_DATA_FOLDER_NAME
                )
            )
            for index, song in enumerate(songs):
                credit_count, split_total = self.get_song_credit_summary(song)
                self.songs_tree.insert(
                    '',
                    tk.END,
                    iid=str(index),
                    values=(
                        song.get('artist', ''),
                        song.get('song', ''),
                        "{}%".format(song.get('percent', 0)),
                        credit_count,
                        "{}%".format(self.format_split(split_total))
                    )
                )
        except Exception as e:
            self.current_song_profiles = []
            self.songs_summary_label.config(text="Could not load songs: {}".format(str(e)))
            self.log("Could not refresh Songs tab: {}".format(str(e)))

    def open_selected_song_window(self, event=None):
        if not self.current_song_profiles:
            self.refresh_songs_tab()
        selection = self.songs_tree.selection() if hasattr(self, 'songs_tree') else []
        if not selection:
            messagebox.showinfo("Songs", "Choose a song first.")
            return
        index = int(selection[0])
        if index >= len(self.current_song_profiles):
            return
        self.open_song_credit_window(self.current_song_profiles[index])

    def open_song_credit_window(self, selected_song):
        if not self.drive:
            messagebox.showerror("Drive Error", "Manager Google Drive is not authenticated.")
            return

        self.load_credit_data()
        songs = self.current_song_profiles or self.get_all_song_profiles(self.ensure_app_drive_root_folder())
        selected_song_id = selected_song.get('song_folder_id') or selected_song.get('id')

        popup = tk.Toplevel(self.root)
        popup.title("{} - Credits".format(selected_song.get('song', 'Song')))
        popup.geometry("900x700")
        popup.configure(bg=self.bg_color)

        header = tk.Frame(popup, bg=self.bg_color)
        header.pack(fill=tk.X, padx=18, pady=(18, 10))
        tk.Label(header, text="Song Credits", bg=self.bg_color, fg=self.fg_color, font=('Arial', 18, 'bold')).pack(anchor='w')
        tk.Label(header, text="Global collaborator profiles are saved in G-DAM / {}".format(CREDITS_DATA_FOLDER_NAME), bg=self.bg_color, fg=self.muted_fg, font=('Arial', 9)).pack(anchor='w', pady=(3, 0))

        body = tk.Frame(popup, bg=self.bg_color)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))

        left = tk.Frame(body, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1, width=300)
        left.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 12))
        left.pack_propagate(False)
        tk.Label(left, text="All Songs", bg=self.panel_bg, fg=self.accent_color, font=('Arial', 11, 'bold'), padx=10, pady=8).pack(fill=tk.X)
        song_list = tk.Listbox(left, bg='#1e1e1e', fg=self.fg_color, selectbackground=self.button_bg, activestyle='none')
        song_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        right = tk.Frame(body, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        title_label = tk.Label(right, text="", bg=self.panel_bg, fg=self.fg_color, font=('Arial', 14, 'bold'), anchor='w', padx=12, pady=10)
        title_label.pack(fill=tk.X)
        progress_label = tk.Label(right, text="", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 9), anchor='w', padx=12)
        progress_label.pack(fill=tk.X)
        progress_bar = ttk.Progressbar(right, orient=tk.HORIZONTAL, mode='determinate', maximum=100, style='Dark.Horizontal.TProgressbar')
        progress_bar.pack(fill=tk.X, padx=12, pady=(6, 10))

        credit_tree = ttk.Treeview(right, columns=('name', 'role', 'credit', 'split'), show='headings', height=7, selectmode='browse')
        credit_tree.heading('name', text='Collaborator')
        credit_tree.heading('role', text='Role')
        credit_tree.heading('credit', text='Credit')
        credit_tree.heading('split', text='Split')
        credit_tree.column('name', width=140, anchor='w')
        credit_tree.column('role', width=100, anchor='w')
        credit_tree.column('credit', width=160, anchor='w')
        credit_tree.column('split', width=70, anchor='center')
        credit_tree.pack(fill=tk.X, padx=12, pady=(0, 10))

        selected = {'song': None}

        def open_create_collaborator_window():
            create_window = tk.Toplevel(popup)
            create_window.title("Create Collaborator")
            create_window.geometry("460x420")
            create_window.configure(bg=self.bg_color)
            create_window.transient(popup)

            tk.Label(
                create_window,
                text="Create Collaborator",
                bg=self.bg_color,
                fg=self.fg_color,
                font=('Arial', 16, 'bold')
            ).pack(anchor='w', padx=18, pady=(18, 4))
            tk.Label(
                create_window,
                text="Saved globally in G-DAM / {}".format(CREDITS_DATA_FOLDER_NAME),
                bg=self.bg_color,
                fg=self.muted_fg,
                font=('Arial', 9)
            ).pack(anchor='w', padx=18, pady=(0, 12))

            profile_panel = tk.Frame(create_window, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
            profile_panel.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 14))

            new_name_var = tk.StringVar()
            new_email_var = tk.StringVar()
            new_bmi_var = tk.StringVar()
            new_ascap_var = tk.StringVar()
            new_pro_var = tk.StringVar()

            def add_labeled_entry(row, label, variable):
                tk.Label(profile_panel, text=label, bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 8, 'bold')).grid(
                    row=row,
                    column=0,
                    sticky='w',
                    padx=12,
                    pady=(10 if row == 0 else 6, 0)
                )
                entry = tk.Entry(
                    profile_panel,
                    textvariable=variable,
                    bg=self.field_bg,
                    fg=self.fg_color,
                    insertbackground=self.fg_color
                )
                entry.grid(row=row, column=1, sticky='ew', padx=(8, 12), pady=(10 if row == 0 else 6, 0))
                return entry

            name_entry = add_labeled_entry(0, "Name", new_name_var)
            add_labeled_entry(1, "Email", new_email_var)
            add_labeled_entry(2, "BMI", new_bmi_var)
            add_labeled_entry(3, "ASCAP", new_ascap_var)
            add_labeled_entry(4, "PRO", new_pro_var)
            tk.Label(profile_panel, text="Notes", bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 8, 'bold')).grid(
                row=5,
                column=0,
                sticky='nw',
                padx=12,
                pady=(8, 0)
            )
            new_notes_text = tk.Text(
                profile_panel,
                bg=self.field_bg,
                fg=self.fg_color,
                insertbackground=self.fg_color,
                height=5,
                wrap=tk.WORD,
                padx=8,
                pady=6
            )
            new_notes_text.grid(row=5, column=1, sticky='nsew', padx=(8, 12), pady=(8, 12))
            profile_panel.columnconfigure(1, weight=1)
            profile_panel.rowconfigure(5, weight=1)

            def finish_create_collaborator():
                profile = self.get_or_create_collaborator_profile(
                    new_name_var.get(),
                    {
                        'email': new_email_var.get().strip(),
                        'bmi': new_bmi_var.get().strip(),
                        'ascap': new_ascap_var.get().strip(),
                        'pro': new_pro_var.get().strip(),
                        'notes': new_notes_text.get(1.0, tk.END).strip()
                    }
                )
                if not profile:
                    messagebox.showwarning("Collaborator Required", "Enter a collaborator name.", parent=create_window)
                    return
                try:
                    self.save_drive_json_file(COLLABORATOR_PROFILES_JSON, {'profiles': self.collaborator_profiles})
                except Exception as e:
                    messagebox.showerror("Collaborator Error", "Unable to save collaborator profile:\n{}".format(str(e)), parent=create_window)
                    return
                self.load_credit_data()
                refresh_credit_tree()
                create_window.destroy()

            button_row = tk.Frame(create_window, bg=self.bg_color)
            button_row.pack(fill=tk.X, padx=18, pady=(0, 18))
            tk.Button(
                button_row,
                text="Done",
                command=finish_create_collaborator,
                bg=self.button_bg,
                fg=self.button_fg,
                font=('Arial', 10, 'bold'),
                width=12
            ).pack(side=tk.RIGHT)
            name_entry.focus_set()

        def selected_record():
            return self.get_song_credit_record(selected['song'])

        def refresh_credit_tree():
            for item in credit_tree.get_children():
                credit_tree.delete(item)
            record = selected_record()
            for index, collaborator in enumerate(record.get('collaborators', [])):
                credit_tree.insert(
                    '',
                    tk.END,
                    iid=str(index),
                    values=(
                        self.get_credit_profile_name(collaborator.get('profile_id')),
                        collaborator.get('role', ''),
                        collaborator.get('credit', ''),
                        "{}%".format(self.format_split(collaborator.get('split', 0)))
                    )
                )

        def choose_song(song):
            selected['song'] = song
            title_label.config(text="{} - {}".format(song.get('artist', ''), song.get('song', '')))
            progress_label.config(
                text="Progress: {}%   Present: {}   Missing: {}".format(
                    song.get('percent', 0),
                    ', '.join(song.get('present', [])) if song.get('present') else 'None',
                    ', '.join(song.get('missing', [])) if song.get('missing') else 'None'
                )
            )
            progress_bar['value'] = song.get('percent', 0)
            refresh_credit_tree()

        def on_song_selected(event=None):
            selection = song_list.curselection()
            if selection:
                choose_song(songs[selection[0]])

        def generate_selected_split_sheet():
            if not selected['song']:
                messagebox.showinfo("Split Sheet", "Choose a song first.", parent=popup)
                return
            self.generate_split_sheet_document(selected['song'], selected_record())

        def view_selected_split_sheet():
            if not selected['song']:
                messagebox.showinfo("View Split Sheet", "Choose a song first.", parent=popup)
                return
            self.view_split_sheet_document(selected['song'])

        def send_selected_split_sheet():
            if not selected['song']:
                messagebox.showinfo("Send Split Sheet", "Choose a song first.", parent=popup)
                return
            self.send_existing_split_sheet_document(selected['song'], selected_record())

        def remove_selected_collaborator():
            if not selected['song']:
                messagebox.showinfo("Remove Collaborator", "Choose a song first.", parent=popup)
                return

            selection = credit_tree.selection()
            if not selection:
                messagebox.showinfo("Remove Collaborator", "Choose a collaborator credit to remove.", parent=popup)
                return

            record = selected_record()
            collaborators = record.get('collaborators', [])
            try:
                collaborator_index = int(selection[0])
                collaborator = collaborators[collaborator_index]
            except (ValueError, IndexError):
                messagebox.showerror("Remove Collaborator", "Unable to find the selected collaborator credit.", parent=popup)
                refresh_credit_tree()
                return

            collaborator_name = self.get_credit_profile_name(collaborator.get('profile_id'))
            collaborator_role = collaborator.get('role', '')
            if not messagebox.askyesno(
                "Remove Collaborator",
                "Remove {} from this song{}?".format(
                    collaborator_name,
                    " as {}".format(collaborator_role) if collaborator_role else ""
                ),
                parent=popup
            ):
                return

            del collaborators[collaborator_index]
            self.reset_song_split_percentages(record)
            try:
                self.save_credit_data()
                refresh_credit_tree()
                self.refresh_songs_tab()
            except Exception as e:
                messagebox.showerror("Credits Error", "Unable to remove collaborator credit:\n{}".format(str(e)), parent=popup)

        def open_add_collaborator_window():
            if not selected['song']:
                messagebox.showinfo("Add Collaborator", "Choose a song first.", parent=popup)
                return

            self.load_credit_data()
            if not self.collaborator_profiles:
                messagebox.showinfo(
                    "Add Collaborator",
                    "Create a collaborator profile first.",
                    parent=popup
                )
                open_create_collaborator_window()
                return

            add_window = tk.Toplevel(popup)
            add_window.title("Add Collaborator")
            add_window.geometry("460x330")
            add_window.configure(bg=self.bg_color)
            add_window.transient(popup)

            tk.Label(
                add_window,
                text="Add Collaborator",
                bg=self.bg_color,
                fg=self.fg_color,
                font=('Arial', 16, 'bold')
            ).pack(anchor='w', padx=18, pady=(18, 4))
            tk.Label(
                add_window,
                text="{} - {}".format(selected['song'].get('artist', ''), selected['song'].get('song', '')),
                bg=self.bg_color,
                fg=self.muted_fg,
                font=('Arial', 9)
            ).pack(anchor='w', padx=18, pady=(0, 12))

            panel = tk.Frame(add_window, bg=self.panel_bg, highlightbackground=self.border_color, highlightthickness=1)
            panel.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 14))

            collaborator_var = tk.StringVar()
            role_var = tk.StringVar()
            split_var = tk.StringVar()
            role_groups = [
                ('Ownership', ['Songwriter', 'Composer', 'Topliner']),
                ('Production', ['Producer', 'Co-Producer', 'Additional Producer']),
                ('Engineering', ['Recording Engineer', 'Mix Engineer', 'Mastering Engineer']),
                ('Performance', ['Primary Artist', 'Featured Artist']),
                ('Business', ['Publisher'])
            ]
            selected_role_label = tk.StringVar(value="Select role")
            selected_role_category = tk.StringVar(value="")

            def add_label(row, label):
                tk.Label(panel, text=label, bg=self.panel_bg, fg=self.muted_fg, font=('Arial', 8, 'bold')).grid(
                    row=row,
                    column=0,
                    sticky='w',
                    padx=12,
                    pady=(12 if row == 0 else 8, 0)
                )

            add_label(0, "Collaborator")
            collaborator_combo = ttk.Combobox(
                panel,
                textvariable=collaborator_var,
                values=[profile.get('name', '') for profile in self.collaborator_profiles],
                state='readonly'
            )
            collaborator_combo.grid(row=0, column=1, sticky='ew', padx=(8, 12), pady=(12, 0))

            add_label(1, "Role")
            role_button = tk.Menubutton(
                panel,
                textvariable=selected_role_label,
                bg=self.field_bg,
                fg=self.fg_color,
                activebackground='#3a2514',
                activeforeground=self.fg_color,
                relief=tk.FLAT,
                anchor='w',
                padx=10,
                pady=6,
                highlightbackground=self.border_color,
                highlightthickness=1
            )
            role_button.grid(row=1, column=1, sticky='ew', padx=(8, 12), pady=(8, 0))
            role_menu = tk.Menu(
                role_button,
                tearoff=0,
                bg='#1e1e1e',
                fg=self.fg_color,
                activebackground=self.accent_color,
                activeforeground='#0d0905',
                borderwidth=0
            )
            role_button.configure(menu=role_menu)

            def choose_role(category, role):
                role_var.set(role)
                selected_role_label.set(role)
                selected_role_category.set(category)
                pool_name, pool_total = self.get_role_split_pool(role)
                record = selected_record()
                if pool_name:
                    pooled_count = sum(
                        1 for collaborator in record.get('collaborators', [])
                        if self.get_role_split_pool(collaborator.get('role', ''))[0] == pool_name
                    )
                    split_var.set(self.format_split(pool_total / (pooled_count + 1)))
                    if pool_name == 'artist':
                        split_hint.config(text="Artist roles share a 50% pool by default.")
                    else:
                        split_hint.config(text="Producer and engineer roles share a 50% pool by default.")
                elif not split_var.get().strip():
                    remaining = max(0.0, 100.0 - self.get_song_split_total_from_record(record))
                    split_var.set(self.format_split(remaining))
                    split_hint.config(text="Defaulted to the remaining song split. You can change it.")

            for category, options in role_groups:
                category_menu = tk.Menu(
                    role_menu,
                    tearoff=0,
                    bg='#1e1e1e',
                    fg=self.fg_color,
                    activebackground=self.accent_color,
                    activeforeground='#0d0905',
                    borderwidth=0
                )
                for option in options:
                    category_menu.add_command(
                        label=option,
                        command=lambda item=option, group=category: choose_role(group, item)
                    )
                role_menu.add_cascade(label=category, menu=category_menu)

            role_hint = tk.Label(
                panel,
                textvariable=selected_role_category,
                bg=self.panel_bg,
                fg=self.accent_color,
                font=('Arial', 8, 'bold'),
                anchor='w'
            )
            role_hint.grid(row=2, column=1, sticky='w', padx=(8, 12), pady=(3, 0))

            add_label(3, "Split %")
            split_entry = tk.Entry(panel, textvariable=split_var, bg=self.field_bg, fg=self.fg_color, insertbackground=self.fg_color)
            split_entry.grid(row=3, column=1, sticky='ew', padx=(8, 12), pady=(8, 0))
            split_hint = tk.Label(
                panel,
                text="Enter this collaborator's song split. Total song splits must equal 100%.",
                bg=self.panel_bg,
                fg=self.muted_fg,
                font=('Arial', 8),
                anchor='w'
            )
            split_hint.grid(row=4, column=1, sticky='w', padx=(8, 12), pady=(3, 0))
            panel.columnconfigure(1, weight=1)

            def finish_add_collaborator():
                profile = self.get_collaborator_profile_by_name(collaborator_var.get())
                if not profile:
                    messagebox.showwarning("Collaborator Required", "Choose a collaborator.", parent=add_window)
                    return
                if not role_var.get().strip():
                    messagebox.showwarning("Role Required", "Choose a role.", parent=add_window)
                    return

                record = selected_record()
                collaborators = record.setdefault('collaborators', [])
                original_splits = [collaborator.get('split', 0) for collaborator in collaborators]
                new_collaborator = {
                    'profile_id': profile['profile_id'],
                    'role': role_var.get().strip(),
                    'credit': '',
                    'split': self.safe_float(split_var.get())
                }
                self.apply_default_split_pool(record, new_collaborator)
                projected_total = self.get_song_split_total_from_record(record) + self.safe_float(new_collaborator.get('split', 0))
                if projected_total > 100.01:
                    for collaborator, original_split in zip(collaborators, original_splits):
                        collaborator['split'] = original_split
                    messagebox.showwarning(
                        "Split Total Too High",
                        "This would make the song splits total {}%. Adjust the split so the song total is 100%.".format(
                            self.format_split(projected_total)
                        ),
                        parent=add_window
                    )
                    return

                collaborators.append(new_collaborator)
                final_total = self.get_song_split_total_from_record(record)
                try:
                    self.save_credit_data()
                    refresh_credit_tree()
                    self.refresh_songs_tab()
                    add_window.destroy()
                    if abs(final_total - 100.0) > 0.01:
                        messagebox.showinfo(
                            "Split Total",
                            "Song splits currently total {}%. Keep adding or editing splits until they equal 100%.".format(
                                self.format_split(final_total)
                            ),
                            parent=popup
                        )
                except Exception as e:
                    messagebox.showerror("Credits Error", "Unable to save collaborator credit:\n{}".format(str(e)), parent=add_window)

            if self.collaborator_profiles:
                collaborator_combo.current(0)

            button_row = tk.Frame(add_window, bg=self.bg_color)
            button_row.pack(fill=tk.X, padx=18, pady=(0, 18))
            tk.Button(
                button_row,
                text="Done",
                command=finish_add_collaborator,
                bg=self.button_bg,
                fg=self.button_fg,
                font=('Arial', 10, 'bold'),
                width=12
            ).pack(side=tk.RIGHT)

        action_row = tk.Frame(right, bg=self.panel_bg)
        action_row.pack(fill=tk.X, padx=12, pady=(0, 12), anchor='w')

        split_sheet_row = tk.Frame(action_row, bg=self.panel_bg)
        split_sheet_row.pack(fill=tk.X, pady=(0, 8), anchor='w')
        tk.Button(
            split_sheet_row,
            text="Generate Split Sheet",
            command=generate_selected_split_sheet,
            bg=self.button_bg,
            fg=self.button_fg,
            activebackground='#3a2514',
            activeforeground=self.button_fg,
            font=('Arial', 9, 'bold'),
            padx=14,
            pady=6
        ).pack(side=tk.LEFT)
        tk.Button(
            split_sheet_row,
            text="View Split Sheet",
            command=view_selected_split_sheet,
            bg=self.button_bg,
            fg=self.button_fg,
            activebackground='#3a2514',
            activeforeground=self.button_fg,
            font=('Arial', 9, 'bold'),
            padx=14,
            pady=6
        ).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(
            split_sheet_row,
            text="Send Split Sheet",
            command=send_selected_split_sheet,
            bg=self.button_bg,
            fg=self.button_fg,
            activebackground='#3a2514',
            activeforeground=self.button_fg,
            font=('Arial', 9, 'bold'),
            padx=14,
            pady=6
        ).pack(side=tk.LEFT, padx=(8, 0))

        collaborator_row = tk.Frame(action_row, bg=self.panel_bg)
        collaborator_row.pack(fill=tk.X, anchor='w')
        tk.Button(
            collaborator_row,
            text="Create Collaborator",
            command=open_create_collaborator_window,
            bg=self.button_bg,
            fg=self.button_fg,
            activebackground='#3a2514',
            activeforeground=self.button_fg,
            font=('Arial', 9, 'bold'),
            padx=14,
            pady=6
        ).pack(side=tk.LEFT)
        tk.Button(
            collaborator_row,
            text="Add Collaborator",
            command=open_add_collaborator_window,
            bg=self.button_bg,
            fg=self.button_fg,
            activebackground='#3a2514',
            activeforeground=self.button_fg,
            font=('Arial', 9, 'bold'),
            padx=14,
            pady=6
        ).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(
            collaborator_row,
            text="Remove Collaborator",
            command=remove_selected_collaborator,
            bg=self.button_bg,
            fg=self.button_fg,
            activebackground='#3a2514',
            activeforeground=self.button_fg,
            font=('Arial', 9, 'bold'),
            padx=14,
            pady=6
        ).pack(side=tk.LEFT, padx=(8, 0))

        for song in songs:
            credit_count, split_total = self.get_song_credit_summary(song)
            song_list.insert(
                tk.END,
                "{} - {}   {}%   {} credits   {}% split".format(
                    song.get('artist', ''),
                    song.get('song', ''),
                    song.get('percent', 0),
                    credit_count,
                    self.format_split(split_total)
                )
            )

        song_list.bind('<<ListboxSelect>>', on_song_selected)
        start_index = 0
        for index, song in enumerate(songs):
            if (song.get('song_folder_id') or song.get('id')) == selected_song_id:
                start_index = index
                break
        if songs:
            song_list.selection_set(start_index)
            song_list.see(start_index)
            choose_song(songs[start_index])

    def refresh_artist_profiles_from_current_folder(self):
        self.artist_profiles_source_folder = self.drive_dest_folder
        self.update_artist_profiles_display()

    def open_artist_profile_popup(self, profile):
        popup = tk.Toplevel(self.root)
        popup.title("{} Profile".format(profile['artist']))
        popup.geometry("560x460")
        popup.configure(bg=self.bg_color)

        header = tk.Frame(popup, bg=self.bg_color)
        header.pack(fill=tk.X, padx=20, pady=(20, 10))

        icon_canvas = tk.Canvas(header, width=92, height=92, bg=self.bg_color, highlightthickness=0)
        icon_canvas.pack(side=tk.LEFT, padx=(0, 15))
        photo = self.load_artist_profile_photo(profile, size=84)
        if photo:
            self.artist_profile_images[('popup', profile['id'])] = photo
            icon_canvas.create_image(46, 46, image=photo)
        else:
            icon_canvas.create_oval(4, 4, 88, 88, fill='#3d5870', outline='#87CEEB', width=2)
            icon_canvas.create_text(
                46,
                46,
                text=self.get_artist_initials(profile['artist']),
                fill=self.fg_color,
                font=('Arial', 18, 'bold')
            )

        summary = tk.Frame(header, bg=self.bg_color)
        summary.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            summary,
            text=profile['artist'],
            bg=self.bg_color,
            fg='#87CEEB',
            font=('Arial', 16, 'bold'),
            anchor='w'
        ).pack(fill=tk.X)
        tk.Label(
            summary,
            text="Overall: {}%   Song drops: {}   Complete: {}".format(
                profile['percent'],
                profile['total_songs'],
                profile['completed_songs']
            ),
            bg=self.bg_color,
            fg=self.fg_color,
            font=('Arial', 10),
            anchor='w'
        ).pack(fill=tk.X, pady=(4, 8))
        progress = ttk.Progressbar(
            summary,
            orient=tk.HORIZONTAL,
            mode='determinate',
            maximum=100,
            value=profile['percent'],
            style='Dark.Horizontal.TProgressbar'
        )
        progress.pack(fill=tk.X)

        tk.Button(
            summary,
            text="Assign Image",
            command=lambda: self.assign_artist_profile_image(profile),
            bg=self.button_bg,
            fg=self.button_fg,
            font=('Arial', 8),
            width=13
        ).pack(anchor='w', pady=(10, 0))
        action_row = tk.Frame(summary, bg=self.bg_color)
        action_row.pack(anchor='w', pady=(6, 0))
        tk.Button(
            action_row,
            text="Delete Artist",
            command=lambda: self.delete_artist_profile(profile, parent_window=popup),
            bg=self.button_bg,
            fg=self.button_fg,
            font=('Arial', 8),
            width=13
        ).pack(side=tk.LEFT)
        tk.Button(
            action_row,
            text="Delete Song",
            command=lambda: self.delete_song_from_profile_popup(profile, parent_window=popup),
            bg=self.button_bg,
            fg=self.button_fg,
            font=('Arial', 8),
            width=12
        ).pack(side=tk.LEFT, padx=(5, 0))

        detail_text = tk.Text(
            popup,
            bg='#1e1e1e',
            fg=self.fg_color,
            font=('Arial', 10),
            wrap=tk.WORD,
            padx=15,
            pady=15
        )
        detail_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        detail_text.tag_config('green', foreground='#7CFC00')
        detail_text.tag_config('yellow', foreground='#FFD700')
        detail_text.tag_config('red', foreground='#FF6347')

        detail_text.insert(tk.END, "{:<32} {:<8} Missing\n".format('Song', 'Status'))
        detail_text.insert(tk.END, "{}\n".format('-'*72))
        for song in profile['songs']:
            detail_text.insert(tk.END, "{:<32} ".format(song['song'][:31]))
            detail_text.insert(tk.END, "{:<8}".format("{}%".format(song['percent'])), song['color'])
            detail_text.insert(tk.END, "{}\n".format(', '.join(song['missing']) if song['missing'] else 'None'))
        detail_text.config(state=tk.DISABLED)

    def refresh_after_drive_delete(self):
        self.update_drive_preview_display()
        self.update_artist_profiles_display()
        self.refresh_songs_tab()
        self.refresh_send_link_dropdowns()

    def delete_drive_folder_by_id(self, folder_id, label):
        drive_folder = self.drive.CreateFile({'id': folder_id})
        drive_folder.FetchMetadata(fields='id,title')
        drive_folder.Delete()
        self.clear_drive_cache()
        self.log("Deleted {}: {}".format(label, drive_folder.get('title', folder_id)))

    def choose_artist_profile_for_delete(self):
        if not self.current_artist_profiles:
            self.update_artist_profiles_display()

        selectable_profiles = [profile for profile in self.current_artist_profiles if profile.get('artist_folder_id')]
        if not selectable_profiles:
            messagebox.showinfo("Delete Artist", "No artist profiles are available to delete.")
            return None

        if len(selectable_profiles) == 1:
            return selectable_profiles[0]

        picker = tk.Toplevel(self.root)
        picker.title("Choose Artist")
        picker.geometry("360x300")
        picker.configure(bg=self.bg_color)
        tk.Label(picker, text="Choose an artist to delete:", bg=self.bg_color, fg=self.fg_color).pack(pady=10)
        listbox = tk.Listbox(picker, bg='#1e1e1e', fg=self.fg_color, selectbackground=self.button_bg)
        listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
        for profile in selectable_profiles:
            listbox.insert(tk.END, "{} ({} song drops)".format(profile['artist'], profile['total_songs']))

        selected = {'profile': None}

        def finish_selection():
            selection = listbox.curselection()
            if selection:
                selected['profile'] = selectable_profiles[selection[0]]
            picker.destroy()

        tk.Button(picker, text="Select", command=finish_selection, bg=self.button_bg, fg=self.button_fg).pack(pady=(0, 10))
        picker.transient(self.root)
        picker.grab_set()
        self.root.wait_window(picker)
        return selected['profile']

    def choose_song_from_profile(self, profile, title="Choose Song"):
        songs = [song for song in profile.get('songs', []) if song.get('song_folder_id')]
        if not songs:
            messagebox.showinfo(title, "No song folders are available to delete.")
            return None

        if len(songs) == 1:
            return songs[0]

        picker = tk.Toplevel(self.root)
        picker.title(title)
        picker.geometry("420x320")
        picker.configure(bg=self.bg_color)
        tk.Label(picker, text="Choose a song to delete:", bg=self.bg_color, fg=self.fg_color).pack(pady=10)
        listbox = tk.Listbox(picker, bg='#1e1e1e', fg=self.fg_color, selectbackground=self.button_bg)
        listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
        for song in songs:
            listbox.insert(tk.END, "{} - {}%".format(song['song'], song['percent']))

        selected = {'song': None}

        def finish_selection():
            selection = listbox.curselection()
            if selection:
                selected['song'] = songs[selection[0]]
            picker.destroy()

        tk.Button(picker, text="Select", command=finish_selection, bg=self.button_bg, fg=self.button_fg).pack(pady=(0, 10))
        picker.transient(self.root)
        picker.grab_set()
        self.root.wait_window(picker)
        return selected['song']

    def delete_artist_profile_from_list(self):
        profile = self.choose_artist_profile_for_delete()
        if profile:
            self.delete_artist_profile(profile)

    def delete_song_from_list(self):
        profile = self.choose_artist_profile_for_delete()
        if not profile:
            return
        song = self.choose_song_from_profile(profile)
        if song:
            self.delete_song_folder(profile, song)

    def delete_artist_profile(self, profile, parent_window=None):
        if not self.drive:
            messagebox.showerror("Drive Error", "Manager Google Drive is not authenticated.")
            return

        artist_folder_id = profile.get('artist_folder_id')
        if not artist_folder_id:
            messagebox.showerror("Delete Artist", "This artist profile does not have a Drive artist folder.")
            return

        confirm = messagebox.askyesno(
            "Delete Artist Profile",
            "Delete the artist profile '{}', including all song folders and profile image?".format(profile['artist'])
        )
        if not confirm:
            return

        try:
            self.delete_drive_folder_by_id(artist_folder_id, "artist profile")
            if parent_window:
                parent_window.destroy()
            self.refresh_after_drive_delete()
        except Exception as e:
            self.log("Failed to delete artist profile: {}".format(str(e)))
            messagebox.showerror("Delete Artist Error", "Unable to delete artist profile:\n{}".format(str(e)))

    def delete_song_from_profile_popup(self, profile, parent_window=None):
        song = self.choose_song_from_profile(profile)
        if song:
            self.delete_song_folder(profile, song, parent_window=parent_window)

    def delete_song_folder(self, profile, song, parent_window=None):
        if not self.drive:
            messagebox.showerror("Drive Error", "Manager Google Drive is not authenticated.")
            return

        song_folder_id = song.get('song_folder_id')
        if not song_folder_id:
            messagebox.showerror("Delete Song", "This song does not have a Drive song folder.")
            return

        confirm = messagebox.askyesno(
            "Delete Song",
            "Delete '{}' by '{}', including all tag folders and files?".format(song['song'], profile['artist'])
        )
        if not confirm:
            return

        try:
            self.delete_drive_folder_by_id(song_folder_id, "song folder")
            if parent_window:
                parent_window.destroy()
            self.refresh_after_drive_delete()
        except Exception as e:
            self.log("Failed to delete song folder: {}".format(str(e)))
            messagebox.showerror("Delete Song Error", "Unable to delete song folder:\n{}".format(str(e)))

    def choose_artist_profile_for_image(self):
        if not self.current_artist_profiles:
            self.update_artist_profiles_display()

        selectable_profiles = [profile for profile in self.current_artist_profiles if profile.get('artist_folder_id')]
        if not selectable_profiles:
            messagebox.showinfo("Assign Image", "No artist profiles are available yet.")
            return None

        if len(selectable_profiles) == 1:
            return selectable_profiles[0]

        picker = tk.Toplevel(self.root)
        picker.title("Choose Artist")
        picker.geometry("360x300")
        picker.configure(bg=self.bg_color)
        tk.Label(picker, text="Choose an artist profile:", bg=self.bg_color, fg=self.fg_color).pack(pady=10)
        listbox = tk.Listbox(picker, bg='#1e1e1e', fg=self.fg_color, selectbackground=self.button_bg)
        listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
        for profile in selectable_profiles:
            listbox.insert(tk.END, profile['artist'])

        selected = {'profile': None}

        def finish_selection():
            selection = listbox.curselection()
            if selection:
                selected['profile'] = selectable_profiles[selection[0]]
            picker.destroy()

        tk.Button(picker, text="Select", command=finish_selection, bg=self.button_bg, fg=self.button_fg).pack(pady=(0, 10))
        picker.transient(self.root)
        picker.grab_set()
        self.root.wait_window(picker)
        return selected['profile']

    def assign_artist_profile_image(self, profile=None):
        if not self.drive:
            messagebox.showerror("Drive Error", "Manager Google Drive is not authenticated.")
            return

        profile = profile or self.choose_artist_profile_for_image()
        if not profile:
            return

        artist_folder_id = profile.get('artist_folder_id')
        if not artist_folder_id:
            messagebox.showerror("Assign Image", "This artist profile does not have a Drive artist folder.")
            return

        image_path = filedialog.askopenfilename(
            title="Choose artist profile image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.webp"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("All files", "*.*")
            ]
        )
        if not image_path:
            return

        try:
            image_folder_id = self.get_artist_profile_image_folder(artist_folder_id, create=True)
            for item in self.get_drive_folder_contents(image_folder_id):
                if not self.is_drive_folder(item):
                    try:
                        self.drive.CreateFile({'id': item['id']}).Delete()
                    except Exception:
                        pass

            filename = "profile{}".format(os.path.splitext(image_path)[1].lower() or '.png')
            drive_file = self.drive.CreateFile({
                'title': filename,
                'parents': [{'id': image_folder_id}]
            })
            drive_file.SetContentFile(image_path)
            drive_file.Upload()
            self.clear_drive_cache()
            self.log("Assigned profile image for {}.".format(profile['artist']))
            self.update_artist_profiles_display()
        except Exception as e:
            self.log("Failed to assign profile image: {}".format(str(e)))
            messagebox.showerror("Assign Image Error", "Unable to assign artist image:\n{}".format(str(e)))

    def update_artist_profiles_display(self):
        if not hasattr(self, 'artist_profiles_text'):
            return
        self.clear_drive_cache()

        self.artist_profiles_text.config(state=tk.NORMAL)
        self.artist_profiles_text.delete(1.0, tk.END)
        self.artist_profiles_progress_bar['value'] = 0
        self.artist_profiles_progress_label.config(text="Overall Progress: 0%")

        if not self.drive:
            self.artist_profiles_source_label.config(text=self.get_drive_folder_display())
            self.artist_profiles_text.insert(tk.END, "Manager Google Drive is not authenticated yet.\n")
            self.current_artist_profiles = []
            self.render_artist_profile_icons([])
            self.artist_profiles_text.config(state=tk.DISABLED)
            return

        source_folder = self.artist_profiles_source_folder or self.drive_dest_folder or 'root'
        self.artist_profiles_source_label.config(text=self.get_drive_folder_path(source_folder))

        try:
            profiles = self.build_artist_profiles_from_drive_folder(source_folder)
            self.current_artist_profiles = profiles
            self.render_artist_profile_icons(profiles)
            if not profiles:
                self.artist_profiles_text.insert(tk.END, "No artist profiles found in this Drive folder.\n\n")
                self.artist_profiles_text.insert(tk.END, "Expected Drive structure:\n")
                self.artist_profiles_text.insert(tk.END, "Artist / Song / Clean, Final, Instrumental, Acapella, Lyrics, Artwork\n")
                self.artist_profiles_text.config(state=tk.DISABLED)
                return

            total_present = sum(profile['total_present'] for profile in profiles)
            total_required = sum(profile['total_required'] for profile in profiles)
            overall_percent = int((total_present / total_required) * 100) if total_required else 0
            total_songs = sum(profile['total_songs'] for profile in profiles)
            completed_songs = sum(profile['completed_songs'] for profile in profiles)

            self.artist_profiles_progress_bar['value'] = overall_percent
            self.artist_profiles_progress_label.config(
                text="Overall Progress: {}% ({} of {} song drops complete)".format(
                    overall_percent,
                    completed_songs,
                    total_songs
                )
            )

            self.artist_profiles_text.insert(tk.END, "Artist Profiles\n", 'header')
            self.artist_profiles_text.insert(tk.END, "Source: {}\n".format(self.get_drive_folder_path(source_folder)))
            self.artist_profiles_text.insert(tk.END, "Artists: {}   Song drops: {}   Complete drops: {}   Overall: {}%\n".format(
                len(profiles),
                total_songs,
                completed_songs,
                overall_percent
            ))
            self.artist_profiles_text.insert(tk.END, "{}\n\n".format('-'*80))

            for profile in profiles:
                self.artist_profiles_text.insert(tk.END, "{}\n".format(profile['artist']), 'header')
                self.artist_profiles_text.insert(
                    tk.END,
                    "Artist progress: {}%   Song drops: {}   Complete: {}\n".format(
                        profile['percent'],
                        profile['total_songs'],
                        profile['completed_songs']
                    ),
                    profile['color']
                )
                self.artist_profiles_text.insert(tk.END, "{:<32} {:<8} Missing\n".format('Song', 'Status'))
                self.artist_profiles_text.insert(tk.END, "{}\n".format('-'*72))

                for song in profile['songs']:
                    percent_label = "{}%".format(song['percent'])
                    self.artist_profiles_text.insert(tk.END, "{:<32} ".format(song['song'][:31]))
                    self.artist_profiles_text.insert(tk.END, "{:<8}".format(percent_label), song['color'])
                    self.artist_profiles_text.insert(
                        tk.END,
                        "{}\n".format(', '.join(song['missing']) if song['missing'] else 'None')
                    )
                self.artist_profiles_text.insert(tk.END, "\n")
        except Exception as e:
            self.current_artist_profiles = []
            self.render_artist_profile_icons([])
            self.artist_profiles_text.insert(tk.END, "Error loading artist profiles: {}\n".format(str(e)))

        self.artist_profiles_text.config(state=tk.DISABLED)

    def update_drive_folder_after_upload(self):
        """Refresh the selected Drive folder after the last upload."""
        app_root_id = self.ensure_app_drive_root_folder()
        if app_root_id:
            self.drive_dest_folder = app_root_id
            self.drive_folder_label.config(text=self.get_drive_folder_display())
            self.save_settings()
            self.log("Google Drive destination remains the app parent folder: {}".format(self.get_drive_folder_display()))
            self.update_drive_preview_display()
            self.refresh_artist_profiles_from_current_folder()
            self.refresh_songs_tab()
            self.refresh_send_link_dropdowns()

    def open_drive_folder_in_browser(self):
        """Open the currently selected Google Drive folder in the browser."""
        import webbrowser
        if not self.drive:
            messagebox.showerror("Error", "Google Drive not authenticated")
            return

        if self.drive_dest_folder == 'root':
            url = 'https://drive.google.com/drive/my-drive'
        else:
            url = 'https://drive.google.com/drive/folders/{}'.format(self.drive_dest_folder)

        webbrowser.open(url)

    def update_drive_preview_display(self):
        """Update the inline Drive folder preview panel."""
        self.drive_preview_text.config(state=tk.NORMAL)
        self.drive_preview_text.delete(1.0, tk.END)

        if not self.drive:
            self.drive_preview_text.insert(tk.END, "Not authenticated with Google Drive.\n")
            self.drive_preview_text.config(state=tk.DISABLED)
            return

        if self.drive_dest_folder == 'root':
            query = "trashed=false and 'root' in parents"
            folder_name = 'My Drive'
        else:
            query = "trashed=false and '{}' in parents".format(self.drive_dest_folder)
            folder_name = self.get_drive_folder_display()

        try:
            self.drive_preview_text.insert(tk.END, "Previewing: {}\n".format(folder_name))
            if self.drive_dest_folder != 'root':
                self.drive_preview_text.insert(tk.END, "Path: {}\n".format(self.get_drive_folder_path(self.drive_dest_folder)))
            self.drive_preview_text.insert(tk.END, "{}\n".format('-'*48))

            files = self.drive.ListFile({'q': query}).GetList()
            self.drive_preview_text.insert(tk.END, "Items in folder: {}\n".format(len(files)))
            if self.current_share_folder_id and self.drive_dest_folder == self.current_share_folder_id:
                current_file_ids = {item['id'] for item in files}
                new_ids = current_file_ids - self.shared_folder_item_ids
                if new_ids and self.shared_folder_item_ids:
                    new_titles = [item['title'] for item in files if item['id'] in new_ids]
                    self.log("New files received via send link: {}".format(', '.join(new_titles)))
                self.shared_folder_item_ids = current_file_ids
                self.root.after(0, self.update_send_link_display)
            if self.last_uploaded_drive_folder_id:
                last_path = self.get_drive_folder_path(self.last_uploaded_drive_folder_id)
                self.drive_preview_text.insert(tk.END, "Last uploaded folder: {}\n".format(last_path))
            self.drive_preview_text.insert(tk.END, "\n")

            folder_status = self.build_drive_folder_status(files, folder_name)
            self.drive_preview_text.insert(tk.END, "Detected tags in this folder: {}\n".format(', '.join(folder_status['present']) if folder_status['present'] else 'None'))
            if folder_status.get('optional_present'):
                self.drive_preview_text.insert(
                    tk.END,
                    "Optional tags present: {} (not required for progress)\n".format(', '.join(folder_status['optional_present']))
                )
            if folder_status['missing']:
                self.drive_preview_text.insert(tk.END, "Missing required tags: {}\n".format(', '.join(folder_status['missing'])))
                self.drive_preview_text.insert(tk.END, "Please upload folders/files for these tags: {}\n".format(', '.join(folder_status['missing'])))
            else:
                self.drive_preview_text.insert(tk.END, "All required tags are present in this folder.\n")
            self.drive_progress_bar['value'] = folder_status['percent']
            self.drive_progress_label.config(text="Progress: {}%".format(folder_status['percent']))
            self.drive_preview_text.insert(tk.END, "Folder progress: {}%\n\n".format(folder_status['percent']))

            if self.last_sent_song_status and self.drive_dest_folder == self.last_uploaded_drive_folder_id:
                self.drive_preview_text.insert(tk.END, "Last upload progress for this folder:\n")
                self.drive_preview_text.insert(tk.END, "{:<24} {:<24} {:<8} Missing\n".format('Artist', 'Song', 'Status'))
                self.drive_preview_text.insert(tk.END, "{}\n".format('-'*80))
                for song in self.last_sent_song_status:
                    self.drive_preview_text.insert(tk.END, "{:<24} {:<24} ".format(song['artist'], song['song']))
                    percent_label = "{}%".format(song['percent'])
                    self.drive_preview_text.insert(tk.END, "{:<8}".format(percent_label), song['color'])
                    self.drive_preview_text.insert(tk.END, "{}\n".format(', '.join(song['missing']) if song['missing'] else 'None'))
                self.drive_preview_text.insert(tk.END, "\n")
            elif self.last_sent_song_status:
                self.drive_preview_text.insert(tk.END, "Last upload progress is available only for the last uploaded song folder.\n")
                self.drive_preview_text.insert(tk.END, "Select or preview the same folder to see exact song progress.\n\n")

            if not files:
                self.drive_preview_text.insert(tk.END, "No items found in this Drive folder.\n")
            else:
                for file_item in files[:50]:
                    icon = '[Folder]' if file_item['mimeType'] == 'application/vnd.google-apps.folder' else '[File]'
                    tag = 'folder' if icon == '[Folder]' else 'file'
                    self.drive_preview_text.insert(tk.END, "{} {}\n".format(icon, file_item['title']), tag)
                if len(files) > 50:
                    self.drive_preview_text.insert(tk.END, "...and more items not shown\n")
        except Exception as e:
            self.drive_preview_text.insert(tk.END, "Error loading preview: {}\n".format(str(e)))

        self.drive_preview_text.config(state=tk.DISABLED)

    def show_drive_folder_contents(self):
        """Show the contents of the current Google Drive folder."""
        if not self.drive:
            messagebox.showerror("Error", "Google Drive not authenticated")
            return

        if self.drive_dest_folder == 'root':
            query = "trashed=false and 'root' in parents"
        else:
            query = "trashed=false and '{}' in parents".format(self.drive_dest_folder)

        try:
            files = self.drive.ListFile({'q': query}).GetList()
            if not files:
                messagebox.showinfo("Drive Folder Contents", "No items found in the current Drive folder.")
                return

            contents = []
            for file_item in files[:50]:
                icon = '[Folder]' if file_item['mimeType'] == 'application/vnd.google-apps.folder' else '[File]'
                contents.append('{} {}'.format(icon, file_item['title']))

            if len(files) > 50:
                contents.append('...and more items not shown')

            messagebox.showinfo("Drive Folder Contents", "\n".join(contents))
        except Exception as e:
            messagebox.showerror("Drive Folder Error", "Failed to load contents:\n{}".format(str(e)))

    def show_drive_folder_picker(self, parent_id='root'):
        """Show a simple folder picker for Google Drive"""
        picker_window = tk.Toplevel(self.root)
        picker_window.title("Choose Google Drive Folder")
        picker_window.geometry("400x300")
        picker_window.configure(bg=self.bg_color)
        
        tk.Label(picker_window, text="Select destination folder in Google Drive:", 
                bg=self.bg_color, fg=self.fg_color).pack(pady=10)
        
        listbox = tk.Listbox(picker_window, bg='#1e1e1e', fg=self.fg_color, selectbackground=self.button_bg)
        listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0,10))
        
        # Add root option
        listbox.insert(tk.END, "[Folder] Root Folder")

        try:
            if parent_id == 'root':
                query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
            else:
                query = "mimeType='application/vnd.google-apps.folder' and '{}' in parents and trashed=false".format(parent_id)
            file_list = self.drive.ListFile({'q': query}).GetList()
            for folder in file_list[:50]:
                listbox.insert(tk.END, "[Folder] {}".format(folder['title']))
        except Exception as e:
            listbox.insert(tk.END, "Error loading folders: {}".format(str(e)))
        
        def select_folder():
            selection = listbox.curselection()
            if selection:
                index = selection[0]
                if index == 0:
                    self.drive_dest_folder = 'root'
                else:
                    try:
                        self.drive_dest_folder = file_list[index-1]['id']
                    except:
                        self.drive_dest_folder = 'root'
                
                self.drive_folder_label.config(text=self.get_drive_folder_display())
                self.save_settings()
                self.log("Google Drive destination changed to: {}".format(self.get_drive_folder_display()))
                self.artist_profiles_source_folder = self.drive_dest_folder
                self.update_drive_preview_display()
                self.update_artist_profiles_display()
                picker_window.destroy()
        
        tk.Button(picker_window, text="Select", command=select_folder, bg=self.button_bg, fg=self.button_fg).pack(pady=10)

    def get_or_create_drive_folder(self, title, parent_id='root'):
        """Get or create a Drive folder with the given title under the parent."""
        try:
            existing_folder = self.find_drive_child_folder_case_insensitive(title, parent_id)
            if existing_folder:
                return existing_folder['id']

            query = "title='{}' and mimeType='application/vnd.google-apps.folder' and '{}' in parents and trashed=false".format(self.escape_drive_query_value(title), parent_id)
            existing = self.drive.ListFile({'q': query}).GetList()
            if existing:
                return existing[0]['id']

            folder = self.drive.CreateFile({
                'title': title,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [{'id': parent_id}]
            })
            folder.Upload()
            self.clear_drive_cache()
            return folder['id']
        except Exception as e:
            self.log("Failed to create or find Drive folder '{}': {}".format(title, str(e)))
            raise

    def ensure_app_drive_root_folder(self):
        """Create or find the fixed parent folder used by this app."""
        if not self.drive:
            return None
        if self.app_drive_root_folder_id:
            return self.app_drive_root_folder_id

        self.app_drive_root_folder_id = self.get_or_create_drive_folder(APP_DRIVE_ROOT_FOLDER_NAME, 'root')
        return self.app_drive_root_folder_id

    def get_current_share_song_context(self):
        """Return artist/song names for the active sender link folder."""
        context = {
            'artist': '',
            'song': '',
            'folder_id': self.current_share_folder_id
        }
        if not self.current_share_folder_id or not self.drive:
            return context

        try:
            song_folder = self.get_drive_folder_metadata(self.current_share_folder_id)
            context['song'] = song_folder.get('title', '')
            parents = song_folder.get('parents') or []
            parent_id = parents[0].get('id') if parents else None
            if parent_id:
                artist_folder = self.get_drive_folder_metadata(parent_id)
                context['artist'] = artist_folder.get('title', '')
        except Exception:
            pass
        return context

    def get_sender_portal_status(self):
        """Build the sender-facing checklist for the active song folder."""
        context = self.get_current_share_song_context()
        items = self.get_drive_folder_contents(self.current_share_folder_id) if self.current_share_folder_id else []
        folder_status = self.build_drive_folder_status(items, context.get('song') or self.get_drive_folder_display())
        required = self.get_required_tags()
        optional = self.get_optional_tags()
        submitted = [
            {
                'tag': tag,
                'present': tag in folder_status['present']
            }
            for tag in required
        ]
        return {
            'artist': context.get('artist', ''),
            'song': context.get('song', ''),
            'required': required,
            'optional': optional,
            'present': folder_status['present'],
            'optional_present': folder_status.get('optional_present', []),
            'missing': folder_status['missing'],
            'percent': folder_status['percent'],
            'submitted': submitted
        }

    def validate_sender_filename(self, filename):
        """Validate a sender filename against the active artist/song and required tags."""
        clean_filename = os.path.basename(filename).replace('\x00', '').strip()
        artist, song, tag = self.parse_filename(clean_filename)
        if not (artist and song and tag):
            return False, "Wrong filename format: {}".format(clean_filename)

        context = self.get_current_share_song_context()
        expected_artist = context.get('artist', '').strip()
        expected_song = context.get('song', '').strip()
        normalized_tag = self.normalize_tag(tag)
        if expected_artist and artist.strip().casefold() != expected_artist.casefold():
            return False, "Artist should be '{}': {}".format(expected_artist, clean_filename)
        if expected_song and song.strip().casefold() != expected_song.casefold():
            return False, "Song should be '{}': {}".format(expected_song, clean_filename)
        if normalized_tag not in self.get_required_tags() + self.get_optional_tags():
            return False, "Tag should be Clean, Final, Instrumental, Acapella, Lyrics, Artwork, or Session Files: {}".format(clean_filename)
        return True, ""

    def validate_sender_upload_filenames(self, filenames):
        wrong = []
        for filename in filenames:
            ok, message = self.validate_sender_filename(filename)
            if not ok:
                wrong.append(message)
        return wrong

    def build_signature_portal_html(self, token):
        request = self.get_signature_request(token)
        if not request:
            return self.build_sender_result_html(
                "Signature link not found",
                "This signature link is missing or expired.",
                is_error=True
            )
        if request.get('status') == 'signed':
            return self.build_sender_result_html(
                "Already Signed",
                "This split sheet has already been signed and received."
            )

        split_sheet_url = html_escape(request.get('split_sheet_url') or '#')
        artist = html_escape(request.get('artist', ''))
        song = html_escape(request.get('song', ''))
        name = html_escape(request.get('name', ''))
        return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Split Sheet Signature</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #20140c; color: #f6ead8; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 42px 22px; }}
    h1 {{ margin: 0 0 8px; }}
    p {{ color: #d8c7b4; line-height: 1.5; }}
    form {{ margin-top: 22px; padding: 22px; background: #17100a; border: 1px solid #5a3518; }}
    label {{ display: block; margin: 14px 0 6px; color: #ffb45a; font-weight: 700; font-size: 13px; }}
    input, textarea {{ width: 100%; box-sizing: border-box; background: #2b2118; color: #f6ead8; border: 1px solid #5a3518; padding: 11px; font: inherit; }}
    textarea {{ min-height: 100px; }}
    button, a.button {{ display: inline-block; margin-top: 18px; background: #ff9f2e; color: #120c07; border: 0; padding: 12px 16px; font-weight: 700; text-decoration: none; cursor: pointer; }}
    a.button {{ background: #2b2118; color: #f6ead8; border: 1px solid #5a3518; margin-right: 8px; }}
    .box {{ padding: 14px; background: #2b2118; border: 1px solid #5a3518; }}
  </style>
</head>
<body>
  <main>
    <h1>Review and Sign Split Sheet</h1>
    <p class="box"><strong>Song:</strong> {artist} - {song}<br><strong>Contributor:</strong> {name}</p>
    <p>Open the Google Doc, review the split sheet, then sign below. Your signed confirmation will be saved back into the song folder.</p>
    <a class="button" href="{split_sheet_url}" target="_blank" rel="noopener">Open Split Sheet</a>
    <form action="/signature/{token}" method="post">
      <label for="signature_name">Typed Signature</label>
      <input id="signature_name" name="signature_name" value="{name}" required>
      <label for="email">Email</label>
      <input id="email" name="email" type="email" value="{email}" required>
      <label for="notes">Notes</label>
      <textarea id="notes" name="notes"></textarea>
      <label>
        <input name="agreement" type="checkbox" value="yes" required style="width:auto;margin-right:8px;">
        I reviewed and approve this split sheet.
      </label>
      <button type="submit">Submit Signature</button>
    </form>
  </main>
</body>
</html>""".format(
            artist=artist,
            song=song,
            name=name,
            email=html_escape(request.get('email', '')),
            split_sheet_url=split_sheet_url,
            token=html_escape(token)
        )

    def save_signature_submission(self, token, form_data):
        request = self.get_signature_request(token)
        if not request:
            raise RuntimeError("Signature request not found.")
        if form_data.get('agreement', [''])[0] != 'yes':
            raise RuntimeError("Signature agreement is required.")

        signature_name = (form_data.get('signature_name', [''])[0] or '').strip()
        email = (form_data.get('email', [''])[0] or '').strip()
        notes = (form_data.get('notes', [''])[0] or '').strip()
        if not signature_name or not email:
            raise RuntimeError("Name and email are required.")

        signed_at = time.strftime('%Y-%m-%d %H:%M:%S')
        html_content = """<!doctype html>
<html><head><meta charset="utf-8"></head><body>
<h1>Signed Split Sheet Confirmation</h1>
<p><strong>Song:</strong> {artist} - {song}</p>
<p><strong>Contributor:</strong> {name}</p>
<p><strong>Email:</strong> {email}</p>
<p><strong>Signed At:</strong> {signed_at}</p>
<p><strong>Agreement:</strong> I reviewed and approve this split sheet.</p>
<p><strong>Split Sheet:</strong> <a href="{split_sheet_url}">{split_sheet_url}</a></p>
<h2>Notes</h2>
<p>{notes}</p>
</body></html>""".format(
            artist=html_escape(request.get('artist', '')),
            song=html_escape(request.get('song', '')),
            name=html_escape(signature_name),
            email=html_escape(email),
            signed_at=html_escape(signed_at),
            split_sheet_url=html_escape(request.get('split_sheet_url', '')),
            notes=html_escape(notes).replace('\n', '<br>')
        )

        signatures_folder_id = request.get('signatures_folder_id')
        if not signatures_folder_id:
            signatures_folder_id = self.get_or_create_drive_folder(SIGNED_SPLIT_SHEETS_FOLDER_NAME, request.get('song_folder_id'))
            request['signatures_folder_id'] = signatures_folder_id

        safe_title = re.sub(r'[<>:"/\\\\|?*]+', '-', "{} - {} Signature".format(
            request.get('song', 'Song'),
            signature_name
        )).strip()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as temp_file:
                temp_file.write(html_content)
                temp_path = temp_file.name
            drive_file = self.drive.CreateFile({
                'title': safe_title,
                'parents': [{'id': signatures_folder_id}],
                'mimeType': 'text/html'
            })
            drive_file.SetContentFile(temp_path)
            drive_file.Upload(param={'convert': True})
            drive_file.FetchMetadata(fields='id,title,alternateLink')
            request['status'] = 'signed'
            request['signed_at'] = int(time.time())
            request['signed_name'] = signature_name
            request['signed_email'] = email
            request['signed_document_id'] = drive_file.get('id')
            request['signed_document_url'] = drive_file.get('alternateLink') or 'https://docs.google.com/document/d/{}/edit'.format(drive_file.get('id'))
            self.signature_requests[token] = request
            self.save_drive_json_file(SIGNATURE_REQUESTS_JSON, {'requests': self.signature_requests})
            self.clear_drive_cache()
            self.threadsafe_log("Signed split sheet received from {} for {} - {}".format(
                signature_name,
                request.get('artist', ''),
                request.get('song', '')
            ))
            return request
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def build_sender_portal_html(self):
        """Build the local HTML upload portal."""
        folder_name = html_escape(self.get_drive_folder_display())
        drive_url = html_escape(self.share_link_url or '#')
        status_json = json.dumps(self.get_sender_portal_status())
        return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Music Upload Portal</title>
  <style>
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #2b2b2b;
      color: #ffffff;
    }}
    .topbar {{
      border-bottom: 1px solid #3a3a3a;
      background: #202020;
    }}
    .topbar-inner {{
      max-width: 920px;
      margin: 0 auto;
      padding: 18px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    .brand {{
      font-size: 15px;
      font-weight: 700;
    }}
    .status {{
      border: 1px solid #4caf50;
      color: #9dff9d;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
    }}
    main {{
      max-width: 920px;
      margin: 0 auto;
      padding: 36px 24px 48px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 28px;
      line-height: 1.2;
    }}
    h2 {{
      margin: 0 0 8px;
      font-size: 20px;
      line-height: 1.25;
    }}
    p {{
      line-height: 1.5;
      color: #d6d6d6;
    }}
    .destination {{
      margin: 18px 0 24px;
      padding: 14px 16px;
      background: #4a4a4a;
      border: 1px solid #5a5a5a;
      overflow-wrap: anywhere;
    }}
    .label {{
      display: block;
      color: #bdbdbd;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 6px;
      text-transform: uppercase;
    }}
    form {{
      margin-top: 18px;
      padding: 24px;
      background: #1e1e1e;
      border: 1px solid #4a4a4a;
    }}
    .dropzone {{
      border: 1px dashed #777777;
      background: #252525;
      padding: 28px;
      text-align: center;
    }}
    input[type=file] {{
      display: block;
      width: 100%;
      margin: 18px 0 0;
      color: #f5f5f5;
    }}
    .contact-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      margin-bottom: 20px;
    }}
    .profile-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-top: 14px;
    }}
    input[type=text],
    input[type=email],
    input[type=tel],
    textarea {{
      width: 100%;
      border: 1px solid #5a5a5a;
      background: #252525;
      color: #ffffff;
      padding: 11px 12px;
      font: inherit;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    button, a.button {{
      display: inline-block;
      border: 0;
      background: #4caf50;
      color: #101010;
      padding: 13px 18px;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
      font-size: 14px;
    }}
    a.button {{
      background: #4a4a4a;
      color: #ffffff;
      border: 1px solid #6a6a6a;
    }}
    .hint {{
      font-size: 14px;
      color: #bdbdbd;
    }}
    .selected {{
      min-height: 20px;
      margin-top: 12px;
      color: #9dff9d;
      font-size: 13px;
      font-weight: 700;
    }}
    .checklist {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin: 18px 0;
    }}
    .check-item {{
      border: 1px solid #4a4a4a;
      background: #242424;
      padding: 10px;
      font-size: 13px;
      font-weight: 700;
    }}
    .ok {{
      border-left: 4px solid #4caf50;
      color: #9dff9d;
    }}
    .missing {{
      border-left: 4px solid #ff6347;
      color: #ffb0a6;
    }}
    .pending {{
      border-left: 4px solid #ffd700;
      color: #ffe784;
    }}
    .warning-list {{
      margin-top: 12px;
      color: #ffb0a6;
      font-size: 13px;
      line-height: 1.45;
    }}
    .status-summary {{
      margin-top: 10px;
      color: #d6d6d6;
      font-size: 14px;
    }}
    @media (max-width: 640px) {{
      .topbar-inner {{
        align-items: flex-start;
        flex-direction: column;
      }}
      .contact-grid {{
        grid-template-columns: 1fr;
      }}
      .profile-grid {{
        grid-template-columns: 1fr;
      }}
      h1 {{
        font-size: 24px;
      }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">Music Distribution Organizer</div>
      <div class="status">Sender Portal Active</div>
    </div>
  </header>
  <main>
    <h1>Upload files for this song</h1>
    <p>Send your masters, clean versions, instrumentals, acapellas, lyrics, and artwork here. Files submitted through this page go straight to the selected Google Drive song folder.</p>
    <div class="destination">
      <span class="label">Destination</span>
      {folder_name}
    </div>
    <section>
      <span class="label">Before upload</span>
      <div id="status-summary" class="status-summary"></div>
      <div id="checklist" class="checklist"></div>
      <div id="warnings" class="warning-list"></div>
    </section>
    <form action="/upload" method="post" enctype="multipart/form-data">
      <div class="contact-grid">
        <div>
          <label class="label" for="sender_email">Email</label>
          <input id="sender_email" name="sender_email" type="email" autocomplete="email" required>
        </div>
        <div>
          <label class="label" for="sender_phone">Phone</label>
          <input id="sender_phone" name="sender_phone" type="tel" autocomplete="tel">
        </div>
      </div>
      <div class="dropzone">
        <label class="label" for="files">Choose files</label>
        <p class="hint">Use filenames like Artist - Song Name (Final).wav</p>
        <input id="files" name="files" type="file" multiple required>
        <div id="selected" class="selected"></div>
      </div>
      <div class="actions">
        <button id="upload-button" type="submit">Upload to Drive</button>
        <a class="button" href="{drive_url}" target="_blank" rel="noopener">Open Drive Folder</a>
      </div>
    </form>
    <form action="/collaborator-profile" method="post">
      <h2>Create collaborator profile</h2>
      <p class="hint">Save your collaborator details to the manager's collaborator profile library.</p>
      <div class="contact-grid">
        <div>
          <label class="label" for="collaborator_name">Name</label>
          <input id="collaborator_name" name="collaborator_name" type="text" autocomplete="name" required>
        </div>
        <div>
          <label class="label" for="collaborator_email">Email</label>
          <input id="collaborator_email" name="collaborator_email" type="email" autocomplete="email" required>
        </div>
      </div>
      <div class="profile-grid">
        <div>
          <label class="label" for="collaborator_bmi">BMI</label>
          <input id="collaborator_bmi" name="collaborator_bmi" type="text">
        </div>
        <div>
          <label class="label" for="collaborator_ascap">ASCAP</label>
          <input id="collaborator_ascap" name="collaborator_ascap" type="text">
        </div>
        <div>
          <label class="label" for="collaborator_pro">PRO</label>
          <input id="collaborator_pro" name="collaborator_pro" type="text">
        </div>
      </div>
      <div style="margin-top:14px;">
        <label class="label" for="collaborator_notes">Notes</label>
        <textarea id="collaborator_notes" name="collaborator_notes" rows="4"></textarea>
      </div>
      <div class="actions">
        <button type="submit">Create Collaborator Profile</button>
      </div>
    </form>
    <p class="hint">Keep the Music Distribution Organizer app open while uploading.</p>
  </main>
  <script>
    const portalStatus = {status_json};
    const input = document.getElementById('files');
    const selected = document.getElementById('selected');
    const checklist = document.getElementById('checklist');
    const warnings = document.getElementById('warnings');
    const statusSummary = document.getElementById('status-summary');
    const uploadButton = document.getElementById('upload-button');
    const required = portalStatus.required || [];
    const optional = portalStatus.optional || [];
    const expectedArtist = (portalStatus.artist || '').toLowerCase();
    const expectedSong = (portalStatus.song || '').toLowerCase();

    function normalizeTag(tag) {{
      const value = (tag || '').trim().toLowerCase();
      if (value === 'artwork' || value === 'cover') return 'Artwork';
      if (value === 'acapella') return 'Acapella';
      if (value === 'instrumental') return 'Instrumental';
      if (value === 'lyrics') return 'Lyrics';
      if (value === 'clean') return 'Clean';
      if (value === 'final') return 'Final';
      if (['session', 'sessions', 'session file', 'session files', 'sessionfiles'].includes(value)) return 'Session Files';
      return tag;
    }}

    function parseFilename(name) {{
      const base = name.replace(/\\.[^/.]+$/, '');
      const match = base.match(/^(.+?)\\s*-\\s*(.+?)\\s*\\((.+?)\\)$/);
      if (!match) return null;
      return {{
        artist: match[1].trim(),
        song: match[2].trim(),
        tag: normalizeTag(match[3].trim())
      }};
    }}

    function getSelectedStatus() {{
      const selectedTags = new Set();
      const wrong = [];
      Array.from(input.files).forEach(file => {{
        const parsed = parseFilename(file.name);
        if (!parsed) {{
          wrong.push(`${{file.name}} - wrong format`);
          return;
        }}
        if (expectedArtist && parsed.artist.toLowerCase() !== expectedArtist) {{
          wrong.push(`${{file.name}} - artist should be "${{portalStatus.artist}}"`);
          return;
        }}
        if (expectedSong && parsed.song.toLowerCase() !== expectedSong) {{
          wrong.push(`${{file.name}} - song should be "${{portalStatus.song}}"`);
          return;
        }}
        if (!required.includes(parsed.tag) && !optional.includes(parsed.tag)) {{
          wrong.push(`${{file.name}} - unsupported tag "${{parsed.tag}}"`);
          return;
        }}
        selectedTags.add(parsed.tag);
      }});
      return {{ selectedTags, wrong }};
    }}

    function renderChecklist() {{
      const present = new Set(portalStatus.present || []);
      const optionalPresent = new Set(portalStatus.optional_present || []);
      const {{ selectedTags, wrong }} = getSelectedStatus();
      checklist.innerHTML = '';
      required.forEach(tag => {{
        const item = document.createElement('div');
        if (present.has(tag)) {{
          item.className = 'check-item ok';
          item.textContent = `[OK] ${{tag}} already submitted`;
        }} else if (selectedTags.has(tag)) {{
          item.className = 'check-item pending';
          item.textContent = `[SELECTED] ${{tag}}`;
        }} else {{
          item.className = 'check-item missing';
          item.textContent = `[MISSING] ${{tag}}`;
        }}
        checklist.appendChild(item);
      }});
      optional.forEach(tag => {{
        const item = document.createElement('div');
        if (optionalPresent.has(tag)) {{
          item.className = 'check-item ok';
          item.textContent = `[OPTIONAL OK] ${{tag}} submitted`;
        }} else if (selectedTags.has(tag)) {{
          item.className = 'check-item pending';
          item.textContent = `[OPTIONAL SELECTED] ${{tag}}`;
        }} else {{
          item.className = 'check-item pending';
          item.textContent = `[OPTIONAL] ${{tag}} not required`;
        }}
        checklist.appendChild(item);
      }});

      const stillMissing = required.filter(tag => !present.has(tag) && !selectedTags.has(tag));
      statusSummary.textContent = `${{portalStatus.percent}}% complete before this upload. Missing after selected files: ${{stillMissing.length ? stillMissing.join(', ') : 'None'}}.`;
      warnings.innerHTML = wrong.length
        ? '<strong>Wrong file names:</strong><br>' + wrong.map(item => `- ${{item}}`).join('<br>')
        : '';
      uploadButton.disabled = wrong.length > 0;
      uploadButton.textContent = wrong.length > 0 ? 'Fix File Names First' : 'Upload to Drive';
    }}

    input.addEventListener('change', () => {{
      const count = input.files.length;
      selected.textContent = count ? `${{count}} file${{count === 1 ? '' : 's'}} selected` : '';
      renderChecklist();
    }});
    renderChecklist();
  </script>
</body>
</html>""".format(folder_name=folder_name, drive_url=drive_url, status_json=status_json)

    def build_sender_result_html(self, title, message, items=None, is_error=False):
        item_html = ''
        if items:
            rows = []
            for item in items:
                if isinstance(item, dict):
                    name = html_escape(item.get('name', 'Uploaded file'))
                    url = html_escape(item.get('url', '#'))
                    rows.append('<li><a href="{}" target="_blank" rel="noopener">{}</a></li>'.format(url, name))
                else:
                    rows.append('<li>{}</li>'.format(html_escape(str(item))))
            item_html = '<ul>{}</ul>'.format(''.join(rows))
        accent = '#ff6347' if is_error else '#4caf50'
        return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #2b2b2b;
      color: #ffffff;
    }}
    main {{
      max-width: 720px;
      margin: 0 auto;
      padding: 48px 24px;
    }}
    .panel {{
      background: #1e1e1e;
      border: 1px solid #4a4a4a;
      border-left: 4px solid {accent};
      padding: 26px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 28px;
    }}
    p, li {{
      color: #d6d6d6;
      line-height: 1.5;
    }}
    a {{
      display: inline-block;
      margin-top: 16px;
      background: #4a4a4a;
      border: 1px solid #6a6a6a;
      color: #ffffff;
      padding: 12px 16px;
      text-decoration: none;
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>{title}</h1>
      <p>{message}</p>
      {item_html}
      <a href="/">Upload more files</a>
    </section>
  </main>
</body>
</html>""".format(
            title=html_escape(title),
            message=html_escape(message),
            item_html=item_html,
            accent=accent
        )

    def get_lan_ip_address(self):
        """Return the best LAN IP for sharing the local portal on the current network."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(('8.8.8.8', 80))
                ip_address = sock.getsockname()[0]
                if ip_address and not ip_address.startswith('127.'):
                    return ip_address
        except Exception:
            pass

        try:
            ip_address = socket.gethostbyname(socket.gethostname())
            if ip_address and not ip_address.startswith('127.'):
                return ip_address
        except Exception:
            pass

        return None

    def format_sender_link_expiration(self):
        if not self.sender_link_expires_at:
            return 'Not set'
        return time.strftime('%A, %B %d, %Y at %I:%M %p', time.localtime(self.sender_link_expires_at)).replace(' 0', ' ')

    def format_sender_link_time_remaining(self):
        if not self.sender_link_expires_at:
            return 'Not set'

        remaining_seconds = max(0, int(self.sender_link_expires_at - time.time()))
        days, remainder = divmod(remaining_seconds, 24 * 60 * 60)
        hours, remainder = divmod(remainder, 60 * 60)
        minutes, _ = divmod(remainder, 60)

        if days:
            return '{} day(s), {} hour(s)'.format(days, hours)
        if hours:
            return '{} hour(s), {} minute(s)'.format(hours, minutes)
        return '{} minute(s)'.format(minutes)

    def schedule_sender_link_expiration(self):
        if self.sender_link_expire_after_id:
            try:
                self.root.after_cancel(self.sender_link_expire_after_id)
            except Exception:
                pass
            self.sender_link_expire_after_id = None

        if not self.sender_link_expires_at:
            return

        remaining_ms = max(1000, int((self.sender_link_expires_at - time.time()) * 1000))
        self.sender_link_expire_after_id = self.root.after(remaining_ms, self.expire_sender_link)

    def expire_sender_link(self):
        self.sender_link_expire_after_id = None
        if self.current_share_folder_id and self.sender_link_expires_at and time.time() >= self.sender_link_expires_at:
            self.close_share_link(automatic=True)
            messagebox.showinfo("Send Link Expired", "The 7-day sender link has expired and was closed.")

    def find_ngrok_executable(self):
        """Find ngrok when it is on PATH, next to the app, or in common download folders."""
        candidates = []
        path_ngrok = shutil.which('ngrok')
        if path_ngrok:
            candidates.append(path_ngrok)

        app_dir = os.getcwd()
        candidates.extend([
            os.path.join(app_dir, 'ngrok.exe'),
            os.path.join(app_dir, 'ngrok', 'ngrok.exe'),
            os.path.join(os.path.expanduser('~'), 'Downloads', 'ngrok.exe'),
            os.path.join(os.path.expanduser('~'), 'Downloads', 'ngrok-v3-stable-windows-amd64', 'ngrok.exe'),
            os.path.join(os.path.expanduser('~'), 'Desktop', 'ngrok.exe'),
        ])

        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate

        downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
        try:
            for root_dir, _, filenames in os.walk(downloads_dir):
                if 'ngrok.exe' in filenames:
                    return os.path.join(root_dir, 'ngrok.exe')
        except Exception:
            pass

        return None

    def get_ngrok_public_url(self):
        """Read the public HTTPS URL from ngrok's local inspection API."""
        try:
            with urlopen('http://127.0.0.1:4040/api/tunnels', timeout=1) as response:
                payload = json.loads(response.read().decode('utf-8'))
            tunnels = payload.get('tunnels', [])
            for tunnel in tunnels:
                public_url = tunnel.get('public_url', '')
                config = tunnel.get('config') or {}
                addr = config.get('addr', '')
                if public_url == NGROK_SENDER_URL and str(self.sender_portal_port) in addr:
                    return public_url
            for tunnel in tunnels:
                public_url = tunnel.get('public_url', '')
                config = tunnel.get('config') or {}
                addr = config.get('addr', '')
                if public_url.startswith('https://') and str(self.sender_portal_port) in addr:
                    return public_url
        except Exception:
            return None

        return None

    def start_ngrok_tunnel(self, port):
        """Start ngrok for the sender portal and return its public URL if available."""
        self.ngrok_public_url = None
        self.ngrok_error = None

        ngrok_path = self.find_ngrok_executable()
        if not ngrok_path:
            self.ngrok_error = "ngrok.exe was not found. Put ngrok.exe next to this app or add it to PATH."
            self.log(self.ngrok_error)
            return None

        try:
            existing_url = self.get_ngrok_public_url()
            if existing_url:
                self.ngrok_public_url = existing_url
                return existing_url

            self.ngrok_process = subprocess.Popen(
                [ngrok_path, 'http', str(port), '--url', NGROK_SENDER_URL],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            for _ in range(20):
                time.sleep(0.25)
                if self.ngrok_process.poll() is not None:
                    self.ngrok_error = "ngrok started and then stopped. Run 'ngrok config add-authtoken YOUR_TOKEN' if your account is not configured yet."
                    self.log(self.ngrok_error)
                    self.ngrok_process = None
                    return None
                public_url = self.get_ngrok_public_url()
                if public_url:
                    self.ngrok_public_url = public_url
                    self.log("ngrok public sender portal started: {}".format(public_url))
                    return public_url

            self.ngrok_error = "ngrok started, but no public URL appeared at http://127.0.0.1:4040/api/tunnels."
            self.log(self.ngrok_error)
            error_message = self.ngrok_error
            self.stop_ngrok_tunnel()
            self.ngrok_error = error_message
        except Exception as e:
            self.ngrok_error = "Unable to start ngrok: {}".format(str(e))
            self.log(self.ngrok_error)

        return None

    def stop_ngrok_tunnel(self):
        if self.ngrok_process:
            try:
                self.ngrok_process.terminate()
                self.ngrok_process.wait(timeout=3)
            except Exception:
                try:
                    self.ngrok_process.kill()
                except Exception:
                    pass
            self.ngrok_process = None
        self.ngrok_public_url = None
        self.ngrok_error = None

    def start_sender_portal(self):
        """Start an upload portal for the active send-link folder."""
        if self.sender_portal_server:
            return self.sender_portal_url

        app = self

        class SenderPortalHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def send_html(self, status, html):
                payload = html.encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def send_json(self, status, data):
                payload = json.dumps(data).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path in ['/', '/index.html']:
                    self.send_html(200, app.build_sender_portal_html())
                    return
                if parsed.path == '/status':
                    self.send_json(200, app.get_sender_portal_status())
                    return
                if parsed.path.startswith('/signature/'):
                    token = unquote(parsed.path.split('/signature/', 1)[1]).strip('/')
                    self.send_html(200, app.build_signature_portal_html(token))
                    return
                self.send_html(404, '<h1>Not found</h1>')

            def do_POST(self):
                parsed = urlparse(self.path)
                if parsed.path.startswith('/signature/'):
                    token = unquote(parsed.path.split('/signature/', 1)[1]).strip('/')
                    try:
                        content_length = int(self.headers.get('Content-Length', '0'))
                        raw_body = self.rfile.read(content_length).decode('utf-8')
                        signed_request = app.save_signature_submission(token, parse_qs(raw_body))
                        self.send_html(
                            200,
                            app.build_sender_result_html(
                                'Signature Received',
                                'Thank you. Your signed confirmation was saved to the song folder.',
                                [{'name': signed_request.get('signed_document_url', 'Signed document')}]
                            )
                        )
                    except Exception as e:
                        app.threadsafe_log("Signature submission failed: {}".format(str(e)))
                        self.send_html(
                            500,
                            app.build_sender_result_html(
                                'Signature failed',
                                str(e),
                                is_error=True
                            )
                    )
                    return

                if parsed.path == '/collaborator-profile':
                    try:
                        content_length = int(self.headers.get('Content-Length', '0'))
                        raw_body = self.rfile.read(content_length).decode('utf-8')
                        profile = app.save_sender_collaborator_profile(parse_qs(raw_body))
                        app.threadsafe_log("Collaborator profile saved from sender portal: {}".format(profile.get('name', '')))
                        self.send_html(
                            200,
                            app.build_sender_result_html(
                                'Collaborator profile saved',
                                '{} was saved to the collaborator profile library.'.format(profile.get('name', 'Collaborator'))
                            )
                        )
                    except Exception as e:
                        app.threadsafe_log("Collaborator profile submission failed: {}".format(str(e)))
                        self.send_html(
                            400,
                            app.build_sender_result_html(
                                'Profile not saved',
                                str(e),
                                is_error=True
                            )
                        )
                    return

                if parsed.path != '/upload':
                    self.send_html(404, '<h1>Not found</h1>')
                    return

                try:
                    content_type = self.headers.get('Content-Type', '')
                    content_length = int(self.headers.get('Content-Length', '0'))
                    body = self.rfile.read(content_length)
                    raw_message = (
                        'Content-Type: {}\r\nMIME-Version: 1.0\r\n\r\n'.format(content_type).encode('utf-8') + body
                    )
                    message = BytesParser(policy=email_policy).parsebytes(raw_message)

                    contact_info = {
                        'email': '',
                        'phone': ''
                    }
                    file_payloads = []
                    for part in message.iter_parts():
                        filename = part.get_filename()
                        if not filename:
                            field_name = part.get_param('name', header='content-disposition')
                            contact_key = field_name.replace('sender_', '') if field_name else ''
                            if contact_key in contact_info:
                                value = part.get_content()
                                contact_info[contact_key] = str(value).strip()
                            continue
                        data = part.get_payload(decode=True)
                        if data:
                            file_payloads.append((filename, data))

                    if not contact_info['email']:
                        self.send_html(
                            400,
                            app.build_sender_result_html(
                                'Contact info required',
                                'Enter your email before uploading files.',
                                is_error=True
                            )
                        )
                        return

                    wrong_filenames = app.validate_sender_upload_filenames([filename for filename, _ in file_payloads])
                    if wrong_filenames:
                        self.send_html(
                            400,
                            app.build_sender_result_html(
                                'Fix file names before uploading',
                                'These files do not match the requested artist, song, or tag.',
                                wrong_filenames,
                                is_error=True
                            )
                        )
                        return

                    uploaded = []
                    for filename, data in file_payloads:
                        uploaded.append(app.upload_sender_file_bytes(filename, data))

                    if uploaded:
                        skipped = [item for item in uploaded if item.get('skipped')]
                        uploaded_files = [item for item in uploaded if not item.get('skipped')]
                        title = 'Upload complete'
                        message = 'These files were uploaded to Google Drive.'
                        if skipped and uploaded_files:
                            title = 'Upload complete with skipped duplicates'
                            message = 'New files were uploaded. Duplicate files were skipped.'
                        elif skipped:
                            title = 'Already uploaded'
                            message = 'No new files were uploaded because every selected file already exists.'
                        app.notify_sender_upload(contact_info, uploaded)
                        self.send_html(
                            200,
                            app.build_sender_result_html(
                                title,
                                message,
                                uploaded
                            )
                        )
                    else:
                        self.send_html(
                            400,
                            app.build_sender_result_html(
                                'No files received',
                                'Choose at least one file and try the upload again.',
                                is_error=True
                            )
                        )
                except Exception as e:
                    app.threadsafe_log("Sender portal upload failed: {}".format(str(e)))
                    self.send_html(
                        500,
                        app.build_sender_result_html(
                            'Upload failed',
                            str(e),
                            is_error=True
                        )
                    )

        try:
            self.sender_portal_server = ThreadingHTTPServer(('0.0.0.0', SENDER_PORTAL_PORT), SenderPortalHandler)
        except OSError as e:
            raise RuntimeError(
                "Unable to start sender portal on port {}. Close the app or service already using that port, then try again. ({})".format(
                    SENDER_PORTAL_PORT,
                    str(e)
                )
            )

        port = SENDER_PORTAL_PORT
        self.sender_portal_port = port
        self.sender_portal_local_url = 'http://127.0.0.1:{}/'.format(port)
        lan_ip = self.get_lan_ip_address()
        if lan_ip:
            self.sender_portal_lan_url = 'http://{}:{}/'.format(lan_ip, port)
        else:
            self.sender_portal_lan_url = self.sender_portal_local_url
        self.sender_portal_url = self.sender_portal_lan_url
        self.sender_portal_thread = threading.Thread(
            target=self.sender_portal_server.serve_forever,
            daemon=True
        )
        self.sender_portal_thread.start()
        public_url = self.start_ngrok_tunnel(port)
        if public_url:
            self.sender_portal_url = public_url
        self.log("Sender portal started for same-network sharing: {}".format(self.sender_portal_lan_url))
        self.log("Local sender portal on this computer: {}".format(self.sender_portal_local_url))
        return self.sender_portal_url

    def stop_sender_portal(self):
        self.stop_ngrok_tunnel()
        if self.sender_portal_server:
            self.sender_portal_server.shutdown()
            self.sender_portal_server.server_close()
            self.sender_portal_server = None
            self.sender_portal_thread = None
        self.sender_portal_url = None
        self.sender_portal_local_url = None
        self.sender_portal_lan_url = None
        self.sender_portal_port = None

    def open_sender_portal(self):
        if not self.current_share_folder_id:
            messagebox.showinfo("Open Portal", "Create a send link first.")
            return

        try:
            portal_url = self.start_sender_portal()
            self.share_link_label.config(text="Portal: {}".format(portal_url))
            self.update_send_link_display()
            webbrowser.open(self.sender_portal_local_url or portal_url)
            self.log("Opened sender portal locally: {}".format(self.sender_portal_local_url or portal_url))
        except Exception as e:
            self.log("Failed to open sender portal: {}".format(str(e)))
            messagebox.showerror("Portal Error", "Unable to open sender portal:\n{}".format(str(e)))

    def threadsafe_log(self, message):
        self.root.after(0, lambda: self.log(message))

    def notify_sender_upload(self, contact_info, uploaded_items):
        """Notify the manager UI that a sender submitted files."""
        sender_email = contact_info.get('email') or 'No email'
        sender_phone = contact_info.get('phone') or 'No phone'
        file_names = [item.get('name', 'Uploaded file') for item in uploaded_items if isinstance(item, dict)]
        file_summary = ', '.join(file_names) if file_names else 'No files listed'

        log_message = "Sender upload received from {} phone: {} files: {}".format(
            sender_email,
            sender_phone,
            file_summary
        )
        self.threadsafe_log(log_message)

        def show_notification():
            body = "Email: {}\nPhone: {}\n\nFiles:\n{}".format(
                sender_email,
                sender_phone,
                '\n'.join(file_names) if file_names else 'No files listed'
            )
            messagebox.showinfo("Sender Upload Received", body)

        self.root.after(0, show_notification)

    def escape_drive_query_value(self, value):
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def verify_drive_file_in_folder(self, filename, folder_id):
        query = "title='{}' and '{}' in parents and trashed=false".format(
            self.escape_drive_query_value(filename),
            folder_id
        )
        try:
            matches = self.drive.ListFile({'q': query}).GetList()
            return len(matches) > 0
        except Exception as e:
            self.threadsafe_log("Warning: could not verify Drive upload for {}: {}".format(filename, str(e)))
            return False

    def find_drive_file_in_folder(self, filename, folder_id):
        """Return an existing non-trashed Drive file with this name in the folder, if any."""
        query = "title='{}' and '{}' in parents and trashed=false".format(
            self.escape_drive_query_value(filename),
            folder_id
        )
        matches = self.drive.ListFile({'q': query}).GetList()
        return matches[0] if matches else None

    def remove_temp_file_later(self, temp_path, attempts=6, delay_ms=500):
        """Delete a temp upload file, retrying when Windows still has it locked."""
        if not temp_path or not os.path.exists(temp_path):
            return

        try:
            os.remove(temp_path)
        except PermissionError:
            if attempts > 1:
                self.root.after(delay_ms, lambda: self.remove_temp_file_later(temp_path, attempts - 1, delay_ms))
            else:
                self.threadsafe_log("Warning: temp upload file is still locked and could not be removed: {}".format(temp_path))
        except FileNotFoundError:
            return
        except Exception as e:
            self.threadsafe_log("Warning: could not remove temp upload file {}: {}".format(temp_path, str(e)))

    def upload_sender_file_bytes(self, filename, data):
        """Upload a file received by the local sender portal to the active Drive folder."""
        if not self.current_share_folder_id:
            raise RuntimeError("No active send-link folder is open.")
        if not self.drive:
            raise RuntimeError("Google Drive is not authenticated.")

        clean_filename = os.path.basename(filename).replace('\x00', '').strip()
        if not clean_filename:
            clean_filename = 'uploaded_file'

        temp_path = None
        try:
            folder_id = self.current_share_folder_id
            suffix = '_' + re.sub(r'[^A-Za-z0-9._-]', '_', clean_filename)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(data)
                temp_path = temp_file.name

            with self.sender_upload_lock:
                target_folder_id = folder_id
                artist, song, tag = self.parse_filename(clean_filename)
                if artist and song and tag:
                    library_root_id = self.get_artist_library_root_for_upload(artist, song)
                    artist_folder_id = self.get_or_create_drive_folder(artist, library_root_id)
                    song_folder_id = self.get_or_create_drive_folder(song, artist_folder_id)
                    tag_folder = self.get_folder_for_tag(tag)
                    target_folder_id = self.get_or_create_drive_folder(tag_folder, song_folder_id)

                folder_path = self.get_drive_folder_path(target_folder_id)
                existing_file = self.find_drive_file_in_folder(clean_filename, target_folder_id)
                if existing_file:
                    existing_id = existing_file.get('id')
                    existing_url = existing_file.get('alternateLink') or 'https://drive.google.com/file/d/{}/view'.format(existing_id)
                    self.threadsafe_log("{} is already uploaded".format(clean_filename))
                    return {
                        'name': "{} is already uploaded".format(clean_filename),
                        'url': existing_url,
                        'id': existing_id,
                        'verified': True,
                        'skipped': True
                    }

                drive_file = self.drive.CreateFile({
                    'title': clean_filename,
                    'parents': [{'id': target_folder_id}]
                })
                drive_file.SetContentFile(temp_path)
                drive_file.Upload()
                self.clear_drive_cache()
                drive_file.FetchMetadata(fields='id,title,alternateLink')
                verified = self.verify_drive_file_in_folder(clean_filename, target_folder_id)
                if getattr(drive_file, 'content', None):
                    try:
                        drive_file.content.close()
                    except Exception:
                        pass

            drive_file_id = drive_file.get('id')
            drive_file_url = drive_file.get('alternateLink') or 'https://drive.google.com/file/d/{}/view'.format(drive_file_id)
            if verified:
                self.threadsafe_log("Sender portal uploaded to {}: {} ({})".format(folder_path, clean_filename, drive_file_id))
            else:
                self.threadsafe_log("Sender portal upload returned an ID but was not found in folder check: {} ({})".format(clean_filename, drive_file_id))
            self.root.after(0, self.update_drive_preview_display)
            self.root.after(0, self.update_artist_profiles_display)
            self.root.after(0, self.refresh_send_link_dropdowns)
            self.root.after(0, self.update_send_link_display)
            return {
                'name': clean_filename,
                'url': drive_file_url,
                'id': drive_file_id,
                'verified': verified
            }
        finally:
            self.remove_temp_file_later(temp_path)

    def resolve_send_link_song_folder(self, artist, song):
        """Resolve the existing song folder for a send link before creating anything new."""
        library_root_id = self.get_artist_library_root_for_upload(artist, song)
        artist_folder_id = self.get_or_create_drive_folder(artist, library_root_id)

        # If the song folder exists under the artist folder, use it.
        direct_song = self.find_drive_child_folder_case_insensitive(song, artist_folder_id)
        if direct_song:
            return direct_song['id'], "Using existing artist/song folder: {}".format(self.get_drive_folder_path(direct_song['id']))

        song_folder_id = self.get_or_create_drive_folder(song, artist_folder_id)
        return song_folder_id, "Created artist/song folder: {}".format(self.get_drive_folder_path(song_folder_id))

    def create_share_link_dialog(self):
        if not self.drive:
            messagebox.showerror("Error", "Google Drive not authenticated")
            return
        artist = simpledialog.askstring("Artist Name", "Enter the artist name for the send link:", parent=self.root)
        if not artist:
            return
        song = simpledialog.askstring("Song Name", "Enter the song name for the send link:", parent=self.root)
        if not song:
            return
        self.create_share_link_folder(artist.strip(), song.strip())

    def create_share_link_folder(self, artist, song):
        try:
            selected_song_folder_id = self.get_selected_send_link_song_folder_id(artist, song)
            if selected_song_folder_id:
                song_folder_id = selected_song_folder_id
                resolution_message = "Using selected artist/song folder: {}".format(self.get_drive_folder_path(song_folder_id))
            else:
                song_folder_id, resolution_message = self.resolve_send_link_song_folder(artist, song)
            folder = self.drive.CreateFile({'id': song_folder_id})
            folder.FetchMetadata(fields='id,title')
            folder.InsertPermission({'type': 'anyone', 'role': 'writer'})

            self.current_share_folder_id = song_folder_id
            self.share_link_url = 'https://drive.google.com/drive/folders/{}'.format(song_folder_id)
            self.sender_link_created_at = time.time()
            self.sender_link_expires_at = self.sender_link_created_at + SEND_LINK_LIFETIME_SECONDS
            self.schedule_sender_link_expiration()
            portal_url = self.start_sender_portal()
            self.share_link_label.config(text="Portal: {}".format(portal_url))
            app_root_id = self.ensure_app_drive_root_folder()
            if app_root_id:
                self.drive_dest_folder = app_root_id
            self.drive_folder_label.config(text=self.get_drive_folder_display())
            self.save_settings()
            self.update_drive_preview_display()
            self.refresh_artist_profiles_from_current_folder()
            self.update_send_link_display()
            webbrowser.open(self.sender_portal_local_url or portal_url)
            self.log(resolution_message)
            self.log("Created send link for: {}".format(self.share_link_url))
            self.log("Sender link expires: {}".format(self.format_sender_link_expiration()))
            self.log("Opened sender portal locally: {}".format(self.sender_portal_local_url or portal_url))
            self.refresh_send_link_dropdowns()
        except Exception as e:
            self.log("Failed to create share link: {}".format(str(e)))
            messagebox.showerror("Share Link Error", "Unable to create send link:\n{}".format(str(e)))

    def close_share_link(self, automatic=False):
        if not self.current_share_folder_id:
            if not automatic:
                messagebox.showinfo("Close Send Link", "No active send link is currently open.")
            return

        if self.sender_link_expire_after_id:
            try:
                self.root.after_cancel(self.sender_link_expire_after_id)
            except Exception:
                pass
            self.sender_link_expire_after_id = None

        try:
            folder = self.drive.CreateFile({'id': self.current_share_folder_id})
            folder.FetchMetadata(fields='permissions')
            for perm in folder.get('permissions', []):
                if perm.get('type') == 'anyone':
                    folder.DeletePermission(perm.get('id'))
        except Exception as e:
            self.log("Warning: could not fully remove share permissions: {}".format(str(e)))

        if not automatic:
            messagebox.showinfo("Send Link Closed", "The send link has been closed.")
        self.log("Send link closed for folder: {}".format(self.share_link_url or self.current_share_folder_id))
        self.current_share_folder_id = None
        self.share_link_url = None
        self.sender_link_created_at = None
        self.sender_link_expires_at = None
        self.stop_sender_portal()
        self.share_link_label.config(text="")
        self.shared_folder_item_ids.clear()
        self.update_send_link_display()

    def on_close(self):
        if self.sender_link_expire_after_id:
            try:
                self.root.after_cancel(self.sender_link_expire_after_id)
            except Exception:
                pass
            self.sender_link_expire_after_id = None
        self.stop_sender_portal()
        self.root.destroy()

    def on_drop(self, event):
        # Get dropped files
        files = self.root.tk.splitlist(event.data)
        self.files.extend(files)
        self.update_main_display()
        self.log("Dropped {} file(s)".format(len(files)))
        self.organize_button.config(state=tk.NORMAL)
        self.set_operation_progress(0, "Progress: Ready ({} file(s) selected)".format(len(self.files)))

    def select_files(self):
        files = filedialog.askopenfilenames(
            title="Select music files",
            filetypes=[("All files", "*.*"), ("Audio files", "*.wav *.mp3 *.flac"), ("Text files", "*.txt")]
        )
        if files:
            self.files.extend(files)
            self.update_main_display()
            self.log("Selected {} file(s)".format(len(files)))
            self.organize_button.config(state=tk.NORMAL)
            self.set_operation_progress(0, "Progress: Ready ({} file(s) selected)".format(len(self.files)))

    def update_main_display(self):
        count = len(self.files)
        self.main_text.config(state=tk.NORMAL)
        # Clear and rewrite the main content
        self.main_text.delete(1.0, tk.END)
        self.main_text.insert(tk.END, "Music Distribution Organizer\n\n")
        self.main_text.insert(tk.END, "Expected filename format: Artist - Song Name (Tag).ext\n")
        self.main_text.insert(tk.END, "Example: Guam - My Song (Final).wav\n\n")
        self.main_text.insert(tk.END, "Required tags: Clean, Final, Instrumental, Acapella, Lyrics, Cover, Artwork\n")
        self.main_text.insert(tk.END, "Optional tags: Session Files (accepted, but not required for progress)\n")
        self.main_text.insert(tk.END, "Files are organized into: /Artist/Song/Tag/\n\n")
        
        if count > 0:
            self.main_text.insert(tk.END, "Selected {} file(s) ready to organize:\n".format(count))
            for i, file_path in enumerate(self.files, 1):
                filename = os.path.basename(file_path)
                self.main_text.insert(tk.END, "{}. {}\n".format(i, filename))

            status = self.build_song_status_for_files(self.files)
            if status:
                self.main_text.insert(tk.END, "\nSong completion status:\n")
                self.main_text.insert(tk.END, "{:<25} {:<25} {:<8} Missing\n".format('Artist', 'Song', 'Status'))
                self.main_text.insert(tk.END, "{}\n".format('-'*80))
                for song in status:
                    self.main_text.insert(tk.END, "{:<25} {:<25} ".format(song['artist'], song['song']))
                    percent_label = "{}%".format(song['percent'])
                    self.main_text.insert(tk.END, "{:<8}".format(percent_label), song['color'])
                    self.main_text.insert(tk.END, "{}\n".format(', '.join(song['missing']) if song['missing'] else 'None'))
                    if song.get('optional_present'):
                        self.main_text.insert(
                            tk.END,
                            "  Optional: {} (does not affect ready-to-upload progress)\n".format(', '.join(song['optional_present'])),
                            'green'
                        )
                self.main_text.insert(tk.END, "\nWhat else am I missing? Look at missing tag column above.\n\n")
            else:
                self.main_text.insert(tk.END, "\nNo valid song tags found yet. Make sure files use Artist - Song Name (Tag).ext format.\n\n")

            self.main_text.insert(tk.END, "Click 'Organize + Upload' to process files.\n\n")
        else:
            self.main_text.insert(tk.END, "Click 'Add Files' to choose music files to organize and upload.\n\n")

        if self.last_sent_song_status:
            self.main_text.insert(tk.END, "Last upload progress:\n")
            self.main_text.insert(tk.END, "{:<25} {:<25} {:<8} Missing\n".format('Artist', 'Song', 'Status'))
            self.main_text.insert(tk.END, "{}\n".format('-'*80))
            for song in self.last_sent_song_status:
                self.main_text.insert(tk.END, "{:<25} {:<25} ".format(song['artist'], song['song']))
                percent_label = "{}%".format(song['percent'])
                self.main_text.insert(tk.END, "{:<8}".format(percent_label), song['color'])
                self.main_text.insert(tk.END, "{}\n".format(', '.join(song['missing']) if song['missing'] else 'None'))
                if song.get('optional_present'):
                    self.main_text.insert(
                        tk.END,
                        "  Optional: {} (does not affect ready-to-upload progress)\n".format(', '.join(song['optional_present'])),
                        'green'
                    )
            self.main_text.insert(tk.END, "\nThe last song upload was tracked above.\n\n")

    def log(self, message):
        self.main_text.config(state=tk.NORMAL)
        self.main_text.insert(tk.END, message + '\n')
        self.main_text.see(tk.END)
        self.main_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def set_operation_progress(self, percent=None, text=None):
        """Update the Files tab progress meter from either the UI or worker thread."""
        def apply_update():
            if percent is not None:
                bounded_percent = max(0, min(100, int(percent)))
                self.operation_progress_bar['value'] = bounded_percent
            if text is not None:
                self.operation_progress_label.config(text=text)

        if threading.current_thread() is threading.main_thread():
            apply_update()
        else:
            self.root.after(0, apply_update)

    def authenticate_drive(self, force_new_token=False):
        try:
            client_secrets_path = get_client_secrets_path()
            token_path = get_token_path()
            gauth = GoogleAuth(settings=build_google_auth_settings(client_secrets_path, token_path))
            
            # Load credentials from client_secrets.json
            if not os.path.exists(client_secrets_path):
                self.log("ERROR: client_secrets.json not found")
                messagebox.showerror(
                    "Auth Error",
                    "client_secrets.json not found.\n\nPlace it next to the app or bundle it with the installer."
                )
                return

            if force_new_token and os.path.exists(token_path):
                os.remove(token_path)
            
            # Try to load existing token first
            if os.path.exists(token_path):
                gauth.LoadCredentialsFile(token_path)
            
            # If no valid token, authenticate
            if gauth.credentials is None:
                self.log("No saved manager Google Drive login found. Opening browser sign-in...")
                gauth.LocalWebserverAuth()
            elif gauth.access_token_expired:
                self.log("Google Drive token expired. Refreshing login...")
                gauth.Refresh()
            
            # Save credentials for future use
            gauth.SaveCredentialsFile(token_path)
            
            self.drive = GoogleDrive(gauth)
            self.app_drive_root_folder_id = None
            app_root_id = self.ensure_app_drive_root_folder()
            if app_root_id:
                self.drive_dest_folder = app_root_id
                self.artist_profiles_source_folder = app_root_id
                self.drive_folder_label.config(text=self.get_drive_folder_display())
                self.save_settings()
            self.log("Manager Google Drive authenticated successfully")
            self.log("Manager credential token saved for this Windows user: {}".format(token_path))
            self.log("App Drive parent folder: {}".format(self.get_drive_folder_path(self.drive_dest_folder)))
            self.update_drive_preview_display()
            self.update_artist_profiles_display()
            self.refresh_songs_tab()
            self.refresh_send_link_dropdowns()
        except Exception as e:
            error_msg = str(e)
            self.log("Google Drive authentication failed: {}".format(error_msg))
            messagebox.showerror("Authentication Error", "Failed to authenticate with Google Drive:\n{}".format(error_msg))

    def reconnect_drive(self):
        """Force a fresh Google Drive sign-in and replace this user's token."""
        if not messagebox.askyesno(
            "Reconnect Manager Google Drive",
            "This will open Google sign-in and replace the saved manager Google token for this Windows user.\n\nUse this after adding Docs/Gmail permissions so Google asks for the new scopes. Continue?"
        ):
            return
        self.drive = None
        self.authenticate_drive(force_new_token=True)

    def parse_filename(self, filename):
        """
        Parse filename using regex to extract artist, song, and tag.
        Expected format: Artist - Song Name (Tag).ext
        """
        # Remove extension for parsing
        name_without_ext = os.path.splitext(filename)[0]

        # Regex pattern: Artist - Song Name (Tag)
        pattern = r'^(.+?)\s*-\s*(.+?)\s*\((.+?)\)$'
        match = re.match(pattern, name_without_ext)

        if match:
            artist = match.group(1).strip()
            song = match.group(2).strip()
            tag = match.group(3).strip()
            return artist, song, tag
        else:
            return None, None, None

    def get_folder_for_tag(self, tag):
        """
        Map tag to appropriate folder.
        """
        tag_lower = tag.lower()
        if tag_lower in ['final', 'clean', 'instrumental', 'acapella']:
            # Create folder with capitalized tag name
            return tag.capitalize()
        elif tag_lower == 'lyrics':
            return 'Lyrics'
        elif tag_lower in ['cover', 'artwork']:
            return 'Artwork'
        elif tag_lower in ['session', 'sessions', 'session file', 'session files', 'sessionfiles']:
            return 'Session Files'
        else:
            return 'Other'

    def get_required_tags(self):
        """Return the list of required song tags."""
        return ['Clean', 'Final', 'Instrumental', 'Acapella', 'Lyrics', 'Artwork']

    def get_optional_tags(self):
        """Return optional accepted tags that do not affect completion progress."""
        return ['Session Files']

    def normalize_tag(self, tag):
        """Normalize tag text for status tracking."""
        normalized = tag.strip().capitalize()
        if normalized.lower() == 'acapella':
            return 'Acapella'
        if normalized.lower() == 'instrumental':
            return 'Instrumental'
        if normalized.lower() == 'clean':
            return 'Clean'
        if normalized.lower() == 'final':
            return 'Final'
        if normalized.lower() == 'lyrics':
            return 'Lyrics'
        if normalized.lower() in ['cover', 'artwork']:
            return 'Artwork'
        if normalized.lower() in ['session', 'sessions', 'session file', 'session files', 'sessionfiles']:
            return 'Session Files'
        return normalized

    def normalize_song_key(self, artist, song):
        """Normalize artist and song names for grouping."""
        return artist.strip().lower(), song.strip().lower()

    def build_song_status_for_files(self, files):
        """Build status data for a list of files."""
        song_map = {}
        required = self.get_required_tags()
        optional = self.get_optional_tags()

        for file_path in files:
            filename = os.path.basename(file_path)
            artist, song, tag = self.parse_filename(filename)
            if not (artist and song and tag):
                continue
            tag_name = self.normalize_tag(tag)
            key = self.normalize_song_key(artist, song)
            if key not in song_map:
                song_map[key] = {
                    'artist': artist.strip(),
                    'song': song.strip(),
                    'tags': set(),
                    'optional_tags': set()
                }
            if tag_name in required:
                song_map[key]['tags'].add(tag_name)
            elif tag_name in optional:
                song_map[key]['optional_tags'].add(tag_name)

        status = []
        for key, item in song_map.items():
            present_tags = item['tags']
            missing = [t for t in required if t not in present_tags]
            percent = int(len(present_tags) / len(required) * 100)
            if percent >= 80:
                color = 'green'
            elif percent >= 50:
                color = 'yellow'
            else:
                color = 'red'
            status.append({
                'artist': item['artist'],
                'song': item['song'],
                'present': sorted(present_tags),
                'optional_present': sorted(item['optional_tags']),
                'missing': missing,
                'percent': percent,
                'color': color
            })

        return status

    def organize_files_locally(self, files, progress_callback=None):
        """
        Organize files into local folder structure.
        """
        organized_files = []
        base_dir = self.local_dest_dir
        total_files = len(files)

        for index, file_path in enumerate(files, 1):
            filename = os.path.basename(file_path)
            artist, song, tag = self.parse_filename(filename)

            if artist and song and tag:
                # Create folder structure
                artist_dir = os.path.join(base_dir, artist)
                song_dir = os.path.join(artist_dir, song)
                tag_folder = self.get_folder_for_tag(tag)
                final_dir = os.path.join(song_dir, tag_folder)

                os.makedirs(final_dir, exist_ok=True)

                # Copy file to organized location
                dest_path = os.path.join(final_dir, filename)
                shutil.copy2(file_path, dest_path)

                organized_files.append(dest_path)
                self.log("Organized: {}".format(filename))
            else:
                # Provide detailed error message
                name_without_ext = os.path.splitext(filename)[0]
                error_msg = "Skipped '{}': Expected format 'Artist - Song Name (Tag).ext', got '{}'".format(filename, name_without_ext)
                self.log(error_msg)

            if progress_callback and total_files:
                progress_callback(index, total_files)

        return organized_files

    def upload_to_drive(self, file_paths, progress_callback=None):
        """
        Upload organized files to Google Drive, creating folder structure.
        """
        # Cache for created folders
        folder_cache = {}

        def get_or_create_folder(name, parent_id='root'):
            cache_key = (name, parent_id)
            if cache_key in folder_cache:
                return folder_cache[cache_key]

            # Search for existing folder
            existing_folder = self.find_drive_child_folder_case_insensitive(name, parent_id)
            if existing_folder:
                folder_id = existing_folder['id']
            else:
                # Create new folder
                folder = self.drive.CreateFile({
                    'title': name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [{'id': parent_id}]
                })
                folder.Upload()
                self.clear_drive_cache()
                folder_id = folder['id']

            folder_cache[cache_key] = folder_id
            return folder_id

        total_files = len(file_paths)
        for index, file_path in enumerate(file_paths, 1):
            try:
                # Get relative path from base directory
                rel_path = os.path.relpath(file_path, self.local_dest_dir)
                path_parts = rel_path.split(os.sep)
                if len(path_parts) < 4:
                    self.log("Skipped upload path without Artist/Song/Tag structure: {}".format(rel_path))
                    if progress_callback and total_files:
                        progress_callback(index, total_files)
                    continue

                artist_name = path_parts[0]
                song_name = path_parts[1]
                tag_folder_name = path_parts[2]
                filename = path_parts[-1]

                library_root_id = self.get_artist_library_root_for_upload(artist_name, song_name)
                artist_folder_id = get_or_create_folder(artist_name, library_root_id)
                song_folder_id = get_or_create_folder(song_name, artist_folder_id)
                current_parent = song_folder_id
                for part in path_parts[2:-1]:
                    current_parent = get_or_create_folder(part, current_parent)

                # Upload file
                existing_file = self.find_drive_file_in_folder(filename, current_parent)
                if existing_file:
                    self.last_uploaded_drive_folder_id = song_folder_id or current_parent
                    self.log("{} is already uploaded".format(filename))
                    if progress_callback and total_files:
                        progress_callback(index, total_files)
                    continue

                file_drive = self.drive.CreateFile({
                    'title': filename,
                    'parents': [{'id': current_parent}]
                })
                file_drive.SetContentFile(file_path)
                file_drive.Upload()
                self.clear_drive_cache()

                self.last_uploaded_drive_folder_id = song_folder_id or current_parent
                self.log("Uploaded to {}: {}".format(self.get_drive_folder_path(current_parent), filename))
            except Exception as e:
                self.log("Failed to upload {}: {}".format(os.path.basename(file_path), str(e)))

            if progress_callback and total_files:
                progress_callback(index, total_files)

    def organize_and_upload(self):
        if not self.files:
            messagebox.showwarning("No Files", "Please select some files first.")
            return

        if not self.drive:
            messagebox.showerror("Drive Error", "Google Drive not authenticated.")
            return

        # Disable button during processing
        self.organize_button.config(state=tk.DISABLED, text="Processing...")
        self.select_button.config(state=tk.DISABLED)
        self.set_operation_progress(0, "Progress: Starting...")

        # Run in thread to avoid freezing UI
        def process():
            try:
                total_selected = len(self.files)

                def local_progress(done, total):
                    percent = int((done / total) * 50)
                    self.set_operation_progress(
                        percent,
                        "Progress: Organizing {}/{} file(s)".format(done, total)
                    )

                def upload_progress(done, total):
                    percent = 50 + int((done / total) * 50)
                    self.set_operation_progress(
                        percent,
                        "Progress: Uploading {}/{} file(s)".format(done, total)
                    )

                # Organize locally
                organized_files = self.organize_files_locally(self.files, progress_callback=local_progress)
                self.last_sent_song_status = self.build_song_status_for_files(self.files)

                if organized_files:
                    self.log("Uploading {} files to Google Drive...".format(len(organized_files)))
                    self.set_operation_progress(
                        50,
                        "Progress: Organized {}/{} file(s), starting upload...".format(len(organized_files), total_selected)
                    )
                    self.upload_to_drive(organized_files, progress_callback=upload_progress)
                    self.set_operation_progress(100, "Progress: Complete ({} uploaded)".format(len(organized_files)))
                    self.log("[OK] Complete! Organized and uploaded {} files.".format(len(organized_files)))

                    if self.last_sent_song_status:
                        for song in self.last_sent_song_status:
                            missing_text = ', '.join(song['missing']) if song['missing'] else 'None'
                            self.log("Progress for {} - {}: {}% missing {}".format(song['artist'], song['song'], song['percent'], missing_text))

                    if self.last_uploaded_drive_folder_id:
                        self.root.after(0, self.update_drive_folder_after_upload)

                    messagebox.showinfo("Success", "Organized and uploaded {} files!".format(len(organized_files)))
                else:
                    self.log("[ERROR] No valid files found to organize.")
                    self.set_operation_progress(0, "Progress: No valid files found")
                    messagebox.showinfo("Info", "No valid files found to organize.")

            except Exception as e:
                self.log("[ERROR] Error during processing: {}".format(str(e)))
                self.set_operation_progress(0, "Progress: Error")
                messagebox.showerror("Error", "An error occurred:\n{}".format(str(e)))
            finally:
                self.organize_button.config(state=tk.NORMAL, text="Organize + Upload")
                self.select_button.config(state=tk.NORMAL)
                self.files.clear()
                self.update_main_display()

        threading.Thread(target=process, daemon=True).start()

if __name__ == "__main__":
    if TKINTER_DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = MusicOrganizerApp(root)
    root.mainloop()
