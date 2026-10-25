"""Loading extractor configs and auto-detecting the bank for a PDF."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from .models import ConfigError, ExtractorConfig


def _builtin_extractors_dir() -> Path:
    """The `extractors/` dir shipped alongside the package in the repo root."""
    # src/statement_parser/config.py -> repo root is three parents up.
    return Path(__file__).resolve().parents[2] / "extractors"


def load_extractors(config_dirs: list[Path]) -> list[ExtractorConfig]:
    """Load all *.yaml / *.yml extractor configs from the given directories.

    Raises ConfigError on the first malformed file so problems surface early.
    """
    extractors: list[ExtractorConfig] = []
    seen_names: dict[str, str] = {}
    seen_dirs: set[Path] = set()
    for d in config_dirs:
        if not d.is_dir():
            continue
        resolved = d.resolve()
        if resolved in seen_dirs:
            continue
        seen_dirs.add(resolved)
        for path in sorted(d.glob("*.y*ml")):
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                raise ConfigError(f"{path}: top-level YAML must be a mapping")
            cfg = ExtractorConfig.from_dict(data, source_path=str(path))
            if cfg.name in seen_names:
                raise ConfigError(
                    f"duplicate extractor name '{cfg.name}' in {path} "
                    f"(already defined in {seen_names[cfg.name]})"
                )
            seen_names[cfg.name] = str(path)
            extractors.append(cfg)
    return extractors


def resolve_config_dirs(extra: list[str] | None) -> list[Path]:
    """Build the ordered list of directories to search for extractor configs."""
    dirs: list[Path] = [_builtin_extractors_dir()]
    env = os.environ.get("STATEMENT_PARSER_CONFIG_DIR")
    if env:
        dirs.append(Path(env))
    for d in extra or []:
        dirs.append(Path(d))
    return dirs


def detect_bank(text: str, extractors: list[ExtractorConfig]) -> ExtractorConfig | None:
    """Return the first extractor whose signature matches the PDF text."""
    for cfg in extractors:
        for sig in cfg.match:
            if re.search(sig, text, re.IGNORECASE | re.MULTILINE):
                return cfg
    return None


def get_extractor(name: str, extractors: list[ExtractorConfig]) -> ExtractorConfig:
    """Return the named extractor, or raise ConfigError listing known banks."""
    for cfg in extractors:
        if cfg.name == name:
            return cfg
    known = ", ".join(sorted(c.name for c in extractors)) or "(none)"
    raise ConfigError(f"no extractor named '{name}'. Known banks: {known}")
