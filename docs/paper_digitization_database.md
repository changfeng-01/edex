# Paper Digitization Database

The paper digitization database turns manually verified GOA literature evidence into CircuitPilot-compatible simulation-only artifacts. It is not an OCR system, not an image-recognition model, and not a method for uniquely recovering W/L/C parameters from one waveform.

## Boundary

Paper figures digitized with WebPlotDigitizer or Engauge are weak labels. They must carry:

```text
source_type = paper_digitized
weak_label = true
engineering_validity = simulation_only
claim_boundary = digitized_from_published_figure_not_original_simulation
```

Values that cannot be read from paper text, tables, captions, or a user-provided digitizer CSV remain `null` or `TODO_NEEDS_MANUAL_EXTRACTION`.

## Workflow

```bash
python -m goa_eval.paper_digitization.init_paper_db

python -m goa_eval.paper_digitization.wpd_import \
  --input data/paper_digitized_raw/you2024_10t2c_scan_driver/fig9/wpd_raw.csv \
  --output data/paper_digitized/you2024_fig9_stage18_19/waveform.csv \
  --time-unit us \
  --voltage-unit V

python -m goa_eval.paper_digitization.evaluate_cases \
  --index data/paper_database/paper_waveform_index.csv \
  --output-root outputs/paper_digitized_eval

python -m goa_eval.paper_digitization.build_leaderboard \
  --cases-root data/paper_digitized \
  --eval-root outputs/paper_digitized_eval \
  --output data/paper_database/paper_goa_leaderboard.csv
```

Tables and text provide input parameters. Digitized figures provide output waveforms. The existing CircuitPilot evaluation layer extracts waveform metrics. The paper leaderboard is then usable as a weak-label input to surrogate or optimizer workflows.

## Papers

- You2024: main 10T-2C MOx scan-driver benchmark.
- Song2022: auxiliary Q-node and multistage propagation dataset.
- Zhou2025: large 31-inch GOA calibration evidence.

## Optimizer And ML Dataset Relationship

```text
paper_goa_leaderboard.csv
  -> compatible with hybrid-goa-optimize candidate generation

goa_training_samples.csv
  -> formal ML training table for surrogate, classifier, active-learning, repair, and multi-objective models
```

The ML dataset is one row per case, not one row per paper. It combines topology, normalized device/timing/load/degradation features, waveform metrics, pass/fail labels, failure mode, evidence weight, and label confidence.

Recommended training weights:

```text
paper_digitized: low weight
own simulation: high weight
validated rerun: highest weight
```

Current data source:

```text
paper_digitized weak labels
```

Future data sources:

```text
paper_digitized weak labels
+ user_simulation_csv
+ self_generated_spice_sweep
+ active_learning_selected_reruns
```

The training goal is to reduce invalid or low-value simulation attempts. The database cannot replace final SPICE, SmartSpice, or ngspice reruns.

## Hybrid GOA Optimize

```bash
python -m goa_eval.cli hybrid-goa-optimize \
  --leaderboard data/paper_database/paper_goa_leaderboard.csv \
  --param-space config/paper_param_spaces/goa_10t2c_param_space.yaml \
  --output-root outputs/paper_hybrid_goa \
  --max-candidates 30 \
  --seed 42
```

Candidates produced from paper-derived data remain next-run simulation suggestions.
