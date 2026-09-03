export function LoadingState({
  label = "Loading…",
}: {
  label?: string;
}) {
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}
