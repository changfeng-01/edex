import { ShieldAlert } from "lucide-react";

import type { EvidenceBoundary } from "../../types/product";

const fallback: EvidenceBoundary = { data_source: "real_simulation_csv", engineering_validity: "simulation_only", must_resimulate: true };

export function EvidenceSummary({ boundary = fallback }: { boundary?: EvidenceBoundary }) {
  return (
    <section className="evidence-strip" aria-label="Evidence boundary">
      <div className="evidence-strip__title"><ShieldAlert aria-hidden="true" size={18} /><span>Evidence boundary</span></div>
      <code>data_source = {boundary.data_source}</code>
      <code>engineering_validity = {boundary.engineering_validity}</code>
      <code>must_resimulate = {String(boundary.must_resimulate)}</code>
    </section>
  );
}
