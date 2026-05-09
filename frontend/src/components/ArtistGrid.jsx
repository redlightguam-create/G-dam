import ArtistCard from './ArtistCard.jsx';

export default function ArtistGrid({ artists, onSelectArtist }) {
  return (
    <section className="artist-grid" aria-label="Artist profiles">
      {artists.map(artist => (
        <ArtistCard
          artist={artist}
          key={artist.id}
          onSelect={onSelectArtist}
        />
      ))}
    </section>
  );
}
