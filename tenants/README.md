# `tenants/` - tenant overlay slot

This directory is a **slot**, not a package. The public kernel includes a
minimal `tenants/example/` overlay so adopters can see the shape. Real tenant
content (mandate text, principal preferences, role definitions, project files,
private evidence, and business-system bindings) should live in a sibling
private repo per tenant. This README documents the overlay pattern so a fork
can host its own tenant cleanly.

## Why the kernel ships only an example

cognitive-firm separates **mechanism** (in `src/`, `org/templates/`, `schemas/`) from **policy** (per-tenant mandates, preferences, role bindings). The kernel only ships mechanism. Policy is loaded at runtime from an overlay so:

- Two organizations can use the same kernel without contaminating each other's
  instantiation.
- The kernel repo can stay public while tenant content stays private.
- A fresh `git clone` can run in **kernel-only mode** or inspect
  `tenants/example/` without live private policy.
- Real tenants can be added without changing public kernel history.

## The overlay pattern, concretely

```
~/cognitive-firm/                         ← public kernel (this repo)
│   org/
│   ├── roles/
│   │   ├── manager.yaml                  ← shipped (kernel-generic)
│   │   ├── engineer.yaml                 ← shipped
│   │   └── research_director.yaml        ← symlink → tenant overlay (gitignored)
│   ├── mandates/
│   │   ├── templates/
│   │   │   └── manager_mandate.md        ← shipped (template only)
│   │   └── manager_mandate.md            ← symlink → tenant overlay (gitignored)
│   └── preferences/
│       ├── templates/
│       │   └── principal.yaml            ← shipped (schema only)
│       └── principal.yaml                ← symlink → tenant overlay (gitignored)
│
~/<tenant>-research-co/                   ← sibling private repo (one per tenant)
│   tenants/<tenant>/
│   ├── mandates/
│   │   ├── manager_mandate.md            ← real text
│   │   ├── research_director_mandate.md
│   │   └── product_manager_mandate.md
│   ├── roles/
│   │   ├── research_director.yaml        ← tenant-specific authorities
│   │   └── product_manager.yaml
│   └── preferences/
│       └── principal.yaml                ← real preference values
└── scripts/
    ├── setup_tenant.sh                   ← creates overlay symlinks
    └── teardown_tenant.sh                ← removes overlay symlinks
```

The bridge between the two repos is a set of relative symlinks placed by the tenant's `setup_tenant.sh`. The kernel's `.gitignore` lists every conventional symlink path, so the symlinks themselves never enter public history.

## Setting up a new tenant

### 1. Create the private repo (once)

```bash
mkdir -p ~/<tenant>-research-co/{scripts,tenants/<tenant>/{mandates,roles,preferences}}
cd ~/<tenant>-research-co
git init
```

### 2. Copy templates from the kernel into the tenant

```bash
cp ~/cognitive-firm/org/mandates/templates/*.md \
   tenants/<tenant>/mandates/
cp ~/cognitive-firm/org/preferences/templates/principal.yaml \
   tenants/<tenant>/preferences/principal.yaml
# Copy any role yaml that is tenant-specific (e.g. research_director, product_manager)
```

Edit the copies with the tenant's actual mandate text, role authorities, and principal preferences. These files are private and stay in the tenant repo.

### 3. Write `setup_tenant.sh` for the tenant

```bash
#!/usr/bin/env bash
set -euo pipefail
PRIVATE="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC="${1:-$HOME/cognitive-firm}"
TENANT="<tenant>"

[[ -d "$PUBLIC/org" ]] || { echo "no $PUBLIC/org/"; exit 2; }
[[ -d "$PRIVATE/tenants/$TENANT" ]] || { echo "no $PRIVATE/tenants/$TENANT/"; exit 2; }

_link() {
  local target=$1 source=$2
  rm -f "$target"
  ln -s "$source" "$target"
}

# Mandates
_link "$PUBLIC/org/mandates/manager_mandate.md" \
      "../../../<tenant>-research-co/tenants/$TENANT/mandates/manager_mandate.md"
_link "$PUBLIC/org/mandates/research_director_mandate.md" \
      "../../../<tenant>-research-co/tenants/$TENANT/mandates/research_director_mandate.md"

# Roles
_link "$PUBLIC/org/roles/research_director.yaml" \
      "../../../<tenant>-research-co/tenants/$TENANT/roles/research_director.yaml"

# Preferences
_link "$PUBLIC/org/preferences/principal.yaml" \
      "../../../<tenant>-research-co/tenants/$TENANT/preferences/principal.yaml"

echo "tenant '$TENANT' overlay installed into $PUBLIC"
```

### 4. Run setup, then run preflight

```bash
~/<tenant>-research-co/scripts/setup_tenant.sh ~/cognitive-firm
cd ~/cognitive-firm
python scripts/org_role_preflight.py --role research_director
```

Preflight should report all paths resolved. If a symlink is broken, preflight names the missing target.

### 5. Confirm public kernel sees zero tenant content

```bash
cd ~/cognitive-firm
git status     # tenant overlays must NOT appear
git ls-files | grep tenant    # should be empty other than this README
```

## Teardown

```bash
~/<tenant>-research-co/scripts/teardown_tenant.sh ~/cognitive-firm
```

The kernel returns to kernel-only mode; templates remain, live policy is gone.

## Multiple tenants on one kernel

A single cognitive-firm checkout should host **one active tenant at a time** in
T1 because the symlink slots are fixed paths. To switch tenants, run teardown
then run the next tenant's setup. For multiple concurrent tenants, run multiple
kernel checkouts (one per tenant), each pointed at its own tenant repo.

For shared-volume / Postgres-backed tenant isolation (the T2 reactivation path), see the threat-model table in `docs/PROTOCOLS.md`.

## What goes in tenant overlays vs. what stays in the kernel

| Stays in the kernel (this repo, public) | Goes to the tenant overlay (private) |
|---|---|
| Role schema (`schemas/role.v1.schema.json`) | Tenant-specific role definitions (e.g. `research_director.yaml`) |
| Mandate templates (`org/mandates/templates/`) | Real mandate text with research-program / IP context |
| Preference templates (`org/preferences/templates/`) | Principal taste, budget priorities, model preferences |
| Generic roles (`org/roles/{manager,engineer,reviewer,principal}.yaml`) | Tenant workers, project-specific reviewers, and domain-specific role offices |
| Bootstrap manifest (`org/bootstrap_manifest.yaml`) | Tenant-specific conditional reads cited from manifest |
| Pattern + anti-pattern catalogs (`org/patterns/`, `org/anti-patterns/`) | Tenant project IDs, in-flight strategy, sealed pre-registrations |
| Signal kinds (`org/signals/SIGNAL_KINDS.md`) | Damage-signal rationale tied to specific tenant incidents |

Rule of thumb: if removing the file would break the kernel's ability to boot in kernel-only mode, it stays in the kernel; if removing it just removes a tenant's instantiation, it goes to the overlay.

## Example implementation

Use `tenants/example/` as the public, generic overlay example. Private
organizations may keep richer overlays in sibling repos and symlink them into
the public kernel checkout.
