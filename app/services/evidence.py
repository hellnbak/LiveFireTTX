from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo
import hmac
import json
import os
import re
import secrets
import stat

from app.models import Exercise
from app.services.paths import exercise_package_path


EVIDENCE_FORMAT = "livefirettx-evidence"
EVIDENCE_SCHEMA_VERSION = 4
SIGNATURE_SCHEMA_VERSION = 1
SIGNATURE_ALGORITHM = "hmac-sha256"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 32
ARCHIVE_NAME_PATTERN = re.compile(
    r"evidence-[0-9]{8}T[0-9]{12}Z-[a-f0-9]{8}\.zip"
)
KEY_BYTES = 32


class EvidenceVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceArchiveRecord:
    filename: str
    size_bytes: int
    created_at: str
    valid: bool
    key_id: str | None


def load_or_create_signing_key(path: Path) -> bytes:
    source = _safe_source_path(path, "Evidence signing key")
    source.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        return load_signing_key(source)
    key = secrets.token_bytes(KEY_BYTES)
    try:
        descriptor = os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return load_signing_key(source)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(urlsafe_b64encode(key) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return key


def load_signing_key(path: Path) -> bytes:
    source = _safe_source_path(path, "Evidence signing key")
    if not source.is_file():
        raise ValueError("Evidence signing key must be a regular file")
    source_stat = source.stat()
    if source_stat.st_size > 4096:
        raise ValueError("Evidence signing key file is too large")
    if os.name == "posix" and source_stat.st_mode & 0o077:
        raise ValueError("Evidence signing key permissions must be owner-only")
    try:
        key = urlsafe_b64decode(source.read_bytes().strip())
    except ValueError as exc:
        raise ValueError("Evidence signing key is not valid base64") from exc
    if len(key) != KEY_BYTES:
        raise ValueError("Evidence signing key must decode to 32 bytes")
    return key


def signing_key_id(key: bytes) -> str:
    _validate_key(key)
    return sha256(key).hexdigest()[:16]


def build_signed_archive(
    *,
    exercise: Exercise,
    exercise_clock: Mapping[str, Any],
    files: Mapping[str, bytes],
    signing_key: bytes,
    generated_at: datetime | None = None,
) -> bytes:
    _validate_key(signing_key)
    if not files:
        raise ValueError("Evidence archive must contain at least one evidence file")
    normalized_files: dict[str, bytes] = {}
    for filename, content in files.items():
        safe_name = _validate_member_name(filename)
        if safe_name in {"manifest.json", "manifest.sig"}:
            raise ValueError("Evidence files cannot replace manifest entries")
        if not isinstance(content, bytes):
            raise TypeError("Evidence file content must be bytes")
        normalized_files[safe_name] = content

    generated = generated_at or datetime.now(timezone.utc)
    key_id = signing_key_id(signing_key)
    manifest = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "format": EVIDENCE_FORMAT,
        "exercise_id": exercise.id,
        "exercise_clock": dict(exercise_clock),
        "generated_at": generated.astimezone(timezone.utc).isoformat(),
        "signature": {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": key_id,
            "signature_file": "manifest.sig",
        },
        "files": [
            {
                "path": filename,
                "size_bytes": len(content),
                "sha256": sha256(content).hexdigest(),
            }
            for filename, content in sorted(normalized_files.items())
        ],
    }
    manifest_bytes = json.dumps(
        manifest,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    signature = hmac.new(signing_key, manifest_bytes, sha256).digest()
    signature_bytes = json.dumps(
        {
            "schema_version": SIGNATURE_SCHEMA_VERSION,
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": key_id,
            "manifest_sha256": sha256(manifest_bytes).hexdigest(),
            "signature": urlsafe_b64encode(signature).decode().rstrip("="),
        },
        indent=2,
        sort_keys=True,
    ).encode("utf-8")

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for filename, content in sorted(normalized_files.items()):
            archive.writestr(filename, content)
        archive.writestr("manifest.json", manifest_bytes)
        archive.writestr("manifest.sig", signature_bytes)
    payload = output.getvalue()
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("Evidence archive exceeds the supported size")
    return payload


def verify_evidence_archive(path: Path, signing_key: bytes) -> dict[str, Any]:
    _validate_key(signing_key)
    source = _safe_source_path(path, "Evidence archive")
    if not source.is_file():
        raise EvidenceVerificationError("Evidence archive does not exist")
    if source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise EvidenceVerificationError("Evidence archive exceeds the supported size")
    try:
        with ZipFile(source) as archive:
            return _verify_open_archive(archive, signing_key)
    except BadZipFile as exc:
        raise EvidenceVerificationError("Evidence archive is not a valid ZIP file") from exc


def save_evidence_archive(
    exercise: Exercise,
    payload: bytes,
    *,
    retention_days: int,
    retention_count: int,
    now: datetime | None = None,
) -> EvidenceArchiveRecord:
    if not 1 <= retention_days <= 36500:
        raise ValueError("Evidence retention days must be between 1 and 36500")
    if not 1 <= retention_count <= 10000:
        raise ValueError("Evidence retention count must be between 1 and 10000")
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("Evidence archive exceeds the supported size")
    created = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    archive_root = _archive_root(exercise)
    archive_root.mkdir(parents=True, exist_ok=True)
    filename = (
        f"evidence-{created.strftime('%Y%m%dT%H%M%S%fZ')}-"
        f"{secrets.token_hex(4)}.zip"
    )
    destination = archive_root / filename
    with destination.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.utime(destination, (created.timestamp(), created.timestamp()))
    _prune_archives(
        exercise,
        retention_days=retention_days,
        retention_count=retention_count,
        now=created,
    )
    return EvidenceArchiveRecord(
        filename=filename,
        size_bytes=len(payload),
        created_at=created.isoformat(),
        valid=True,
        key_id=None,
    )


def list_evidence_archives(
    exercise: Exercise,
    signing_key: bytes | None = None,
    *,
    limit: int = 25,
) -> list[EvidenceArchiveRecord]:
    if not 1 <= limit <= 100:
        raise ValueError("Evidence archive list limit must be between 1 and 100")
    archive_root = _archive_root(exercise)
    if not archive_root.is_dir():
        return []
    records = []
    for path in _known_archives(archive_root)[:limit]:
        valid = False
        key_id = None
        if signing_key is not None:
            try:
                verification = verify_evidence_archive(path, signing_key)
                valid = True
                key_id = str(verification["key_id"])
            except EvidenceVerificationError:
                pass
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        records.append(
            EvidenceArchiveRecord(
                filename=path.name,
                size_bytes=path.stat().st_size,
                created_at=modified.isoformat(),
                valid=valid,
                key_id=key_id,
            )
        )
    return records


def read_retained_archive(
    exercise: Exercise,
    filename: str,
    signing_key: bytes,
) -> bytes:
    if not ARCHIVE_NAME_PATTERN.fullmatch(filename):
        raise EvidenceVerificationError("Evidence archive name is invalid")
    path = next(
        (
            candidate
            for candidate in _known_archives(_archive_root(exercise))
            if hmac.compare_digest(candidate.name, filename)
        ),
        None,
    )
    if path is None:
        raise EvidenceVerificationError("Evidence archive was not found")
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise EvidenceVerificationError("Evidence archive exceeds the supported size")
    verify_evidence_archive(path, signing_key)
    return path.read_bytes()


def existing_key_id(path: Path) -> str | None:
    if not path.exists():
        return None
    return signing_key_id(load_signing_key(path))


def _verify_open_archive(archive: ZipFile, signing_key: bytes) -> dict[str, Any]:
    members = archive.infolist()
    if len(members) > MAX_MEMBERS:
        raise EvidenceVerificationError("Evidence archive contains too many files")
    names: set[str] = set()
    total_size = 0
    for member in members:
        name = _validate_member_name(member.filename, EvidenceVerificationError)
        if name in names:
            raise EvidenceVerificationError("Evidence archive contains duplicate files")
        if _is_symlink(member):
            raise EvidenceVerificationError("Evidence archive contains a symbolic link")
        if _is_unsupported_file_type(member):
            raise EvidenceVerificationError("Evidence archive contains a non-regular file")
        names.add(name)
        total_size += member.file_size
        if total_size > MAX_UNCOMPRESSED_BYTES:
            raise EvidenceVerificationError("Evidence archive expands beyond the size limit")
    if not {"manifest.json", "manifest.sig"}.issubset(names):
        raise EvidenceVerificationError("Evidence archive is missing signature metadata")
    manifest_bytes = archive.read("manifest.json")
    signature_bytes = archive.read("manifest.sig")
    try:
        manifest = json.loads(manifest_bytes)
        signature = json.loads(signature_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceVerificationError("Evidence signature metadata is invalid") from exc
    if not isinstance(manifest, dict) or not isinstance(signature, dict):
        raise EvidenceVerificationError("Evidence signature metadata is invalid")
    if manifest.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise EvidenceVerificationError("Evidence manifest schema is unsupported")
    if manifest.get("format") != EVIDENCE_FORMAT:
        raise EvidenceVerificationError("Evidence manifest format is invalid")
    expected_key_id = signing_key_id(signing_key)
    manifest_signature = manifest.get("signature", {})
    if not isinstance(manifest_signature, dict):
        raise EvidenceVerificationError("Evidence manifest signature metadata is invalid")
    if (
        signature.get("schema_version") != SIGNATURE_SCHEMA_VERSION
        or signature.get("algorithm") != SIGNATURE_ALGORITHM
        or manifest_signature.get("algorithm") != SIGNATURE_ALGORITHM
        or signature.get("key_id") != expected_key_id
        or manifest_signature.get("key_id") != expected_key_id
        or manifest_signature.get("signature_file") != "manifest.sig"
    ):
        raise EvidenceVerificationError("Evidence signature key or algorithm does not match")
    if signature.get("manifest_sha256") != sha256(manifest_bytes).hexdigest():
        raise EvidenceVerificationError("Evidence manifest digest does not match")
    try:
        encoded_signature = str(signature["signature"])
        supplied_signature = urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
    except (KeyError, ValueError) as exc:
        raise EvidenceVerificationError("Evidence signature is invalid") from exc
    expected_signature = hmac.new(signing_key, manifest_bytes, sha256).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise EvidenceVerificationError("Evidence manifest signature is invalid")

    declared_files = manifest.get("files")
    if not isinstance(declared_files, list) or not declared_files:
        raise EvidenceVerificationError("Evidence manifest file list is invalid")
    expected_names = {"manifest.json", "manifest.sig"}
    for item in declared_files:
        if not isinstance(item, dict):
            raise EvidenceVerificationError("Evidence manifest file entry is invalid")
        filename = _validate_member_name(
            str(item.get("path", "")),
            EvidenceVerificationError,
        )
        if filename in expected_names:
            raise EvidenceVerificationError("Evidence manifest contains duplicate files")
        expected_names.add(filename)
        if filename not in names:
            raise EvidenceVerificationError("Evidence archive is missing a declared file")
        content = archive.read(filename)
        if item.get("size_bytes") != len(content):
            raise EvidenceVerificationError("Evidence file size does not match the manifest")
        if item.get("sha256") != sha256(content).hexdigest():
            raise EvidenceVerificationError("Evidence file digest does not match the manifest")
    if names != expected_names:
        raise EvidenceVerificationError("Evidence archive contains undeclared files")
    return {
        "valid": True,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "exercise_id": manifest.get("exercise_id"),
        "generated_at": manifest.get("generated_at"),
        "key_id": expected_key_id,
        "file_count": len(declared_files),
    }


def _archive_root(exercise: Exercise) -> Path:
    return exercise_package_path(exercise, "reports", "evidence")


def _known_archives(root: Path) -> list[Path]:
    paths = [
        path
        for path in root.iterdir()
        if ARCHIVE_NAME_PATTERN.fullmatch(path.name)
        and not path.is_symlink()
        and path.is_file()
    ]
    return sorted(paths, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)


def _prune_archives(
    exercise: Exercise,
    *,
    retention_days: int,
    retention_count: int,
    now: datetime,
) -> None:
    cutoff = now - timedelta(days=retention_days)
    for index, path in enumerate(_known_archives(_archive_root(exercise))):
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if index >= retention_count or modified < cutoff:
            path.unlink()


def _validate_member_name(
    name: str,
    error_type: type[ValueError] = ValueError,
) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or len(name) > 160
        or path.is_absolute()
        or "\\" in name
        or any(part in {"", ".", ".."} for part in path.parts)
        or len(path.parts) > 3
    ):
        raise error_type("Evidence archive contains an unsafe file name")
    return path.as_posix()


def _validate_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) != KEY_BYTES:
        raise ValueError("Evidence signing key must be 32 bytes")


def _is_symlink(member: ZipInfo) -> bool:
    return stat.S_ISLNK(member.external_attr >> 16)


def _is_unsupported_file_type(member: ZipInfo) -> bool:
    mode = member.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    return member.is_dir() or file_type not in {0, stat.S_IFREG}


def _safe_source_path(path: Path, label: str) -> Path:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink():
        raise EvidenceVerificationError(f"{label} cannot be a symbolic link")
    return candidate.parent.resolve() / candidate.name
