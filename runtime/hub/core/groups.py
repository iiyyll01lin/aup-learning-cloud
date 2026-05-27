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

"""
Group Sync and Resource Resolution

Provides functions for:
- Fetching GitHub team memberships via API
- Syncing GitHub teams to JupyterHub groups (protected, source=github-team)
- Resolving user resources from JupyterHub group memberships
"""

from __future__ import annotations

import logging

import aiohttp
from jupyterhub.orm import Group as ORMGroup
from jupyterhub.user import User as JupyterHubUser
from sqlalchemy.orm import Session

log = logging.getLogger("jupyterhub.groups")

GITHUB_TEAM_SOURCE = "github-team"
SYSTEM_SOURCE = "system"


async def fetch_github_teams(access_token: str, org_name: str) -> list[str] | None:
    """Fetch the user's GitHub team slugs for the given organization.

    Args:
        access_token: GitHub OAuth access token.
        org_name: GitHub organization name to filter teams by.

    Returns:
        List of team slugs the user belongs to in the organization, or ``None``
        if the GitHub API request failed and membership is unknown.
    """
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    teams: list[str] = []
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get("https://api.github.com/user/teams", headers=headers) as resp,
        ):
            if resp.status == 200:
                data = await resp.json()
                for team in data:
                    if team["organization"]["login"] == org_name:
                        teams.append(team["slug"])
            else:
                log.warning("GitHub API returned status %d when fetching teams", resp.status)
                return None
    except Exception as e:
        log.warning("Error fetching GitHub teams: %s", e)
        return None

    return teams


def sync_user_github_teams(
    user: JupyterHubUser,
    team_slugs: list[str] | None,
    valid_mapping_keys: set[str],
    db: Session,
) -> None:
    """Sync a user's GitHub team memberships to JupyterHub groups.

    For each team slug that exists in ``valid_mapping_keys``, ensures
    a JupyterHub group exists with ``properties.source = "github-team"``
    and adds the user to it. Removes the user from any github-team groups
    they no longer belong to.

    Args:
        user: JupyterHub User object.
        team_slugs: Team slugs the user currently belongs to on GitHub.
        valid_mapping_keys: Set of group names that have resource mappings in config.
        db: JupyterHub database session (``self.db`` from a handler or hook).
    """
    if team_slugs is None:
        log.warning("Skipping github-team sync for user '%s' because team membership could not be fetched", user.name)
        return

    relevant_teams = set(team_slugs) & valid_mapping_keys
    assert user.orm_user is not None  # populated by JupyterHub on init

    # Ensure groups exist and add user
    for team_slug in relevant_teams:
        orm_group = db.query(ORMGroup).filter_by(name=team_slug).first()
        if orm_group is None:
            orm_group = ORMGroup(name=team_slug)
            orm_group.properties = {"source": GITHUB_TEAM_SOURCE}  # type: ignore[assignment]
            db.add(orm_group)
            db.commit()
            log.info("Created JupyterHub group '%s' (source: github-team)", team_slug)
        elif orm_group.properties.get("source") != GITHUB_TEAM_SOURCE:
            # GitHub team always takes priority over admin-created groups
            orm_group.properties = {**orm_group.properties, "source": GITHUB_TEAM_SOURCE}  # type: ignore[assignment]
            db.commit()
            log.info("Group '%s' promoted to github-team source", team_slug)

        # Add user to group if not already a member
        if orm_group not in user.orm_user.groups:
            user.orm_user.groups.append(orm_group)
            db.commit()
            log.info("Added user '%s' to group '%s'", user.name, team_slug)

    # Remove user from github-team groups they no longer belong to
    for orm_group in list(user.orm_user.groups):
        if orm_group.properties.get("source") == GITHUB_TEAM_SOURCE and orm_group.name not in relevant_teams:
            user.orm_user.groups.remove(orm_group)
            db.commit()
            log.info("Removed user '%s' from group '%s'", user.name, orm_group.name)


def assign_user_to_group(
    user: JupyterHubUser,
    group_name: str,
    db: Session,
) -> None:
    """Assign a user to a JupyterHub group, creating it if needed.

    Used for native users to assign them to pattern-based groups.

    Args:
        user: JupyterHub User object.
        group_name: Name of the group to assign to.
        db: JupyterHub database session.
    """
    assert user.orm_user is not None  # populated by JupyterHub on init

    orm_group = db.query(ORMGroup).filter_by(name=group_name).first()
    if orm_group is None:
        orm_group = ORMGroup(name=group_name)
        orm_group.properties = {"source": SYSTEM_SOURCE}  # type: ignore[assignment]
        db.add(orm_group)
        db.commit()
        log.info("Created JupyterHub group '%s' (source: system)", group_name)
    elif not orm_group.properties.get("source"):
        orm_group.properties = {**orm_group.properties, "source": SYSTEM_SOURCE}  # type: ignore[assignment]
        db.commit()

    if orm_group not in user.orm_user.groups:
        user.orm_user.groups.append(orm_group)
        db.commit()
        log.info("Added user '%s' to group '%s'", user.name, group_name)


def get_resources_for_user(
    user: JupyterHubUser,
    team_resource_mapping: dict[str, list[str]],
) -> list[str]:
    """Get available resources for a user based on their JupyterHub group memberships.

    Iterates over the user's groups and looks up each group name in the
    ``team_resource_mapping``. If a group maps to ``"official"``, the full
    official resource list is returned immediately (short-circuit).

    Args:
        user: JupyterHub User object.
        team_resource_mapping: Mapping of group/team names to resource lists.

    Returns:
        Deduplicated list of resource names the user can access.
    """
    assert user.orm_user is not None  # populated by JupyterHub on init
    user_group_names = {g.name for g in user.orm_user.groups}
    available_resources: list[str] = []

    for group_name in user_group_names:
        if group_name not in team_resource_mapping:
            continue
        available_resources.extend(team_resource_mapping[group_name])

    # Deduplicate while preserving order
    return list(dict.fromkeys(available_resources))


def resolve_resources_for_user(
    user: JupyterHubUser,
    team_resource_mapping: dict[str, list[str]],
    auth_mode: str,
    all_resources: list[str],
) -> list[str]:
    """Resolve the resources visible to a user for UI and spawn flows."""
    username = user.name.strip()

    if auth_mode in ["auto-login", "dummy"]:
        return all_resources

    available_resources = get_resources_for_user(user, team_resource_mapping)
    if available_resources:
        return available_resources

    if not username.startswith("github:"):
        return team_resource_mapping.get("native-users", team_resource_mapping.get("official", []))

    return ["none"]


def is_readonly_group(group: ORMGroup) -> bool:
    """Check if a group's membership is fully read-only.

    Only system-managed groups are fully read-only.  GitHub-team groups
    allow manual member additions (admins can add native users to grant
    them the same resources).  Synced GitHub members are auto-managed:
    they may be re-added or removed on the next login sync.

    Args:
        group: JupyterHub ORM Group object.

    Returns:
        True if the group's source is "system".
    """
    return group.properties.get("source") == SYSTEM_SOURCE  # type: ignore[union-attr]


def is_undeletable_group(group: ORMGroup) -> bool:
    """Check if a group cannot be deleted.

    Both GitHub-synced groups and system-managed groups are undeletable.

    Args:
        group: JupyterHub ORM Group object.

    Returns:
        True if the group's source is "github-team" or "system".
    """
    return group.properties.get("source") in (GITHUB_TEAM_SOURCE, SYSTEM_SOURCE)  # type: ignore[union-attr]
