---
id: PATTERN-014
name: cold_shot_dispatch
version: 1
status: active
discovered: 2026-05-09
discovered_reason: |
  Extracted from tenant practice: difficult questions sometimes need a
  one-shot, cross-family review that starts from a clean prompt rather than
  another continuation of the same working context.
triggers:
  lexical: [
    "treat as the book", "Erdős-style", "Erdős style", "alien-math",
    "alien math tradition", "no prior context", "de-anchor", "de_anchor",
    "ignore the literature", "fresh attempt"
  ]
  structural:
    - load_bearing_eigenquestion_with_anchored_failure_modes
    - same_family_agent_dispatches_have_converged_on_a_dead_route
    - need_to_break_anchoring_on_canonical_literature
    - cross_vocabulary_audit_flagged_anchoring_risk
  problem_classes:
    - hard_mathematical_residual
    - vocabulary_drift_risk
    - pre_category_emergence
    - load_bearing_falsifiable_proposition
spawn:
  mode: cold_shot
  variants:
    - mode: kernel_library
      description: |
        Existing tenant primitive. Used during an iterative research loop
        pre-run advisory phase. Multi-family cold-shot policy is selected per
        substrate class by the tenant overlay.
      module: tenant_overlay.cold_shot_adapter
      project_examples:
        - tenants/<name>/projects/*/workspace/cold_shot_policy.json
    - mode: rd_direct_external_prover
      description: |
        Research-Director-direct cross-family LLM cold-shot via external
        model providers. Used when (a) no iterative research loop is active
        on the substrate, or (b) the load-bearing question is at the
        meta-architecture layer (e.g. "is this Lean encoding faithful?").
        Cost caps and provider policy are deployment choices.
      tools: [bash]
      scripts:
        - tenant_overlay/scripts/<cold-shot-dispatcher>.py
      kill_criteria:
        - provider_cost_cap_exceeded
        - prompt_missing_failure_modes
output_schema: cold_shot_response_v1
fallback: PATTERN-011  # if cold-shot reveals the question needs N parallel attacks, escalate to swarm
preconditions:
  - eigenquestion_shape_validated: yes  # see PATTERN-015
  - anchored_failure_modes_explicit: yes  # the cold-shot prompt MUST list "do not anchor on [X / Y / Z]"
chain_position: pre_iter | post_demolition  # before main iter, OR after a route is demolished and we need a fresh attempt
related_patterns:
  - id: PATTERN-005
    relation: child  # falsifiable_asymmetry, cold-shot prompts demand a falsifiable verdict
  - id: PATTERN-009
    relation: sibling  # both are cross-validation; PATTERN-009 is CAS, PATTERN-014 is LLM
  - id: PATTERN-011
    relation: parent  # swarm_dispatch is N-parallel; cold-shot is 1-shot deep
  - id: PATTERN-015
    relation: required  # cold-shot is only as good as its eigenquestion phrasing
references:
  - existing tenant primitive: tenant_overlay.cold_shot_adapter
  - cold-shot policy schema: tenants/<name>/projects/*/workspace/cold_shot_policy.json
  - ANTI-PATTERN-006 (cross_agent_monoculture), cold-shot is the cross-family answer
---

# PATTERN-014, Cold-Shot Dispatch

## What this pattern is

A **single-dispatch, cross-family, no-prior-context, de-anchored, alien-
math-discipline** prompt to an LLM, used
to attack a load-bearing eigenquestion when same-family agents have
converged on a dead route or the question lives at the meta-architecture
layer that same-family agent swarms cannot reach without bias.

Distinct from:
* **PATTERN-009 (independent_cas_verification)**: SymPy/numpy CAS check,
  not an LLM dispatch.
* **PATTERN-011 (swarm_dispatch)**: N parallel workers (agent-based or
  PY-LLM-based). Cold-shot is **1 deep dispatch**, not N parallel.
* **PATTERN-002 (darwin_idea_killer)**: same-family adversarial attack.
  Cold-shot is **cross-family** with explicit de-anchoring.

## The 5-bullet cold-shot discipline

Every cold-shot prompt MUST contain (verbatim or close paraphrase):

1. **No prior context**: "You are receiving this with no prior
   conversation context."
2. **The book framing**: "Treat the data as a problem from 'the book',
   attack it on its merits, not on the canonical framings the
   literature has already tried."
3. **Explicit de-anchoring**: "Do not anchor on [LIST: papers/ techniques
   the failing route used] even though those are cited below."
4. **Drop non-load-bearing frames**: "If a frame is not load-bearing for
   the problem, drop it."
5. **Alien-math tradition swap**: "Alien-math discipline: assume you are
   a mathematician from a different tradition than [the tradition that
   produced the failing route], what would such a tradition reach for
   first?"

Plus the standard problem-statement structure:
* THE PROBLEM (eigenquestion in ≤200 words).
* EMPIRICAL DATA / WHAT IS KNOWN (≤500 words, including counterexamples
  that ruled out earlier routes).
* WHAT'S BEEN TRIED AND REFUTED (named with arXiv ids + verdicts).
* FALSIFIABLE OUTPUT FORMAT (per PATTERN-005): demand a verdict line
  ending in "[yes / no / partially / unknown, one-sentence rationale]".

Without these bullets, the dispatch is a generic LLM call and reverts
to single-family bias.

## When to deploy

* **Pre-run advisory** (kernel mode): before launching an iterative run on
  a new substrate, fire the cold-shot family policy to seed the iter
  with diverse non-self-derived starting points.
* **Post-demolition** (RD-direct mode): after a same-family agent swarm
  has converged on a route that an external cross-vocabulary audit or
  external prover demolished, re-attack with cold-shot from a different
  tradition. Tonight's two operator-relayed GPT-5.5 dispatches (Q1 on
  BKGSW+NC, Q2 on Lerner-port faithfulness) are canonical examples.
* **Load-bearing meta-architecture question**: when the question is
  about how the apparatus is itself thinking ("is this Lean encoding
  faithful to the published theorem"), same-family agents have bias.
  Cold-shot is the cross-family answer.

## When NOT to deploy

* When the question is tractable for an internal swarm and same-family
  bias is a feature (e.g. closing a Lean sorry on a proof the dispatcher
  is already in the middle of). PATTERN-001 (friction_debate) or
  PATTERN-011 (swarm_dispatch) is cheaper and adequate.
* When the eigenquestion has not yet been validated under PATTERN-015
  (eigenquestion_phrasing_discipline), a poorly-phrased cold-shot
  wastes paid cross-family capacity.

## Cost discipline

* A tenant dispatcher can enforce a session cap.
* Per-dispatch cap default $5; override via `--max-cost-usd`.
* Every dispatch should log a row to an external-prover ledger and a
  pattern-deployment ledger tagged PATTERN-014.

## Falsifiable-asymmetry test (per PATTERN-005)

Cold-shot is "working" iff: there exists at least one cold-shot dispatch
in the campaign window whose verdict (a) contradicted a same-family
verdict the RD had previously relied on, or (b) named a structural
defect the RD missed. Tonight's C-58 + C-59 are two such instances
(operator-relayed cold-shots). The pattern is **falsified** if cold-
shots only ever confirm existing internal verdicts, that would mean
the cross-family-lift hypothesis is empirically wrong.

## Theory-building vs falsification mode (added 2026-05-09 ~19:30 UTC; sharpened by Codex swarm 2026-05-09)

Empirical finding: the apparatus has been deploying cold-shots in
~80% FALSIFICATION mode ("is X faithful?", "is Y over-strengthened?",
"what's our Lord Kelvin?") and ~20% THEORY-BUILDING mode. Operator
catch verbatim 2026-05-09 ~19:25 UTC: "instead of falsifying attempt
theory building and problem solving in the cold shot with the 1800s
framing... we need to select the right problemsolving/theory building
questions for cold shots, not only falsification attempts. though
falsification is the hallmark of darwin and our apparatus, i know that."

Cold-shots have TWO orthogonal modes:

* **FALSIFICATION mode**: dispatch asks GPT-5 to AUDIT/CRITIQUE/TEST
  an existing claim, approach, or artifact. Output is a verdict
  (yes/no/partial), counterexample, or named obstruction. Pattern:
  PATTERN-005 falsifiable_asymmetry deployed. Examples tonight:
  PL-070 Lerner port faithfulness, PL-082 plancherel axiom verification,
  PL-088 axioms #1/#3 over-strengthening, PL-090 Clay timeline, PL-091
  X post expert critique, PL-093 Lord Kelvin diagnosis, PL-098
  Caccioppoli charter target validity.

* **THEORY-BUILDING mode**: dispatch asks GPT-5 to PRODUCE a
  construction, candidate definition, missing abstraction, or new
  lemma. Output is mathematical content, not a verdict. Pattern:
  Gowers methodology, give the model a relatively-new framework
  and ask DIRECTLY for the proof/construction. Examples tonight:
  PL-094 NS-arc projection (produced 6-week pivot plan), PL-099
  μ[u] candidate construction (in flight as of writing).

The 1880s/2080s benchmark framing is a THEORY-BUILDING tool, not a
falsification one. Riemann pre-Selberg had rich pattern recognition;
the BENCHMARK (Selberg trace formula 90 years later) tells us the
missing piece was a STRUCTURAL OBJECT linking zeta to spectral
theory. Projecting forward: the NS Clay missing piece is candidate
defect-calculus per C-93. Cold-shot should ASK FOR THE CONSTRUCTION,
not audit whether existing approaches are faithful.

### Submode: retrospective_failure_benchmark

This is the reusable form of the operator's "1880s / what will look
obvious in 50-100 years?" instruction. It remains inside PATTERN-014
rather than receiving a new pattern id as of 2026-05-09, because the
catalog already covers it as a theory-building cold-shot submode and
the independent catalog explorer recommended extension over minting.

Required output shape:

1. Name the historical failure class (e.g. wrong carrier, wrong
   topology, missing invariant, missing compactness principle).
2. Map it to a present artifact: file, theorem, prediction row, catch,
   or cold-shot packet.
3. Produce or repair the theorem/construction first.
4. Only then fill verification forks, three-leg checks, or retrospective
   verdicts.
5. State the exact next artifact to change.

Anti-capture rule: if the prompt's first requested deliverable is only
an audit/fork/verdict, rewrite before dispatch. PL-111 was superseded
for this reason; PL-112 was proof-attempt-first and produced the L3A
concentration-carrier repair.

Gowers protocol connection: the 2026-05-08 Gowers report is relevant
not because it is an authority, but because its workflow asks for
construction/proof writeup first, then human checking and preferably
formalization. Use forks and checks as guardrails around proof work,
not substitutes for proof work.

Mix going forward: roughly 50% falsification + 50% theory-building.
Theory-building for genuinely Clay-relevant constructions (where
the missing-abstraction projection points). Falsification for any
apparatus-shipped artifact before downstream commitment.

## Reasoning-effort preference (added 2026-05-09 per operator directive ~16:35 UTC)

Empirical finding from tonight's batch: `reasoning-effort=high` is the
right default for Tier-1 cold-shot dispatches. Specifically for:

* Strategic eigenquestions (substrate-target pair selection,
  Clay-timeline tests, methodology audits).
* Multi-step proof-rigor verifications (e.g. Bochner-Fejér limit
  passages, Plancherel identities).
* Cross-vocabulary translation audits.

`reasoning-effort=medium` is acceptable for:
* Tactical refactor-execution (e.g. axiom rewrites, citation
  updates).
* Verification of already-known classical identities.
* Quick pivot-residual scoping where speed matters more than depth.

The cost differential (medium vs high) is typically $0.20-0.50 per
dispatch, small relative to the strategic value of high-quality
Tier-1 verdicts. Default to high for genuinely Tier-1 work; only
drop to medium for tactical verification.

A tenant dispatcher should default to `high` effort for Tier-1 work;
explicit lower-effort overrides should be reserved for tactical-only
dispatches.

## Citation-verification rule (added 2026-05-09 per catch C-70)

**Mandatory abstract-first-sentence-quote requirement.** Empirical 2026-05-09:
single GPT-5 cold-shot dispatch returned 3 of 3 PHANTOM arXiv identifiers
(IDs resolved to statistics / judo / info-science papers, not the cited NS
results). The conceptual content was roughly correct (backward DSS Liouville
IS open; Seregin DOES work on stationary Liouville) but the IDENTIFIER LAYER
is hallucinated.

Calibration: GPT-5 cold-shot arXiv-ID hallucination prior is empirically
~0.50, not the ~0.05 the RD initially estimated.

**Every cold-shot prompt that asks for citations MUST require:**

> For each arXiv ID you cite, quote the ABSTRACT'S FIRST SENTENCE
> alongside the ID. This is a verification anchor; it lets a downstream
> internal verification agent cross-check the ID without fetching the
> paper.

**Mandatory post-dispatch step**: PATTERN-009 (independent_cas_verification,
same-family-with-web-retrieval variant) is REQUIRED on any cold-shot output
containing arXiv IDs BEFORE the IDs propagate to any downstream artifact
(catch ledger, paper draft, X post, journey doc, task description).

**Failure-mode note**: cold-shot output can be useful while still being
unreliable at the identifier layer: author names, theorem labels, arXiv IDs,
journal volumes, and page numbers may be fabricated or stale. The verification
protocol exists to keep that error from propagating.

## Cold-shot-before-encoding rule

When an external prover (cold-shot or operator-relay) proposes a
**next-campaign target** (a new theorem statement, a new analytic
framework, a new replacement route after a previous demolition), the
target MUST itself be cold-shot tested via PATTERN-014 BEFORE any
internal Lean encoding consumes agent-hours.

**Mitigation**: every next-campaign-target proposition gets an inexpensive
de-anchored review before implementation starts. This is a routing check, not
a proof of correctness.

## Anti-laundering catches

* **ANTI-PATTERN-006 (cross_agent_monoculture)**: cold-shot's whole
  point is to defeat single-family laundering. If the "cold-shot"
  is actually a same-family agent dispatched without the 5-bullet
  discipline, the pattern is misapplied.
* **Pattern laundering**: do not relabel a normal same-context review as a
  cold-shot. The value comes from context separation and explicit failure
  modes.
