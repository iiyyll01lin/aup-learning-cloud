# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Unit tests for core.groups module."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub out jupyterhub.orm so we can import core.groups without a real hub
# ---------------------------------------------------------------------------


class FakeORMGroup:
    """Lightweight stand-in for jupyterhub.orm.Group."""

    def __init__(self, name: str = "", properties: dict | None = None):
        self.name = name
        self.properties = properties or {}
        self.users: list = []

    def __repr__(self):
        return f"<FakeORMGroup {self.name!r}>"


class FakeQuery:
    """Minimal query mock that supports filter_by().first()."""

    def __init__(self, groups: list[FakeORMGroup]):
        self._groups = groups

    def filter_by(self, **kwargs):
        name = kwargs.get("name")
        self._filtered = [g for g in self._groups if g.name == name]
        return self

    def first(self):
        return self._filtered[0] if self._filtered else None


class FakeDB:
    """Minimal DB mock with query(), add(), commit(), delete()."""

    def __init__(self, groups: list[FakeORMGroup] | None = None):
        self.groups = groups or []
        self._added: list = []
        self._deleted: list = []
        self._committed = 0

    def query(self, model):
        return FakeQuery(self.groups)

    def add(self, obj):
        self._added.append(obj)
        self.groups.append(obj)

    def delete(self, obj):
        self._deleted.append(obj)
        self.groups.remove(obj)

    def commit(self):
        self._committed += 1


class FakeORMUser:
    """Stand-in for jupyterhub.orm.User."""

    def __init__(self, name: str = "", groups: list[FakeORMGroup] | None = None):
        self.name = name
        self.groups = groups or []


class FakeUser:
    """Stand-in for jupyterhub.user.User (wrapper around orm_user)."""

    def __init__(self, name: str = "", groups: list[FakeORMGroup] | None = None):
        self.name = name
        self.orm_user = FakeORMUser(name=name, groups=groups or [])
        self.db = FakeDB(groups or [])


import importlib.util  # noqa: E402
from pathlib import Path  # noqa: E402

# Install stubs before importing core.groups
_orm_mod = ModuleType("jupyterhub.orm")
_orm_mod.Group = FakeORMGroup  # type: ignore[attr-defined]
sys.modules.setdefault("jupyterhub", ModuleType("jupyterhub"))
sys.modules["jupyterhub.orm"] = _orm_mod

# Also stub aiohttp so the module-level import doesn't fail
sys.modules.setdefault("aiohttp", MagicMock())

_groups_path = Path(__file__).resolve().parent.parent / "core" / "groups.py"
_spec = importlib.util.spec_from_file_location("core.groups", _groups_path)
_groups_mod = importlib.util.module_from_spec(_spec)
sys.modules["core.groups"] = _groups_mod
_spec.loader.exec_module(_groups_mod)  # type: ignore[union-attr]

GITHUB_TEAM_SOURCE = _groups_mod.GITHUB_TEAM_SOURCE
SYSTEM_SOURCE = _groups_mod.SYSTEM_SOURCE
assign_user_to_group = _groups_mod.assign_user_to_group
get_resources_for_user = _groups_mod.get_resources_for_user
is_readonly_group = _groups_mod.is_readonly_group
is_undeletable_group = _groups_mod.is_undeletable_group
sync_user_github_teams = _groups_mod.sync_user_github_teams


# =========================================================================
# is_readonly_group / is_undeletable_group
# =========================================================================


class TestGroupProtection:
    def test_github_team_is_not_readonly(self):
        # GitHub-team groups allow manual member additions
        g = FakeORMGroup("gpu", {"source": GITHUB_TEAM_SOURCE})
        assert is_readonly_group(g) is False

    def test_system_is_readonly(self):
        g = FakeORMGroup("native-users", {"source": SYSTEM_SOURCE})
        assert is_readonly_group(g) is True

    def test_admin_is_not_readonly(self):
        g = FakeORMGroup("custom", {"source": "admin"})
        assert is_readonly_group(g) is False

    def test_no_source_is_not_readonly(self):
        g = FakeORMGroup("old-group", {})
        assert is_readonly_group(g) is False

    def test_github_team_is_undeletable(self):
        g = FakeORMGroup("gpu", {"source": GITHUB_TEAM_SOURCE})
        assert is_undeletable_group(g) is True

    def test_system_is_undeletable(self):
        g = FakeORMGroup("native-users", {"source": SYSTEM_SOURCE})
        assert is_undeletable_group(g) is True

    def test_admin_is_deletable(self):
        g = FakeORMGroup("custom", {"source": "admin"})
        assert is_undeletable_group(g) is False


# =========================================================================
# sync_user_github_teams
# =========================================================================


class TestSyncUserGitHubTeams:
    def test_creates_new_group_and_adds_user(self):
        db = FakeDB()
        user = FakeUser("alice")
        user.db = db

        sync_user_github_teams(user, ["gpu"], {"gpu", "cpu"}, db)

        assert len(db.groups) == 1
        assert db.groups[0].name == "gpu"
        assert db.groups[0].properties["source"] == GITHUB_TEAM_SOURCE
        assert db.groups[0] in user.orm_user.groups

    def test_ignores_teams_not_in_mapping(self):
        db = FakeDB()
        user = FakeUser("alice")
        user.db = db

        sync_user_github_teams(user, ["unknown-team"], {"gpu", "cpu"}, db)

        assert len(db.groups) == 0

    def test_adds_user_to_existing_group(self):
        existing = FakeORMGroup("gpu", {"source": GITHUB_TEAM_SOURCE})
        db = FakeDB([existing])
        user = FakeUser("alice")
        user.db = db

        sync_user_github_teams(user, ["gpu"], {"gpu"}, db)

        assert existing in user.orm_user.groups

    def test_removes_user_from_old_github_team(self):
        old_group = FakeORMGroup("cpu", {"source": GITHUB_TEAM_SOURCE})
        db = FakeDB([old_group])
        user = FakeUser("alice", groups=[old_group])
        user.db = db

        # User is no longer in "cpu" team, only in "gpu"
        sync_user_github_teams(user, ["gpu"], {"gpu", "cpu"}, db)

        assert old_group not in user.orm_user.groups

    def test_does_not_remove_user_from_non_github_group(self):
        admin_group = FakeORMGroup("custom", {"source": "admin"})
        db = FakeDB([admin_group])
        user = FakeUser("alice", groups=[admin_group])
        user.db = db

        sync_user_github_teams(user, [], {"gpu"}, db)

        # Admin group should not be touched
        assert admin_group in user.orm_user.groups

    def test_promotes_admin_group_to_github_team(self):
        admin_group = FakeORMGroup("gpu", {"source": "admin"})
        db = FakeDB([admin_group])
        user = FakeUser("alice")
        user.db = db

        sync_user_github_teams(user, ["gpu"], {"gpu"}, db)

        assert admin_group.properties["source"] == GITHUB_TEAM_SOURCE

    def test_backfills_source_on_group_without_source(self):
        no_source = FakeORMGroup("gpu", {})
        db = FakeDB([no_source])
        user = FakeUser("alice")
        user.db = db

        sync_user_github_teams(user, ["gpu"], {"gpu"}, db)

        assert no_source.properties["source"] == GITHUB_TEAM_SOURCE


# =========================================================================
# assign_user_to_group
# =========================================================================


class TestAssignUserToGroup:
    def test_creates_group_if_not_exists(self):
        db = FakeDB()
        user = FakeUser("bob")
        user.db = db

        assign_user_to_group(user, "native-users", db)

        assert len(db.groups) == 1
        assert db.groups[0].name == "native-users"
        assert db.groups[0].properties["source"] == SYSTEM_SOURCE
        assert db.groups[0] in user.orm_user.groups

    def test_adds_user_to_existing_group(self):
        existing = FakeORMGroup("native-users", {"source": SYSTEM_SOURCE})
        db = FakeDB([existing])
        user = FakeUser("bob")
        user.db = db

        assign_user_to_group(user, "native-users", db)

        assert existing in user.orm_user.groups

    def test_does_not_duplicate_membership(self):
        existing = FakeORMGroup("native-users", {"source": SYSTEM_SOURCE})
        db = FakeDB([existing])
        user = FakeUser("bob", groups=[existing])
        user.db = db

        assign_user_to_group(user, "native-users", db)

        # No extra commit for membership since user is already a member
        assert user.orm_user.groups.count(existing) == 1

    def test_backfills_source_on_existing_group_without_source(self):
        no_source = FakeORMGroup("native-users", {})
        db = FakeDB([no_source])
        user = FakeUser("bob")
        user.db = db

        assign_user_to_group(user, "native-users", db)

        assert no_source.properties["source"] == SYSTEM_SOURCE


# =========================================================================
# get_resources_for_user
# =========================================================================


class TestGetResourcesForUser:
    def _make_user_with_groups(self, group_names: list[str]) -> FakeUser:
        groups = [FakeORMGroup(name) for name in group_names]
        return FakeUser("alice", groups=groups)

    def test_returns_resources_for_matching_groups(self):
        user = self._make_user_with_groups(["gpu"])
        mapping = {"gpu": ["res-a", "res-b"], "cpu": ["res-c"]}

        result = get_resources_for_user(user, mapping)

        assert result == ["res-a", "res-b"]

    def test_official_shortcircuits(self):
        user = self._make_user_with_groups(["official", "gpu"])
        mapping = {
            "official": ["res-a", "res-b", "res-c"],
            "gpu": ["res-a"],
        }

        result = get_resources_for_user(user, mapping)

        assert result == ["res-a", "res-b", "res-c"]

    def test_merges_multiple_groups(self):
        user = self._make_user_with_groups(["gpu", "cpu"])
        mapping = {"gpu": ["res-a"], "cpu": ["res-b", "res-c"]}

        result = get_resources_for_user(user, mapping)

        assert set(result) == {"res-a", "res-b", "res-c"}

    def test_deduplicates_resources(self):
        user = self._make_user_with_groups(["gpu", "cpu"])
        mapping = {"gpu": ["res-a", "res-b"], "cpu": ["res-b", "res-c"]}

        result = get_resources_for_user(user, mapping)

        assert set(result) == {"res-a", "res-b", "res-c"}
        assert len(result) == 3  # no duplicates

    def test_returns_empty_for_no_matching_groups(self):
        user = self._make_user_with_groups(["unknown"])
        mapping = {"gpu": ["res-a"]}

        result = get_resources_for_user(user, mapping)

        assert result == []

    def test_returns_empty_for_user_with_no_groups(self):
        user = self._make_user_with_groups([])
        mapping = {"gpu": ["res-a"]}

        result = get_resources_for_user(user, mapping)

        assert result == []
