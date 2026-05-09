export default function TagBadge({ label, status = 'present' }) {
  return (
    <span className={`tag-badge tag-badge--${status}`}>
      {label}
    </span>
  );
}
