from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from althea_mcp.errors import AltheaConfigurationError
from althea_mcp.models import StoredCredentials


def load_credentials(path: Path) -> StoredCredentials | None:
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return StoredCredentials.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise AltheaConfigurationError(
            f"Could not read Althea MCP credentials from {path}: {exc}"
        ) from exc


def save_credentials(path: Path, credentials: StoredCredentials) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
        )
        temporary_path = Path(temporary_name)
        file_descriptor_chmod = getattr(os, "fchmod", None)
        if file_descriptor_chmod is not None:
            file_descriptor_chmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            json.dump(
                credentials.model_dump(mode="json"),
                temporary_file,
                indent=2,
            )
            temporary_file.write("\n")
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        raise AltheaConfigurationError(
            f"Could not save Althea MCP credentials to {path}: {exc}"
        ) from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
