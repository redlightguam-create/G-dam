import { useEffect, useState } from 'react';
import ProgressBar from '../components/ProgressBar.jsx';
import SongCreditsDrawer from '../components/SongCreditsDrawer.jsx';
import TagBadge from '../components/TagBadge.jsx';
import { useSongs } from '../hooks/useSongs.js';
import Header from '../layout/Header.jsx';

export default function SongsPage({ songToOpen, onSongOpened }) {
  const { songs, loading, error, reload } = useSongs();
  const [selectedSong, setSelectedSong] = useState(null);

  function handleRowKeyDown(event, song) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setSelectedSong(song);
    }
  }

  useEffect(() => {
    if (!songToOpen) return;
    const freshSong = songs.find(song => song.id === songToOpen.id) || songToOpen;
    setSelectedSong(freshSong);
    onSongOpened?.();
  }, [songToOpen, songs, onSongOpened]);

  return (
    <>
      <Header
        title="Songs"
        subtitle="Review every song folder in G-DAM and check asset completion."
        onRefresh={reload}
      />

      {loading && <section className="state-panel">Loading songs...</section>}
      {!loading && error && <section className="state-panel state-panel--error">{error}</section>}
      {!loading && !error && songs.length === 0 && (
        <section className="state-panel">No songs found yet.</section>
      )}

      {!loading && !error && songs.length > 0 && (
        <section className="table-panel">
          <table>
            <thead>
              <tr>
                <th>Artist</th>
                <th>Song</th>
                <th>Progress</th>
                <th>Present</th>
                <th>Missing</th>
              </tr>
            </thead>
            <tbody>
              {songs.map(song => (
                <tr
                  className="clickable-row"
                  key={song.id}
                  onClick={() => setSelectedSong(song)}
                  onKeyDown={event => handleRowKeyDown(event, song)}
                  tabIndex={0}
                >
                  <td>{song.artist}</td>
                  <td>{song.name}</td>
                  <td className="progress-cell">
                    <span>{song.progress}%</span>
                    <ProgressBar value={song.progress} label={`${song.name} completion`} />
                  </td>
                  <td>
                    <div className="tag-list">
                      {song.present.map(tag => (
                        <TagBadge key={`${song.id}-present-${tag}`} label={tag} status="present" />
                      ))}
                    </div>
                  </td>
                  <td>
                    <div className="tag-list">
                      {song.missing.map(tag => (
                        <TagBadge key={`${song.id}-missing-${tag}`} label={tag} status="missing" />
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <SongCreditsDrawer song={selectedSong} onClose={() => setSelectedSong(null)} />
    </>
  );
}
