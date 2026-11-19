"""Create an owner-only workspace and bind it to a separate Vault."""

import os
from pathlib import Path, PurePosixPath
from uuid import uuid4

from . import SCHEMA, VERSION
from .life import REGISTRY, archive_coverage, field_registry, validate_registry
from .model import LEVELS, Conflict, Denied, HubError, canonical, one_of, read_json, seq, shape
from .store import Store, checked_relative, instance_path, protect_root, reparse

WORKSPACE_FORMAT = "1.0"
TEMPLATE_MAP = Path(__file__).with_name("workspace-files.json")
CONFIG = "config/workspace.json"
IGNORE_TEMPLATE = "config/workspace.gitignore"
PROFILE = "life-archive/profile.json"
TIMELINE = "life-archive/timeline.json"


def get_templates():
    data = read_json(TEMPLATE_MAP)
    shape(data, ("files", "demo"))
    for group in data.values():
        for entry in seq(group):
            if (not isinstance(entry, str) or "\\" in entry or ":" in entry or not entry
                    or any(part in ("", ".", "..") for part in entry.split("/"))):
                raise HubError("invalid workspace template path")
        if len(group) != len(set(group)):
            raise HubError("duplicate workspace template path")
    return data


def template_root():
    packaged = Path(__file__).resolve().with_name("_workspace")
    return instance_template_root(packaged if packaged.is_dir() else Path(__file__).resolve().parents[1])


def instance_template_root(path):
    if reparse(path):
        raise Denied("workspace template root must be a regular directory")
    return path


def private_pair(workspace, vault):
    if workspace.is_relative_to(vault) or vault.is_relative_to(workspace):
        raise Denied("workspace and Vault must have separate non-nested paths")


def write_exclusive(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as file:
        file.write(contents)


def reserve(path, owned):
    path.mkdir(mode=0o700)
    info = path.stat()
    owned.append((path, info.st_dev, info.st_ino))
    protect_root(path, create=True)


def remove_failed_initialization(owned):
    for path, device, inode in reversed(owned):
        try:
            if instance_path(path) != path or reparse(path):
                continue
            current = path.stat()
            if (current.st_dev, current.st_ino) == (device, inode):
                path.rmdir()
        except (HubError, OSError):
            # A replaced or protected path remains untouched. A retry always
            # requires new paths or an explicit owner cleanup.
            pass


def init_workspace(path, vault_path=None, sensitivity="private", demo=False):
    one_of(sensitivity, LEVELS)
    root = instance_path(path)
    if not root.name:
        raise Denied("choose a workspace directory below an existing parent")
    vault = instance_path(vault_path if vault_path is not None else root.with_name(root.name + "-vault"))
    private_pair(root, vault)
    for target in (root, vault):
        if os.path.lexists(target):
            raise Conflict("choose new workspace and Vault paths")
        if not target.parent.is_dir():
            raise HubError("workspace and Vault parent directories must already exist")
    templates = get_templates()
    source = template_root()
    owned = []
    try:
        reserve(root, owned)
        reserve(vault, owned)
        for relative in templates["files"]:
            if relative == CONFIG:
                raise HubError("the template map must exclude local binding")
            item = checked_relative(source, relative)
            target = ".gitignore" if relative == IGNORE_TEMPLATE else relative
            write_exclusive(root / target, item.read_bytes())
        if demo:
            for relative in templates["demo"]:
                item = checked_relative(source, relative)
                target = root / "demo-inbox" / PurePosixPath(relative).name
                if item.suffix == ".json":
                    data = read_json(item)
                    if "sensitivity" in data:
                        data["sensitivity"] = sensitivity
                    contents = (canonical(data) + "\n").encode("utf-8")
                else:
                    contents = item.read_bytes()
                write_exclusive(target, contents)
        store = Store(vault, initialize=sensitivity, require_fresh=True)
        identity = uuid4().hex
        with store.transaction(write=True) as db:
            db.execute("INSERT INTO settings VALUES (?,?)", ("workspace_identity", canonical(identity)))
        binding = {
            "format": WORKSPACE_FORMAT, "template_version": VERSION, "sensitivity": sensitivity,
            "vault": str(vault), "vault_identity": identity, "demo": demo,
        }
        write_exclusive(root / CONFIG, (canonical(binding) + "\n").encode("utf-8"))
    except BaseException:
        remove_failed_initialization(owned)
        raise
    return {"status": "initialized", "workspace": str(root), **binding,
            "switches": store.settings()["switches"], "scheduler": "not_verified"}


def bound_workspace(path):
    root = instance_path(path)
    protect_root(root)
    binding = read_json(checked_relative(root, CONFIG))
    shape(binding, ("format", "template_version", "sensitivity", "vault", "vault_identity", "demo"))
    one_of(binding["format"], (WORKSPACE_FORMAT,))
    one_of(binding["sensitivity"], LEVELS)
    if (not isinstance(binding["template_version"], str) or not isinstance(binding["vault"], str)
            or not Path(binding["vault"]).is_absolute() or type(binding["demo"]) is not bool):
        raise HubError("invalid workspace binding")
    vault = instance_path(binding["vault"])
    private_pair(root, vault)
    store = Store(vault)
    if store.level != binding["sensitivity"]:
        raise Denied("bound Vault sensitivity differs from the workspace")
    with store.transaction() as db:
        result = db.execute("SELECT value FROM settings WHERE key='workspace_identity'").fetchone()
        if result is None or result["value"] != canonical(binding["vault_identity"]):
            raise Denied("Vault identity does not match this workspace")
    return root, binding, store


def check_workspace(path):
    root, binding, store = bound_workspace(path)
    for required in ("AGENTS.md", "core/INDEX.md", "memory/README.md", "projects/README.md",
                     "sessions/README.md", "life-archive/README.md"):
        if not checked_relative(root, required).is_file():
            raise HubError("workspace entry document is missing")
    registry = field_registry()
    registry_present = os.path.lexists(root / REGISTRY)
    if registry_present and validate_registry(read_json(checked_relative(root, REGISTRY))) != registry:
        raise HubError("workspace archive field registry differs from the engine")
    coverage = archive_coverage(
        read_json(checked_relative(root, PROFILE)), read_json(checked_relative(root, TIMELINE)), store.level, registry,
    )
    settings = store.settings()
    return {"status": "checked", "workspace": str(root), **binding, "engine_version": VERSION,
            "template_matches_engine": binding["template_version"] == VERSION, "schema_version": SCHEMA,
            "switches": settings["switches"], "scheduler": settings["scheduler"], "life_archive": coverage,
            "local_field_registry": registry_present}


def facts_projection(path):
    _, _, store = bound_workspace(path)
    with store.transaction() as db:
        items = store.latest(db, "memory")
    return {"schema_version": SCHEMA, "facts": [item for item in items if item["data"]["status"] == "accepted"]}
