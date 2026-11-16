# Randomized intervention onset, contract 1.0

## Design fixed before implementation

One athlete transitions once from baseline to a persistent intervention. The app draws
one onset uniformly with `secrets.choice` from the explicitly saved permissible scheduled
occasions. It saves the complete support, probability, draw, timestamp, outcome, schedule
and analysis rule in the existing append-only protocol version. No imported historical
allocation or investigator-selected draw is accepted. A previously planned investigation
cannot be converted or redrawn. Later versions may correct narrative metadata but cannot
change the allocation, outcome, conditions, schedule or analysis rule.

Question: is this athlete's measured trajectory incompatible with the sharp null that
every scheduled outcome would be identical under every permissible onset? The target
scientific contrast is the within-athlete response to onset timing over this finite
schedule. The reported post-minus-pre mean is descriptive; it is not an identified
constant causal effect or population effect.

The randomization unit is the athlete's complete onset sequence (one draw); measurement
units are QC-eligible session means. Trials are averaged within a session. All permissible
starts must leave at least three scheduled baseline and three intervention sessions.
The schedule contains increasing timezone-aware timestamps and ordinal measurement keys,
all future at allocation and beyond admitted measurements and visit records. Onset occurs
immediately before its scheduled measurement. Uniform independent athlete-specific draws
may coexist in one workspace; this method does not pool them or test a staggered joint null.

Statistic: absolute post-minus-pre session mean at each permissible onset. Exact two-sided
p = number of support statistics >= observed statistic / support size, including ties
and the observed allocation. Decimal session values use rational arithmetic for tail
comparisons. Resolution and minimum possible p are 1/support size; a small support may
make p <= .05 impossible. No Monte Carlo correction or asymptotic approximation is used.

Time order is held fixed. Arbitrary fixed trends and serial dependence are allowed under
the sharp null; no residual independence assumption or trend removal is imposed. These
features can reduce sensitivity and confound descriptive magnitudes. The fixed statistic
targets an immediate level difference. Delayed/gradual effects may be missed; no lag search
or response-function model is implemented. Treatment persists through the final visit;
no reversal or washout is assumed. No anticipation, faithful allocation, stable measurement,
no interference, and no assignment-dependent co-intervention or observation process are
required and explicitly acknowledged before drawing.

Incomplete, missing, nonfinite, off-schedule or QC-excluded measurements return
NOT_ESTIMABLE without a p-value. Wrong designs, absent allocation, incompatible revisions,
condition/adherence deviations and invalid provenance return NOT_QUALIFIED. This conservative
complete-schedule implementation does not impute or assume ignorable missingness. Temporal
or treatment deviations can still be recorded, inspected and described. Failure to reject
does not establish no effect; rejection does not validate causal magnitude, a physiological
mechanism, clinical importance, another athlete, or an optimization/forecast claim.

## Scientific basis

The assignment support must match the actual design, and outcomes remain ordered:
[Tanious et al., response-function framework](https://pmc.ncbi.nlm.nih.gov/articles/PMC11133040/).
This implementation uses only the elementary fixed immediate-level statistic, not the
paper's response-function extensions. Reporting and numerical qualification do not replace
human scientific review or consent for a real intervention.

## Executable evidence

`tests/test_randomized_onset.py` independently computes a weighted assignment-mask
contrast using rational arithmetic and enumerates rejection rates over the entire null
assignment support, including a fixed trend and serial dependence. Hand-checkable eight
session step example: support {4,5,6}, observed onset 5, statistic 10, p=1/3; constant
outcomes give p=1. Irregular prespecified dates and a delayed step retain the fixed rule.

Two SQLite-persisted synthetic athletes share one workspace. Both protocols are saved
before later data admission (the test controls the random generator for reproducibility).
The positive series has a descriptive +8 cm step at assigned onset 15 and p=1/26; the
constant series at onset 24 has p=1. These are synthetic algorithm checks, not athlete
efficacy evidence. Their frozen runs survive append-only visit corrections and a narrative
protocol amendment, and reports retain the exact allocation, observations and result.

Backend/regression command through `scripts/scoped_tests.py`: randomized-onset,
experiments, phase-analysis, frozen-report test and method-catalogue tests: **36 passed
in 125.03 s**, sampled scratch peak 7,793,786 bytes, scratch removed. A subsequent focused
scientific/native regression: **19 passed in 28.38 s**, peak 6,930,411 bytes, scratch removed.
The runner limits scratch to 512 MiB and execution to 300 seconds. No installer campaign,
private dataset access, push or merge. The native workflow additions receive a separate
focused Qt validation and commit.
