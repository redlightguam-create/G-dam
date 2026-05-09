import { useState } from 'react';
import ArtistDrawer from '../components/ArtistDrawer.jsx';
import ArtistGrid from '../components/ArtistGrid.jsx';
import Header from '../layout/Header.jsx';
import { useArtists } from '../hooks/useArtists.js';

export default function ArtistProfilesPage({ onOpenSong }) {
  const { artists, loading, error, reload } = useArtists();
  const [selectedArtist, setSelectedArtist] = useState(null);

  return (
    <div className="artist-profiles-page">
      <Header
        title="Artist Profiles"
        subtitle="Track release readiness by artist, song, and required asset tags."
        onRefresh={reload}
      />

      <div className="artist-profiles-layout">
        {loading && <section className="state-panel">Loading artist profiles...</section>}

        {!loading && error && (
          <section className="state-panel state-panel--error">{error}</section>
        )}

        {!loading && !error && artists.length === 0 && (
          <section className="state-panel">
            No artist profiles found yet. Upload song assets to create profiles.
          </section>
        )}

        {!loading && !error && artists.length > 0 && (
          <ArtistGrid artists={artists} onSelectArtist={setSelectedArtist} />
        )}
      </div>

      <ArtistDrawer
        artist={selectedArtist}
        onClose={() => setSelectedArtist(null)}
        onOpenSong={onOpenSong}
        onUpdated={reload}
      />
    </div>
  );
}
