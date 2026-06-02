interface AnalysisProgressProps {
  status: "idle" | "running" | "completed" | "failed";
  message: string;
}

export function AnalysisProgress({ status, message }: AnalysisProgressProps) {
  const color = status === "failed" ? "border-rose-300/30 bg-rose-300/10 text-rose-100" : "border-cyan-300/20 bg-cyan-300/10 text-cyan-100";
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${color}`} role="status">
      {message || "等待上传输入文件。"}
    </div>
  );
}
