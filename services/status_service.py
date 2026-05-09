from .collaborator_service import get_song_credit_total, load_collaborators, load_song_credit_assignments
from .song_service import get_song_completeness
from .split_sheet_service import load_signature_requests


def _unique_credit_profile_ids(record):
    profile_ids = []
    seen = set()
    for collaborator in record.get('collaborators', []):
        profile_id = (collaborator.get('profile_id') or '').strip()
        if profile_id and profile_id not in seen:
            seen.add(profile_id)
            profile_ids.append(profile_id)
    return profile_ids


def calculate_song_release_status(song_folder_id, drive=None, record=None):
    assignments = load_song_credit_assignments(drive)
    record = record or assignments.get(song_folder_id, {})
    completeness = get_song_completeness(song_folder_id, drive)
    profiles = {profile.get('profile_id'): profile for profile in load_collaborators(drive)}
    signature_requests = [
        request for request in load_signature_requests(drive).values()
        if request.get('song_folder_id') == song_folder_id
    ]

    credit_profile_ids = _unique_credit_profile_ids(record)
    split_total = get_song_credit_total(record)
    asset_complete = completeness.get('percent') == 100
    has_credits = bool(credit_profile_ids)
    splits_complete = has_credits and abs(split_total - 100.0) <= 0.01
    credit_complete = has_credits and splits_complete
    split_sheet_generated = bool(record.get('split_sheet_doc_id') or record.get('split_sheet_url'))

    sent_profile_ids = {
        request.get('profile_id')
        for request in signature_requests
        if request.get('email_sent_at')
    }
    signed_profile_ids = {
        request.get('profile_id')
        for request in signature_requests
        if request.get('status') == 'signed'
    }
    missing_email_profile_ids = [
        profile_id for profile_id in credit_profile_ids
        if not (profiles.get(profile_id, {}).get('email') or '').strip()
    ]
    collaborators = []
    for profile_id in credit_profile_ids:
        profile = profiles.get(profile_id, {})
        requests = [request for request in signature_requests if request.get('profile_id') == profile_id]
        sent = any(request.get('email_sent_at') for request in requests)
        signed_request = next((request for request in requests if request.get('status') == 'signed'), None)
        collaborators.append({
            'profile_id': profile_id,
            'name': profile.get('name') or profile_id,
            'email': profile.get('email', ''),
            'sent': sent,
            'signed': bool(signed_request),
            'signed_at': signed_request.get('signed_at') if signed_request else None,
            'signed_document_url': signed_request.get('signed_document_url', '') if signed_request else '',
            'missing_email': profile_id in missing_email_profile_ids,
        })

    sent_to_all = bool(credit_profile_ids) and all(profile_id in sent_profile_ids for profile_id in credit_profile_ids)
    signed_by_all = bool(credit_profile_ids) and all(profile_id in signed_profile_ids for profile_id in credit_profile_ids)
    complete = asset_complete and credit_complete and sent_to_all and signed_by_all
    steps = [
        {'id': 'assets', 'label': 'Assets complete', 'complete': asset_complete, 'detail': '{}% assets'.format(completeness.get('percent', 0))},
        {'id': 'credits', 'label': 'Credits assigned', 'complete': has_credits, 'detail': '{} collaborator{}'.format(len(credit_profile_ids), '' if len(credit_profile_ids) == 1 else 's')},
        {'id': 'splits', 'label': 'Splits total 100%', 'complete': splits_complete, 'detail': '{:.2f}% splits'.format(split_total)},
        {'id': 'generated', 'label': 'Split sheet generated', 'complete': split_sheet_generated, 'detail': 'Generated' if split_sheet_generated else 'Not generated'},
        {'id': 'sent', 'label': 'Sent to all collaborators', 'complete': sent_to_all, 'detail': '{} / {} sent'.format(len(sent_profile_ids.intersection(credit_profile_ids)), len(credit_profile_ids))},
        {'id': 'signed', 'label': 'Signed back by all collaborators', 'complete': signed_by_all, 'detail': '{} / {} signed'.format(len(signed_profile_ids.intersection(credit_profile_ids)), len(credit_profile_ids))},
    ]
    percent = int(round((sum(1 for step in steps if step['complete']) / len(steps)) * 100)) if steps else 0

    if complete:
        label = 'Complete'
    elif not asset_complete:
        label = 'Needs Assets'
    elif not has_credits:
        label = 'Needs Credits'
    elif not splits_complete:
        label = 'Needs 100% Splits'
    elif not split_sheet_generated:
        label = 'Ready To Generate Split Sheet'
    elif missing_email_profile_ids:
        label = 'Missing Collaborator Emails'
    elif not sent_to_all:
        label = 'Ready To Send Split Sheet'
    elif not signed_by_all:
        label = 'Awaiting Signatures'
    else:
        label = 'In Progress'

    return {
        'label': label,
        'percent': percent,
        'complete': complete,
        'steps': steps,
        'collaborators': collaborators,
        'asset_complete': asset_complete,
        'asset_percent': completeness.get('percent', 0),
        'credit_complete': credit_complete,
        'has_credits': has_credits,
        'split_total': split_total,
        'split_sheet_generated': split_sheet_generated,
        'sent_to_all': sent_to_all,
        'signed_by_all': signed_by_all,
        'collaborator_count': len(credit_profile_ids),
        'sent_count': len(sent_profile_ids.intersection(credit_profile_ids)),
        'signed_count': len(signed_profile_ids.intersection(credit_profile_ids)),
        'missing_email_count': len(missing_email_profile_ids),
    }
