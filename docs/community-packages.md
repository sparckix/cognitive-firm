# Community Packages — A Roadmap

A *package* is a versioned, installable bundle that composes an organization on
top of the kernel — a `distro` (a full starter organization) or an `overlay`
(an add-on installed onto an existing org). See
[`protocols/distribution.md`](protocols/distribution.md) for the format and
[`protocols/extension-schemas.md`](protocols/extension-schemas.md) for how a
package validates a custom primitive type.

This page is a roadmap of packages the community could build. It is an
invitation, not a committed plan: anyone can author a package, and a good
ecosystem of distros and overlays is how the kernel becomes adoptable without
every adopter assembling an organization from the protocol catalog by hand.

## The one discipline

**Authorship is open; adoption is governed.** Anyone may write and publish a
package. But installing one onto a *running* organization changes who-can-do-
what — it amends the org's authority structure. A package install is a
governance act, not a `npm install`. Author packages with that in mind:
declare authority narrowly, document what each role can do, and never assume an
operator wants more authority granted than the task needs.

## Distros — full starter organizations

A distro brings up a complete, runnable governed organization for a domain.
`starter-firm` is the generic baseline; domain distros specialize it.

| Idea | What it composes | For |
|---|---|---|
| `research-lab` | a principal, a research director, a skeptic/reviewer, an analyst; mandates tuned for evidence and external-validity review | small research groups running agents on a literature or experiment program |
| `solo-consultancy` | a principal, a delivery lead, a researcher, a client-comms reviewer; an operating unit per engagement | one person running a consultancy with agent leverage |
| `oss-maintainer` | a maintainer (authority), a triage role, a review role; an operating unit for the issue/PR pipeline | an open-source maintainer governing agent help on a repo |
| `small-fund` | a principal, an analyst, a risk reviewer, a compliance role; gated approval for any external commitment | a solo or small investment operation |
| `content-studio` | an editor-in-chief (authority), writers, a fact-check reviewer; a per-piece operating unit | a small content or media operation |

## Overlays — add-ons to an existing organization

An overlay adds or modifies roles, mandates, operating units, or config. With
the `add` / `replace` / `patch` composition model, an overlay can introduce new
structure or amend existing structure precisely.

| Idea | What it adds | For |
|---|---|---|
| `compliance-officer` | a compliance role, its mandate, an accountability-case review cadence | any org that needs a standing compliance function |
| `eu-ai-act` | the EU AI Act deploy-gate config, a mapping checklist, a reviewer role | orgs deploying under the EU AI Act |
| `audit-hardening` | audit-integrity manifest cadence, tighter receipt requirements, a stricter closure-review routine | orgs raising their audit bar |
| `incident-response` | an incident operating unit, an on-call routing config, a post-incident review routine | orgs that need a governed incident loop |
| `hiring-pipeline` | a hiring operating unit with typed stages and bounded exits, a hiring-manager role | orgs running a recurring hiring process |
| `treasury` | a finance/treasury role with narrow `authorized_paths`, gated approval for any movement of funds | orgs that handle money and want it tightly scoped |
| `leanmill-formal-verification` | provider trust policy for LeanMill `formal-verification-provider/v1` payloads; requires signed, re-runnable, and faithfulness-backed evidence | orgs that want formal-verification evidence in governed-run bundles without importing checker code into the kernel |

## Adapter Packs

An adapter pack is an overlay for a runtime, provider, or external system. It
does not need to contain the executable adapter. It installs the governed side
of the integration: role policy, capability grants, extension schemas,
trusted-provider keys or key placeholders, example project files, conformance
fixture config, and post-install instructions.

| Idea | What it installs | External code path |
|---|---|---|
| `langgraph-runtime-adapter` | a role/mandate example for graph-owned work, runtime-adapter conformance fixture config, and human-interrupt A2H policy | a Python adapter that maps LangGraph callbacks to `RuntimeEvent` rows |
| `openai-agents-runtime-adapter` | lifecycle projection policy, trace-reference conventions, and action-attestation examples | an adapter over the OpenAI Agents SDK lifecycle and tracing hooks |
| `mcp-linear-readonly` | mandate capability grants for read-only Linear tools and projection-fixture config | the Linear MCP server and existing MCP transport |
| `leanmill-formal-verification` | formal-verification trust policy and evidence requirements | the LeanMill adapter/checker process |

This split is deliberate. The package manager composes governed organization
state. Executable code is installed by its normal route — a Python package, a
container, a local binary, or a hosted service — then proved acceptable through
adapter conformance, signatures, digest references, or provider trust policy.

## Extension-schema packages

A package can ship JSON Schemas (see `extension-schemas.md`) that validate a
custom primitive type — for example a domain-specific `WorkItem` `kind` with a
required payload shape. Useful community packages here are *schema packs*: a
bundle of validated work-item and operating-unit types for a domain (a
code-review schema pack, a research-claim schema pack), so custom types are
type-safe, not just allowed.

## Adapter-policy packages

Some packages install policy for an external adapter rather than adapter
binaries. For example, `leanmill-formal-verification` installs the org-owned
trust policy used by governed-run bundle export. The LeanMill adapter can be
distributed separately; the overlay only states which provider payloads this
org will treat as trusted evidence and what proof artifacts must accompany
them. The operator still configures the provider public key before signed
payloads can clear without caveats. This keeps executable checker code outside
the kernel while still making adoption inspectable and reversible through the
package manager. `make formal-provider-proof-pack` packages the overlay
manifest, conformance config, trust policy, signed-provider happy path, and
missing-evidence caveat path into one adoption receipt.

## Authoring a package

1. Copy the package template at `docs/templates/package/` (or start from the
   `starter-firm` layout, `distro/starter-firm/`): a `package.yaml` manifest
   and a `files/` tree.
2. Keep authority narrow — every role's `authorized_paths` and mandate should
   grant the least the role needs. Installing an overlay onto a running org is
   governed; an overlay that *widens* a role's authority is blocked outright.
3. Lint the manifest as you author: `cognitive-firm-distro lint <package>`
   reports every authoring problem at once (missing component sources, an
   unknown composition `op`, escaping paths, a too-short description).
4. Preview the install without applying it:
   `cognitive-firm-distro install <package> --into <dir> --dry-run` prints the
   full file plan and each component's composition `op`.
5. For overlays, preview against a real org before filing a proposal:
   `cognitive-firm-distro preview-overlay <overlay> --into <org> --json`
   stages the overlay on a copy, reports the authority diff, and exits nonzero
   when the overlay widens or ambiguously changes authority.
6. Verify it boots: an installed organization must pass `boot_check` (authority
   roles are scoped, escalation reaches authority, mandates resolve) and any
   installed adapter/provider policy must validate.
7. Publish it as a git repository — a package is just a repo with a
   `package.yaml`. Anyone can install it directly:
   `cognitive-firm-distro install <git-url> --into <dir>` fetches it SHA-pinned
   and records a content-hashed `packages.lock`. There is no central registry
   to clear.

The kernel stays generic. A distro or overlay is policy; composing one must
never require a kernel change.

The bundled `langgraph-runtime-adapter` overlay is the reference runtime
adapter-policy package. It installs only `adapters/` and
`adapter_conformance/` declarations: the adapter manifest, required fixture
checks, and the boundary statement that LangGraph owns graph execution while
cognitive-firm owns the organizational projection. It is intentionally
authority-neutral and should pass `preview-overlay` without a proposal. Run
`make langgraph-adapter-policy-preview` for a no-cost proof against a temporary
starter org.
