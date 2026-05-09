import { useEffect, useState } from 'react';
import { useCollaborators } from '../hooks/useCollaborators.js';
import Header from '../layout/Header.jsx';
import { saveCollaborator } from '../services/api.js';

const emptyProfile = {
  profile_id: '',
  name: '',
  email: '',
  bmi: '',
  ascap: '',
  pro: '',
  notes: ''
};

export default function CollaboratorsPage() {
  const { collaborators, loading, error, reload } = useCollaborators();
  const [form, setForm] = useState(emptyProfile);
  const [message, setMessage] = useState('');
  const [saveError, setSaveError] = useState('');

  useEffect(() => {
    if (!form.profile_id && collaborators[0]) {
      selectCollaborator(collaborators[0]);
    }
  }, [collaborators]);

  function selectCollaborator(profile) {
    setForm({
      profile_id: profile.id,
      name: profile.name,
      email: profile.email,
      bmi: profile.bmi,
      ascap: profile.ascap,
      pro: profile.pro,
      notes: profile.notes
    });
    setMessage('');
    setSaveError('');
  }

  function updateField(field, value) {
    setForm(current => ({ ...current, [field]: value }));
  }

  async function handleSave(event) {
    event.preventDefault();
    setMessage('');
    setSaveError('');

    try {
      await saveCollaborator(form);
      setMessage('Collaborator saved.');
      await reload();
    } catch (err) {
      setSaveError(err.message || 'Unable to save collaborator.');
    }
  }

  return (
    <>
      <Header
        title="Collaborators"
        subtitle="Edit the global collaborator profile library."
        onRefresh={reload}
      />

      <section className="split-panel">
        <div className="list-panel">
          {loading && <p>Loading collaborators...</p>}
          {!loading && error && <p className="notice notice--error">{error}</p>}
          {!loading && !error && collaborators.length === 0 && <p>No collaborators saved yet.</p>}
          {collaborators.map(profile => (
            <button
              className={`list-button ${form.profile_id === profile.id ? 'is-selected' : ''}`}
              key={profile.id}
              onClick={() => selectCollaborator(profile)}
              type="button"
            >
              <strong>{profile.name}</strong>
              <span>{profile.email || 'No email'}</span>
            </button>
          ))}
        </div>

        <form className="form-panel" onSubmit={handleSave}>
          <div className="form-grid">
            <label>
              <span>Name</span>
              <input value={form.name} onChange={event => updateField('name', event.target.value)} />
            </label>
            <label>
              <span>Email</span>
              <input value={form.email} onChange={event => updateField('email', event.target.value)} />
            </label>
            <label>
              <span>BMI</span>
              <input value={form.bmi} onChange={event => updateField('bmi', event.target.value)} />
            </label>
            <label>
              <span>ASCAP</span>
              <input value={form.ascap} onChange={event => updateField('ascap', event.target.value)} />
            </label>
            <label>
              <span>PRO</span>
              <input value={form.pro} onChange={event => updateField('pro', event.target.value)} />
            </label>
            <label className="full-width">
              <span>Notes</span>
              <textarea value={form.notes} onChange={event => updateField('notes', event.target.value)} />
            </label>
          </div>

          <div className="button-row">
            <button type="submit">Save</button>
            <button type="button" className="secondary-button" onClick={() => setForm(emptyProfile)}>
              New
            </button>
          </div>

          {message && <p className="notice notice--success">{message}</p>}
          {saveError && <p className="notice notice--error">{saveError}</p>}
        </form>
      </section>
    </>
  );
}
