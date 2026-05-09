import ProgressBar from './ProgressBar.jsx';

function getInitials(name = '') {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join('')
    .toUpperCase();
}

export default function ArtistCard({ artist, onSelect }) {
  return (
    <button className="artist-card" onClick={() => onSelect(artist)} type="button">
      <div className="artist-card__image" aria-hidden="true">
        {artist.imageUrl ? (
          <img alt="" src={artist.imageUrl} />
        ) : (
          <div className="artist-card__initials">{getInitials(artist.name)}</div>
        )}
      </div>

      <div className="artist-card__body">
        <div className="artist-card__meta">
          <h3>{artist.name}</h3>
          <span>{artist.progress}%</span>
        </div>
        <ProgressBar value={artist.progress} label={`${artist.name} completion`} />
        <p>{artist.completedSongs} of {artist.totalSongs} songs complete</p>
      </div>
    </button>
  );
}
