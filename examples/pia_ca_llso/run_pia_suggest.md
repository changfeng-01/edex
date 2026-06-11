# Run PIA-CA-LLSO Suggestion Demo

```bash
python -m goa_eval.cli pia-label --history-csv examples/pia_ca_llso/sample_history.csv --config config/pia_ca_llso_goa_profile.yaml --output-dir outputs/pia_label
python -m goa_eval.cli pia-suggest --history-csv outputs/pia_label/labeled_history.csv --candidate-csv examples/pia_ca_llso/sample_candidates.csv --config config/pia_ca_llso_goa_profile.yaml --strategy pia_physics_distance --top-k 4 --output-dir outputs/pia_suggest
```

The output is a next-run simulation suggestion set. It is not physical validation.
