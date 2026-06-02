interface AnalysisProgressProps {
  status: "idle" | "running" | "completed" | "failed";
  message: string;
}

const steps = ["保存文件", "波形评价", "约束诊断", "候选参数", "Dashboard 打包"];

export function AnalysisProgress({ status, message }: AnalysisProgressProps) {
  const color =
    status === "failed"
      ? "border-rose-300/30 bg-rose-300/10 text-rose-100"
      : status === "completed"
        ? "border-emerald-300/30 bg-emerald-300/10 text-emerald-100"
        : "border-cyan-300/20 bg-cyan-300/10 text-cyan-100";
  const fallback =
    status === "idle"
      ? "等待上传输入文件，或直接运行内置演示。"
      : status === "completed"
        ? "分析完成，dashboard 数据包已生成。"
        : status === "failed"
          ? "分析失败，请检查后端错误信息。"
          : "正在生成 dashboard 数据包。";

  return (
    <div className={`rounded-lg border px-4 py-4 text-sm ${color}`} role="status">
      <div className="font-medium">{message || fallback}</div>
      <div className="mt-4 grid gap-2">
        {steps.map((step, index) => {
          const isActive = status === "running";
          const isDone = status === "completed";
          const tone = isDone ? "border-emerald-200/35 text-emerald-50" : isActive ? "border-cyan-200/35 text-cyan-50" : "border-white/10 text-slate-400";
          return (
            <div key={step} className={`flex items-center gap-3 rounded-md border px-3 py-2 ${tone}`}>
              <span className="grid h-6 w-6 place-items-center rounded-full border border-current/30 text-xs">{isDone ? "done" : index + 1}</span>
              <span>{step}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
