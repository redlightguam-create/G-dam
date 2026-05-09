import { useEffect, useState } from 'react';
import SongRow from './SongRow.jsx';
import ProgressBar from './ProgressBar.jsx';
import { deleteArtistProfile, updateArtistProfile, uploadArtistProfileImage } from '../services/api.js';
import { formatDisplayName } from '../services/transform.js';

function getInitials(name = '') {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join('')
    .toUpperCase();
}

export default function ArtistDrawer({ artist, onClose, onOpenSong, onUpdated }) {
  const isOpen = Boolean(artist);
  const songs = artist?.songs || [];
  const [artistName, setArtistName] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setArtistName(artist?.name || '');
    setImageUrl(artist?.imageUrl || '');
    setMessage('');
    setError('');
    setConfirmDelete(false);
  }, [artist]);

  async function saveProfileName() {
    if (!artist?.id) return;
    const nextName = formatDisplayName(artistName);
    setSaving(true);
    setMessage('');
    setError('');
    try {
      await updateArtistProfile(artist.id, { artist_name: nextName });
      setArtistName(nextName);
      setMessage('Artist profile updated.');
      await onUpdated?.();
    } catch (err) {
      setError(err.message || 'Unable to update artist profile.');
    } finally {
      setSaving(false);
    }
  }

  async function saveProfileImage(event) {
    const file = event.target.files?.[0];
    if (!artist?.id || !file) return;

    setSaving(true);
    setMessage('');
    setError('');
    try {
      const result = await uploadArtistProfileImage(artist.id, file);
      const nextImageUrl = `${result.image?.image_url || artist.imageUrl}?v=${Date.now()}`;
      setImageUrl(nextImageUrl);
      setMessage('Artist image updated.');
      await onUpdated?.();
    } catch (err) {
      setError(err.message || 'Unable to update artist image.');
    } finally {
      setSaving(false);
      event.target.value = '';
    }
  }

  async function deleteProfile() {
    if (!artist?.id) return;

    setSaving(true);
    setMessage('');
    setError('');
    try {
      await deleteArtistProfile(artist.id);
      await onUpdated?.();
      onClose?.();
    } catch (err) {
      setError(err.message || 'Unable to delete artist profile.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside className={`artist-drawer ${isOpen ? 'is-open' : ''}`} aria-hidden={!isOpen}>
      <button className="artist-drawer__close" onClick={onClose} type="button">
        Close
      </button>

      {artist && (
        <div className="artist-drawer__content">
          <section className="artist-drawer__hero">
            <div className="artist-drawer__image" aria-hidden="true">
              {imageUrl ? (
                <img alt="" src={imageUrl} />
              ) : (
                <div className="artist-drawer__initials">{getInitials(artistName)}</div>
              )}
            </div>
            <div>
              <p>Artist Profile</p>
              <h2>{artistName}</h2>
            </div>
          </section>

          <section className="artist-drawer__summary">
            <div>
              <span>Songs Completed</span>
              <strong>{artist.completedSongs} / {artist.totalSongs}</strong>
            </div>
            <div>
              <span>Overall</span>
              <strong>{artist.progress}%</strong>
            </div>
            <ProgressBar value={artist.progress} label={`${artistName} overall completion`} />
          </section>

          <section className="artist-drawer__details">
            <h3>Edit Profile</h3>
            <div className="artist-drawer__edit-grid">
              <label>
                <span>Artist Name</span>
                <input value={artistName} onChange={event => setArtistName(event.target.value)} />
              </label>
              <label>
                <span>Profile Image</span>
                <input accept="image/*" disabled={saving} type="file" onChange={saveProfileImage} />
              </label>
            </div>
            <div className="button-row">
              <button type="button" disabled={saving || !artistName.trim()} onClick={saveProfileName}>
                Save Profile
              </button>
              <button className="danger-button" type="button" disabled={saving} onClick={() => setConfirmDelete(true)}>
                Delete Artist
              </button>
            </div>
            {confirmDelete && (
              <div className="confirm-panel">
                <strong>Are you sure?</strong>
                <p>Deleting is not temporary. This will delete {artistName} and all songs inside this artist profile.</p>
                <div className="button-row">
                  <button className="danger-button" type="button" disabled={saving} onClick={deleteProfile}>
                    Yes, Delete
                  </button>
                  <button className="secondary-button" type="button" disabled={saving} onClick={() => setConfirmDelete(false)}>
                    No, Keep Artist
                  </button>
                </div>
              </div>
            )}
            {message && <p className="notice notice--success">{message}</p>}
            {error && <p className="notice notice--error">{error}</p>}
            <p>{artist.totalSongs} song{artist.totalSongs === 1 ? '' : 's'} in this profile.</p>
          </section>

          <section className="artist-drawer__songs">
            <div className="artist-drawer__songs-header">
              <h3>Songs</h3>
              <span>{songs.length}</span>
            </div>
            <div className="artist-drawer__song-list">
              {songs.length === 0 && <p className="artist-drawer__empty">No songs found for this artist.</p>}
              {songs.map(song => (
                <SongRow key={song.id} song={song} onClick={() => onOpenSong?.(song)} />
              ))}
            </div>
          </section>
        </div>
      )}
    </aside>
  );
}
