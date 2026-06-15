# System Positioning

`cognitive-firm` can run governed role-office work through its first-party
daemon and can also sit around external runtimes such as LangGraph, CrewAI,
AutoGen, ADK, and Letta. Its useful surface is narrower than a general agent
platform: it records durable organizational authority and review state around
repeated work.

The positioning question is therefore not "which framework runs agents better?"
It is:

> When an agent system becomes part of an organization, where do authority,
> evidence, human work, residual risk, and approved learning live?

## Adoption Decision

Use an agent runtime directly when the problem is a single application flow:
model calls, tools, graph execution, retries, memory, traces, and evals. Those
systems are built for that.

Add cognitive-firm when the application has become organizational work:

- roles act under mandates;
- humans perform bounded work with receipts;
- external actions need provenance and review;
- unresolved risk needs an owner and recourse path;
- accepted lessons should change future behavior through reviewed records;
- a reviewer needs a compact packet for what happened in a run.

This repo is therefore not trying to replace LangChain, LangGraph, Letta,
AutoGen, CrewAI, or workflow tools. It gives those systems a durable
organization boundary when their outputs affect accountable work.

## Adjacent Systems

| Category | Examples | What they are strong at | cognitive-firm boundary |
|---|---|---|---|
| Graph and workflow runtimes | LangGraph, Google ADK, Microsoft Agent Framework | Stateful execution, graph replay, interrupts, deployment, runtime observability. | Use them to run work. Project lifecycle events into cognitive-firm through runtime adapters. |
| Multi-agent orchestration frameworks | CrewAI, AutoGen, Microsoft Agent Framework | Agent roles, crews, conversational collaboration, task routing, tool use. | Keep their orchestration semantics. Record role authority, obligations, side effects, and closure in cognitive-firm. |
| Stateful-agent and memory platforms | Letta / MemGPT | Persistent agent memory, messages, tools, memory blocks, agent context. | Let memory platforms manage agent context. cognitive-firm keeps organizational memory as files, events, receipts, and approved learning records. |
| SaaS automation, workflow, and BPM tools | n8n, Zapier, workflow builders, BPM engines | App triggers, API glue, process modeling, business-process automation, stage routing. | Use them as execution and connector surfaces. cognitive-firm governs authority, evidence, receipts, outcomes, and learning around the process; it does not become the process designer. |
| Observability and evaluation platforms | LangSmith, runtime traces, eval suites | Traces, evals, debugging, model-output inspection. | Consume summaries or links. Do not make trace systems the source of organizational authority. |
| Governance and compliance layers | Enterprise IAM, GRC, audit systems, internal policy engines | Identity, access, compliance reporting, external audit workflows. | T2 integrations may connect to them. The T1 kernel stays small and keeps tenant-specific compliance policy outside the public kernel. |

## Kernel Boundary

The kernel boundary is not model capability, prompt quality, graph execution,
or tool integrations. Those categories already have large ecosystems.

The kernel contributes a small set of organization-level invariants and a
first-party governance runtime around them:

- **Typed authority:** roles, actors, mandates, leases, and capability checks
  decide who may act before the action occurs.
- **Human work as state:** humans can perform bounded object-level work with
  deliverables and receipts, not only approve or reject an agent output.
- **Obligation lifecycle:** role-to-role work has explicit waiting, blocking,
  handoff, follow-up, and closure states.
- **Machine provenance:** runs and side effects have producer, policy, input,
  output, and digest references.
- **Accountable closure:** residual risk has a named owner, recourse path, and
  closure evidence.
- **Durable learning:** approved lessons become future behavior through
  reviewed state transitions, not chat memory.

The built-in daemon is therefore a role-office governance runtime: it discovers
work, routes it through mandates and gates, dispatches configured agent CLIs
and capability-gated tools, projects its own lifecycle into run checkpoints,
and records the resulting organization state. External runtimes can still own
graph replay, native memory, assistant UX, and deployment when an adopter wants
those capabilities.

These are valuable when the user is no longer asking "can this agent complete a
task?" but "can I let agents and humans coordinate repeatedly without losing
authority, evidence, or accountability?"

## Integration Boundary

Keep framework-native capabilities in the systems that already provide them:

- graph/node replay;
- model inference;
- prompt orchestration;
- native long-term agent memory;
- tracing and eval dashboards;
- SaaS connector catalogs;
- process modeling, BPMN-style design, and workflow-stage optimization;
- enterprise IAM administration;
- hosted multi-tenant isolation as a public-kernel default.

Build thin adapter boundaries around them.

## Public Pull-Forwards

1. **Adapter packs.** Keep `runtime_adapters` framework-neutral, then provide
   small examples for LangGraph first, followed by CrewAI, AutoGen/Microsoft
   Agent Framework, Letta, and Google ADK. Each adapter should translate native
   lifecycle events into `started`, `checkpointed`, `state_changed`, and
   `interrupted` events.
2. **Human-interrupt bridge.** The LangGraph-style interrupt example is the
   current reference path: runtime pauses, cognitive-firm creates A2H work,
   human returns a receipt, runtime resumes with its own token.
3. **Failure fixtures.** Keep `make governance-failure-benchmark` green and
   broaden it only when the new case maps to a kernel surface: authorization,
   attestation, human receipt, outcome verdict, or accountability closure.
   Runtime-adapter conformance can build on this by proving that an adapter
   cannot create a second durable ledger, import tenant policy into the kernel,
   or widen role authority.
4. **Portable attestation bundle.** The governed-run export joins run
   checkpoints, action attestations, formal verifications, human-work
   sessions, outcome links, accountability cases, linked leases, governance
   approvals, authority snapshots, and observability refs. Broaden it toward
   contract hashes, input-state hashes, verifier version, and a stricter
   interchange schema.
5. **Field pilot result.** The decisive public validation path is a
   pre-registered recurring decision pipeline showing whether governed
   execution reduces error, rework, hidden human burden, or unresolved
   accountability versus the baseline.
6. **Userland completion.** Finish the operator-facing surfaces that let a
   non-technical user run the kernel: inbox, vocabulary, enrollment, and review
   panes over the shipped userland logic.

## External Positioning

Use this sentence externally:

> `cognitive-firm` is a governance kernel for persistent human-agent
> organizations; it wraps agent runtimes with authority, human-work,
> provenance, accountability, and learning state.

Avoid this sentence:

> `cognitive-firm` is an agent framework.

That claim invites the wrong comparison and loses the actual edge.
