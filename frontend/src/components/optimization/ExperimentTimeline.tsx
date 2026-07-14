const steps = ["Proposed", "Approved", "Exported", "Resimulated", "Evaluated"];

export function ExperimentTimeline({ current = "Proposed" }: { current?: string }) {
  const normalized = current.toLowerCase();
  const aliases: Record<string, number> = { proposed: 0, approved: 1, simulation_pending: 2, exported: 2, resimulated: 3, evaluated: 4, confirmed_improvement: 4 };
  const active = aliases[normalized] ?? Math.max(0, steps.findIndex((step) => step.toLowerCase() === normalized));
  return <ol className="workflow-timeline" aria-label="Manual simulation workflow">
    {steps.map((step, index) => <li key={step} className={index <= active ? "is-reached" : ""}><span>{index + 1}</span>{step}</li>)}
  </ol>;
}
