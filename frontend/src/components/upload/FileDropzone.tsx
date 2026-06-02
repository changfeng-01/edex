import { FileUp } from "lucide-react";

export interface UploadFiles {
  waveform: File | null;
  params: File | null;
  netlist: File | null;
  attachments: File[];
}

interface FileDropzoneProps {
  files: UploadFiles;
  onFilesChange: (files: UploadFiles) => void;
}

export function FileDropzone({ files, onFilesChange }: FileDropzoneProps) {
  return (
    <section className="rounded-lg border border-cyan-300/15 bg-slate-950/70 p-5 shadow-2xl shadow-black/20">
      <div className="flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg border border-cyan-200/20 bg-cyan-300/10 text-cyan-100">
          <FileUp size={20} />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-50">文件上传</h2>
          <p className="text-sm text-slate-400">保存仿真输入文件；图片仅作为附件展示。</p>
        </div>
      </div>

      <div className="mt-5 grid gap-4">
        <UploadInput
          label="waveform.csv"
          requiredLabel="必需"
          accept=".csv,text/csv"
          file={files.waveform}
          onChange={(file) => onFilesChange({ ...files, waveform: file })}
        />
        <UploadInput
          label="params.yaml"
          requiredLabel="可选"
          accept=".yaml,.yml"
          file={files.params}
          onChange={(file) => onFilesChange({ ...files, params: file })}
        />
        <UploadInput
          label="source_netlist.spice / .sp / .netlist"
          requiredLabel="可选"
          accept=".spice,.sp,.netlist"
          file={files.netlist}
          onChange={(file) => onFilesChange({ ...files, netlist: file })}
        />
        <label className="block rounded-lg border border-dashed border-slate-500/40 bg-slate-950/45 p-4 text-sm text-slate-300 transition hover:border-cyan-200/35">
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium">png / jpg 附件</span>
            <span className="rounded-full border border-white/10 px-2 py-0.5 text-xs text-slate-400">可选</span>
          </div>
          <input
            className="mt-3 block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-cyan-300/10 file:px-3 file:py-2 file:text-cyan-100"
            type="file"
            accept=".png,.jpg,.jpeg,image/png,image/jpeg"
            multiple
            onChange={(event) => onFilesChange({ ...files, attachments: Array.from(event.currentTarget.files ?? []) })}
          />
        </label>
      </div>
    </section>
  );
}

interface UploadInputProps {
  label: string;
  requiredLabel: string;
  accept: string;
  file: File | null;
  onChange: (file: File | null) => void;
}

function UploadInput({ label, requiredLabel, accept, file, onChange }: UploadInputProps) {
  return (
    <label className="block rounded-lg border border-dashed border-slate-500/40 bg-slate-950/45 p-4 text-sm text-slate-300 transition hover:border-cyan-200/35">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium">{label}</span>
        <span className="rounded-full border border-white/10 px-2 py-0.5 text-xs text-slate-400">{requiredLabel}</span>
      </div>
      <input
        className="mt-3 block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-cyan-300/10 file:px-3 file:py-2 file:text-cyan-100"
        type="file"
        accept={accept}
        onChange={(event) => onChange(event.currentTarget.files?.[0] ?? null)}
      />
      {file ? <div className="mt-2 text-xs text-cyan-100">{file.name}</div> : null}
    </label>
  );
}

