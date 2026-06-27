import { apiUrl } from '../config';

export async function apiFetch(path, options = {}) {
  const url = apiUrl(path);
  const response = await fetch(url, {
    credentials: 'include',
    ...options
  });
  const data = await response.json().catch(() => ({
    ok: false,
    detail: response.statusText
  }));

  if (!response.ok) {
    const message = data.detail || `Request failed: ${response.status}`;
    const detail = typeof message === 'string' ? message : JSON.stringify(message);
    throw new Error(`${detail} (${url})`);
  }

  return data;
}

export function getGoogleLoginUrl() {
  return apiUrl('/auth/google/start');
}

export function fetchAuthStatus() {
  return apiFetch('/auth/status');
}

export function logout() {
  return apiFetch('/auth/logout', {
    method: 'POST'
  });
}

export function fetchArtistProfiles() {
  return apiFetch('/artist-profiles');
}

export function updateArtistProfile(artistFolderId, payload) {
  return apiFetch(`/artist-profiles/${encodeURIComponent(artistFolderId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function uploadArtistProfileImage(artistFolderId, image) {
  const form = new FormData();
  form.append('image', image);
  return apiFetch(`/artist-profiles/${encodeURIComponent(artistFolderId)}/image`, {
    method: 'POST',
    body: form
  });
}

export function deleteArtistProfile(artistFolderId) {
  return apiFetch(`/artist-profiles/${encodeURIComponent(artistFolderId)}`, {
    method: 'DELETE'
  });
}

export function fetchSongs() {
  return apiFetch('/songs');
}

export function fetchCollaborators() {
  return apiFetch('/collaborators');
}

export function createArtist(payload) {
  return apiFetch('/create-artist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function createSong(payload) {
  return apiFetch('/create-song', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function saveCollaborator(payload) {
  return apiFetch('/collaborators', {
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
  return apiFetch('/upload', {
    method: 'POST',
    body: form
  });
}

export function fetchSongCredits(songFolderId, context = {}) {
  const params = new URLSearchParams();
  if (context.artist) params.set('artist', context.artist);
  if (context.song) params.set('song', context.song);
  const query = params.toString();
  return apiFetch(`/song-credits/${encodeURIComponent(songFolderId)}${query ? `?${query}` : ''}`);
}

export function addSongCredit(songFolderId, payload) {
  return apiFetch(`/song-credits/${encodeURIComponent(songFolderId)}/collaborators`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export function removeSongCredit(songFolderId, collaboratorIndex) {
  return apiFetch(
    `/song-credits/${encodeURIComponent(songFolderId)}/collaborators/${encodeURIComponent(collaboratorIndex)}`,
    { method: 'DELETE' }
  );
}

export function resetSongSplits(songFolderId) {
  return apiFetch(`/song-credits/${encodeURIComponent(songFolderId)}/reset-splits`, {
    method: 'POST'
  });
}

export function updateSongStatus(songFolderId, status) {
  return apiFetch(`/songs/${encodeURIComponent(songFolderId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status })
  });
}

export function generateSplitSheet(songFolderId) {
  return apiFetch(`/songs/${encodeURIComponent(songFolderId)}/generate-split-sheet`, {
    method: 'POST'
  });
}

export function sendSplitSheet(songFolderId) {
  return apiFetch(`/songs/${encodeURIComponent(songFolderId)}/send-split-sheet`, {
    method: 'POST'
  });
}

export function createSendLink(payload) {
  return apiFetch('/send-links', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}
