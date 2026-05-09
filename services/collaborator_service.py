import time
import uuid

from .config import COLLABORATOR_PROFILES_JSON, CREDITS_DATA_FOLDER_NAME, SONG_CREDITS_JSON
from .drive_service import (
    ensure_app_drive_root_folder,
    get_authenticated_drive,
    get_or_create_drive_folder,
    load_drive_json_file,
    save_drive_json_file,
)
from .song_service import get_song_context


def ensure_credits_data_folder(drive):
    app_root = ensure_app_drive_root_folder(drive)
    return get_or_create_drive_folder(drive, CREDITS_DATA_FOLDER_NAME, app_root['id'])


def load_collaborators(drive=None):
    drive = drive or get_authenticated_drive()
    folder = ensure_credits_data_folder(drive)
    data = load_drive_json_file(drive, COLLABORATOR_PROFILES_JSON, {'profiles': []}, folder['id'])
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
        saved = {'profile_id': profile_id or str(uuid.uuid4()), **payload, 'created_at': int(time.time())}
        profiles.append(saved)
        created = True

    profiles.sort(key=lambda item: item.get('name', '').casefold())
    folder = ensure_credits_data_folder(drive)
    save_drive_json_file(drive, COLLABORATOR_PROFILES_JSON, {'profiles': profiles}, folder['id'])
    return {'profile': saved, 'created': created}


def load_song_credit_assignments(drive=None):
    drive = drive or get_authenticated_drive()
    folder = ensure_credits_data_folder(drive)
    data = load_drive_json_file(drive, SONG_CREDITS_JSON, {'songs': {}}, folder['id'])
    return data.get('songs', {})


def save_song_credit_assignments(assignments, drive=None):
    drive = drive or get_authenticated_drive()
    folder = ensure_credits_data_folder(drive)
    save_drive_json_file(drive, SONG_CREDITS_JSON, {'songs': assignments}, folder['id'])
    return assignments


def get_song_credit_record(song_folder_id, artist='', song='', drive=None):
    if not song_folder_id:
        raise ValueError("song_folder_id is required.")
    drive = drive or get_authenticated_drive()
    assignments = load_song_credit_assignments(drive)
    record = assignments.setdefault(song_folder_id, {
        'artist': artist,
        'song': song,
        'song_folder_id': song_folder_id,
        'collaborators': [],
    })
    if artist:
        record['artist'] = artist
    if song:
        record['song'] = song
    return record


def get_role_split_pool(role):
    if role in {'Primary Artist', 'Featured Artist'}:
        return 'artist', 50.0
    if role in {
        'Producer',
        'Co-Producer',
        'Additional Producer',
        'Recording Engineer',
        'Mix Engineer',
        'Mastering Engineer',
    }:
        return 'production_engineering', 50.0
    return None, None


def reset_song_split_percentages(record):
    collaborators = record.get('collaborators', [])
    if not collaborators:
        return record

    pooled = {}
    unpooled = []
    used_pool_total = 0.0
    for collaborator in collaborators:
        pool_name, pool_total = get_role_split_pool(collaborator.get('role', ''))
        if pool_name:
            if pool_name not in pooled:
                pooled[pool_name] = {'total': pool_total, 'collaborators': []}
                used_pool_total += pool_total
            pooled[pool_name]['collaborators'].append(collaborator)
        else:
            unpooled.append(collaborator)

    for pool in pooled.values():
        split = pool['total'] / len(pool['collaborators'])
        for collaborator in pool['collaborators']:
            collaborator['split'] = split

    if unpooled:
        split = max(0.0, 100.0 - used_pool_total) / len(unpooled)
        for collaborator in unpooled:
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
        'collaborators': [],
    })
    if artist:
        record['artist'] = artist
    if song:
        record['song'] = song

    record.setdefault('collaborators', []).append({
        'profile_id': profile_id,
        'role': role,
        'credit': credit or '',
        'split': float(split) if split is not None else 0.0,
    })
    reset_song_split_percentages(record)
    save_song_credit_assignments(assignments, drive)
    return {'record': record, 'split_total': get_song_credit_total(record)}


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
    return {'removed': removed, 'record': record, 'split_total': get_song_credit_total(record)}


def reset_song_credit_splits(song_folder_id, drive=None):
    drive = drive or get_authenticated_drive()
    assignments = load_song_credit_assignments(drive)
    record = assignments.get(song_folder_id)
    if not record:
        raise ValueError("Song credit record was not found.")
    reset_song_split_percentages(record)
    save_song_credit_assignments(assignments, drive)
    return {'record': record, 'split_total': get_song_credit_total(record)}


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
        'collaborators': [],
    })
    record['artist'] = record.get('artist') or context.get('artist', '')
    record['song'] = record.get('song') or context.get('song', '')
    record['status'] = clean_status
    record['status_updated_at'] = int(time.time())
    save_song_credit_assignments(assignments, drive)
    return record

