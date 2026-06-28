# PIA-CA-LLSO Paper and Defense Package Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert Phase 3 experimental validation outputs into a defensible paper package, presentation deck, speaking notes, Q&A bank, and evidence appendix without overstating simulation-only results.

**Architecture:** Treat Phase 3 validation artifacts as the data backbone. Build a manuscript-style technical report, figure/table package, defense slide deck, speaker notes, and reviewer/examiner response materials from the same source artifacts so claims, numbers, figures, and evidence boundaries remain consistent.

**Tech Stack:** Markdown, CSV/JSON validation outputs, Python/pandas for figure/table extraction, existing `goa_eval.pia_ca_llso` reports, optional PPTX/PDF generation, no new algorithmic dependencies.

---

## Required Starting State

This phase should start only after Phase 3 has produced at least:

- `validation_runs.csv`
- `validation_summary.csv`
- `pairwise_win_rates.csv`
- `validation_summary.json`
- `experimental_validation_report.md`
- boundary audit outputs
- scenario-level run artifacts

If Phase 3 is not complete, do not fabricate numbers. Use placeholders:

```text
TODO_AFTER_PHASE3_VALIDATION
```

Preserve these exact labels in every report, slide, appendix, and generated table:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

Allowed claim:

```text
Under the configured simulation-only benchmark protocol, PIA-CA-LLSO improved
budget-to-target and/or best simulated score relative to tested baselines.
```

Forbidden claims:

- physical validation
- silicon validation
- lab validation
- tapeout validation
- measured hardware improvement
- guaranteed circuit improvement without resimulation

---

## Deliverables

Create a complete artifact package under:

```text
docs/pia_ca_llso_paper_package/
```

Required outputs:

- `paper_outline.md`
- `manuscript_draft.md`
- `defense_slide_plan.md`
- `defense_speaker_notes.md`
- `defense_qa_bank.md`
- `figure_manifest.md`
- `table_manifest.md`
- `evidence_appendix.md`
- `claim_boundary_checklist.md`
- `README.md`

Optional generated presentation output:

- `slides/pia_ca_llso_defense.pptx`
- `slides/pia_ca_llso_defense.pdf`

---

## Narrative Positioning

The paper/defense should frame the contribution as:

```text
PIA-CA-LLSO is a simulation-only, evidence-gated, closed-loop optimization
framework for expensive GOA circuit optimization. It combines level-based
learning, classifier-assisted ranking, adaptive CAPM physics distance,
constraint-ledger repair, simulation-window scheduling, and strict
result-import auditing.
```

Core novelty claims:

1. **Physics-aware candidate selection**
   CAPM features and barrier terms prevent pure black-box ranking from ignoring GOA constraints.

2. **Classifier-assisted level learning**
   Level prediction and hard-pass probability guide simulation budget toward likely L1 candidates.

3. **Constraint-ledger repair**
   Violated constraints are converted into bounded next-run repair candidates instead of being discarded.

4. **Closed-loop simulation evidence**
   `pia-evolve` turns one-step suggestions into a resumable generate-select-simulate-import loop.

5. **Evidence boundary discipline**
   Every artifact distinguishes suggestions from imported simulation evidence and preserves `simulation_only`.

Do not claim that this is a complete silicon-proven optimizer.

---

## Task 1: Evidence Inventory and Source Lock

**Files:**

- Create: `docs/pia_ca_llso_paper_package/evidence_inventory.md`
- Create: `docs/pia_ca_llso_paper_package/source_lock.json`
- Test: manual review

**Step 1: Collect Phase 3 artifacts**

Record absolute or repo-relative paths for:

- protocol file
- validation output directory
- scenario manifests
- summary CSV files
- boundary audit files
- generated figures
- generated tables

**Step 2: Create evidence inventory**

`evidence_inventory.md` must include:

- artifact path
- artifact type
- evidence role
- whether it is simulation-only
- whether it is local fixture, imported simulator result, or paper-derived weak label
- what claims it can support
- what claims it cannot support

**Step 3: Create source lock**

`source_lock.json` should include:

```json
{
  "phase3_commit": "TODO_AFTER_PHASE3_VALIDATION",
  "validation_output_dir": "TODO_AFTER_PHASE3_VALIDATION",
  "protocol": "TODO_AFTER_PHASE3_VALIDATION",
  "generated_at": "TODO",
  "data_source": "real_simulation_csv",
  "engineering_validity": "simulation_only"
}
```

**Step 4: Review**

Check that no paper-derived weak labels are listed as real simulation evidence.

**Step 5: Commit**

```bash
git add docs/pia_ca_llso_paper_package/evidence_inventory.md docs/pia_ca_llso_paper_package/source_lock.json
git commit -m "docs: lock PIA validation evidence sources"
```

---

## Task 2: Figure and Table Manifest

**Files:**

- Create: `docs/pia_ca_llso_paper_package/figure_manifest.md`
- Create: `docs/pia_ca_llso_paper_package/table_manifest.md`
- Optional create: `scripts/build_pia_paper_figures.py`

**Step 1: Define figures**

Minimum figure set:

1. **Figure 1: Algorithm Architecture**
   Shows history -> LLSO offspring -> PIA selector -> simulation batch -> result import -> next generation.

2. **Figure 2: Evidence Boundary Flow**
   Shows suggestion rows vs imported simulation evidence, including `must_resimulate`.

3. **Figure 3: Convergence Curves**
   Best score vs simulation budget, grouped by method.

4. **Figure 4: Ablation Impact**
   Full loop vs no classifier/no adaptive CAPM/no repair/no offspring/no scheduler.

5. **Figure 5: Constraint Behavior**
   Hard-pass rate and mean constraint violation across generations.

6. **Figure 6: Scenario Robustness**
   Per-scenario target hit rate and simulations-to-target.

**Step 2: Define tables**

Minimum table set:

1. **Table 1: Method Comparison**
   Maps PIA-CA-LLSO components against the three reference paper directions.

2. **Table 2: Experimental Protocol**
   Scenarios, seeds, budgets, target score, metrics.

3. **Table 3: Main Results**
   Best score, hit rate, simulations-to-target, convergence AUC.

4. **Table 4: Ablation Results**
   Contribution of classifier, CAPM, repair, LLSO, scheduler.

5. **Table 5: Limitations and Evidence Scope**
   What is validated, what remains unvalidated.

**Step 3: Add source mapping**

Every figure/table entry must include:

- source CSV/JSON
- script or command used to generate it
- supported claim
- evidence boundary

**Step 4: Commit**

```bash
git add docs/pia_ca_llso_paper_package/figure_manifest.md docs/pia_ca_llso_paper_package/table_manifest.md scripts/build_pia_paper_figures.py
git commit -m "docs: define PIA paper figures and tables"
```

---

## Task 3: Manuscript Outline

**Files:**

- Create: `docs/pia_ca_llso_paper_package/paper_outline.md`

**Step 1: Create IMRAD outline**

Sections:

1. Title
2. Abstract
3. Introduction
4. Related Work
5. Method
6. Experimental Protocol
7. Results
8. Discussion
9. Limitations
10. Conclusion
11. Appendix

**Step 2: Define section messages**

Use this section logic:

- **Introduction:** Expensive GOA optimization needs fewer simulation calls and stronger evidence discipline.
- **Related Work:** Position against classifier-assisted expensive optimization, adaptive constraint evaluation, and distributed/data-driven constrained optimization.
- **Method:** Describe PIA-CA-LLSO components and closed-loop workflow.
- **Experiments:** Explain fixed budgets, seeds, scenarios, baselines, ablations, and metrics.
- **Results:** Report Phase 3 outcomes only.
- **Discussion:** Explain why modules help or fail.
- **Limitations:** Simulation-only evidence, scenario count, local fixture limitations, no silicon validation.

**Step 3: Add citation placeholders**

Use placeholders if citations are not verified in this phase:

```text
[REF: classifier-assisted LLSO paper]
[REF: adaptive constraint evaluation surrogate EA]
[REF: distributed data-driven multi-constraint EA]
```

Do not invent DOI, venue, or numerical claims.

**Step 4: Commit**

```bash
git add docs/pia_ca_llso_paper_package/paper_outline.md
git commit -m "docs: outline PIA manuscript narrative"
```

---

## Task 4: Manuscript Draft

**Files:**

- Create: `docs/pia_ca_llso_paper_package/manuscript_draft.md`

**Step 1: Draft in full paragraphs**

Use full prose for paper sections. Bullet points are allowed only in planning notes, tables, or appendices.

**Step 2: Abstract**

Write one paragraph covering:

- problem
- method
- validation protocol
- key results from Phase 3
- simulation-only boundary

If Phase 3 values are missing, write:

```text
TODO_AFTER_PHASE3_VALIDATION
```

**Step 3: Methods**

Describe:

- level labeling
- LLSO offspring generation
- classifier-level hybrid ranking
- adaptive CAPM
- constraint-ledger repair
- simulation-window scheduling
- resume/import/audit loop

**Step 4: Results**

Only report numbers from Phase 3 artifacts. Use exact source paths in comments or footnotes.

**Step 5: Discussion and limitations**

Explicitly include:

```text
These results are simulation-only evidence and do not constitute physical,
silicon, lab, tapeout, or hardware validation.
```

**Step 6: Commit**

```bash
git add docs/pia_ca_llso_paper_package/manuscript_draft.md
git commit -m "docs: draft PIA validation manuscript"
```

---

## Task 5: Defense Slide Plan

**Files:**

- Create: `docs/pia_ca_llso_paper_package/defense_slide_plan.md`

**Step 1: Choose talk length**

Default: 15-minute defense/report talk with 16 core slides plus backup.

**Step 2: Core slide sequence**

1. Title: PIA-CA-LLSO simulation-only closed-loop optimizer
2. Problem: expensive GOA optimization and simulation budget
3. Gap: one-step suggestion is not enough
4. Prior work map: classifier-assisted, adaptive constraint, distributed constrained optimization
5. Contribution overview
6. System architecture
7. CAPM physics manifold and barrier features
8. Classifier-level hybrid ranking
9. Constraint-ledger repair
10. Closed-loop `pia-evolve`
11. Experimental protocol
12. Main benchmark results
13. Ablation results
14. Failure cases and limitations
15. Evidence boundary and engineering validity
16. Conclusion and next steps

**Step 3: Backup slide sequence**

Backup slides:

- detailed formula slide
- config and parameter columns
- result schema validation
- boundary audit
- per-scenario curves
- Q&A on why not physical validation
- Q&A on why this differs from the three papers

**Step 4: Visual rule**

Every slide needs one strong visual:

- architecture diagram
- convergence curve
- ablation bar chart
- flow diagram
- comparison matrix
- evidence boundary schematic

Avoid text-heavy slides.

**Step 5: Commit**

```bash
git add docs/pia_ca_llso_paper_package/defense_slide_plan.md
git commit -m "docs: plan PIA defense slide deck"
```

---

## Task 6: Speaker Notes

**Files:**

- Create: `docs/pia_ca_llso_paper_package/defense_speaker_notes.md`

**Step 1: Write timing plan**

For a 15-minute talk:

- 0:00-1:00 problem
- 1:00-3:00 related work and gap
- 3:00-7:00 method
- 7:00-11:30 results
- 11:30-13:30 limitations
- 13:30-15:00 conclusion

**Step 2: Write per-slide notes**

Each slide should include:

- speaking goal
- 2-4 sentences to say
- transition to next slide
- likely question

**Step 3: Add short and long variants**

Create:

- 5-minute compressed version
- 15-minute standard version
- 30-minute detailed version

**Step 4: Commit**

```bash
git add docs/pia_ca_llso_paper_package/defense_speaker_notes.md
git commit -m "docs: add PIA defense speaker notes"
```

---

## Task 7: Defense Q&A Bank

**Files:**

- Create: `docs/pia_ca_llso_paper_package/defense_qa_bank.md`

**Step 1: Add technical questions**

Include answers for:

- Why is this still LLSO?
- What does CAPM add beyond raw distance?
- Why use classifier predictions?
- How do you prevent leakage from result columns?
- How do you handle constraint conflicts?
- What happens when no L1 samples exist?
- Why is local fixture not real evidence?

**Step 2: Add experimental questions**

Include:

- Why these baselines?
- Why these budgets?
- How many seeds are enough?
- What if one scenario dominates results?
- How do you compare under equal simulation budgets?
- What are the failure cases?

**Step 3: Add claim-boundary questions**

Include:

- Is this silicon validated?
- Can it be used directly for tapeout?
- What does `engineering_validity = simulation_only` mean?
- Why must candidates be resimulated?

**Step 4: Add answer style**

Answers should be short, direct, and conservative. Do not overclaim.

**Step 5: Commit**

```bash
git add docs/pia_ca_llso_paper_package/defense_qa_bank.md
git commit -m "docs: add PIA defense Q&A bank"
```

---

## Task 8: Evidence Appendix

**Files:**

- Create: `docs/pia_ca_llso_paper_package/evidence_appendix.md`
- Create: `docs/pia_ca_llso_paper_package/claim_boundary_checklist.md`

**Step 1: Evidence appendix**

Include:

- full experiment protocol
- scenario list
- seed list
- budget list
- baseline definitions
- ablation definitions
- metric definitions
- artifact paths
- source commit

**Step 2: Claim checklist**

Checklist:

- Every result has source artifact path.
- Every figure has source CSV/JSON.
- Every table has source CSV/JSON.
- All reports include `engineering_validity = simulation_only`.
- No claim says physical/silicon/lab/tapeout/hardware validation.
- Paper-derived weak labels are not treated as real simulation results.

**Step 3: Commit**

```bash
git add docs/pia_ca_llso_paper_package/evidence_appendix.md docs/pia_ca_llso_paper_package/claim_boundary_checklist.md
git commit -m "docs: add PIA evidence appendix and claim checklist"
```

---

## Task 9: Optional Slide Deck Artifact

**Files:**

- Optional create: `docs/pia_ca_llso_paper_package/slides/`
- Optional create: `docs/pia_ca_llso_paper_package/slides/pia_ca_llso_defense.pptx`
- Optional create: `docs/pia_ca_llso_paper_package/slides/pia_ca_llso_defense.pdf`

**Step 1: Choose output format**

Recommended:

- editable PowerPoint for defense revisions;
- PDF backup for safe presentation.

**Step 2: Build visual assets**

Use existing Phase 3 figures first. Do not invent result plots.

Required visuals:

- closed-loop architecture
- evidence boundary flow
- main convergence curve
- ablation chart
- per-scenario robustness chart
- limitation matrix

**Step 3: Visual validation**

Inspect slides for:

- no overflow
- no overlap
- readable figures
- high contrast
- consistent terminology
- visible evidence boundary slide

**Step 4: Commit only if artifacts are small enough**

If binary deck files are too large, commit only source plan and generated figures, not the deck.

```bash
git add docs/pia_ca_llso_paper_package/slides
git commit -m "docs: add PIA defense slide deck"
```

---

## Task 10: Final Consistency Audit

**Files:**

- Modify as needed.

**Step 1: Search for overclaims**

Search all package files for:

```text
physical validation
silicon validation
hardware validated
tapeout validated
lab validated
proven
guaranteed
```

Allowed only when negated, e.g. "not physical validation".

**Step 2: Check boundary labels**

Every major artifact must include:

```text
engineering_validity = simulation_only
```

**Step 3: Check numerical consistency**

Every number in the manuscript and slides must trace to:

- `validation_summary.csv`
- `validation_runs.csv`
- `pairwise_win_rates.csv`
- scenario-level artifact

**Step 4: Run available tests**

```bash
python -m pytest tests -k pia -q
```

**Step 5: Commit final package**

```bash
git add docs/pia_ca_llso_paper_package
git commit -m "docs: finalize PIA paper and defense package"
```

---

## Acceptance Criteria

This phase is complete when:

- The manuscript draft has a coherent IMRAD narrative.
- Figures and tables map to Phase 3 artifacts.
- The defense slide plan covers problem, method, results, ablation, limitations, and evidence boundary.
- Speaker notes support 5-, 15-, and 30-minute versions.
- Q&A bank covers technical, experimental, and claim-boundary questions.
- Evidence appendix makes every result traceable.
- No artifact overclaims beyond simulation-only validation.
- The package can be handed to a human advisor, reviewer, or defense committee without requiring them to inspect code first.

---

## Recommended Final Folder Shape

```text
docs/pia_ca_llso_paper_package/
  README.md
  source_lock.json
  evidence_inventory.md
  paper_outline.md
  manuscript_draft.md
  figure_manifest.md
  table_manifest.md
  defense_slide_plan.md
  defense_speaker_notes.md
  defense_qa_bank.md
  evidence_appendix.md
  claim_boundary_checklist.md
  slides/
    pia_ca_llso_defense.pptx
    pia_ca_llso_defense.pdf
```

---

## README Template

`README.md` should say:

```markdown
# PIA-CA-LLSO Paper and Defense Package

This folder contains the manuscript draft, defense slide plan, speaker notes,
Q&A bank, and evidence appendix for the PIA-CA-LLSO simulation-only validation.

Evidence boundary:

- data_source = real_simulation_csv
- engineering_validity = simulation_only
- candidate suggestions must keep must_resimulate = true before simulation

The package summarizes simulation-only validation results. It does not claim
physical, silicon, lab, tapeout, or hardware validation.
```
