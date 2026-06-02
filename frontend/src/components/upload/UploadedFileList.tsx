import type { UploadFiles } from "./FileDropzone";

interface UploadedFileListProps {
  files: UploadFiles;
}

export function UploadedFileList({ files }: UploadedFileListProps) {
  const rows = [
    files.waveform,
    files.params,
    files.netlist,
    ...files.attachments,
  ].filter(Boolean) as File[];

  return (
    <div className="rounded-lg border border-white/10 bg-slate-950/55 p-4">
      <div className="text-sm font-semibold text-slate-100">已选择文件</div>
      {rows.length === 0 ? (
        <div className="mt-3 rounded-lg border border-dashed border-slate-500/35 bg-slate-900/40 p-4 text-sm text-slate-400">
          尚未选择输入文件。
        </div>
      ) : (
        <div className="mt-3 grid gap-2">
          {rows.map((file) => (
            <div key={`${file.name}-${file.size}`} className="flex items-center justify-between gap-3 rounded-md bg-white/[0.04] px-3 py-2 text-sm">
              <span className="truncate text-slate-200">{file.name}</span>
              <span className="shrink-0 text-xs text-slate-400">{formatBytes(file.size)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  return `${(value / 1024).toFixed(1)} KB`;
}

