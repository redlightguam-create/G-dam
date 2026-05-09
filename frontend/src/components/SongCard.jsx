import ProgressBar from './ProgressBar.jsx';
import TagBadge from './TagBadge.jsx';

export default function SongCard({ song }) {
  return (
    <article className="song-card">
      <div className="song-card__header">
        <h4>{song.name}</h4>
        <span>{song.progress}%</span>
      </div>

      <ProgressBar value={song.progress} label={`${song.name} completion`} />

      <div className="tag-list">
        {song.present.map(tag => (
          <TagBadge key={`present-${song.id}-${tag}`} label={tag} status="present" />
        ))}
        {song.missing.map(tag => (
          <TagBadge key={`missing-${song.id}-${tag}`} label={tag} status="missing" />
        ))}
      </div>
    </article>
  );
}
