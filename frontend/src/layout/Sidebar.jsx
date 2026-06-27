export const navItems = [
  { id: 'artist-profiles', label: 'Artist Profiles' },
  { id: 'songs', label: 'Songs' },
  { id: 'upload', label: 'Upload' },
  { id: 'collaborators', label: 'Collaborators' }
];

export default function Sidebar({ activeView, onNavigate, user, onLogout }) {
  return (
    <aside className="sidebar">
      <div className="brand">G-DAM</div>
      <nav>
        {navItems.map(item => (
          <button
            className={`nav-item ${activeView === item.id ? 'is-active' : ''}`}
            key={item.id}
            onClick={() => onNavigate(item.id)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>
      {user && (
        <div className="sidebar-user">
          {user.picture && <img src={user.picture} alt="" />}
          <div>
            <strong>{user.name || user.email}</strong>
            <span>{user.email}</span>
          </div>
          <button type="button" onClick={onLogout}>Sign Out</button>
        </div>
      )}
      <a className="docs-link" href="/docs">API Docs</a>
    </aside>
  );
}
