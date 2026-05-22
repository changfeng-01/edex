import { useEffect, useState } from "react";

import { CommandScreen } from "./components/StatusOverview";
import { ConstraintPanel } from "./components/ConstraintPanel";
import { FigureGallery } from "./components/FigureGallery";
import { MetricTrends } from "./components/MetricTrends";
import { OptimizationSnapshot } from "./components/OptimizationSnapshot";
import { fallbackData, loadDashboardData } from "./data/loaders";
import type { DashboardData } from "./types";

export default function App() {
  const [data, setData] = useState<DashboardData>(() => fallbackData());

  useEffect(() => {
    let active = true;
    loadDashboardData().then((loaded) => {
      if (active) {
        setData(loaded);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="app-shell">
      <CommandScreen summary={data.summary} score={data.score} />
      <ConstraintPanel score={data.score} />
      <MetricTrends metrics={data.metrics} />
      <FigureGallery />
      <OptimizationSnapshot rows={data.optimization} score={data.score} />
    </main>
  );
}
