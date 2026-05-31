import { useEffect, useState } from "react";

import { BeforeAfterPanel } from "./components/BeforeAfterPanel";
import { CandidateRankingTable } from "./components/CandidateRankingTable";
import { ConstraintStatusPanel } from "./components/ConstraintStatusPanel";
import { EvidenceBoundaryCard } from "./components/EvidenceBoundaryCard";
import { FiguresGallery } from "./components/FiguresGallery";
import { Header } from "./components/Header";
import { OverviewCards } from "./components/OverviewCards";
import { ReportsPanel } from "./components/ReportsPanel";
import { loadProductDemoDashboard } from "./lib/demoData";
import type { ProductDemoDashboardData } from "./types";

export default function App() {
  const [data, setData] = useState<ProductDemoDashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    loadProductDemoDashboard()
      .then((loaded) => {
        if (active) {
          setData(loaded);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  if (!data) {
    return (
      <main className="min-h-screen bg-slate-950 p-6 text-slate-100">
        <div className="mx-auto grid min-h-[70vh] max-w-5xl place-items-center rounded-lg border border-white/10 bg-white/[0.04]">
          <div className="text-center">
            <div className="text-sm font-semibold uppercase tracking-wide text-cyan-200">CircuitPilot Dashboard</div>
            <div className="mt-3 text-2xl font-bold">{loading ? "Loading product-demo package..." : "Dashboard data unavailable"}</div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="dashboard-bg" aria-hidden="true" />
      <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-5 px-4 py-5 md:px-6 lg:px-8">
        <Header summary={data.summary} />

        {data.resourceErrors.length > 0 ? (
          <section className="rounded-lg border border-amber-300/25 bg-amber-300/[0.08] p-4 text-sm text-amber-100" aria-label="Resource warnings">
            Some static resources are missing or unavailable. The dashboard is showing available data and local fallback states.
          </section>
        ) : null}

        <OverviewCards summary={data.summary} />
        <EvidenceBoundaryCard evidence={data.summary.evidence} />
        <ConstraintStatusPanel rows={data.tables.constraints?.rows ?? []} />
        <CandidateRankingTable rows={data.tables.candidates?.rows ?? []} />
        <BeforeAfterPanel rows={data.tables.before_after?.rows ?? []} />
        <FiguresGallery figures={data.figures} />
        <ReportsPanel reports={data.reports} />
      </div>
    </main>
  );
}
