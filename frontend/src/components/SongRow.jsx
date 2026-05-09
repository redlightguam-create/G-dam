import ProgressBar from './ProgressBar.jsx';

export default function SongRow({ song, onClick }) {
  return (
    <article className="song-row" onClick={onClick}>
      <header className="song-row__header">
        <h4>{song.name}</h4>
        <span>{song.progress}%</span>
      </header>
      <ProgressBar value={song.progress} label={`${song.name} completion`} />
    </article>
  );
}
