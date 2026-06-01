import { Images, X } from "lucide-react";
import { useState } from "react";

import type { DashboardFigure } from "../types";

interface FiguresGalleryProps {
  figures: DashboardFigure[];
}

export function FiguresGallery({ figures }: FiguresGalleryProps) {
  const [selected, setSelected] = useState<DashboardFigure | null>(null);

  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.04] p-5" aria-label="图像预览">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-cyan-200">
            <Images size={17} />
            图像预览
          </div>
          <h2 className="mt-2 text-2xl font-bold text-slate-50">product-demo 图像包</h2>
        </div>
        <p className="max-w-xl text-sm leading-6 text-slate-400">点击图像可以放大查看；缺失文件会显示本地占位提示。</p>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {figures.map((figure) => (
          <FigureCard key={figure.key} figure={figure} onOpen={() => setSelected(figure)} />
        ))}
      </div>

      {selected ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label={`${selected.title} 预览`}
          onClick={() => setSelected(null)}
        >
          <div className="max-h-[92vh] w-full max-w-6xl rounded-lg border border-white/15 bg-slate-950 p-4 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between gap-4">
              <div>
                <div className="text-lg font-semibold text-slate-50">{selected.title}</div>
                <div className="font-mono text-xs text-slate-400">{selected.file}</div>
              </div>
              <button
                type="button"
                className="rounded-full border border-white/10 bg-white/5 p-2 text-slate-200 transition hover:bg-white/10"
                onClick={() => setSelected(null)}
                aria-label="关闭预览"
              >
                <X size={18} />
              </button>
            </div>
            <img src={selected.url} alt={selected.title} className="max-h-[76vh] w-full rounded-lg bg-white object-contain" />
          </div>
        </div>
      ) : null}
    </section>
  );
}

function FigureCard({ figure, onOpen }: { figure: DashboardFigure; onOpen: () => void }) {
  const [missing, setMissing] = useState(false);

  return (
    <button
      type="button"
      className="group overflow-hidden rounded-lg border border-white/10 bg-slate-950/55 text-left transition duration-200 hover:-translate-y-0.5 hover:border-cyan-200/35 hover:bg-slate-900/70"
      onClick={missing ? undefined : onOpen}
    >
      {missing ? (
        <div className="grid aspect-[16/10] place-items-center border-b border-white/10 bg-slate-900/80 p-6 text-center text-sm text-slate-400">
          图像文件缺失：{figure.file}
        </div>
      ) : (
        <img
          src={figure.url}
          alt={figure.title}
          loading="lazy"
          className="aspect-[16/10] w-full border-b border-white/10 bg-white object-contain"
          onError={() => setMissing(true)}
        />
      )}
      <div className="p-4">
        <div className="font-semibold text-slate-100">{figure.title}</div>
        <div className="mt-1 font-mono text-xs text-slate-400">{figure.file}</div>
      </div>
    </button>
  );
}
