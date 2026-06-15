PYTHON ?= $(shell if [ -n "$$VIRTUAL_ENV" ] && [ -x "$$VIRTUAL_ENV/bin/python" ]; then printf '%s/bin/python' "$$VIRTUAL_ENV"; elif [ -x ./venv/bin/python ]; then printf './venv/bin/python'; elif [ -x ./.venv/bin/python ]; then printf './.venv/bin/python'; else printf 'python3'; fi)
NPM ?= npm
CF_PYTHONPATH ?= src
ORBIT_SMOKE_OUTDIR ?= /private/tmp/cognitive-firm-orbit-smoke-dist
AUDIT_SOURCE ?= cognitive_firm_workspace/transitions.jsonl
AUDIT_MANIFEST ?= org/audit/transitions.manifest.json
AUDIT_SIGNING_KEY ?=
SELF_EVOLVING_DEMO_WORKDIR ?= .cognitive-firm-runs/self-evolving-org-$(shell date +%Y%m%d-%H%M%S)
SELF_EVOLVING_COMPARISON_WORKDIR ?= .cognitive-firm-runs/self-evolving-feedback-comparison-$(shell date +%Y%m%d-%H%M%S)
SELF_EVOLVING_COMPARISON_SERVE_WORKDIR ?= $(SELF_EVOLVING_COMPARISON_WORKDIR)
SELF_EVOLVING_DEMO_REALTIME_WORKDIR ?= .cognitive-firm-runs/self-evolving-org-realtime
SELF_EVOLVING_DAEMON_WORKDIR ?= .cognitive-firm-runs/self-evolving-daemon-$(shell date +%Y%m%d-%H%M%S)
SELF_EVOLVING_DAEMON_TIMEOUT ?= 300
SELF_EVOLVING_RUNTIME ?= fixture
SELF_EVOLVING_FEEDBACK ?= score_totals
SELF_EVOLVING_EFFECTIVE_WORKLOAD_FEEDBACK = $(if $(filter compare,$(SELF_EVOLVING_FEEDBACK)),$(error SELF_EVOLVING_FEEDBACK=compare is only supported by `make self-evolving-org`; use `make self-evolving-org-compare` for the explicit comparison target),$(SELF_EVOLVING_FEEDBACK))
SELF_EVOLVING_DEMO_ITERATIONS ?= 3
SELF_EVOLVING_DEMO_BUDGET_UNITS ?=
SELF_EVOLVING_DEMO_STOP_FILE ?=
SELF_EVOLVING_DEMO_RUN_UNTIL_STOPPED ?=
SELF_EVOLVING_DEMO_PORT ?= 8765
SELF_EVOLVING_SERVE ?= 0
SELF_EVOLVING_PLANNER_PROMPT_MODE ?= full
SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS ?= 600
SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME ?=
SELF_EVOLVING_WORKLOAD_EXECUTOR_ADAPTER ?= $(AGENT_ADAPTER)
SELF_EVOLVING_WORKLOAD_EXECUTOR_LIMIT ?= 0
SELF_EVOLVING_LIVE_WORKLOAD_LIMIT ?= 3
SELF_EVOLVING_CODEX_WORKLOAD_LIMIT ?= $(SELF_EVOLVING_LIVE_WORKLOAD_LIMIT)
SELF_EVOLVING_WORKLOAD_EXECUTOR_TIMEOUT_SECONDS ?= 180
MODEL_ID ?=
AGENT_RUNTIME ?= $(COGNITIVE_FIRM_SUBSCRIPTION_RUNTIME)
AGENT_CLI ?= $(if $(AGENT_RUNTIME),$(AGENT_RUNTIME),$(COGNITIVE_FIRM_AGENT_CLI))
AGENT_ADAPTER ?= $(if $(COGNITIVE_FIRM_AGENT_ADAPTER),$(COGNITIVE_FIRM_AGENT_ADAPTER),auto)
AGENT_REVIEWER_RUNTIME ?=
AGENT_REVIEWER_ADAPTER ?= $(AGENT_ADAPTER)
SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS ?=
SELF_EVOLVING_AGENT_RUNTIME := $(if $(filter command line,$(origin AGENT_CLI)),$(AGENT_CLI),$(if $(AGENT_RUNTIME),$(AGENT_RUNTIME),$(AGENT_CLI)))
SELF_EVOLVING_PLANNER_JSON ?= workspace/daemon_planner_steps.json

.PHONY: help test org-surface first-gated-action agent-fleet-audit-demo runtime-adapter-smoke native-e2e-demo native-e2e-demo-full-smoke governance-failure-benchmark decision-log-replay-demo field-pilot-action-impact-compile-help field-pilot-action-impact-demo formal-provider-bundle-demo langgraph-governance-demo self-evolving-org self-evolving-org-demo self-evolving-org-view self-evolving-feedback-comparison self-evolving-org-compare self-evolving-org-compare-serve self-evolving-org-serve self-evolving-org-realtime-view self-evolving-org-realtime-serve self-evolving-daemon-smoke self-evolving-daemon-governed-smoke self-evolving-daemon-live-governed-demo self-evolving-agent-adapters self-evolving-agent-preflight self-evolving-planner-validate self-evolving-org-agent-demo self-evolving-org-codex self-evolving-org-api-demo multi-agent-trace-attribution-demo phase-execution-demo protocol-experiment-demo capability-signal-demo adoption-demo kernel-service-smoke app-integration-conformance app-service-integration-smoke kernel-conformance-smoke a2h-command-conformance source-coverage-walkthrough learning-loop-walkthrough multi-actor-authority-walkthrough backup-restore-smoke package-smoke docs-surface-check public-claims-check release-hygiene-check release-diff-audit field-pilot-scaffold-smoke field-pilot-validate-smoke orbit-install orbit-build orbit-smoke-build audit-manifest audit-verify mcp-linear-live-smoke smoke-public smoke-docker release-candidate-check

help:
	@echo "cognitive-firm commands"
	@echo "  make test          # Python test suite"
	@echo "  make org-surface   # render the generic organization surface"
	@echo "  make first-gated-action  # shortest no-cost path: one governed action + receipt bundle"
	@echo "  make agent-fleet-audit-demo  # local agent invocation receipt -> attestation bundle"
	@echo "  make runtime-adapter-smoke  # exercise framework-neutral runtime events"
	@echo "  make native-e2e-demo  # no-cost native kernel path: authority -> work -> run -> attestation"
	@echo "  make native-e2e-demo-full-smoke  # validate native demo full JSON export quietly"
	@echo "  make governance-failure-benchmark  # no-cost fixtures for blocked/flagged governance failures"
	@echo "  make decision-log-replay-demo  # replay action-impact logs into governance packets"
	@echo "  make field-pilot-action-impact-compile-help  # show pilot row compiler usage"
	@echo "  make field-pilot-action-impact-demo  # field-pilot action-impact evidence to review packet"
	@echo "  make formal-provider-bundle-demo  # signed formal-provider payloads into governed-run bundles"
	@echo "  make langgraph-governance-demo  # runtime interrupt -> human work -> attestation bundle"
	@echo "  make self-evolving-org  # one-command demo; set SELF_EVOLVING_RUNTIME=fixture|codex|claude and SELF_EVOLVING_FEEDBACK=score_totals|withheld|compare"
	@echo "      optional: set SELF_EVOLVING_SERVE=1 to serve the generated viewer over localhost"
	@echo "  make self-evolving-org-demo  # no-cost governed org-evolution proof fixture"
	@echo "  make self-evolving-org-view  # persistent self-evolving demo reports + HTML timeline"
	@echo "  make self-evolving-feedback-comparison  # compare score-feedback vs no-feedback arms"
	@echo "  make self-evolving-org-compare  # alias for the score-feedback vs no-feedback comparison"
	@echo "  make self-evolving-org-compare-serve  # serve a generated comparison workdir"
	@echo "  make self-evolving-org-serve  # serve generated self-evolving demo reports for live polling"
	@echo "  make self-evolving-org-realtime-view  # stable-workdir realtime viewer run"
	@echo "  make self-evolving-org-realtime-serve  # serve the stable realtime viewer"
	@echo "  make self-evolving-daemon-smoke  # starter-firm + daemon-native org_evolver dispatch smoke"
	@echo "  make self-evolving-daemon-governed-smoke  # daemon dispatch -> governed mutation proof path"
	@echo "  make self-evolving-daemon-live-governed-demo  # live agent CLI daemon demo; set AGENT_CLI"
	@echo "  make self-evolving-agent-adapters  # inspect supported live-worker adapter shapes"
	@echo "  make self-evolving-agent-preflight  # no-mutation subscription/local agent readiness check"
	@echo "  make self-evolving-planner-validate  # validate SELF_EVOLVING_PLANNER_JSON"
	@echo "  make self-evolving-org-agent-demo  # live subscription/local agent planner; set AGENT_RUNTIME=codex or claude"
	@echo "  make self-evolving-org-codex  # live Codex planner + reviewers + first workload packets"
	@echo "      optional: set AGENT_REVIEWER_RUNTIME to spawn evaluator/risk/learning reviewer offices"
	@echo "      optional: set SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME and SELF_EVOLVING_WORKLOAD_EXECUTOR_LIMIT=N for live packet work"
	@echo "  make self-evolving-org-api-demo  # live API model-call planner; requires API key"
	@echo "  make multi-agent-trace-attribution-demo  # recursive trace evidence -> governed carrier"
	@echo "  make phase-execution-demo  # strategy/execution/verification with retry budget decay"
	@echo "  make protocol-experiment-demo  # compare coordination protocols before governed promotion"
	@echo "  make capability-signal-demo  # typed abstention/capability gap routing evidence"
	@echo "  make adoption-demo  # no-cost governed-run, adapter, failure, and org-evolution suite"
	@echo "  make kernel-service-smoke  # exercise service + SQLite fenced mutation path"
	@echo "  make app-integration-conformance  # deterministic MCP/webhook fixtures"
	@echo "  make app-service-integration-smoke  # actor -> membership -> lease -> service mutation -> org surface"
	@echo "  make kernel-conformance-smoke  # runtime interrupt, OTel projection, policy, inventory"
	@echo "  make a2h-command-conformance  # CLI fixture for A2H receipt-before-integration"
	@echo "  make source-coverage-walkthrough  # source-health and source-repair fixture"
	@echo "  make learning-loop-walkthrough  # evidence/human-work/action-impact to learning fixture"
	@echo "  make multi-actor-authority-walkthrough  # two humans + two services authority fixture"
	@echo "  make backup-restore-smoke  # snapshot/restore a minimal org state"
	@echo "  make package-smoke  # validate package metadata; build wheel when backend is installed"
	@echo "  make docs-surface-check  # verify adopter-facing docs link the abstraction/catalog layer"
	@echo "  make public-claims-check  # fail on public overclaim language or missing caveats"
	@echo "  make release-hygiene-check  # fail if private/generated state is tracked, staged, or unignored"
	@echo "  make release-diff-audit  # classify current changed paths into review buckets"
	@echo "  make field-pilot-scaffold-smoke  # copy field-pilot templates into a temp workspace"
	@echo "  make field-pilot-validate-smoke  # validate the scaffolded pilot templates"
	@echo "  make orbit-install # install Orbit dependencies if node_modules is absent"
	@echo "  make orbit-build   # type-check/build Orbit"
	@echo "  make orbit-smoke-build  # type-check/build Orbit into a temp dir"
	@echo "  make audit-manifest  # create audit manifest for AUDIT_SOURCE"
	@echo "  make audit-verify    # verify AUDIT_SOURCE against AUDIT_MANIFEST"
	@echo "  make mcp-linear-live-smoke  # optional live Linear MCP smoke; requires LINEAR_API_KEY"
	@echo "  make smoke-public  # public clone smoke: tests + conformance + walkthroughs + Orbit build"
	@echo "  make smoke-docker  # build/run/remove Docker smoke container"
	@echo "  make release-candidate-check  # public + clean-container + diff-audit gates for a tag candidate"

test:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) -m pytest tests

org-surface:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) -m cognitive_firm.orchestration.org_surface

first-gated-action:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/native_e2e_demo.py

agent-fleet-audit-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/agent_fleet_audit_demo.py

runtime-adapter-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/runtime_adapter_smoke.py

native-e2e-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/native_e2e_demo.py

native-e2e-demo-full-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/native_e2e_demo.py --full-json >/dev/null

governance-failure-benchmark:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/governance_failure_benchmark.py

decision-log-replay-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/decision_log_replay_demo.py

field-pilot-action-impact-compile-help:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/field_pilot_action_impact_compile.py --help

field-pilot-action-impact-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/field_pilot_action_impact_demo.py

formal-provider-bundle-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/formal_provider_bundle_demo.py

langgraph-governance-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/langgraph_governance_demo.py

self-evolving-org:
ifeq ($(SELF_EVOLVING_FEEDBACK),compare)
ifeq ($(SELF_EVOLVING_RUNTIME),fixture)
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --compare-feedback --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workdir "$(SELF_EVOLVING_COMPARISON_WORKDIR)" --replace-existing $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",)
else
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --compare-feedback --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workdir "$(SELF_EVOLVING_COMPARISON_WORKDIR)" --replace-existing --planner-prompt-mode "$(SELF_EVOLVING_PLANNER_PROMPT_MODE)" --planner-timeout-seconds "$(SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS)" --agent-planner-runtime "$(SELF_EVOLVING_RUNTIME)" --agent-planner-adapter "$(AGENT_ADAPTER)" --agent-reviewer-runtime "$(SELF_EVOLVING_RUNTIME)" --agent-reviewer-adapter "$(AGENT_ADAPTER)" --workload-executor-runtime "$(SELF_EVOLVING_RUNTIME)" --workload-executor-adapter "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_ADAPTER)" --workload-executor-limit "$(SELF_EVOLVING_LIVE_WORKLOAD_LIMIT)" --workload-executor-timeout-seconds "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_TIMEOUT_SECONDS)" $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",)
endif
	@echo "Comparison report: $(SELF_EVOLVING_COMPARISON_WORKDIR)/reports/self-evolving-feedback-comparison.md"
	@echo "Comparison viewer file: $(SELF_EVOLVING_COMPARISON_WORKDIR)/reports/self-evolving-feedback-comparison.html"
	@echo "Score-feedback viewer: $(SELF_EVOLVING_COMPARISON_WORKDIR)/score-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "No-feedback viewer: $(SELF_EVOLVING_COMPARISON_WORKDIR)/no-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "Open commands:"
	@echo "  open $(SELF_EVOLVING_COMPARISON_WORKDIR)/reports/self-evolving-feedback-comparison.md"
	@echo "  open $(SELF_EVOLVING_COMPARISON_WORKDIR)/reports/self-evolving-feedback-comparison.html"
	@echo "  open $(SELF_EVOLVING_COMPARISON_WORKDIR)/score-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "  open $(SELF_EVOLVING_COMPARISON_WORKDIR)/no-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "Serve command:"
	@echo "  make self-evolving-org-compare-serve SELF_EVOLVING_COMPARISON_SERVE_WORKDIR=$(SELF_EVOLVING_COMPARISON_WORKDIR)"
ifeq ($(SELF_EVOLVING_SERVE),1)
	@echo "Stop the viewer with Ctrl-C."
	$(PYTHON) -m http.server "$(SELF_EVOLVING_DEMO_PORT)" --bind 127.0.0.1 --directory "$(SELF_EVOLVING_COMPARISON_WORKDIR)"
endif
else ifeq ($(SELF_EVOLVING_RUNTIME),fixture)
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workdir "$(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)" --replace-existing --workload-feedback "$(SELF_EVOLVING_FEEDBACK)" $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",)
	@echo "Viewer file: $(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "Workdir: $(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)"
	@echo "Serve command:"
	@echo "  make self-evolving-org-serve SELF_EVOLVING_DEMO_WORKDIR=$(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)"
ifeq ($(SELF_EVOLVING_SERVE),1)
	@echo "Stop the viewer with Ctrl-C."
	$(PYTHON) -m http.server "$(SELF_EVOLVING_DEMO_PORT)" --bind 127.0.0.1 --directory "$(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)/demo-firm/reports"
endif
else
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workdir "$(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)" --replace-existing --planner-prompt-mode "$(SELF_EVOLVING_PLANNER_PROMPT_MODE)" --planner-timeout-seconds "$(SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS)" --workload-feedback "$(SELF_EVOLVING_FEEDBACK)" --agent-planner-runtime "$(SELF_EVOLVING_RUNTIME)" --agent-planner-adapter "$(AGENT_ADAPTER)" --agent-reviewer-runtime "$(SELF_EVOLVING_RUNTIME)" --agent-reviewer-adapter "$(AGENT_ADAPTER)" --workload-executor-runtime "$(SELF_EVOLVING_RUNTIME)" --workload-executor-adapter "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_ADAPTER)" --workload-executor-limit "$(SELF_EVOLVING_LIVE_WORKLOAD_LIMIT)" --workload-executor-timeout-seconds "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_TIMEOUT_SECONDS)" $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",)
	@echo "Viewer file: $(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "Workdir: $(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)"
	@echo "Serve command:"
	@echo "  make self-evolving-org-serve SELF_EVOLVING_DEMO_WORKDIR=$(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)"
ifeq ($(SELF_EVOLVING_SERVE),1)
	@echo "Stop the viewer with Ctrl-C."
	$(PYTHON) -m http.server "$(SELF_EVOLVING_DEMO_PORT)" --bind 127.0.0.1 --directory "$(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)/demo-firm/reports"
endif
endif

self-evolving-org-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workload-feedback "$(SELF_EVOLVING_EFFECTIVE_WORKLOAD_FEEDBACK)" $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",) $(if $(SELF_EVOLVING_DEMO_STOP_FILE),--stop-file "$(SELF_EVOLVING_DEMO_STOP_FILE)",) $(if $(SELF_EVOLVING_DEMO_RUN_UNTIL_STOPPED),--run-until-stopped,)

self-evolving-org-view:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workdir "$(SELF_EVOLVING_DEMO_WORKDIR)" --workload-feedback "$(SELF_EVOLVING_EFFECTIVE_WORKLOAD_FEEDBACK)" $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",) $(if $(SELF_EVOLVING_DEMO_STOP_FILE),--stop-file "$(SELF_EVOLVING_DEMO_STOP_FILE)",) $(if $(SELF_EVOLVING_DEMO_RUN_UNTIL_STOPPED),--run-until-stopped,)
	@echo "Demo viewer: $(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "Operator runbook: $(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports/self-evolving-org-runbook.md"
	@echo "Report JSON: $(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports/self-evolving-org-demo.json"

self-evolving-feedback-comparison:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --compare-feedback --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workdir "$(SELF_EVOLVING_COMPARISON_WORKDIR)" $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",)
	@echo "Comparison report: $(SELF_EVOLVING_COMPARISON_WORKDIR)/reports/self-evolving-feedback-comparison.md"
	@echo "Comparison viewer file: $(SELF_EVOLVING_COMPARISON_WORKDIR)/reports/self-evolving-feedback-comparison.html"
	@echo "Score-feedback viewer: $(SELF_EVOLVING_COMPARISON_WORKDIR)/score-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "No-feedback viewer: $(SELF_EVOLVING_COMPARISON_WORKDIR)/no-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "Open commands:"
	@echo "  open $(SELF_EVOLVING_COMPARISON_WORKDIR)/reports/self-evolving-feedback-comparison.md"
	@echo "  open $(SELF_EVOLVING_COMPARISON_WORKDIR)/reports/self-evolving-feedback-comparison.html"
	@echo "  open $(SELF_EVOLVING_COMPARISON_WORKDIR)/score-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "  open $(SELF_EVOLVING_COMPARISON_WORKDIR)/no-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "Serve command:"
	@echo "  make self-evolving-org-compare-serve SELF_EVOLVING_COMPARISON_SERVE_WORKDIR=$(SELF_EVOLVING_COMPARISON_WORKDIR)"
ifeq ($(SELF_EVOLVING_SERVE),1)
	@echo "Stop the viewer with Ctrl-C."
	$(PYTHON) -m http.server "$(SELF_EVOLVING_DEMO_PORT)" --bind 127.0.0.1 --directory "$(SELF_EVOLVING_COMPARISON_WORKDIR)"
endif

self-evolving-org-compare: self-evolving-feedback-comparison

self-evolving-org-compare-serve:
	@echo "Serving comparison workdir at http://127.0.0.1:$(SELF_EVOLVING_DEMO_PORT)/"
	@echo "Comparison viewer: http://127.0.0.1:$(SELF_EVOLVING_DEMO_PORT)/reports/self-evolving-feedback-comparison.html"
	@echo "Score-feedback viewer: http://127.0.0.1:$(SELF_EVOLVING_DEMO_PORT)/score-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "No-feedback viewer: http://127.0.0.1:$(SELF_EVOLVING_DEMO_PORT)/no-feedback/demo-firm/reports/self-evolving-org-company-state.html"
	$(PYTHON) -m http.server "$(SELF_EVOLVING_DEMO_PORT)" --bind 127.0.0.1 --directory "$(SELF_EVOLVING_COMPARISON_SERVE_WORKDIR)"

self-evolving-org-serve:
	@echo "Serving self-evolving demo reports at http://127.0.0.1:$(SELF_EVOLVING_DEMO_PORT)/self-evolving-org-company-state.html"
	$(PYTHON) -m http.server "$(SELF_EVOLVING_DEMO_PORT)" --bind 127.0.0.1 --directory "$(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports"

self-evolving-org-realtime-view:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workdir "$(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)" --replace-existing --workload-feedback "$(SELF_EVOLVING_EFFECTIVE_WORKLOAD_FEEDBACK)" $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",) $(if $(SELF_EVOLVING_DEMO_STOP_FILE),--stop-file "$(SELF_EVOLVING_DEMO_STOP_FILE)",) $(if $(SELF_EVOLVING_DEMO_RUN_UNTIL_STOPPED),--run-until-stopped,)
	@echo "Realtime company-state URL: http://127.0.0.1:$(SELF_EVOLVING_DEMO_PORT)/self-evolving-org-company-state.html"
	@echo "Realtime operator runbook: $(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)/demo-firm/reports/self-evolving-org-runbook.md"
	@echo "Realtime workdir: $(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)"

self-evolving-org-realtime-serve:
	@echo "Serving realtime self-evolving demo reports at http://127.0.0.1:$(SELF_EVOLVING_DEMO_PORT)/self-evolving-org-company-state.html"
	mkdir -p "$(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)/demo-firm/reports"
	$(PYTHON) -m http.server "$(SELF_EVOLVING_DEMO_PORT)" --bind 127.0.0.1 --directory "$(SELF_EVOLVING_DEMO_REALTIME_WORKDIR)/demo-firm/reports"

self-evolving-daemon-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/daemon_smoke.py --workdir "$(SELF_EVOLVING_DAEMON_WORKDIR)" --daemon-timeout "$(SELF_EVOLVING_DAEMON_TIMEOUT)"

self-evolving-daemon-governed-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/daemon_smoke.py --governed --workdir "$(SELF_EVOLVING_DAEMON_WORKDIR)" --daemon-timeout "$(SELF_EVOLVING_DAEMON_TIMEOUT)"

self-evolving-daemon-live-governed-demo:
	test -n "$(AGENT_CLI)"
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/daemon_smoke.py --governed --agent-cli "$(AGENT_CLI)" --agent-adapter "$(AGENT_ADAPTER)" --workdir "$(SELF_EVOLVING_DAEMON_WORKDIR)" --daemon-timeout "$(SELF_EVOLVING_DAEMON_TIMEOUT)" $(if $(AGENT_REVIEWER_RUNTIME),--agent-reviewer-runtime "$(AGENT_REVIEWER_RUNTIME)" --agent-reviewer-adapter "$(AGENT_REVIEWER_ADAPTER)",) $(if $(SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS),--reviewer-timeout "$(SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS)",)

self-evolving-agent-adapters:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) -m cognitive_firm.orchestration.agent_runtime_invocation list-adapters

self-evolving-agent-preflight:
	test -n "$(SELF_EVOLVING_AGENT_RUNTIME)"
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/agent_preflight.py --agent-runtime "$(SELF_EVOLVING_AGENT_RUNTIME)" --agent-adapter "$(AGENT_ADAPTER)" --timeout-seconds "$(SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS)" $(if $(AGENT_REVIEWER_RUNTIME),--agent-reviewer-runtime "$(AGENT_REVIEWER_RUNTIME)" --agent-reviewer-adapter "$(AGENT_REVIEWER_ADAPTER)" $(if $(SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS),--reviewer-timeout-seconds "$(SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS)",),) $(if $(SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME),--workload-executor-runtime "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME)" --workload-executor-adapter "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_ADAPTER)" --workload-executor-timeout-seconds "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_TIMEOUT_SECONDS)",) $(if $(AGENT_REVIEWER_RUNTIME)$(SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME),--readiness-summary,)

self-evolving-planner-validate:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/planner_validate.py "$(SELF_EVOLVING_PLANNER_JSON)"

self-evolving-org-agent-demo:
	test -n "$(AGENT_PLANNER_COMMAND)$(SELF_EVOLVING_AGENT_RUNTIME)"
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workdir "$(SELF_EVOLVING_DEMO_WORKDIR)" --planner-prompt-mode "$(SELF_EVOLVING_PLANNER_PROMPT_MODE)" --planner-timeout-seconds "$(SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS)" --workload-feedback "$(SELF_EVOLVING_EFFECTIVE_WORKLOAD_FEEDBACK)" $(if $(AGENT_PLANNER_COMMAND),--agent-planner-command "$(AGENT_PLANNER_COMMAND)",--agent-planner-runtime "$(SELF_EVOLVING_AGENT_RUNTIME)" --agent-planner-adapter "$(AGENT_ADAPTER)") $(if $(AGENT_REVIEWER_RUNTIME),--agent-reviewer-runtime "$(AGENT_REVIEWER_RUNTIME)" --agent-reviewer-adapter "$(AGENT_REVIEWER_ADAPTER)",) $(if $(SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS),--reviewer-timeout-seconds "$(SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS)",) $(if $(SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME),--workload-executor-runtime "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME)" --workload-executor-adapter "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_ADAPTER)" --workload-executor-limit "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_LIMIT)" --workload-executor-timeout-seconds "$(SELF_EVOLVING_WORKLOAD_EXECUTOR_TIMEOUT_SECONDS)",) $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",) $(if $(SELF_EVOLVING_DEMO_STOP_FILE),--stop-file "$(SELF_EVOLVING_DEMO_STOP_FILE)",) $(if $(SELF_EVOLVING_DEMO_RUN_UNTIL_STOPPED),--run-until-stopped,)
	@echo "Demo viewer: $(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "Operator runbook: $(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports/self-evolving-org-runbook.md"
	@echo "Report JSON: $(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports/self-evolving-org-demo.json"

self-evolving-org-codex:
	$(MAKE) self-evolving-org SELF_EVOLVING_RUNTIME=codex SELF_EVOLVING_LIVE_WORKLOAD_LIMIT="$(SELF_EVOLVING_CODEX_WORKLOAD_LIMIT)"

self-evolving-org-api-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/self_evolving_org/run.py --iterations "$(SELF_EVOLVING_DEMO_ITERATIONS)" --workdir "$(SELF_EVOLVING_DEMO_WORKDIR)" --planner-prompt-mode "$(SELF_EVOLVING_PLANNER_PROMPT_MODE)" --workload-feedback "$(SELF_EVOLVING_EFFECTIVE_WORKLOAD_FEEDBACK)" --api-planner $(if $(MODEL_ID),--model-id $(MODEL_ID),) $(if $(SELF_EVOLVING_DEMO_BUDGET_UNITS),--budget-units "$(SELF_EVOLVING_DEMO_BUDGET_UNITS)",) $(if $(SELF_EVOLVING_DEMO_STOP_FILE),--stop-file "$(SELF_EVOLVING_DEMO_STOP_FILE)",) $(if $(SELF_EVOLVING_DEMO_RUN_UNTIL_STOPPED),--run-until-stopped,)
	@echo "Demo viewer: $(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports/self-evolving-org-company-state.html"
	@echo "Operator runbook: $(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports/self-evolving-org-runbook.md"
	@echo "Report JSON: $(SELF_EVOLVING_DEMO_WORKDIR)/demo-firm/reports/self-evolving-org-demo.json"

multi-agent-trace-attribution-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/governance_carriers/multi_agent_trace_attribution_demo.py

phase-execution-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/governance_carriers/phase_execution_demo.py

protocol-experiment-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/governance_carriers/protocol_experiment_demo.py

capability-signal-demo:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) demos/governance_carriers/capability_signal_demo.py

adoption-demo: native-e2e-demo agent-fleet-audit-demo governance-failure-benchmark decision-log-replay-demo field-pilot-action-impact-demo formal-provider-bundle-demo langgraph-governance-demo self-evolving-org-demo self-evolving-daemon-smoke multi-agent-trace-attribution-demo phase-execution-demo protocol-experiment-demo capability-signal-demo

kernel-service-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/kernel_service_smoke.py

app-integration-conformance:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/app_integration_conformance.py

app-service-integration-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/app_service_integration_smoke.py

kernel-conformance-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/kernel_conformance_smoke.py

a2h-command-conformance:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/a2h_command_conformance.py

source-coverage-walkthrough:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/source_coverage_walkthrough.py

learning-loop-walkthrough:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/learning_loop_walkthrough.py

multi-actor-authority-walkthrough:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/multi_actor_authority_walkthrough.py

backup-restore-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/backup_restore_smoke.py

package-smoke:
	$(PYTHON) scripts/package_smoke.py

docs-surface-check:
	$(PYTHON) scripts/docs_surface_check.py

public-claims-check:
	$(PYTHON) scripts/public_claims_check.py

release-hygiene-check:
	$(PYTHON) scripts/release_hygiene_check.py

release-diff-audit:
	$(PYTHON) scripts/release_diff_audit.py

field-pilot-scaffold-smoke:
	$(PYTHON) scripts/field_pilot_scaffold.py /private/tmp/cognitive-firm-field-pilot-smoke --force

field-pilot-validate-smoke: field-pilot-scaffold-smoke
	$(PYTHON) scripts/field_pilot_validate_smoke.py

orbit-install:
	cd orbit && test -d node_modules || $(NPM) ci

orbit-build: orbit-install
	cd orbit && $(NPM) run build

orbit-smoke-build: orbit-install
	cd orbit && node node_modules/typescript/lib/tsc.js --noEmit
	cd orbit && node node_modules/vite/bin/vite.js build --configLoader runner --outDir $(ORBIT_SMOKE_OUTDIR) --emptyOutDir true

audit-manifest:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) -m cognitive_firm.orchestration.audit_integrity create --source $(AUDIT_SOURCE) --manifest $(AUDIT_MANIFEST) $(if $(AUDIT_SIGNING_KEY),--signing-key $(AUDIT_SIGNING_KEY),)

audit-verify:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) -m cognitive_firm.orchestration.audit_integrity verify --source $(AUDIT_SOURCE) --manifest $(AUDIT_MANIFEST) $(if $(AUDIT_SIGNING_KEY),--signing-key $(AUDIT_SIGNING_KEY),)

mcp-linear-live-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/mcp_linear_live_smoke.py

smoke-public: test org-surface runtime-adapter-smoke native-e2e-demo native-e2e-demo-full-smoke agent-fleet-audit-demo governance-failure-benchmark decision-log-replay-demo field-pilot-action-impact-compile-help field-pilot-action-impact-demo formal-provider-bundle-demo langgraph-governance-demo self-evolving-org-demo self-evolving-daemon-smoke multi-agent-trace-attribution-demo phase-execution-demo protocol-experiment-demo capability-signal-demo kernel-service-smoke app-integration-conformance app-service-integration-smoke kernel-conformance-smoke a2h-command-conformance source-coverage-walkthrough learning-loop-walkthrough multi-actor-authority-walkthrough backup-restore-smoke package-smoke docs-surface-check public-claims-check release-hygiene-check field-pilot-validate-smoke orbit-smoke-build

smoke-docker:
	bash scripts/docker_smoke.sh

release-candidate-check: smoke-public smoke-docker release-diff-audit
	@echo "OK: release candidate gates passed. Inspect git status and final diff before tagging."
