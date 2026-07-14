import type { SimulationImportPreview } from "../../types/product";

interface Props {
  file: File | null;
  preview: SimulationImportPreview | null;
  busy: boolean;
  onFile: (file: File | null) => void;
  onPreview: () => void;
  onCommit: () => void;
}

export function SimulationImportPanel({ file, preview, busy, onFile, onPreview, onCommit }: Props) {
  return <section className="section-panel import-panel">
    <div className="section-heading"><h2>Import simulator results</h2><p>Preview validates the exported manifest before any result is committed.</p></div>
    <label className="file-input">Simulation result CSV<input aria-label="Simulation result CSV" type="file" accept=".csv,text/csv" onChange={(event) => onFile(event.target.files?.[0] ?? null)} /></label>
    {file ? <p className="selected-file"><span>Selected file</span><strong>{file.name}</strong></p> : null}
    <div className="workflow-actions"><button className="button button--primary" disabled={!file || busy} onClick={onPreview}>Preview import</button>{preview ? <button className="button" disabled={busy} onClick={onCommit}>Commit validated import</button> : null}</div>
    {preview ? <div className="import-summary"><span>{preview.row_count} result row(s)</span><code>manifest {preview.manifest_sha256.slice(0, 12)}</code>{preview.warnings.map((warning, index) => <p className="warning" key={`${warning.type}-${index}`}>{warning.type}</p>)}</div> : null}
  </section>;
}
