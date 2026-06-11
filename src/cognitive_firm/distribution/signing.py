"""Distribution-layer package signing (O3-P1, constraint 4).

The first authority-bearing files of a distro (its ``roles/``, ``mandates/``)
are written onto an empty directory *before any governed event exists*. A
tampered distro would seed untrusted root authority and nothing downstream
could detect it, because every later governance check trusts those files. That
is the **bootstrap trust hole** — a genuine trust-root problem that cannot be
closed by a governed event, because there is no prior authority to govern
against.

This module closes it as far as it can be closed: with **provenance**. A
package directory is signed with a detached Ed25519 signature over a *canonical
content hash* of `package.yaml` plus every file under `files/`. An installer
that trusts the publisher's public key can then verify, before install, that
the bytes are exactly what that publisher signed.

What this does NOT do — and the honest residual — is turn trust into proof.
Verifying a signature only moves the question to "do you trust this publisher's
key." The trust store (``.cognitive-firm/trusted_publishers/<publisher>.pub``)
is populated by an out-of-band human decision; signing makes that decision
*explicit and auditable* rather than implicit. An **unsigned** package (e.g.
the in-repo ``starter-firm``) is still installable — the installer records
``signature_verified: false`` — so signing is additive, never a gate that
breaks existing distros.

This is package-manager (userland) layer — no kernel change.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from cognitive_firm.distribution.manifest import FILES_DIRNAME

# The manifest file at a package root that is covered by the signature
# alongside everything under files/.
MANIFEST_FILENAME = "package.yaml"

# The manifest key that carries the signature itself. It is stripped from the
# manifest before hashing — otherwise adding the signature would change the
# very hash the signature is computed over (a chicken-and-egg deadlock).
SIGNING_KEY = "signing"

# Local trust store: one public key per trusted publisher, under an org's
# (or the operator's) .cognitive-firm/ directory.
TRUST_STORE_DIRNAME = ".cognitive-firm"
TRUSTED_PUBLISHERS_DIRNAME = "trusted_publishers"
PUBLIC_KEY_SUFFIX = ".pub"


class SigningError(RuntimeError):
    """Raised when signing, verification, or trust-store handling fails."""


# --------------------------------------------------------------------------
# Canonical content hash
# --------------------------------------------------------------------------


def _canonical_manifest_bytes(manifest_path: Path) -> bytes:
    """Return the manifest's signable bytes: parsed, ``signing`` stripped,
    re-serialized canonically.

    The ``signing`` block is removed before hashing so that signing a package
    and then writing the signature back into ``package.yaml`` does not change
    the hash — otherwise sign and verify would never agree. Re-serializing with
    sorted keys also makes the hash robust to YAML cosmetic reordering.
    """
    try:
        raw = yaml.safe_load(manifest_path.read_text())
    except yaml.YAMLError as exc:
        raise SigningError(
            f"cannot parse {manifest_path} for hashing: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise SigningError(f"manifest is not a mapping: {manifest_path}")
    raw.pop(SIGNING_KEY, None)
    return yaml.safe_dump(raw, sort_keys=True).encode("utf-8")


def canonical_content_hash(package_root: Path) -> str:
    """Return a stable content hash over a package's signable bytes.

    The hash covers ``package.yaml`` at the package root (with its ``signing``
    block stripped — see :func:`_canonical_manifest_bytes`) plus every file
    under ``files/``. It mirrors ``lockfile.hash_directory``'s scheme so the
    two hashes stay consistent and reviewable: each member contributes its
    POSIX-relative path, a NUL, its bytes, and a NUL; members are sorted by
    relative path; the digest is SHA-256. The result is ``sha256:<hex>`` so the
    algorithm is self-describing.

    Only ``package.yaml`` + ``files/`` are covered — never ``.git``, never the
    ``.cognitive-firm`` receipt/lock/trust directory — so the hash is
    deterministic and a package signs itself, not its install side effects.
    """
    package_root = Path(package_root)
    if not package_root.is_dir():
        raise SigningError(f"not a package directory: {package_root}")

    manifest = package_root / MANIFEST_FILENAME
    if not manifest.is_file():
        raise SigningError(
            f"package has no {MANIFEST_FILENAME}: {package_root}"
        )

    members: list[tuple[str, bytes]] = [
        (MANIFEST_FILENAME, _canonical_manifest_bytes(manifest))
    ]
    files_root = package_root / FILES_DIRNAME
    if files_root.is_dir():
        for path in files_root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(package_root).as_posix()
            members.append((rel, path.read_bytes()))

    digest = hashlib.sha256()
    for rel_posix, content in sorted(members, key=lambda m: m[0]):
        digest.update(rel_posix.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


# --------------------------------------------------------------------------
# Keypair generation and (de)serialization
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Keypair:
    """An Ed25519 keypair, PEM-encoded for storage.

    ``private_pem`` is the secret half — never write it into a trust store or
    a repo. ``public_pem`` is what a publisher distributes; it lands in an
    operator's trust store as ``<publisher>.pub``.
    """

    private_pem: str
    public_pem: str


def generate_keypair() -> Keypair:
    """Generate a fresh Ed25519 keypair, PEM-encoded.

    The private key is PKCS#8 / unencrypted PEM; the public key is
    SubjectPublicKeyInfo PEM. A publisher keeps the private PEM secret and ships
    the public PEM for operators to add to their trust store.
    """
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return Keypair(private_pem=private_pem, public_pem=public_pem)


def _load_private_key(private_pem: str) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(
            private_pem.encode("utf-8"), password=None
        )
    except (ValueError, TypeError) as exc:
        raise SigningError(f"cannot load private key: {exc}") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningError("private key is not an Ed25519 key")
    return key


def _load_public_key(public_pem: str) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(public_pem.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise SigningError(f"cannot load public key: {exc}") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise SigningError("public key is not an Ed25519 key")
    return key


def validate_public_key(public_pem: str) -> None:
    """Raise ``SigningError`` unless ``public_pem`` is an Ed25519 public key."""
    _load_public_key(public_pem)


# --------------------------------------------------------------------------
# Sign / verify
# --------------------------------------------------------------------------


def sign_package(package_root: Path, private_key: str) -> str:
    """Return a detached Ed25519 signature over a package's canonical hash.

    ``private_key`` is a PEM string (the secret half of a :func:`generate_keypair`
    result). The signature is computed over the UTF-8 bytes of
    :func:`canonical_content_hash` and returned as lowercase hex — a compact,
    text-safe form suitable for the manifest ``signing.signature`` field.
    """
    key = _load_private_key(private_key)
    content_hash = canonical_content_hash(package_root)
    signature = key.sign(content_hash.encode("utf-8"))
    return signature.hex()


def sign_message(message: bytes, private_key: str) -> str:
    """Return a detached Ed25519 signature over arbitrary bytes.

    This is shared by package signing and provider-payload signing. Callers own
    the canonicalization of ``message`` before signing.
    """
    key = _load_private_key(private_key)
    return key.sign(message).hex()


def verify_message_signature(message: bytes, signature: str, public_key: str) -> bool:
    """Return True iff ``signature`` is a valid Ed25519 signature of bytes."""
    key = _load_public_key(public_key)
    try:
        raw_sig = bytes.fromhex(signature)
    except ValueError as exc:
        raise SigningError(f"signature is not valid hex: {exc}") from exc
    try:
        key.verify(raw_sig, message)
    except InvalidSignature:
        return False
    return True


def verify_package_signature(
    package_root: Path, signature: str, public_key: str
) -> bool:
    """Return True iff ``signature`` is a valid signature of ``package_root``.

    Recomputes the package's canonical content hash and checks the detached
    Ed25519 ``signature`` (hex) against it with the publisher's ``public_key``
    (PEM). Returns ``False`` on a bad signature or a tampered package; raises
    :class:`SigningError` only when the inputs are structurally unusable (an
    unparseable key, a non-hex signature, a missing package).
    """
    content_hash = canonical_content_hash(package_root)
    return verify_message_signature(content_hash.encode("utf-8"), signature, public_key)


# --------------------------------------------------------------------------
# Local trust store
# --------------------------------------------------------------------------


def trust_store_dir(root: Path) -> Path:
    """The trusted-publishers directory under ``root``'s ``.cognitive-firm/``."""
    return (
        Path(root) / TRUST_STORE_DIRNAME / TRUSTED_PUBLISHERS_DIRNAME
    )


def _publisher_key_path(root: Path, publisher: str) -> Path:
    publisher = str(publisher).strip()
    if not publisher or "/" in publisher or publisher.startswith("."):
        raise SigningError(f"invalid publisher name: {publisher!r}")
    return trust_store_dir(root) / f"{publisher}{PUBLIC_KEY_SUFFIX}"


def add_trusted_publisher(
    root: Path, publisher: str, public_key: str
) -> Path:
    """Add (or replace) a publisher's public key in the local trust store.

    The key is stored at ``.cognitive-firm/trusted_publishers/<publisher>.pub``.
    The PEM is validated as a real Ed25519 public key before it is written, so
    a malformed key never enters the store. Returns the written path.

    Adding a key here IS the trust decision — see this module's docstring on the
    residual assumption: signature verification proves only that the publisher
    whose key is in this directory signed the bytes.
    """
    key_path = _publisher_key_path(root, publisher)
    _load_public_key(public_key)  # validate before persisting
    key_path.parent.mkdir(parents=True, exist_ok=True)
    pem = public_key if public_key.endswith("\n") else public_key + "\n"
    key_path.write_text(pem, encoding="utf-8")
    return key_path


def get_trusted_publisher_key(root: Path, publisher: str) -> str | None:
    """Return a trusted publisher's stored public-key PEM, or None if absent."""
    key_path = _publisher_key_path(root, publisher)
    if not key_path.is_file():
        return None
    return key_path.read_text(encoding="utf-8")


def list_trusted_publishers(root: Path) -> list[str]:
    """Return the sorted names of every publisher in the local trust store."""
    store = trust_store_dir(root)
    if not store.is_dir():
        return []
    return sorted(
        p.name[: -len(PUBLIC_KEY_SUFFIX)]
        for p in store.iterdir()
        if p.is_file() and p.name.endswith(PUBLIC_KEY_SUFFIX)
    )


def trust_store_is_populated(root: Path) -> bool:
    """True iff ``root``'s trust store holds at least one trusted publisher.

    This is the downgrade-resistance signal: once an org has opted into signing
    by trusting any publisher, an unsigned package must be refused — accepting
    it silently would let an attacker strip a ``signing:`` block and defeat the
    very protection the org opted into. An empty or absent trust store means the
    org has not opted in (the bootstrap case), so an unsigned package may still
    install.
    """
    return bool(list_trusted_publishers(root))


def verify_against_trust_store(
    package_root: Path, publisher: str, signature: str, *, trust_root: Path
) -> bool:
    """Verify a package's signature against a publisher in the trust store.

    Looks up ``publisher`` in ``trust_root``'s trust store and verifies
    ``signature`` against the package. Raises :class:`SigningError` if the
    publisher is not trusted (no key on file) — refusing is the caller's job,
    but an untrusted publisher is a structurally unusable input, not a merely
    bad signature. Returns the boolean verification result otherwise.
    """
    public_key = get_trusted_publisher_key(trust_root, publisher)
    if public_key is None:
        raise SigningError(
            f"publisher '{publisher}' is not in the trust store at "
            f"{trust_store_dir(trust_root)} — add its public key with "
            f"add_trusted_publisher() before installing a signed package"
        )
    return verify_package_signature(package_root, signature, public_key)
