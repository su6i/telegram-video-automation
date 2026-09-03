"""Regression test for entry point CLI structures.

Static/AST test, not a subprocess import test — most of these modules open live
Telegram or Selenium sessions and prompt for credentials at runtime, so a real
import or subprocess test would itself have live side effects. This test only
inspects source text.
"""
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# These correspond to load_dotenv(...), sys.path.insert(...),
# logging.basicConfig(...), and warnings.filterwarnings(...), which are
# inert bootstrap and may run at import time.
ALLOWED_MODULE_LEVEL_CALLS = frozenset(
    {"load_dotenv", "insert", "basicConfig", "filterwarnings"}
)

# Per-file exemptions for module-level calls that pre-date T-938 and were
# explicitly left untouched by it (audited "already compliant" in
# wo-tva-0010-T-938-argparse-every-entrypoint.md). Two of the three gate
# real work behind their OWN module-level `parser.parse_args()` (an
# assignment, not a bare call, so it isn't caught by the generic scan
# below) — a different but equally valid shape from the main()-wrapped
# files this WO fixed. The third is a known residual; see its note.
# Do not widen the general allowlist above for these; add a new file entry
# here instead, deliberately, if a specific file needs one.
PER_FILE_EXEMPT_MODULE_LEVEL_CALLS = {
    # Parser is built and parsed at module level (before any dangerous
    # work), so its own parser.add_argument(...) calls are safe by
    # construction; os.makedirs(STORAGE_DIR) runs after parse_args().
    "scripts/process_and_upload.py": {"add_argument", "makedirs"},
    # os.chdir(ROOT) is inert filesystem bookkeeping before parse_args().
    "scripts/purge_batch.py": {"chdir"},
}


def _has_argument_parser(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "ArgumentParser":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "ArgumentParser":
                return True
    return False


def _is_main_guard(node):
    if isinstance(node, ast.If):
        dumped = ast.dump(node.test)
        if "__name__" in dumped and "__main__" in dumped:
            return True
    return False


def _get_call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def test_every_entrypoint_has_an_argument_parser():
    offenders = []
    for directory in ("scripts", "tools"):
        for path in sorted((REPO / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            if not _has_argument_parser(tree):
                rel = path.relative_to(REPO)
                offenders.append(str(rel))

    assert not offenders, "Missing ArgumentParser in:\n" + "\n".join(offenders)


def test_every_entrypoint_guards_main():
    offenders = []
    for directory in ("scripts", "tools"):
        for path in sorted((REPO / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            if not any(_is_main_guard(node) for node in tree.body):
                rel = path.relative_to(REPO)
                offenders.append(str(rel))

    assert not offenders, (
        "Missing if __name__ == '__main__': in:\n" + "\n".join(offenders)
    )


def test_no_module_level_side_effects():
    offenders = []
    for directory in ("scripts", "tools"):
        for path in sorted((REPO / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            rel = path.relative_to(REPO)
            exempt = PER_FILE_EXEMPT_MODULE_LEVEL_CALLS.get(str(rel), frozenset())
            for node in tree.body:
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    name = _get_call_name(node.value.func) or "<unknown>"
                    if name not in ALLOWED_MODULE_LEVEL_CALLS and name not in exempt:
                        offenders.append(
                            f"{rel}:{node.lineno}: module-level call to {name}(...)"
                        )

    assert not offenders, (
        "Forbidden module-level side effects found:\n" + "\n".join(offenders)
    )
