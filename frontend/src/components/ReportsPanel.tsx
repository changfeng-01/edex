import { FileText } from "lucide-react";

import type { ReportPreview } from "../types";

interface ReportsPanelProps {
  reports: ReportPreview[];
}

export function ReportsPanel({ reports }: ReportsPanelProps) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.04] p-5" aria-label="报告交付">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-cyan-200">
            <FileText size={17} />
            报告 / 交付
          </div>
          <h2 className="mt-2 text-2xl font-bold text-slate-50">评审材料与项目演示包</h2>
        </div>
        <p className="max-w-xl text-sm leading-6 text-slate-400">
          这些报告是从 product-demo 输出包复制过来的静态交付材料。
        </p>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        {reports.map((report) => (
          <article key={report.file} className="rounded-lg border border-white/10 bg-slate-950/55 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-50">{report.title}</h3>
                <a className="mt-1 block break-all font-mono text-xs text-cyan-200 hover:text-cyan-100" href={report.url} target="_blank" rel="noreferrer">
                  {report.url}
                </a>
              </div>
              <FileText className="shrink-0 text-cyan-200" size={20} />
            </div>
            {report.content ? (
              <div className="mt-4 max-h-48 overflow-hidden rounded-lg border border-white/10 bg-black/20 p-3 text-sm leading-6 text-slate-300">
                <pre className="m-0 whitespace-pre-wrap font-sans">{trimMarkdown(report.content)}</pre>
              </div>
            ) : (
              <div className="mt-4 rounded-lg border border-dashed border-slate-500/40 bg-slate-900/60 p-3 text-sm text-slate-400">
                Markdown 预览不可用。请确认报告已复制到 public demo data 对应目录。
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function trimMarkdown(content: string): string {
  const lines = content.trim().split(/\r?\n/).slice(0, 12);
  return lines.join("\n");
}
