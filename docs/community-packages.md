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

## Extension-schema packages

A package can ship JSON Schemas (see `extension-schemas.md`) that validate a
custom primitive type — for example a domain-specific `WorkItem` `kind` with a
required payload shape. Useful community packages here are *schema packs*: a
bundle of validated work-item and operating-unit types for a domain (a
code-review schema pack, a research-claim schema pack), so custom types are
type-safe, not just allowed.

## Authoring a package

1. Start from the `starter-firm` layout (`distro/starter-firm/`): a
   `package.yaml` manifest and a `files/` tree.
2. Keep authority narrow — every role's `authorized_paths` and mandate should
   grant the least the role needs.
3. Verify it boots: an installed organization must pass `boot_check` (one
   authority role, escalation reaches it, mandates resolve).
4. Validate the manifest with `cognitive-firm-distro show <package>`.
5. Publish it as a git repository — a package is just a repo with a
   `package.yaml`; there is no central registry to clear.

The kernel stays generic. A distro or overlay is policy; composing one must
never require a kernel change.
