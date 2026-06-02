"""Sandboxed filesystem writer for the Executor agent."""

import json
import zipfile
from pathlib import Path
from uuid import UUID

from agencyos.config import settings


def conversation_dir(conversation_id: UUID) -> Path:
    p = settings.output_dir / str(conversation_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_text(conversation_id: UUID, filename: str, content: str) -> Path:
    target = conversation_dir(conversation_id) / filename
    target.write_text(content, encoding="utf-8")
    return target


def write_json(conversation_id: UUID, filename: str, payload: dict) -> Path:
    return write_text(conversation_id, filename, json.dumps(payload, indent=2, default=str))


def zip_bundle(conversation_id: UUID) -> Path:
    folder = conversation_dir(conversation_id)
    zip_path = folder.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in folder.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(folder.parent))
    return zip_path
