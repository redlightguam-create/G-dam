import { useState } from 'react';
import Header from '../layout/Header.jsx';
import { createSendLink } from '../services/api.js';

export default function SendLinksPage() {
  const [artistName, setArtistName] = useState('');
  const [songName, setSongName] = useState('');
  const [link, setLink] = useState(null);
  const [error, setError] = useState('');

  async function handleSubmit(event) {
    event.preventDefault();
    setLink(null);
    setError('');

    try {
      const result = await createSendLink({ artist_name: artistName, song_name: songName });
      setLink(result.send_link);
    } catch (err) {
      setError(err.message || 'Unable to create send link.');
    }
  }

  return (
    <>
      <Header title="Send Links" subtitle="Create a Drive-backed upload destination for a sender." />

      <form className="form-panel" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label>
            <span>Artist Name</span>
            <input value={artistName} onChange={event => setArtistName(event.target.value)} />
          </label>
          <label>
            <span>Song Name</span>
            <input value={songName} onChange={event => setSongName(event.target.value)} />
          </label>
        </div>
        <div className="button-row">
          <button type="submit">Create Send Link</button>
        </div>

        {link && (
          <div className="result-panel">
            <strong>{link.artist} - {link.song}</strong>
            <a href={link.drive_folder_url} target="_blank" rel="noreferrer">
              Open Drive Folder
            </a>
          </div>
        )}
        {error && <p className="notice notice--error">{error}</p>}
      </form>
    </>
  );
}
