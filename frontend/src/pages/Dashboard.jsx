import { useState } from 'react';
import Sidebar from '../layout/Sidebar.jsx';
import ArtistProfilesPage from './ArtistProfilesPage.jsx';
import CollaboratorsPage from './CollaboratorsPage.jsx';
import SongsPage from './SongsPage.jsx';
import UploadPage from './UploadPage.jsx';

const pages = {
  'artist-profiles': ArtistProfilesPage,
  songs: SongsPage,
  upload: UploadPage,
  collaborators: CollaboratorsPage
};

export default function Dashboard() {
  const [activeView, setActiveView] = useState('artist-profiles');
  const [songToOpen, setSongToOpen] = useState(null);
  const ActivePage = pages[activeView] || ArtistProfilesPage;

  function openSongFromArtist(song) {
    setSongToOpen(song);
    setActiveView('songs');
  }

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onNavigate={setActiveView} />

      <main className="content">
        <ActivePage onOpenSong={openSongFromArtist} songToOpen={songToOpen} onSongOpened={() => setSongToOpen(null)} />
      </main>
    </div>
  );
}
