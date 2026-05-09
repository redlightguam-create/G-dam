import { useEffect, useState } from 'react';
import { useCollaborators } from '../hooks/useCollaborators.js';
import {
  addSongCredit,
  fetchSongCredits,
  generateSplitSheet,
  removeSongCredit,
  resetSongSplits,
  sendSplitSheet
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

export default function SongCreditsDrawer({ song, onClose }) {
  const isOpen = Boolean(song);
  const { collaborators } = useCollaborators();
  const [record, setRecord] = useState(null);
  const [releaseStatus, setReleaseStatus] = useState(null);
  const [profileId, setProfileId] = useState('');
  const [role, setRole] = useState(roles[0]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);

  const songId = song?.id || '';
  const credits = record?.collaborators || [];
  const splitTotal = credits.reduce((total, credit) => total + Number(credit.split || 0), 0);
  const collaboratorNames = new Map(collaborators.map(profile => [profile.id, profile.name]));

  async function refreshCredits() {
    const result = await fetchSongCredits(songId, { artist: song.artist, song: song.name });
    const nextRecord = result.song_credit || null;
    setRecord(nextRecord);
    setReleaseStatus(result.release_status || null);
  }

  async function run(action, successMessage, shouldRefresh = false) {
    if (!songId) return;
    setMessage('');
    setError('');
    try {
      const result = await action();
      if (result.song_credit || result.record) {
        const nextRecord = result.song_credit || result.record;
        setRecord(nextRecord);
        if (result.release_status) setReleaseStatus(result.release_status);
      }
      if (shouldRefresh) {
        await refreshCredits();
      }
      setMessage(successMessage);
    } catch (err) {
      setError(err.message || 'Action failed.');
    }
  }

  function addSelectedCollaborator() {
    if (!profileId) {
      setMessage('');
      setError('Select a collaborator first.');
      return;
    }

    run(
      () => addSongCredit(songId, {
        profile_id: profileId,
        role,
        artist: song.artist,
        song: song.name
      }),
      'Collaborator added.'
    );
  }

  useEffect(() => {
    let cancelled = false;

    async function loadCredits() {
      if (!songId) {
        setRecord(null);
        return;
      }

      setLoading(true);
      setMessage('');
      setError('');
      setProfileId('');
      try {
        const result = await fetchSongCredits(songId, { artist: song.artist, song: song.name });
        if (!cancelled) {
          const nextRecord = result.song_credit || null;
          setRecord(nextRecord);
          setReleaseStatus(result.release_status || null);
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Unable to load credits.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadCredits();
    return () => {
      cancelled = true;
    };
  }, [songId, song?.artist, song?.name]);

  return (
    <aside className={`song-credits-drawer ${isOpen ? 'is-open' : ''}`} aria-hidden={!isOpen}>
      <button className="song-credits-drawer__close" onClick={onClose} type="button">
        Close
      </button>

      {song && (
        <div className="song-credits-drawer__content">
          <section className="song-credits-drawer__hero">
            <p>Song Credits</p>
            <h2>{song.name}</h2>
            <span>{song.artist}</span>
          </section>

          <section className="song-credits-drawer__summary">
            <div>
              <span>Asset Progress</span>
              <strong>{song.progress}%</strong>
            </div>
            <div>
              <span>Split Total</span>
              <strong>{splitTotal.toFixed(2)}%</strong>
            </div>
            <div>
              <span>Credits</span>
              <strong>{credits.length}</strong>
            </div>
            <div>
              <span>Status</span>
              <strong>{releaseStatus ? `${releaseStatus.percent}%` : 'Loading'}</strong>
            </div>
          </section>

          {releaseStatus && (
            <section className="song-credits-drawer__status-panel">
              <button
                className="song-credits-drawer__status-toggle"
                type="button"
                onClick={() => setStatusOpen(current => !current)}
              >
                <span>{releaseStatus.label}</span>
                <strong>{releaseStatus.percent}%</strong>
              </button>
              {statusOpen && (
                <div className="song-credits-drawer__status-details">
                  <div className="song-credits-drawer__steps">
                    {releaseStatus.steps.map(step => (
                      <div className={`song-credits-drawer__step ${step.complete ? 'is-complete' : ''}`} key={step.id}>
                        <strong>{step.complete ? 'Done' : 'Missing'}</strong>
                        <span>{step.label}</span>
                        <em>{step.detail}</em>
                      </div>
                    ))}
                  </div>
                  <div className="song-credits-drawer__signatures">
                    <h3>Split Sheet Signatures</h3>
                    {releaseStatus.collaborators.length === 0 && <p>No collaborators assigned.</p>}
                    {releaseStatus.collaborators.map(collaborator => (
                      <div className="song-credits-drawer__signature-row" key={collaborator.profile_id}>
                        <div>
                          <strong>{collaborator.name}</strong>
                          <span>{collaborator.email || 'No email'}</span>
                        </div>
                        <span>{collaborator.sent ? 'Sent' : 'Not sent'}</span>
                        <span>{collaborator.signed ? 'Signed' : 'Not signed'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          <section className="song-credits-drawer__panel">
            <div className="form-grid">
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
            </div>

            <div className="button-row">
              <button
                type="button"
                onClick={addSelectedCollaborator}
              >
                Add Collaborator
              </button>
              <button type="button" onClick={() => run(() => resetSongSplits(songId), 'Splits reset.')}>
                Reset Splits
              </button>
              <button type="button" onClick={() => run(() => generateSplitSheet(songId), 'Split sheet generated.', true)}>
                Generate Split Sheet
              </button>
              <button type="button" onClick={() => run(() => sendSplitSheet(songId), 'Split sheet emails sent.', true)}>
                Send Split Sheet
              </button>
            </div>

            {message && <p className="notice notice--success">{message}</p>}
            {error && <p className="notice notice--error">{error}</p>}
          </section>

          <section className="song-credits-drawer__credits">
            <div className="song-credits-drawer__section-title">
              <h3>Assigned Credits</h3>
              {loading && <span>Loading...</span>}
            </div>
            {credits.length === 0 && !loading && (
              <p className="song-credits-drawer__empty">No collaborators assigned to this song yet.</p>
            )}
            {credits.length > 0 && (
              <div className="song-credits-drawer__table">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Collaborator</th>
                      <th>Role</th>
                      <th>Split</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {credits.map((credit, index) => (
                      <tr key={`${credit.profile_id}-${index}`}>
                        <td>{index}</td>
                        <td>{collaboratorNames.get(credit.profile_id) || credit.profile_id}</td>
                        <td>{credit.role}</td>
                        <td>{Number(credit.split || 0).toFixed(2)}%</td>
                        <td>
                          <button
                            type="button"
                            className="small-button"
                            onClick={() => run(() => removeSongCredit(songId, index), 'Collaborator removed.')}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </aside>
  );
}
