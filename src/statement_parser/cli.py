"""Command-line interface for pdf-statement-parser."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pdfplumber

from . import __version__
from .config import detect_bank, get_extractor, load_extractors, resolve_config_dirs
from .extract import ExtractionError, extract, read_full_text
from .models import ConfigError
from .output import to_csv, to_json
from .reconcile import reconcile

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_MATCH = 2
EXIT_RECON_FAILED = 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="statement-parser",
        description="Extract transaction data from machine-generated bank statement PDFs.",
    )
    p.add_argument(
        "pdf",
        type=Path,
        nargs="?",
        help="path to the statement PDF",
    )
    p.add_argument("--bank", help="force a specific extractor by name (skips auto-detect)")
    p.add_argument(
        "--config-dir",
        action="append",
        default=[],
        metavar="DIR",
        help="additional directory to load extractor configs from (repeatable)",
    )
    p.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="output format (default: csv)",
    )
    p.add_argument("-o", "--output", type=Path, help="write to a file instead of stdout")
    p.add_argument(
        "--strict",
        action="store_true",
        help="treat a balance reconciliation mismatch as an error (exit 3)",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="on no-match, dump the PDF's extracted text to stderr for authoring a config",
    )
    p.add_argument(
        "--list-banks",
        action="store_true",
        help="list the known extractors and exit",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config_dirs = resolve_config_dirs(args.config_dir)
        extractors = load_extractors(config_dirs)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.list_banks:
        if not extractors:
            print("no extractors found", file=sys.stderr)
            return EXIT_ERROR
        for cfg in sorted(extractors, key=lambda c: c.name):
            print(f"{cfg.name}\t({cfg.source_path})")
        return EXIT_OK

    if args.pdf is None:
        print("error: a PDF path is required (or use --list-banks)", file=sys.stderr)
        return EXIT_ERROR

    if not args.pdf.exists():
        print(f"error: no such file: {args.pdf}", file=sys.stderr)
        return EXIT_ERROR

    try:
        with pdfplumber.open(args.pdf) as pdf:
            if args.bank:
                try:
                    cfg = get_extractor(args.bank, extractors)
                except ConfigError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return EXIT_ERROR
            else:
                text = read_full_text(pdf)
                cfg = detect_bank(text, extractors)
                if cfg is None:
                    known = ", ".join(sorted(c.name for c in extractors)) or "(none)"
                    print(
                        f"error: no extractor matched {args.pdf.name}. "
                        f"Known banks: {known}. "
                        f"Use --bank to force one, or add a config to an extractors dir.",
                        file=sys.stderr,
                    )
                    if args.debug:
                        print("--- extracted text (for authoring a config) ---", file=sys.stderr)
                        print(text, file=sys.stderr)
                    return EXIT_NO_MATCH

            try:
                statement = extract(pdf, cfg)
            except ExtractionError as exc:
                print(f"error: {exc}", file=sys.stderr)
                if args.debug:
                    print("--- extracted text ---", file=sys.stderr)
                    print(read_full_text(pdf), file=sys.stderr)
                return EXIT_ERROR
    except ExtractionError:
        raise
    except Exception as exc:  # pdfplumber / file errors
        print(f"error: failed to read {args.pdf}: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # Reconciliation.
    recon = reconcile(statement)
    exit_code = EXIT_OK
    if recon is not None:
        if recon.ok:
            print(f"✓ {recon.message}", file=sys.stderr)
        else:
            level = "error" if args.strict else "warning"
            print(f"{level}: {recon.message}", file=sys.stderr)
            if args.strict:
                exit_code = EXIT_RECON_FAILED

    rendered = to_json(statement) if args.format == "json" else to_csv(statement)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
        if not rendered.endswith("\n"):
            sys.stdout.write("\n")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
