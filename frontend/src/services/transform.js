const REQUIRED_ASSET_COUNT = 6;

export function formatDisplayName(value = '') {
  return String(value)
    .trim()
    .split(/\s+/)
    .map(word => word ? `${word.charAt(0).toUpperCase()}${word.slice(1).toLowerCase()}` : '')
    .join(' ');
}

export function calculateSongProgress(present = []) {
  return Math.floor((present.length / REQUIRED_ASSET_COUNT) * 100);
}

export function calculateArtistProgress(songs = []) {
  if (!songs.length) return 0;
  const completedSongs = songs.filter(song => song.progress === 100).length;
  return Math.floor((completedSongs / songs.length) * 100);
}

export function normalizeSong(song = {}) {
  const present = Array.isArray(song.present) ? song.present : [];
  const missing = Array.isArray(song.missing) ? song.missing : [];
  const progress = Number.isFinite(Number(song.percent))
    ? Number(song.percent)
    : calculateSongProgress(present);

  return {
    id: song.song_folder_id || song.id || '',
    name: formatDisplayName(song.song || 'Untitled Song'),
    artist: formatDisplayName(song.artist || ''),
    artistId: song.artist_folder_id || '',
    present,
    missing,
    optionalPresent: Array.isArray(song.optional_present) ? song.optional_present : [],
    itemCount: Number(song.item_count) || 0,
    progress
  };
}

export function normalizeArtistData(apiData = {}) {
  const artists = Array.isArray(apiData.artist_profiles) ? apiData.artist_profiles : [];

  return artists.map(artist => {
    const songs = (artist.songs || []).map(normalizeSong);

    return {
      id: artist.artist_folder_id || artist.id || artist.artist || '',
      name: formatDisplayName(artist.artist || 'Untitled Artist'),
      imageUrl: artist.image_url || '',
      imageFileId: artist.image_file_id || '',
      imageTitle: artist.image_title || '',
      songs,
      totalSongs: songs.length,
      completedSongs: songs.filter(song => song.progress === 100).length,
      progress: calculateArtistProgress(songs)
    };
  });
}

export function normalizeSongData(apiData = {}) {
  const songs = Array.isArray(apiData.songs) ? apiData.songs : [];
  return songs.map(normalizeSong);
}

export function normalizeCollaboratorData(apiData = {}) {
  const collaborators = Array.isArray(apiData.collaborators) ? apiData.collaborators : [];
  return collaborators.map(profile => ({
    id: profile.profile_id || '',
    name: profile.name || 'Unnamed Collaborator',
    email: profile.email || '',
    bmi: profile.bmi || '',
    ascap: profile.ascap || '',
    pro: profile.pro || '',
    notes: profile.notes || ''
  }));
}
