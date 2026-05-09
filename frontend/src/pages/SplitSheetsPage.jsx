import { useState } from 'react';
import { useSongs } from '../hooks/useSongs.js';
import Header from '../layout/Header.jsx';
import { generateSplitSheet, sendSplitSheet } from '../services/api.js';

export default function SplitSheetsPage() {
  const { songs, reload } = useSongs();
  const [songId, setSongId] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function run(action, successMessage) {
    setMessage('');
    setError('');
    try {
      await action();
      setMessage(successMessage);
    } catch (err) {
      setError(err.message || 'Action failed.');
    }
  }

  return (
    <>
      <Header
        title="Split Sheets"
        subtitle="Generate a split sheet first, then send signature emails separately."
        onRefresh={reload}
      />

      <section className="form-panel">
        <label>
          <span>Song</span>
          <select value={songId} onChange={event => setSongId(event.target.value)}>
            <option value="">Select a song</option>
            {songs.map(song => (
              <option key={song.id} value={song.id}>
                {song.artist} - {song.name}
              </option>
            ))}
          </select>
        </label>

        <div className="button-row">
          <button type="button" disabled={!songId} onClick={() => run(() => generateSplitSheet(songId), 'Split sheet generated.')}>
            Generate Split Sheet
          </button>
          <button type="button" disabled={!songId} onClick={() => run(() => sendSplitSheet(songId), 'Split sheet emails sent.')}>
            Send Split Sheet
          </button>
        </div>

        {message && <p className="notice notice--success">{message}</p>}
        {error && <p className="notice notice--error">{error}</p>}
      </section>
    </>
  );
}
