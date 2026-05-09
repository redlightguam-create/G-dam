import { useCallback, useEffect, useState } from 'react';
import { fetchArtistProfiles } from '../services/api.js';
import { normalizeArtistData } from '../services/transform.js';

export function useArtists() {
  const [artists, setArtists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadArtists = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const data = await fetchArtistProfiles();
      setArtists(normalizeArtistData(data));
    } catch (err) {
      setError(err.message || 'Unable to load artist profiles.');
      setArtists([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadArtists();
  }, [loadArtists]);

  return {
    artists,
    loading,
    error,
    reload: loadArtists
  };
}
