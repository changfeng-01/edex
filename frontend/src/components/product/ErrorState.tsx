import { AlertTriangle } from "lucide-react";

import { ProductApiError } from "../../api/productClient";

export function ErrorState({ error, compact = false }: { error: unknown; compact?: boolean }) {
  const productError = error instanceof ProductApiError ? error : null;
  return (
    <div className={`error-state${compact ? " error-state--compact" : ""}`} role="alert">
      <AlertTriangle aria-hidden="true" size={18} />
      <div>
        <strong>{productError?.errorCode || "RESOURCE_FAILED"}</strong>
        <p>{productError?.message || "This resource could not be loaded."}</p>
      </div>
    </div>
  );
}
