"""Regression test for T-936: every scripts/ and tools/ entry point that
imports from src must put the repo root on sys.path *before* that import.

Static/AST test, not a subprocess import test — most of these modules open a
Telegram Client or read os.getenv(...) at import time, so actually importing
them needs credentials and network. This test only inspects source text.
"""
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _first_src_import_line(tree):
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module \
                and node.module.split(".")[0] == "src":
            return node.lineno
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "src":
                    return node.lineno
    return None


def _is_syspath_insert(node):
    func = getattr(node, "func", None)
    return (
        isinstance(node, ast.Call)
        and isinstance(func, ast.Attribute)
        and func.attr == "insert"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "path"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "sys"
    )


def _first_syspath_insert_line(tree):
    lines = [n.lineno for n in ast.walk(tree) if _is_syspath_insert(n)]
    return min(lines) if lines else None


def test_every_entrypoint_bootstraps_syspath_before_importing_src():
    offenders = []
    for directory in ("scripts", "tools"):
        for path in sorted((REPO / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            src_import_line = _first_src_import_line(tree)
            if src_import_line is None:
                continue
            insert_line = _first_syspath_insert_line(tree)
            rel = path.relative_to(REPO)
            if insert_line is None:
                offenders.append(f"{rel}: imports from src (line {src_import_line}) with no sys.path.insert")
            elif not insert_line < src_import_line:
                offenders.append(
                    f"{rel}: sys.path.insert (line {insert_line}) does not precede "
                    f"the src import (line {src_import_line})"
                )

    assert not offenders, "sys.path bootstrap missing/misplaced in:\n" + "\n".join(offenders)
