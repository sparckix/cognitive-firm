"""Tests for O3-P1 package signing — the bootstrap trust root.

Covers the canonical content hash, Ed25519 sign/verify, the local trust store,
the manifest ``signing`` block, and the installer's verify-or-refuse wiring.
The load-bearing invariant: signed packages are gated, unsigned packages still
install (``starter-firm`` must not break).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from cognitive_firm.distribution import InstallError, install, load_receipt
from cognitive_firm.distribution.manifest import (
    ManifestError,
    PackageManifest,
    SigningInfo,
    load_manifest,
)
from cognitive_firm.distribution.signing import (
    SigningError,
    add_trusted_publisher,
    canonical_content_hash,
    generate_keypair,
    get_trusted_publisher_key,
    list_trusted_publishers,
    sign_package,
    verify_against_trust_store,
    verify_package_signature,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER = REPO_ROOT / "distro" / "starter-firm"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _make_package(root: Path) -> Path:
    """Build a genuinely bootable package by copying the starter-firm distro.

    Using real distro files means ``install`` actually boots — so the signing
    tests exercise the real install path, not a stub. The copy is mutable, so
    a test can tamper with it after signing.
    """
    pkg = root / "pkg"
    shutil.copytree(STARTER, pkg)
    return pkg


def _signable_file(pkg: Path) -> Path:
    """A file under the package's files/ a test can tamper with."""
    return pkg / "files" / "roles" / "analyst.yaml"


# --------------------------------------------------------------------------
# Canonical content hash
# --------------------------------------------------------------------------


def test_content_hash_is_stable_and_self_describing(tmp_path):
    pkg = _make_package(tmp_path)
    h1 = canonical_content_hash(pkg)
    h2 = canonical_content_hash(pkg)
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_content_hash_changes_when_a_file_changes(tmp_path):
    pkg = _make_package(tmp_path)
    before = canonical_content_hash(pkg)
    _signable_file(pkg).write_text(
        _signable_file(pkg).read_text() + "\n# tampered\n"
    )
    assert canonical_content_hash(pkg) != before


def test_content_hash_changes_when_manifest_changes(tmp_path):
    pkg = _make_package(tmp_path)
    before = canonical_content_hash(pkg)
    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    raw["version"] = "9.9.9"
    (pkg / "package.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    assert canonical_content_hash(pkg) != before


def test_content_hash_ignores_signing_block(tmp_path):
    """Writing the signature back into the manifest must not change the hash —
    sign and verify would otherwise never agree."""
    pkg = _make_package(tmp_path)
    before = canonical_content_hash(pkg)
    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    raw["signing"] = {"publisher": "acme", "signature": "abcd"}
    (pkg / "package.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    assert canonical_content_hash(pkg) == before


def test_content_hash_ignores_yaml_cosmetics(tmp_path):
    """Re-serializing the manifest with reordered keys must not change the
    hash — the hash is over semantics, not formatting."""
    pkg = _make_package(tmp_path)
    before = canonical_content_hash(pkg)
    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    (pkg / "package.yaml").write_text(
        yaml.safe_dump(dict(reversed(list(raw.items()))), sort_keys=False)
    )
    assert canonical_content_hash(pkg) == before


def test_content_hash_ignores_cognitive_firm_dir(tmp_path):
    """The receipt/lock/trust dir is an install side effect, not package
    content — it must not perturb the signable hash."""
    pkg = _make_package(tmp_path)
    before = canonical_content_hash(pkg)
    noise = pkg / ".cognitive-firm"
    noise.mkdir()
    (noise / "receipt.json").write_text("{}")
    assert canonical_content_hash(pkg) == before


def test_content_hash_rejects_non_package(tmp_path):
    with pytest.raises(SigningError):
        canonical_content_hash(tmp_path / "missing")
    (tmp_path / "empty").mkdir()
    with pytest.raises(SigningError):
        canonical_content_hash(tmp_path / "empty")


# --------------------------------------------------------------------------
# Keypair + sign/verify
# --------------------------------------------------------------------------


def test_generate_keypair_produces_pem():
    kp = generate_keypair()
    assert "PRIVATE KEY" in kp.private_pem
    assert "PUBLIC KEY" in kp.public_pem
    assert generate_keypair().private_pem != kp.private_pem


def test_sign_then_verify_roundtrip(tmp_path):
    pkg = _make_package(tmp_path)
    kp = generate_keypair()
    sig = sign_package(pkg, kp.private_pem)
    assert verify_package_signature(pkg, sig, kp.public_pem) is True


def test_verify_fails_for_tampered_package(tmp_path):
    pkg = _make_package(tmp_path)
    kp = generate_keypair()
    sig = sign_package(pkg, kp.private_pem)
    _signable_file(pkg).write_text(
        _signable_file(pkg).read_text() + "\n# evil\n"
    )
    assert verify_package_signature(pkg, sig, kp.public_pem) is False


def test_verify_fails_for_wrong_key(tmp_path):
    pkg = _make_package(tmp_path)
    signer = generate_keypair()
    other = generate_keypair()
    sig = sign_package(pkg, signer.private_pem)
    assert verify_package_signature(pkg, sig, other.public_pem) is False


def test_verify_raises_on_unusable_inputs(tmp_path):
    pkg = _make_package(tmp_path)
    kp = generate_keypair()
    with pytest.raises(SigningError):
        verify_package_signature(pkg, "not-hex!!", kp.public_pem)
    with pytest.raises(SigningError):
        verify_package_signature(pkg, "ab", "not a pem")
    with pytest.raises(SigningError):
        sign_package(pkg, "not a pem")


# --------------------------------------------------------------------------
# Trust store
# --------------------------------------------------------------------------


def test_trust_store_add_get_list(tmp_path):
    assert list_trusted_publishers(tmp_path) == []
    kp_a = generate_keypair()
    kp_b = generate_keypair()
    path = add_trusted_publisher(tmp_path, "acme", kp_a.public_pem)
    add_trusted_publisher(tmp_path, "globex", kp_b.public_pem)
    assert path.name == "acme.pub"
    assert path.parent == tmp_path / ".cognitive-firm" / "trusted_publishers"
    assert list_trusted_publishers(tmp_path) == ["acme", "globex"]
    assert get_trusted_publisher_key(tmp_path, "acme") == kp_a.public_pem
    assert get_trusted_publisher_key(tmp_path, "nobody") is None


def test_trust_store_rejects_bad_key_and_bad_name(tmp_path):
    with pytest.raises(SigningError):
        add_trusted_publisher(tmp_path, "acme", "not a pem")
    kp = generate_keypair()
    with pytest.raises(SigningError):
        add_trusted_publisher(tmp_path, "../escape", kp.public_pem)


def test_verify_against_trust_store(tmp_path):
    pkg = _make_package(tmp_path / "p")
    kp = generate_keypair()
    sig = sign_package(pkg, kp.private_pem)
    trust = tmp_path / "org"
    trust.mkdir()
    # Untrusted publisher is a structural error, not a False result.
    with pytest.raises(SigningError):
        verify_against_trust_store(pkg, "acme", sig, trust_root=trust)
    add_trusted_publisher(trust, "acme", kp.public_pem)
    assert verify_against_trust_store(pkg, "acme", sig, trust_root=trust) is True


# --------------------------------------------------------------------------
# Manifest signing block
# --------------------------------------------------------------------------


def test_manifest_signing_block_parses():
    raw = {"publisher": "acme", "signature": "deadbeef"}
    info = SigningInfo.from_raw(raw)
    assert info.publisher == "acme"
    assert info.signature == "deadbeef"


def test_manifest_signing_block_requires_both_fields():
    with pytest.raises(ManifestError):
        SigningInfo.from_raw({"publisher": "acme"})
    with pytest.raises(ManifestError):
        SigningInfo.from_raw({"signature": "deadbeef"})


def test_manifest_without_signing_block_is_none():
    m = PackageManifest.from_raw(
        {
            "name": "x",
            "version": "0.1.0",
            "kind": "overlay",
            "description": "no signing block here at all",
            "components": [{"source": "a"}],
        }
    )
    assert m.signing is None


def test_manifest_from_raw_parses_signing_block():
    m = PackageManifest.from_raw(
        {
            "name": "x",
            "version": "0.1.0",
            "kind": "overlay",
            "description": "a signed overlay manifest for the test",
            "components": [{"source": "a"}],
            "signing": {"publisher": "acme", "signature": "abcd"},
        }
    )
    assert m.signing == SigningInfo(publisher="acme", signature="abcd")


def test_starter_firm_is_unsigned():
    """starter-firm is the in-repo unsigned distro — it must stay unsigned."""
    manifest = load_manifest(STARTER / "package.yaml")
    assert manifest.signing is None


# --------------------------------------------------------------------------
# Installer wiring
# --------------------------------------------------------------------------


def test_unsigned_package_installs_with_signature_not_verified(tmp_path):
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    manifest = load_manifest(pkg / "package.yaml")
    receipt = install(manifest, pkg, target, kernel_version="0.1.0")
    assert receipt.signature_verified is False
    on_disk = load_receipt(target, "starter-firm")
    assert on_disk.signature_verified is False


def test_signed_package_installs_and_records_verified(tmp_path):
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    target.mkdir()
    kp = generate_keypair()
    add_trusted_publisher(target, "acme", kp.public_pem)
    sig = sign_package(pkg, kp.private_pem)

    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    raw["signing"] = {"publisher": "acme", "signature": sig}
    (pkg / "package.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))

    manifest = load_manifest(pkg / "package.yaml")
    receipt = install(manifest, pkg, target, kernel_version="0.1.0")
    assert receipt.signature_verified is True


def test_install_refuses_bad_signature(tmp_path):
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    target.mkdir()
    kp = generate_keypair()
    add_trusted_publisher(target, "acme", kp.public_pem)
    sig = sign_package(pkg, kp.private_pem)

    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    raw["signing"] = {"publisher": "acme", "signature": sig}
    (pkg / "package.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    # Tamper a file AFTER signing — the signature no longer covers the bytes.
    _signable_file(pkg).write_text(
        _signable_file(pkg).read_text() + "\n# evil\n"
    )

    manifest = load_manifest(pkg / "package.yaml")
    with pytest.raises(InstallError, match="does not verify"):
        install(manifest, pkg, target, kernel_version="0.1.0")
    # Refusal happens before mutation — nothing landed.
    assert not (target / "roles").exists()


def test_install_refuses_untrusted_publisher(tmp_path):
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    target.mkdir()
    kp = generate_keypair()
    sig = sign_package(pkg, kp.private_pem)

    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    raw["signing"] = {"publisher": "stranger", "signature": sig}
    (pkg / "package.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))

    manifest = load_manifest(pkg / "package.yaml")
    with pytest.raises(InstallError, match="not in the trust store"):
        install(manifest, pkg, target, kernel_version="0.1.0")


# --------------------------------------------------------------------------
# Downgrade-resistant trust policy
# --------------------------------------------------------------------------


def test_populated_trust_store_refuses_unsigned_package(tmp_path):
    """Once an org trusts any publisher it has opted into signing — an unsigned
    package must be refused, not silently accepted as ``signature_verified:
    false``."""
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    target.mkdir()
    kp = generate_keypair()
    add_trusted_publisher(target, "acme", kp.public_pem)

    manifest = load_manifest(pkg / "package.yaml")  # starter-firm: unsigned
    assert manifest.signing is None
    with pytest.raises(InstallError, match="unsigned"):
        install(manifest, pkg, target, kernel_version="0.1.0")
    # Refusal happens before mutation — nothing landed.
    assert not (target / "roles").exists()


def test_populated_trust_store_refuses_signature_stripped_package(tmp_path):
    """The downgrade attack: take a signed package, tamper a file, delete the
    ``signing:`` block, install. With a populated trust store it is refused."""
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    target.mkdir()
    kp = generate_keypair()
    add_trusted_publisher(target, "acme", kp.public_pem)
    sig = sign_package(pkg, kp.private_pem)

    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    raw["signing"] = {"publisher": "acme", "signature": sig}
    (pkg / "package.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    # Attacker tampers a file then strips the signing block.
    _signable_file(pkg).write_text(
        _signable_file(pkg).read_text() + "\n# evil\n"
    )
    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    raw.pop("signing", None)
    (pkg / "package.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))

    manifest = load_manifest(pkg / "package.yaml")
    assert manifest.signing is None
    with pytest.raises(InstallError, match="unsigned"):
        install(manifest, pkg, target, kernel_version="0.1.0")
    assert not (target / "roles").exists()


def test_empty_trust_store_still_installs_unsigned_bootstrap(tmp_path):
    """The bootstrap path: a brand-new org with no trust store installs an
    unsigned package, recorded ``signature_verified: false`` — unchanged."""
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    manifest = load_manifest(pkg / "package.yaml")
    receipt = install(manifest, pkg, target, kernel_version="0.1.0")
    assert receipt.signature_verified is False
    assert (target / "roles").exists()


def test_require_signed_refuses_unsigned_even_with_empty_trust_store(tmp_path):
    """The explicit opt-in: require_signed refuses an unsigned package even
    when the trust store is empty."""
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    manifest = load_manifest(pkg / "package.yaml")
    with pytest.raises(InstallError, match="require_signed"):
        install(
            manifest, pkg, target, kernel_version="0.1.0", require_signed=True
        )
    assert not (target / "roles").exists()


def test_signed_package_from_trusted_publisher_still_installs(tmp_path):
    """Regression: a properly signed package from a trusted publisher installs,
    with the trust-store-non-empty rule active."""
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    target.mkdir()
    kp = generate_keypair()
    add_trusted_publisher(target, "acme", kp.public_pem)
    sig = sign_package(pkg, kp.private_pem)
    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    raw["signing"] = {"publisher": "acme", "signature": sig}
    (pkg / "package.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))

    manifest = load_manifest(pkg / "package.yaml")
    receipt = install(
        manifest, pkg, target, kernel_version="0.1.0", require_signed=True
    )
    assert receipt.signature_verified is True
    assert (target / "roles").exists()


def test_signed_install_event_records_signature_verified(tmp_path):
    pkg = _make_package(tmp_path / "src")
    target = tmp_path / "org"
    target.mkdir()
    kp = generate_keypair()
    add_trusted_publisher(target, "acme", kp.public_pem)
    sig = sign_package(pkg, kp.private_pem)
    raw = yaml.safe_load((pkg / "package.yaml").read_text())
    raw["signing"] = {"publisher": "acme", "signature": sig}
    (pkg / "package.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))

    manifest = load_manifest(pkg / "package.yaml")
    install(manifest, pkg, target, kernel_version="0.1.0")

    events_log = target / ".cognitive-firm" / "distribution-events.jsonl"
    events = [json.loads(line) for line in events_log.read_text().splitlines()]
    installed = [e for e in events if e["verb"] == "package.installed"]
    assert installed and installed[-1]["payload"]["signature_verified"] is True
