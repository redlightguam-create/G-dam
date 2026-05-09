import { useState } from 'react';
import { useCollaborators } from '../hooks/useCollaborators.js';
import { useSongs } from '../hooks/useSongs.js';
import Header from '../layout/Header.jsx';
import {
  addSongCredit,
  fetchSongCredits,
  removeSongCredit,
  resetSongSplits,
  updateSongStatus
} from '../services/api.js';

const roles = [
  'Songwriter',
  'Composer',
  'Topliner',
  'Producer',
  'Co-Producer',
  'Additional Producer',
  'Recording Engineer',
  'Mix Engineer',
  'Mastering Engineer',
  'Primary Artist',
  'Featured Artist',
  'Publisher'
];

export default function SongCreditsPage() {
  const { songs } = useSongs();
  const { collaborators } = useCollaborators();
  const [songId, setSongId] = useState('');
  const [record, setRecord] = useState(null);
  const [profileId, setProfileId] = useState('');
  const [role, setRole] = useState(roles[0]);
  const [status, setStatus] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const selectedSong = songs.find(song => song.id === songId);

  async function run(action, successMessage) {
    setMessage('');
    setError('');
    try {
      const result = await action();
      setRecord(result.song_credit || result.record || null);
      setMessage(successMessage);
    } catch (err) {
      setError(err.message || 'Action failed.');
    }
  }

  async function loadCredits(nextSongId = songId) {
    if (!nextSongId) return;
    await run(() => fetchSongCredits(nextSongId), 'Credits loaded.');
  }

  return (
    <>
      <Header title="Song Credits" subtitle="Assign collaborators, roles, splits, and status." />

      <section className="form-panel">
        <div className="form-grid">
          <label className="full-width">
            <span>Song</span>
            <select
              value={songId}
              onChange={event => {
                const nextSongId = event.target.value;
                setSongId(nextSongId);
                setRecord(null);
                loadCredits(nextSongId);
              }}
            >
              <option value="">Select a song</option>
              {songs.map(song => (
                <option key={song.id} value={song.id}>
                  {song.artist} - {song.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Collaborator</span>
            <select value={profileId} onChange={event => setProfileId(event.target.value)}>
              <option value="">Select collaborator</option>
              {collaborators.map(profile => (
                <option key={profile.id} value={profile.id}>{profile.name}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Role</span>
            <select value={role} onChange={event => setRole(event.target.value)}>
              {roles.map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="full-width">
            <span>Status</span>
            <input value={status} onChange={event => setStatus(event.target.value)} placeholder="In progress, Ready, Sent..." />
          </label>
        </div>

        <div className="button-row">
          <button
            type="button"
            disabled={!songId || !profileId}
            onClick={() => run(
              () => addSongCredit(songId, {
                profile_id: profileId,
                role,
                artist: selectedSong?.artist || '',
                song: selectedSong?.name || ''
              }),
              'Collaborator added.'
            )}
          >
            Add Collaborator
          </button>
          <button type="button" disabled={!songId} onClick={() => run(() => resetSongSplits(songId), 'Splits reset.')}>
            Reset Splits
          </button>
          <button type="button" disabled={!songId || !status} onClick={() => run(() => updateSongStatus(songId, status), 'Status saved.')}>
            Save Status
          </button>
        </div>

        {message && <p className="notice notice--success">{message}</p>}
        {error && <p className="notice notice--error">{error}</p>}
      </section>

      {record && (
        <section className="table-panel">
          <h2>{record.artist || selectedSong?.artist} - {record.song || selectedSong?.name}</h2>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Collaborator ID</th>
                <th>Role</th>
                <th>Split</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(record.collaborators || []).map((credit, index) => (
                <tr key={`${credit.profile_id}-${index}`}>
                  <td>{index}</td>
                  <td>{credit.profile_id}</td>
                  <td>{credit.role}</td>
                  <td>{Number(credit.split || 0).toFixed(2)}%</td>
                  <td>
                    <button type="button" className="small-button" onClick={() => run(() => removeSongCredit(songId, index), 'Collaborator removed.')}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
