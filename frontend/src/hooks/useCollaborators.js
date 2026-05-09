import { useCallback, useEffect, useState } from 'react';
import { fetchCollaborators } from '../services/api.js';
import { normalizeCollaboratorData } from '../services/transform.js';

export function useCollaborators() {
  const [collaborators, setCollaborators] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadCollaborators = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const data = await fetchCollaborators();
      setCollaborators(normalizeCollaboratorData(data));
    } catch (err) {
      setError(err.message || 'Unable to load collaborators.');
      setCollaborators([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCollaborators();
  }, [loadCollaborators]);

  return {
    collaborators,
    loading,
    error,
    reload: loadCollaborators
  };
}
