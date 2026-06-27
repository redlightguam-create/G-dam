import { useEffect, useState } from 'react';
import Sidebar from '../layout/Sidebar.jsx';
import ArtistProfilesPage from './ArtistProfilesPage.jsx';
import CollaboratorsPage from './CollaboratorsPage.jsx';
import LoginPage from './LoginPage.jsx';
import SongsPage from './SongsPage.jsx';
import UploadPage from './UploadPage.jsx';
import { fetchAuthStatus, logout } from '../services/api.js';

const pages = {
  'artist-profiles': ArtistProfilesPage,
  songs: SongsPage,
  upload: UploadPage,
  collaborators: CollaboratorsPage
};

export default function Dashboard() {
  const [activeView, setActiveView] = useState('artist-profiles');
  const [songToOpen, setSongToOpen] = useState(null);
  const [auth, setAuth] = useState({ loading: true, requireLogin: false, authenticated: false, user: null });
  const [authError, setAuthError] = useState('');
  const ActivePage = pages[activeView] || ArtistProfilesPage;

  useEffect(() => {
    let isMounted = true;
    fetchAuthStatus()
      .then(result => {
        if (!isMounted) return;
        setAuth({
          loading: false,
          requireLogin: Boolean(result.require_login),
          authenticated: Boolean(result.authenticated),
          user: result.user || null
        });
      })
      .catch(error => {
        if (!isMounted) return;
        setAuthError(error.message);
        setAuth({ loading: false, requireLogin: true, authenticated: false, user: null });
      });
    return () => {
      isMounted = false;
    };
  }, []);

  function openSongFromArtist(song) {
    setSongToOpen(song);
    setActiveView('songs');
  }

  async function handleLogout() {
    await logout();
    setAuth({ loading: false, requireLogin: true, authenticated: false, user: null });
  }

  if (auth.loading) {
    return <main className="loading-screen">Loading G-DAM...</main>;
  }

  if (auth.requireLogin && !auth.authenticated) {
    return <LoginPage error={authError} />;
  }

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onNavigate={setActiveView} user={auth.user} onLogout={handleLogout} />

      <main className="content">
        <ActivePage onOpenSong={openSongFromArtist} songToOpen={songToOpen} onSongOpened={() => setSongToOpen(null)} />
      </main>
    </div>
  );
}
