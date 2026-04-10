import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

if "aiohttp" not in sys.modules:
    aiohttp_module = types.ModuleType("aiohttp")
    aiohttp_module.ClientSession = object
    sys.modules["aiohttp"] = aiohttp_module

if "jupyterhub.orm" not in sys.modules:
    orm_module = types.ModuleType("jupyterhub.orm")
    orm_module.Group = type("Group", (), {})
    sys.modules["jupyterhub.orm"] = orm_module

if "jupyterhub.user" not in sys.modules:
    user_module = types.ModuleType("jupyterhub.user")
    user_module.User = type("User", (), {})
    sys.modules["jupyterhub.user"] = user_module

if "sqlalchemy.orm" not in sys.modules:
    sa_orm_module = types.ModuleType("sqlalchemy.orm")
    sa_orm_module.Session = type("Session", (), {})
    sys.modules["sqlalchemy.orm"] = sa_orm_module

if "core" not in sys.modules:
    core_module = types.ModuleType("core")
    core_module.__path__ = [str(CORE)]
    sys.modules["core"] = core_module


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


groups = load_module("core.groups", CORE / "groups.py")
sync_user_github_teams = groups.sync_user_github_teams


class DummyGroup:
    def __init__(self, name, source="github-team"):
        self.name = name
        self.properties = {"source": source}


class DummyOrmUser:
    def __init__(self, groups):
        self.groups = groups


class DummyUser:
    def __init__(self, groups):
        self.name = "github:test"
        self.orm_user = DummyOrmUser(groups)


class DummyQuery:
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return None


class DummyDb:
    def query(self, _model):
        return DummyQuery()

    def add(self, _obj):
        pass

    def commit(self):
        pass


def test_sync_user_github_teams_skips_removals_when_team_fetch_failed():
    existing_group = DummyGroup("team-a")
    user = DummyUser([existing_group])

    sync_user_github_teams(user, None, {"team-a"}, DummyDb())

    assert user.orm_user.groups == [existing_group]
