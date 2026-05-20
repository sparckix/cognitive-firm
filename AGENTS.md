# Agent Instructions

This repository is the reusable cognitive-firm kernel. Keep tenant-specific
mandates, credentials, strategic context, and runtime state out of the public
kernel. Use `tenants/example/` and `org/*/templates/` as copyable examples.

When editing the kernel:

- Keep core primitives domain-neutral.
- Put tenant/app policy in overlays, adapters, or examples.
- Run `make smoke-public` before shipping public-facing changes.
- Run `make smoke-docker` when validating clean-container boot.
- Do not commit local `.env`, principal preferences, daemon state, or private
  tenant symlinks.
