###########################################################################
#
# Copyright (C) ZeroPoint Technologies AB - All Rights Reserved.
#
# NOTICE: All information contained herein is, and remains
# the property of ZeroPoint Technologies AB and its suppliers,
# if any. The intellectual and technical concepts contained
# herein are proprietary to ZeroPoint Technologies AB
# and its suppliers and may be covered by U.S. and Foreign Patents,
# patents in process, and are protected by trade secret or copyright law.
# Dissemination of this information or reproduction of this material
# is strictly forbidden unless prior written permission is obtained
# from ZeroPoint Technologies AB.
#
#
# Description:
# Helper module that contains functions for generating different scripts
# for running the generated experiments.
#
#
# Authors:
# Anders Persson <anders.persson@zptcorp.com>
# ZeroPoint Technologies AB
#
# Created: 2021/03/24
#
############################################################################

import doctest
import logging
import re
import os
import glob
import sys
from conans import ConanFile, tools


class GitSemVer(object):
    """
    Base class for Conan packages using Semantic Versioning derived from Git tags and branches

    Example use:
    class Pkg(ConanFile):
        python_requires = "semver/0.1@user/channel"
        python_requires_extend = "semver.GitSemVer"
    """

    def set_version(self):
        if self.version != None:
            return

        self.version = git_get_semver(name=self.name, recipe_folder=self.recipe_folder)


def parseVer(version):
    """
    Parse a version string into major.minor.patch

    >>> parseVer("0.0.0")
    ('0', '0', '0')

    >>> parseVer("X.Y.Z")
    ('X', 'Y', 'Z')

    >>> parseVer("0,0,0")
    ('0,0,0', '', '')
    """
    major = None
    minor = None
    patch = None

    major, _, version = version.partition(".")
    minor, _, version = version.partition(".")
    patch, _, version = version.partition(".")

    return major, minor, patch


def parseGitDescribe(tag):
    ver = None
    ahead = None
    commit = None

    ver, _, tag = tag.partition("-")
    ahead, _, tag = tag.partition("-")
    commit, _, tag = tag.partition("-")

    return ver, ahead, commit


class VersionRep:
    """
    >>> str(VersionRep("1.2.3-5-gabcdef"))
    '1.2.3-rc5-gabcdef'
    >>> VersionRep("0.0.0") == VersionRep("0.0.0")
    True
    >>> VersionRep("0.0.1") < VersionRep("0.0.0")
    False
    >>> VersionRep("0.1.3") < VersionRep("0.2.0")
    True
    """

    major = 0
    minor = 0
    patch = 0
    prerelease = ""
    build = ""

    def __init__(self, tag):
        version, ahead, commit = parseGitDescribe(tag)
        assert tag
        ma, mi, pa = parseVer(version)
        self.major = int(ma)
        self.minor = int(mi)
        if pa:
            self.patch = int(pa)
        if ahead and int(ahead) > 0:
            self.prerelease = "rc" + ahead
        if commit:
            self.prerelease += "-" + commit

    def __str__(self):
        str = f"{self.major}.{self.minor}.{self.patch}"
        if len(self.prerelease) > 0:
            str += "-" + self.prerelease
        if len(self.build) > 0:
            str += "+" + self.build
        return str

    def __lt__(self, other):
        if self.major < other.major:
            return True
        elif self.major == other.major:
            if self.minor < other.minor:
                return True
            elif self.minor == other.minor:
                if self.patch < other.patch:
                    return True
                elif self.patch == other.patch:
                    if self.prerelease < other.prerelease:
                        return True
        return False

    def __eq__(self, other):
        if self.major == other.major:
            if self.minor == other.minor:
                if self.patch == other.patch:
                    return True
        return False


def get_version_from_string(string, name="module"):
    """
    Extract the version major.minor.patch from a tag or branch

    >>> str(get_version_from_string("module/0.1.0"))
    '0.1.0'
    >>> str(get_version_from_string("module/0.1.0", name="modul"))
    '0.0.0'
    >>> str(get_version_from_string("release/module/0.1.0"))
    '0.1.0'
    >>> str(get_version_from_string("origin/release/module/0.1.0"))
    '0.1.0'
    """

    parts = string.split("/")
    if len(parts) < 2:
        return VersionRep("0.0.0")
    [module, version] = parts[-2:]
    if module == name:
        return VersionRep(version)
    return VersionRep("0.0.0")


def git_get_semver(
    ref_name="HEAD", name="module", master="origin/HEAD", recipe_folder=None
):
    """
    Calculate the Semantic Version based on git tags and brances.

    The following cases exist:

    UNTAGGED:
         No valid SemVer exists, return "0.0.0"

    TAGGED:
         If a version has a tag "module/major.minor.patch" and
         the tag is a valid SemVer, use it.

    PARENT-TAGGED:
         If a version has a parent that is TAGGED,
         add one to the patch version of the tag and add a
         prerelease "rcN" where N is the number of commits
         from the tagged version.
         The number of commits is calculated as the sum of all commits
         leading to the current version. See the example for O below.

    RELEASE-BRANCH:
         If a version is on a release branch "release/module/major.minor",
         find the common ancestor and create a SemVer as in PARENT-TAGGED,
         but with the ancestor as the reference commit.

    RELEASE-BRANCH-TAGGED:
         A combination of RELEASE-BRANCH and PARENT-TAGGED.
         Use the larger SemVer of the two cases.

    Examples:

        A---B(module/0.1.3)---C(other/0.3.5)---D-----------------        test
                              |\              /                  \
                              | E---F--------G(module/0.2.1)---H  \      release/module/0.2
                              |  \            \                    \
                              |   \            \                    S    release/module/0.3
                              |    \            \                  /
                              I-----J---K--------O---P-------------      dev_module
                                     \            \
                                      L---M---N----Q---R                 feat/amazing

        Here A is UNTAGGED, B is TAGGED and C is PARENT-TAGGED
        >>> git_get_semver("A")
        '0.0.0'
        >>> git_get_semver("B")
        '0.1.3'
        >>> git_get_semver("C")
        '0.1.4-rc1-g0e7e30bc68'

        D is a merge where both ancestors are TAGGED, use the larger SemVer
        and proceed as PARENT-TAGGED
        >>> git_get_semver("D")
        '0.2.2-rc1-gced7ff8494'

        E and F are both on the "release/module/0.2" branch and are interpreted
        as RELEASE-BRANCH.
        G is TAGGED and H is RELEASE-BRANCH-TAGGED.
        >>> git_get_semver("E", master="test")
        '0.2.0-rc1-g8213582ebb'
        >>> git_get_semver("F", master="test")
        '0.2.0-rc2-g8c990ed70f'
        >>> git_get_semver("G", recipe_folder="test")
        '0.2.1'
        >>> git_get_semver("H")
        '0.2.2-rc1-g25c7e7e593'

        I is on the "dev" branch and PARENT-TAGGED from B
        >>> git_get_semver("I")
        '0.1.4-rc2-gb4c695c5bb'

        J is a merge of the release branch into "dev", since there is no tag
        ancestor in the release branch, J is PARENT-TAGGED from B.
        The number of commits is calculated as count(J, I, E, C)
        K, L, M, and N follows J
        >>> git_get_semver("J")
        '0.1.4-rc4-g2302af49d9'
        >>> git_get_semver("K")
        '0.1.4-rc5-gf749b08edc'
        >>> git_get_semver("L")
        '0.1.4-rc5-g3dba32efbb'
        >>> git_get_semver("M")
        '0.1.4-rc6-g7e9ced54a9'
        >>> git_get_semver("N")
        '0.1.4-rc7-gae88aaf43a'

        O is a merge of the release branch into "dev". In this case there
        is a tagged ancestor in the release branch, so O is PARENT-TAGGED from G

        The number of commits is calculated as count(O, K, J, I, C)
        >>> git_get_semver("O")
        '0.2.2-rc4-gb978aaf2a6'

        >>> git_get_semver("P")
        '0.2.2-rc5-g5d7a03e5ca'

        Q is a merge of the "dev" branch into "feat/amazing". It inherits the
        tagged ancestor and is PARENT-TAGGED from G.
        The number of commits is calculated as count(Q, N, M, L, O, K, J, I, C)
        >>> git_get_semver("Q")
        '0.2.2-rc8-g7281b66edf'
        >>> git_get_semver("R")
        '0.2.2-rc9-g050e3f48dd'
    """

    log = logging.getLogger("semver")

    # Run all git commands from the root of the repo
    git = tools.Git()
    git = tools.Git(folder=git.get_repo_root())

    if "true" == git.run("rev-parse --is-shallow-repository"):
        raise ConanInvalidConfiguration(
            "Semantic versioning requires a full repository history"
        )

    # Validate the git reference
    try:
        ref = git.run(f"rev-parse --verify {ref_name}")
    except:
        raise ConanInvalidConfiguration(f"Not a valid reference {ref_name}")

    # Validate recipe_folder
    if not recipe_folder:
        recipe_folder = git.get_repo_root()

    recipe_folder = os.path.relpath(recipe_folder, git.get_repo_root())

    log.info(f"Working with recipe in folder {recipe_folder}")

    def get_nearest_tag(name, ref):
        return git.run(f"describe --tags --abbrev=0 --always --match {name}/\\* {ref}")

    def rev_parse(ref):
        log.debug(f"rev_parse {ref[:10]}")
        try:
            return git.run(f"rev-parse --verify {ref}")
        except:
            return None

    # Find nearest tag ancestor
    prev_tag = get_nearest_tag(name, ref)
    commits_behind_tag = int(
        git.run(f"rev-list --count {prev_tag}..{ref} -- {recipe_folder}")
    )

    tag_version = get_version_from_string(prev_tag, name=name)

    tag_ref = rev_parse(prev_tag)

    log.debug(f"{prev_tag} {tag_version} {tag_ref[:10]}")

    # Find root of release branch, if any
    base_version = None
    commits_behind_branch = 0
    release = None

    # find branches containing the commit
    release_branches = git.run(
        f"branch --all --list 'release/{name}/*' --contains {ref}"
    ).split()

    def fork_point(master_ref, branch):
        log.debug(f"fork_point {branch} {master_ref[:10]}")
        try:
            return git.run(f"merge-base --fork-point {branch} {master_ref}")
        except:
            return None

    def is_ancestor(fp):
        log.debug(f"is_ancestor {fp[:10]} {ref[:10]}")
        try:
            git.run(f"merge-base --is-ancestor {fp} {ref}")
            return True
        except:
            return False

    def filter_branch(branch):
        master_ref = rev_parse(master)
        while master_ref:
            fp = fork_point(master_ref, branch)
            if fp is None:
                log.debug("no fork point")
                return None
            if fp == ref:
                log.debug("fork_point reached ref")
                return None
            if fp == tag_ref:
                log.debug("fork_point reached tag")
                return None
            if is_ancestor(fp):
                log.debug(f"found {fp[:10]} {git.run(f'describe --all {fp}')}")
                return (branch, fp)
            else:
                master_ref = rev_parse(master_ref + "^")

    log.debug(release_branches)
    release_branches = list(filter(None, map(filter_branch, release_branches)))
    log.debug(release_branches)
    base_candidate = None
    for (branch, base_ref) in release_branches:
        for prefix in [f"release/{name}/", f"origin/release/{name}"]:
            if branch.startswith(prefix):
                release = branch[len(prefix) :]
                base_version = VersionRep(release)
                base_candidate = base_ref
                commits_behind_branch = int(
                    git.run(
                        f"rev-list --count {base_candidate}..{ref} -- {recipe_folder}"
                    )
                )
                break

    commits_behind = commits_behind_tag
    if commits_behind_branch:
        commits_behind = min(commits_behind, commits_behind_branch)

    log.debug(
        f"{base_candidate} {commits_behind_tag} {commits_behind_branch} {commits_behind}"
    )

    log.debug(f"tag_version {tag_version} base_version {base_version}")

    if base_version and tag_version < base_version:
        version = base_version
        commits_behind = commits_behind_branch
    else:
        version = tag_version
        commits_behind = commits_behind_tag
        if commits_behind > 0:
            version.patch += 1

    if commits_behind > 0:
        version.prerelease = f"rc{commits_behind}-g{ref[:10]}"

    log.info(
        f"Calculated semantic version {version} from commit {ref[:10]} with tag {prev_tag} and branch {release}"
    )

    return str(version)


class Pkg(ConanFile):
    name = "semver"
    license = "LICENSE"
    url = "git@bitbucket.org:zpt/conan.git"
    description = "Semantic Versions derived from Git tags and branches"
    no_copy_source = True

    def package_id(self):
        self.info.header_only()

    def set_version(self):
        if self.version != None:
            return

        logging.basicConfig(level=logging.DEBUG)
        self.version = git_get_semver(name=self.name, recipe_folder=self.recipe_folder)

    pass


if __name__ == "__main__":
    import doctest

    logging.basicConfig(level=logging.DEBUG)
    doctest.testmod()
