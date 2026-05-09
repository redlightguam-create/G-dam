export default function Header({ title, subtitle, onRefresh }) {
  return (
    <header className="app-header">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {onRefresh && <button type="button" onClick={onRefresh}>Refresh</button>}
    </header>
  );
}
