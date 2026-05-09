import { useCallback, useEffect, useState } from 'react';
import { fetchSongs } from '../services/api.js';
import { normalizeSongData } from '../services/transform.js';

export function useSongs() {
  const [songs, setSongs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadSongs = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const data = await fetchSongs();
      setSongs(normalizeSongData(data));
    } catch (err) {
      setError(err.message || 'Unable to load songs.');
      setSongs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSongs();
  }, [loadSongs]);

  return {
    songs,
    loading,
    error,
    reload: loadSongs
  };
}
