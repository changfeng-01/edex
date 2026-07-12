import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createProductClient } from "../api/productClient";
import { EvidenceSummary } from "../components/product/EvidenceSummary";
import { PageHeader } from "../components/product/PageHeader";
import { SectionPanel } from "../components/product/SectionPanel";
import { SimulationInputPanel } from "../components/product/SimulationInputPanel";

export function DesignVersionPage() {
  const { versionId = "" } = useParams();
  const navigate = useNavigate();
  const [label, setLabel] = useState(versionId);
  const client = createProductClient();
  useEffect(() => { client.getDesignVersion(versionId).then((version) => setLabel(version.label)).catch(() => {}); }, [versionId]);
  return <><PageHeader eyebrow="Design version" title="Design version" description={`${label} / ${versionId}`} /><EvidenceSummary /><SectionPanel title="Simulation input" description="Preview validates both waveform and parameter inputs before analysis."><SimulationInputPanel resolveContext={async () => ({ versionId })} onAnalysisCreated={(run) => navigate(`/analysis/${run.analysis_run_id}`)} /></SectionPanel></>;
}
