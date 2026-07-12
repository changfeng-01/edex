export function LoadingSkeleton({ label = "Loading" }: { label?: string }) {
  return <div className="loading-skeleton" aria-label={label} role="status"><span /><span /><span /></div>;
}
