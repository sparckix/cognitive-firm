PYTHON ?= python3
NPM ?= npm
CF_PYTHONPATH ?= src
ORBIT_SMOKE_OUTDIR ?= /private/tmp/cognitive-firm-orbit-smoke-dist
AUDIT_SOURCE ?= cognitive_firm_workspace/transitions.jsonl
AUDIT_MANIFEST ?= org/audit/transitions.manifest.json
AUDIT_SIGNING_KEY ?=

.PHONY: help test org-surface runtime-adapter-smoke kernel-service-smoke app-integration-conformance app-service-integration-smoke kernel-conformance-smoke source-coverage-walkthrough learning-loop-walkthrough multi-actor-authority-walkthrough backup-restore-smoke package-smoke docs-surface-check field-pilot-scaffold-smoke field-pilot-validate-smoke orbit-install orbit-build orbit-smoke-build audit-manifest audit-verify mcp-linear-live-smoke smoke-public smoke-docker

help:
	@echo "cognitive-firm commands"
	@echo "  make test          # Python test suite"
	@echo "  make org-surface   # render the generic organization surface"
	@echo "  make runtime-adapter-smoke  # exercise framework-neutral runtime events"
	@echo "  make kernel-service-smoke  # exercise service + SQLite fenced mutation path"
	@echo "  make app-integration-conformance  # deterministic MCP/webhook fixtures"
	@echo "  make app-service-integration-smoke  # actor -> membership -> lease -> service mutation -> org surface"
	@echo "  make kernel-conformance-smoke  # runtime interrupt, OTel projection, policy, inventory"
	@echo "  make source-coverage-walkthrough  # source-health and source-repair fixture"
	@echo "  make learning-loop-walkthrough  # evidence/human-work/action-impact to learning fixture"
	@echo "  make multi-actor-authority-walkthrough  # two humans + two services authority fixture"
	@echo "  make backup-restore-smoke  # snapshot/restore a minimal org state"
	@echo "  make package-smoke  # validate package metadata; build wheel when backend is installed"
	@echo "  make docs-surface-check  # verify adopter-facing docs link the abstraction/catalog layer"
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

test:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) -m pytest tests

org-surface:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) -m cognitive_firm.orchestration.org_surface

runtime-adapter-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/runtime_adapter_smoke.py

kernel-service-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/kernel_service_smoke.py

app-integration-conformance:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/app_integration_conformance.py

app-service-integration-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/app_service_integration_smoke.py

kernel-conformance-smoke:
	PYTHONPATH=$(CF_PYTHONPATH) $(PYTHON) scripts/kernel_conformance_smoke.py

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

smoke-public: test org-surface runtime-adapter-smoke kernel-service-smoke app-integration-conformance app-service-integration-smoke kernel-conformance-smoke source-coverage-walkthrough learning-loop-walkthrough multi-actor-authority-walkthrough backup-restore-smoke package-smoke docs-surface-check field-pilot-validate-smoke orbit-smoke-build

smoke-docker:
	bash scripts/docker_smoke.sh
