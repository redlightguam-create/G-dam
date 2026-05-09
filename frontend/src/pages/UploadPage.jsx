import { useState } from 'react';
import Header from '../layout/Header.jsx';
import { createArtist, createSong, uploadSongFile } from '../services/api.js';

export default function UploadPage() {
  const [artistName, setArtistName] = useState('');
  const [songName, setSongName] = useState('');
  const [file, setFile] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function runAction(action) {
    setSaving(true);
    setMessage('');
    setError('');

    try {
      const result = await action();
      setMessage(result.created === false ? 'Already exists.' : 'Done.');
    } catch (err) {
      setError(err.message || 'Action failed.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <Header
        title="Upload"
        subtitle="Create artist/song folders and upload a file into the selected song drop."
      />

      <section className="form-panel">
        <div className="form-grid">
          <label>
            <span>Artist Name</span>
            <input value={artistName} onChange={event => setArtistName(event.target.value)} />
          </label>
          <label>
            <span>Song Name</span>
            <input value={songName} onChange={event => setSongName(event.target.value)} />
          </label>
          <label className="full-width">
            <span>File</span>
            <input type="file" onChange={event => setFile(event.target.files?.[0] || null)} />
          </label>
        </div>

        <div className="button-row">
          <button type="button" disabled={saving} onClick={() => runAction(() => createArtist({ artist_name: artistName }))}>
            Create Artist
          </button>
          <button type="button" disabled={saving} onClick={() => runAction(() => createSong({ artist_name: artistName, song_name: songName }))}>
            Create Song
          </button>
          <button type="button" disabled={saving || !file} onClick={() => runAction(() => uploadSongFile({ file, artistName, songName }))}>
            Upload File
          </button>
        </div>

        {message && <p className="notice notice--success">{message}</p>}
        {error && <p className="notice notice--error">{error}</p>}
      </section>
    </>
  );
}
