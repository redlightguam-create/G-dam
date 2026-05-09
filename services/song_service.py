import os
import re
import tempfile

from .config import (
    APP_DRIVE_ROOT_FOLDER_NAME,
    CREDITS_DATA_FOLDER_NAME,
    OPTIONAL_TAGS,
    PROFILE_IMAGE_FOLDER_NAME,
    REQUIRED_TAGS,
)
from .drive_service import (
    ensure_app_drive_root_folder,
    find_drive_child_folder_case_insensitive,
    find_drive_file_by_title,
    get_authenticated_drive,
    get_drive_folder_contents,
    get_drive_folder_metadata,
    get_or_create_drive_folder,
)


def parse_filename(filename):
    name_without_ext = os.path.splitext(filename)[0]
    match = re.match(r'^(.+?)\s*-\s*(.+?)\s*\((.+?)\)$', name_without_ext)
    if not match:
        return None, None, None
    return match.group(1).strip(), match.group(2).strip(), match.group(3).strip()


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


def is_drive_folder(item):
    return item.get('mimeType') == 'application/vnd.google-apps.folder'


def title_matches_required_tag(title):
    title_key = title.strip().casefold()
    return any(title_key == tag.casefold() for tag in REQUIRED_TAGS)


def build_drive_folder_status(items, folder_name=None):
    present_tags = set()
    optional_tags = set()

    def tag_from_title(title):
        title_lower = title.lower()
        for tag in REQUIRED_TAGS + OPTIONAL_TAGS:
            if tag.lower() in title_lower:
                return tag
        return None

    if folder_name:
        folder_tag = tag_from_title(folder_name)
        if folder_tag in REQUIRED_TAGS:
            present_tags.add(folder_tag)
        elif folder_tag in OPTIONAL_TAGS:
            optional_tags.add(folder_tag)

    for item in items:
        if is_drive_folder(item):
            folder_tag = tag_from_title(item.get('title', ''))
            if folder_tag in REQUIRED_TAGS:
                present_tags.add(folder_tag)
            elif folder_tag in OPTIONAL_TAGS:
                optional_tags.add(folder_tag)
        else:
            _, _, tag = parse_filename(item.get('title', ''))
            if tag:
                normalized_tag = normalize_tag(tag)
                if normalized_tag in REQUIRED_TAGS:
                    present_tags.add(normalized_tag)
                elif normalized_tag in OPTIONAL_TAGS:
                    optional_tags.add(normalized_tag)

    missing = [tag for tag in REQUIRED_TAGS if tag not in present_tags]
    return {
        'present': sorted(present_tags),
        'optional_present': sorted(optional_tags),
        'missing': missing,
        'percent': int(len(present_tags) / len(REQUIRED_TAGS) * 100) if REQUIRED_TAGS else 0,
    }


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
        'created': artist_folder['created'],
    }


def create_song_folder(artist_name, song_name, drive=None, parent_id=None):
    clean_song = song_name.strip()
    if not clean_song:
        raise ValueError("song_name is required.")
    drive = drive or get_authenticated_drive()
    artist_folder = create_artist_folder(artist_name, drive=drive, parent_id=parent_id)
    song_folder = get_or_create_drive_folder(drive, clean_song, artist_folder['artist_folder_id'])
    return {
        'artist': artist_folder['artist'],
        'artist_folder_id': artist_folder['artist_folder_id'],
        'song': song_folder['title'],
        'song_folder_id': song_folder['id'],
        'parent_folder_id': artist_folder['parent_folder_id'],
        'created': song_folder['created'],
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
        if artist and song and tag and normalize_tag(tag) in REQUIRED_TAGS:
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


def list_artist_profiles(drive=None, root_folder_id=None):
    drive = drive or get_authenticated_drive()
    songs = list_songs(drive=drive, root_folder_id=root_folder_id)
    profiles = {}
    for song in songs:
        artist_key = song.get('artist_folder_id') or song.get('artist', '')
        profile = profiles.setdefault(artist_key, {
            'artist': song.get('artist', ''),
            'artist_folder_id': song.get('artist_folder_id'),
            'songs': [],
            'total_songs': 0,
            'completed_songs': 0,
            'total_present': 0,
            'total_required': 0,
            'percent': 0,
        })
        profile['songs'].append(song)
        profile['total_songs'] += 1
        profile['completed_songs'] += 1 if song.get('percent') == 100 else 0
        profile['total_present'] += len(song.get('present', []))
        profile['total_required'] += len(REQUIRED_TAGS)

    for profile in profiles.values():
        image_file = get_artist_profile_image_file(profile.get('artist_folder_id'), drive=drive)
        profile['percent'] = int((profile['total_present'] / profile['total_required']) * 100) if profile['total_required'] else 0
        profile['songs'] = sorted(profile['songs'], key=lambda item: item.get('song', '').casefold())
        profile['image_file_id'] = image_file.get('id') if image_file else None
        profile['image_title'] = image_file.get('title') if image_file else None
        profile['image_url'] = '/artist-profiles/{}/image'.format(profile.get('artist_folder_id')) if image_file else ''

    return sorted(profiles.values(), key=lambda item: item.get('artist', '').casefold())


def get_artist_profile_image_folder(artist_folder_id, create=False, drive=None):
    if not artist_folder_id:
        raise ValueError("artist_folder_id is required.")
    drive = drive or get_authenticated_drive()
    if create:
        return get_or_create_drive_folder(drive, PROFILE_IMAGE_FOLDER_NAME, artist_folder_id)

    folder = find_drive_child_folder_case_insensitive(drive, PROFILE_IMAGE_FOLDER_NAME, artist_folder_id)
    return {'id': folder['id'], 'title': folder.get('title', PROFILE_IMAGE_FOLDER_NAME)} if folder else None


def get_artist_profile_image_file(artist_folder_id, drive=None):
    if not artist_folder_id:
        return None
    drive = drive or get_authenticated_drive()
    image_folder = get_artist_profile_image_folder(artist_folder_id, create=False, drive=drive)
    if not image_folder:
        return None

    images = [
        item for item in get_drive_folder_contents(drive, image_folder['id'])
        if item.get('mimeType', '').startswith('image/')
    ]
    return images[0] if images else None


def rename_artist_profile(artist_folder_id, artist_name, drive=None):
    clean_name = (artist_name or '').strip()
    if not artist_folder_id:
        raise ValueError("artist_folder_id is required.")
    if not clean_name:
        raise ValueError("artist_name is required.")

    drive = drive or get_authenticated_drive()
    artist_folder = drive.CreateFile({'id': artist_folder_id})
    artist_folder.FetchMetadata(fields='id,title,mimeType')
    if artist_folder.get('mimeType') != 'application/vnd.google-apps.folder':
        raise ValueError("artist_folder_id must point to an artist folder.")
    artist_folder['title'] = clean_name
    artist_folder.Upload()
    return {'artist': clean_name, 'artist_folder_id': artist_folder_id}


def delete_artist_profile(artist_folder_id, drive=None):
    if not artist_folder_id:
        raise ValueError("artist_folder_id is required.")

    drive = drive or get_authenticated_drive()
    artist_folder = drive.CreateFile({'id': artist_folder_id})
    artist_folder.FetchMetadata(fields='id,title,mimeType')
    if artist_folder.get('mimeType') != 'application/vnd.google-apps.folder':
        raise ValueError("artist_folder_id must point to an artist folder.")

    artist_name = artist_folder.get('title', '')
    artist_folder.Delete()
    return {'artist': artist_name, 'artist_folder_id': artist_folder_id, 'deleted': True}


def upload_artist_profile_image(artist_folder_id, image_path, filename=None, drive=None):
    if not artist_folder_id:
        raise ValueError("artist_folder_id is required.")
    if not image_path or not os.path.exists(image_path):
        raise ValueError("image file is required.")

    drive = drive or get_authenticated_drive()
    image_folder = get_artist_profile_image_folder(artist_folder_id, create=True, drive=drive)
    for item in get_drive_folder_contents(drive, image_folder['id']):
        if not item.get('mimeType', '').startswith('application/vnd.google-apps.folder'):
            try:
                drive.CreateFile({'id': item['id']}).Delete()
            except Exception:
                pass

    extension = os.path.splitext(filename or image_path)[1].lower() or '.png'
    drive_file = drive.CreateFile({
        'title': 'profile{}'.format(extension),
        'parents': [{'id': image_folder['id']}],
    })
    drive_file.SetContentFile(image_path)
    drive_file.Upload()
    drive_file.FetchMetadata(fields='id,title,mimeType')
    return {
        'id': drive_file.get('id'),
        'title': drive_file.get('title'),
        'mimeType': drive_file.get('mimeType', ''),
        'image_url': '/artist-profiles/{}/image'.format(artist_folder_id),
    }


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
        'song_folder_id': song_folder_id,
    }


def get_song_completeness(song_folder_id, drive=None):
    drive = drive or get_authenticated_drive()
    context = get_song_context(song_folder_id, drive)
    items = get_drive_folder_contents(drive, song_folder_id)
    status = build_drive_folder_status(items, context.get('song', ''))
    return {
        **context,
        'required': REQUIRED_TAGS,
        'optional': OPTIONAL_TAGS,
        'present': status['present'],
        'optional_present': status['optional_present'],
        'missing': status['missing'],
        'percent': status['percent'],
        'complete': status['percent'] == 100,
    }


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
        tag_folder = get_or_create_drive_folder(drive, get_folder_for_tag(parsed_tag), target_folder_id)
        target_folder_id = tag_folder['id']

    existing_file = find_drive_file_by_title(drive, clean_filename, target_folder_id)
    if existing_file:
        existing_id = existing_file.get('id')
        return {
            'name': clean_filename,
            'id': existing_id,
            'url': existing_file.get('alternateLink') or 'https://drive.google.com/file/d/{}/view'.format(existing_id),
            'skipped': True,
            'verified': True,
        }

    drive_file = drive.CreateFile({'title': clean_filename, 'parents': [{'id': target_folder_id}]})
    drive_file.SetContentFile(file_path)
    drive_file.Upload()
    drive_file.FetchMetadata(fields='id,title,alternateLink')
    drive_file_id = drive_file.get('id')
    return {
        'name': clean_filename,
        'id': drive_file_id,
        'url': drive_file.get('alternateLink') or 'https://drive.google.com/file/d/{}/view'.format(drive_file_id),
        'skipped': False,
        'verified': True,
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
        'permission': 'anyone_writer',
    }
