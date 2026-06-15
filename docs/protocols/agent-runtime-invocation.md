# Agent Runtime Invocation Policy

`agent_runtime_invocation` is the first-party subprocess boundary for
role-bearing local or subscription agent CLIs. It answers a narrow execution
question:

> When the daemon or a kernel-native demo needs a local agent runtime, which
> command, project root, permission mode, sandbox, tool flags, and environment
> are used?

It does not run a model, schedule a graph, manage native agent memory, approve
work, or record run state. Those concerns remain in the selected agent runtime,
the first-party daemon, and the existing runtime/checkpoint protocols.

## Why This Exists

The Python daemon already dispatches role-office work through configured agent
CLIs. The self-evolving organization demo now uses the same class of
role-bearing local/subscription agent for live planner proposals. Without a
shared invocation policy, daemon runs and demos can drift:

- one path may use a stale project/root flag;
- one path may accidentally use a different auth environment;
- one path may block on interactive tool approval;
- one path may use a different sandbox or permission mode;
- receipts may expose prompt text in command metadata.

The policy makes those choices explicit and testable while leaving actual
execution to the runtime.

## Boundary

| Concern | Owner |
|---|---|
| work discovery, mandate checks, task authorization | daemon/kernel |
| command construction for local/subscription CLIs | `agent_runtime_invocation` |
| model inference, native tool execution, native memory | selected agent CLI |
| run lifecycle projection | `runtime_adapters` and `run_checkpoints` |
| structural mutation approval | governance-change proposal flow |
| mutation proof | governed mutation proof row |

This is intentionally smaller than a runtime adapter. Runtime adapters import
lifecycle events into cognitive-firm. Invocation policy prepares the subprocess
command that a first-party daemon or demo will launch.

## Supported Adapters

The supported worker shapes are inspectable from code:

```bash
PYTHONPATH=src python -m cognitive_firm.orchestration.agent_runtime_invocation list-adapters
PYTHONPATH=src python -m cognitive_firm.orchestration.agent_runtime_invocation list-adapters --cli-only
```

The current registry is:

| Adapter | Worker shape | Runtime | Prompt transport | Boundary |
|---|---|---|---|---|
| `claude_print` | subscription/local CLI | Claude Code | argv by default | Uses local Claude login/token state; kernel builds command and records receipt. |
| `codex_exec` | subscription/local CLI | Codex | stdin by default | Uses local Codex login/token state; kernel builds command and records receipt. |
| `custom_planner_command` | local wrapper | wrapper-defined | stdin or `{prompt_file}` | Any local executable can participate if it emits the planner JSON schema. |
| `api_model_call` | API model call | provider-defined | request body | Existing `LLMRuntime` path for OpenAI, Anthropic, Gemini, DeepSeek, or OpenAI-compatible servers. |

`infer_agent_adapter(agent_cli, requested="auto")` maps a subscription/local CLI
command to one of:

- `claude_print`: Claude Code noninteractive print mode.
- `codex_exec`: Codex noninteractive exec mode.

`auto` maps a CLI basename of `codex` to `codex_exec`; everything else defaults
to `claude_print`. Wrappers can pass an explicit adapter when basename
inference is not enough.

This registry is descriptive. It does not grant authority and it does not make
API model calls equivalent to persistent local agent workers. The stronger demo
shape is a role-bearing subscription/local CLI because the worker has local
tool context, native session identity when exposed, and a concrete subprocess
receipt. API model calls remain useful for no-subscription fallback and
provider coverage.

## Claude Code

`build_agent_command(..., adapter="claude_print")` emits:

```text
claude --print --permission-mode <mode> [tool flags] <prompt>
```

Environment controls:

- `COGNITIVE_FIRM_CLAUDE_PERMISSION_MODE`
- `COGNITIVE_FIRM_CLAUDE_ALLOWED_TOOLS`
- `COGNITIVE_FIRM_CLAUDE_DISALLOWED_TOOLS`
- `COGNITIVE_FIRM_CLAUDE_ADD_DIRS`
- `COGNITIVE_FIRM_CLAUDE_EXTRA_ARGS`
- `COGNITIVE_FIRM_AGENT_PROMPT_TRANSPORT`

Claude session continuity remains daemon-owned. When the daemon supplies a
session id, the command builder adds `--session-id` for first use or `--resume`
for later ticks.

## Codex

`build_agent_command(..., adapter="codex_exec")` emits:

```text
codex exec --cd <project-root> --sandbox <mode> [profile/model/extra args] -
```

Environment controls:

- `COGNITIVE_FIRM_CODEX_SANDBOX`
- `COGNITIVE_FIRM_CODEX_PROFILE`
- `COGNITIVE_FIRM_CODEX_MODEL`
- `COGNITIVE_FIRM_CODEX_EXTRA_ARGS`
- `COGNITIVE_FIRM_CODEX_BYPASS_SANDBOX`
- `COGNITIVE_FIRM_AGENT_PROMPT_TRANSPORT`

The bypass flag is explicit because it changes the execution risk profile. It
should only be set when the surrounding operator environment is already trusted
and separately bounded.

## Prompt Transport

The default prompt transport is `auto`. The policy uses the transport supported
by each CLI:

- Claude Code receives the prompt as an argument because its print mode
  documents `[prompt]` as the noninteractive input.
- Codex receives the prompt over stdin via `codex exec ... -`.

Set `COGNITIVE_FIRM_AGENT_PROMPT_TRANSPORT=stdin` or `argv` only for wrappers
that need an explicit transport. Receipts redact prompt content from command
metadata when argv transport is used.

## Runtime Auth Environment

`agent_subprocess_env(runtime=...)` prefers subscription/local CLI auth by
default for known agent runtimes. If a provider API key is present, the CLI may
choose metered API-key auth instead of subscription/OAuth/token auth, so the
kernel scrubs known provider API-key variables unless the operator explicitly
opts in.

Provider-specific scrub:

- Claude subprocesses remove `ANTHROPIC_API_KEY`,
  `CLAUDE_CODE_USE_BEDROCK`, and `CLAUDE_CODE_USE_VERTEX`.
- Codex subprocesses remove `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and
  `OPENAI_ORG_ID`.
- Token-shaped local auth such as `ANTHROPIC_AUTH_TOKEN`, `HOME`, and the
  normal CLI config directories are preserved.
- Relative `PYTHONPATH` entries are converted to absolute paths before launch so
  role tools still import correctly after the subprocess changes working
  directory.

Set `COGNITIVE_FIRM_AGENT_ALLOW_API_KEY_AUTH=1` only when the operator
intentionally wants a spawned role-bearing CLI to use API-key auth. Set
`COGNITIVE_FIRM_AGENT_SCRUB_ALL_MODEL_API_KEYS=1` to additionally remove
cross-provider model API keys such as `GEMINI_API_KEY`,
`DEEPSEEK_API_KEY`, and `OPENAI_COMPATIBLE_API_KEY`.

Substrate-side API model calls still use `LLMRuntime`; this auth policy applies
only to spawned role-bearing agent subprocesses.

## Receipts

`build_agent_invocation_receipt()` is the canonical local evidence carrier for
spawned role-bearing agent subprocesses. It records:

- `schema_version: agent_invocation_receipt.v1`;
- runtime and adapter;
- redacted command argv;
- prompt transport and prompt digest;
- stdout/stderr digests and bounded previews;
- return code, optional timeout/error, prompt mode, and prompt-file use;
- a detected native agent session id when the CLI exposes one.

`safe_command_for_receipt()` remains the lower-level redaction helper. Planner
receipts and daemon logs should embed the invocation receipt rather than
hand-rolling command metadata. Prompt content belongs in prompt artifacts with
normal digest refs, not in command metadata or stderr previews.

The daemon also embeds the same receipt in the `agent_cli_dispatch` action
attestation metadata and adds prompt/stdout/stderr digest refs to the
attestation inputs/outputs. This lets an operator inspect one governed-run
bundle and see both role/run state and the concrete local agent invocation
evidence.

## Runtime Slot Readiness

`AgentRuntimeSlot` and `build_agent_runtime_readiness_summary()` provide a
pre-run readiness projection for bounded live demos and adapters that may spawn
several role-bearing workers. A slot names:

- the role office or offices expected to use the runtime;
- the purpose of that runtime in the bounded run;
- runtime, adapter, timeout, and whether the slot is required.

Callers still execute the tiny preflight command themselves. The summary only
normalizes the results:

```python
summary = build_agent_runtime_readiness_summary(
    slots=[
        AgentRuntimeSlot(
            slot_id="planner",
            role_id="role.org_evolver",
            purpose="propose bounded structural mutations",
            runtime="codex",
            adapter="codex_exec",
            required=True,
        ),
        AgentRuntimeSlot(
            slot_id="reviewer",
            role_id="role.evaluator,role.risk_guardian,role.learning_steward",
            purpose="emit advisory reviewer positions",
            runtime="claude",
            adapter="claude_print",
            required=False,
        ),
    ],
    preflight_results={
        "planner": planner_preflight_result,
        "reviewer": reviewer_preflight_result,
    },
)
```

The output schema is `agent_runtime_readiness_summary.v1`. It is an inspection
surface, not a scheduler, approval, or authority check. A required slot that is
missing or failed blocks a bounded live run at the operator layer. Optional
slots can be absent while the run falls back to protocol/fixture participation.

## Current Callers

- `scripts/agent_daemon.py`
- `demos/self_evolving_org/run.py` in `--agent-planner-runtime` mode
- `demos/self_evolving_org/run.py` in optional `--agent-reviewer-runtime`
  mode, where evaluator, risk guardian, and learning steward outputs become
  A2A evidence, decision positions, and `agent_cli_dispatch` attestations
- `demos/self_evolving_org/agent_preflight.py`, which can return a single
  preflight result or an `agent_runtime_readiness_summary.v1` for planner,
  reviewer, and workload-executor slots

Raw wrapper commands remain supported for the demo through
`--agent-planner-command`, but first-party Claude/Codex usage should prefer
`--agent-planner-runtime` / `AGENT_RUNTIME` so daemon and demo behavior stays
aligned.

## Failure Mode

If the selected CLI is not authenticated, the live self-evolving demo records a
rejected planner receipt and stops before mutation. This is expected: local
login is an external runtime precondition, not a kernel approval.

## Tests

- `tests/test_agent_daemon_roots.py`
- `tests/test_agent_runtime_invocation.py`
- `tests/test_self_evolving_agent_preflight.py`
- `tests/test_self_evolving_org_demo.py`
