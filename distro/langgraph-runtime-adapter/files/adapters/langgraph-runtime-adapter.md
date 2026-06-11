# LangGraph Runtime Adapter Overlay

This overlay installs the organization-side declaration for a LangGraph
runtime adapter.

It does not install LangGraph and it does not install executable adapter code.
The adapter runs in the runtime environment and emits `RuntimeEvent` rows into
cognitive-firm.

The installed manifest requires the adapter to prove:

- stable `(runtime_name, external_run_id)` mapping to one cognitive-firm run;
- checkpoint projection with side-effect keys preserved;
- interrupt projection into a bounded human-work session;
- state changes that close the projected run without creating a second ledger;
- governed-run bundle export with no caveats for the fixture path.

Use the no-cost fixture as the reference behavior:

```bash
make langgraph-governance-demo
```

For package review before filing a governance proposal:

```bash
cognitive-firm-distro preview-overlay langgraph-runtime-adapter \
  --into <org> \
  --json
```
