import { apiUrl } from '../config';

async function requestJson(path, options = {}) {
  const response = await fetch(apiUrl(path), options);
  const data = await response.json().catch(() => ({
    ok: false,
    detail: response.statusText
  }));

  if (!response.ok) {
    const message = data.detail || `Request failed: ${response.status}`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }

  return data;
}

export function fetchArtistProfiles() {
  return requestJson('/artist-profiles');
}

export function updateArtistProfile(artistFolderId, payload) {
  return requestJson(`/artist-profiles/${encodeURIComponent(artistFolderId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function uploadArtistProfileImage(artistFolderId, image) {
  const form = new FormData();
  form.append('image', image);
  return requestJson(`/artist-profiles/${encodeURIComponent(artistFolderId)}/image`, {
    method: 'POST',
    body: form
  });
}

export function deleteArtistProfile(artistFolderId) {
  return requestJson(`/artist-profiles/${encodeURIComponent(artistFolderId)}`, {
    method: 'DELETE'
  });
}

export function fetchSongs() {
  return requestJson('/songs');
}

export function fetchCollaborators() {
  return requestJson('/collaborators');
}

export function createArtist(payload) {
  return requestJson('/create-artist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function createSong(payload) {
  return requestJson('/create-song', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function saveCollaborator(payload) {
  return requestJson('/collaborators', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function uploadSongFile({ file, artistName, songName }) {
  const form = new FormData();
  form.append('file', file);
  if (artistName) form.append('artist_name', artistName);
  if (songName) form.append('song_name', songName);
  return requestJson('/upload', {
    method: 'POST',
    body: form
  });
}

export function fetchSongCredits(songFolderId, context = {}) {
  const params = new URLSearchParams();
  if (context.artist) params.set('artist', context.artist);
  if (context.song) params.set('song', context.song);
  const query = params.toString();
  return requestJson(`/song-credits/${encodeURIComponent(songFolderId)}${query ? `?${query}` : ''}`);
}

export function addSongCredit(songFolderId, payload) {
  return requestJson(`/song-credits/${encodeURIComponent(songFolderId)}/collaborators`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function removeSongCredit(songFolderId, collaboratorIndex) {
  return requestJson(
    `/song-credits/${encodeURIComponent(songFolderId)}/collaborators/${encodeURIComponent(collaboratorIndex)}`,
    { method: 'DELETE' }
  );
}

export function resetSongSplits(songFolderId) {
  return requestJson(`/song-credits/${encodeURIComponent(songFolderId)}/reset-splits`, {
    method: 'POST'
  });
}

export function updateSongStatus(songFolderId, status) {
  return requestJson(`/songs/${encodeURIComponent(songFolderId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status })
  });
}

export function generateSplitSheet(songFolderId) {
  return requestJson(`/songs/${encodeURIComponent(songFolderId)}/generate-split-sheet`, {
    method: 'POST'
  });
}

export function sendSplitSheet(songFolderId) {
  return requestJson(`/songs/${encodeURIComponent(songFolderId)}/send-split-sheet`, {
    method: 'POST'
  });
}

export function createSendLink(payload) {
  return requestJson('/send-links', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}
