import json
import os
import sys
import tempfile

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

from .config import APP_DRIVE_ROOT_FOLDER_NAME, APP_NAME, TOKEN_FILENAME


def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.abspath('.'))
    return os.path.join(base_path, relative_path)


def get_app_data_dir():
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


def build_google_auth_settings(client_secrets_path=None, token_path=None):
    return {
        'client_config_backend': 'file',
        'client_config_file': client_secrets_path or get_client_secrets_path(),
        'save_credentials': True,
        'save_credentials_backend': 'file',
        'save_credentials_file': token_path or get_token_path(),
        'get_refresh_token': True,
        'oauth_scope': [
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/gmail.send',
        ],
    }


def get_authenticated_drive(force_new_token=False):
    token_path = get_token_path()
    gauth = GoogleAuth(settings=build_google_auth_settings(token_path=token_path))
    should_save_credentials = False

    if force_new_token and os.path.exists(token_path):
        os.remove(token_path)

    if os.path.exists(token_path) and not force_new_token:
        gauth.LoadCredentialsFile(token_path)

    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
        should_save_credentials = True
    elif gauth.access_token_expired:
        gauth.Refresh()
        should_save_credentials = True
    else:
        gauth.Authorize()

    if should_save_credentials:
        gauth.SaveCredentialsFile(token_path)
    return GoogleDrive(gauth)


def escape_drive_query_value(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def find_drive_child_folder_case_insensitive(drive, title, parent_id='root'):
    wanted = title.strip().casefold()
    if not wanted:
        return None

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
        return {'id': existing_folder['id'], 'title': existing_folder.get('title', clean_title), 'created': False}

    query = "title='{}' and mimeType='application/vnd.google-apps.folder' and '{}' in parents and trashed=false".format(
        escape_drive_query_value(clean_title),
        parent_id,
    )
    existing = drive.ListFile({'q': query}).GetList()
    if existing:
        return {'id': existing[0]['id'], 'title': existing[0].get('title', clean_title), 'created': False}

    folder = drive.CreateFile({
        'title': clean_title,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [{'id': parent_id}],
    })
    folder.Upload()
    return {'id': folder['id'], 'title': clean_title, 'created': True}


def ensure_app_drive_root_folder(drive):
    return get_or_create_drive_folder(drive, APP_DRIVE_ROOT_FOLDER_NAME, 'root')


def get_drive_folder_contents(drive, folder_id):
    query = "trashed=false and '{}' in parents".format(folder_id if folder_id != 'root' else 'root')
    return drive.ListFile({'q': query}).GetList()


def get_drive_folder_metadata(drive, folder_id):
    if folder_id == 'root':
        return {'id': 'root', 'title': 'My Drive', 'parents': []}
    folder = drive.CreateFile({'id': folder_id})
    folder.FetchMetadata(fields='id,title,parents,mimeType')
    return folder


def find_drive_file_by_title(drive, title, parent_id):
    query = "title='{}' and '{}' in parents and trashed=false".format(
        escape_drive_query_value(title),
        parent_id,
    )
    matches = drive.ListFile({'q': query}).GetList()
    return matches[0] if matches else None


def load_drive_json_file(drive, title, default_value, folder_id):
    existing = find_drive_file_by_title(drive, title, folder_id)
    if not existing:
        return default_value
    raw = drive.CreateFile({'id': existing['id']}).GetContentString()
    return json.loads(raw) if raw.strip() else default_value


def save_drive_json_file(drive, title, data, folder_id):
    existing = find_drive_file_by_title(drive, title, folder_id)
    metadata = {'id': existing['id']} if existing else {'title': title, 'parents': [{'id': folder_id}]}
    drive_file = drive.CreateFile(metadata)
    drive_file.SetContentString(json.dumps(data, indent=2, sort_keys=True))
    drive_file.Upload()
    return {'id': drive_file.get('id'), 'title': title}
