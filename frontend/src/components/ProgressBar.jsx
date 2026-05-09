export default function ProgressBar({ value = 0, label }) {
  const percent = Math.max(0, Math.min(100, Number(value) || 0));

  return (
    <div className="progress-shell" aria-label={label || `Progress ${percent}%`}>
      <div className="progress-fill" style={{ width: `${percent}%` }} />
    </div>
  );
}
