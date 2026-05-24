const figures = [
  { src: "/data/figures/o1_o8_overview.png", title: "Output overview" },
  { src: "/data/figures/o1_o8_stacked.png", title: "Stacked waveform" },
  { src: "/data/figures/block_stability_heatmap.png", title: "Block stability" },
  { src: "/data/figures/overlap_ratio_bar.png", title: "Overlap ratio" },
  { src: "/data/figures/ripple_trend.png", title: "Ripple trend" },
  { src: "/data/figures/delay_trend.png", title: "Delay trend" },
];

export function FigureGallery() {
  return (
    <section className="section-block" aria-label="图像输出">
      <div className="section-heading">
        <div>
          <span className="section-kicker">Generated figures</span>
          <h2>仿真图像快照</h2>
        </div>
        <span className="muted-label">from outputs/compat_check</span>
      </div>
      <div className="figure-grid">
        {figures.map((figure) => (
          <figure key={figure.src}>
            <img src={figure.src} alt={figure.title} loading="lazy" />
            <figcaption>{figure.title}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
