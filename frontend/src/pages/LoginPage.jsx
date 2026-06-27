import { getGoogleLoginUrl } from '../services/api.js';

export default function LoginPage({ error }) {
  return (
    <main className="login-screen">
      <section className="login-panel">
        <div>
          <p className="eyebrow">G-DAM</p>
          <h1>Sign in with Google</h1>
          <p className="login-copy">
            Connect Drive, Docs, and Gmail so G-DAM can organize your catalog, build split sheets,
            and send signature links from your own Google account.
          </p>
        </div>

        {error && <p className="form-error">{error}</p>}

        <a className="primary-action" href={getGoogleLoginUrl()}>
          Continue with Google
        </a>
      </section>
    </main>
  );
}
