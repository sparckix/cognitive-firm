# Releasing `cognitive-firm` to PyPI

The kernel ships as a wheel: the importable `cognitive_firm` package plus the
bundled `distro/` tree (so `cognitive-firm-distro list` finds the starter
distro from a plain `pip install`). This is the checklist to cut a release.

The packaging is verified — a built wheel installs into a clean environment
and all three console scripts (`cognitive-firm-kernel-service`,
`cognitive-firm-distro`, `cognitive-firm-userland`) run. What remains for a
release is the steps below.

## 1. Pre-flight

- [ ] Full suite green: `.venv/bin/python -m pytest -q`.
- [ ] Version set in `pyproject.toml` `[project] version`. Follow semver;
      `0.1.0` is the current alpha line.
- [ ] `CHANGELOG`/release notes updated (what changed since the last tag).
- [ ] Runtime dependencies in `pyproject.toml` `[project] dependencies` match
      what the code actually imports — `requirements.txt` is for development
      and is **not** what the wheel ships. (Any new third-party import must be
      added to `dependencies`.)
- [ ] Working tree clean and committed.

## 2. Build

```bash
rm -rf dist build
.venv/bin/python -m pip install --upgrade build twine
.venv/bin/python -m build            # writes dist/*.whl and dist/*.tar.gz
.venv/bin/python -m twine check dist/*
```

## 3. Verify the artifact in a clean environment

```bash
python3 -m venv /tmp/cf-verify && source /tmp/cf-verify/bin/activate
pip install dist/cognitive_firm-*.whl
cognitive-firm-distro list           # must show the bundled starter-firm distro
cognitive-firm-userland vocabulary   # must print the glossary
python -c "import cognitive_firm; from cognitive_firm.distribution import signing"
deactivate
```

## 4. Upload

Credentials are **never** stored in the repo. Use a PyPI API token via
`~/.pypirc` or the `TWINE_USERNAME=__token__` / `TWINE_PASSWORD=<token>`
environment variables for the upload command only.

```bash
# Dry run first — TestPyPI:
.venv/bin/python -m twine upload --repository testpypi dist/*
# Then the real index:
.venv/bin/python -m twine upload dist/*
```

Then:

```bash
git tag v<version> && git push origin v<version>
```

## 5. Post-release

- [ ] `pip install cognitive-firm` from a clean machine resolves the new
      version and the CLIs run.
- [ ] Update `docs/getting-started.md` Path A — drop the note that the PyPI
      release is "not yet cut" once it is.
- [ ] **Rotate the PyPI API token** if it was ever pasted into a chat,
      terminal scrollback, or any non-secret store.

## Security note

Publishing to PyPI is irreversible — a released version cannot be re-uploaded,
only yanked. Verify step 3 before every upload. An API token grants publish
rights to the project; treat it as a secret and scope it to this project only.
