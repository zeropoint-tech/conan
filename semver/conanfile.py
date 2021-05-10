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

        self.version = git_get_semver(self.name)


def parseVer(version):
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



def git_get_semver(name="module", ref_name="HEAD", branch=None):
    """
    Calculate the Semantic Version base on git tags and brances.

    The following cases exist:

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

    UNTAGGED:
         No valid SemVer exists, return "0.0.0"

    Examples:

        A---B(module/0.1.3)---C(other_module/0.3.5)---D                   master
                              |\                     /
                              | E---F---------------G(module/0.2.1)---H   release/module/0.2
                              |  \                   \
                              I---J---K---------------O---P               dev
                               \                       \
                                L---M---N---------------Q                 feat/amazing

        Here A is UNTAGGED, B is TAGGED and C is PARENT-TAGGED
        >>> git_get_semver("A")
        '0.0.0'
        >>> git_get_semver("B")
        '0.1.3'
        >>> git_get_semver("C")
        '0.1.4-rc1-ghash(C)'

        D is a merge where both ancestors are TAGGED, use the larger SemVer
        and proceed as PARENT-TAGGED
        >>> git_get_semver("D")
        '0.2.2-rc2-ghash(D)'

        E and F are bothn on the "release/module/0.2" branch and are interpreted
        as RELEASE-BRANCH.
        G is TAGGED and H is RELEASE-BRANCH-TAGGED.
        >>> git_get_semver("E", "release/module/0.2")
        '0.2.0-rc1-ghash(E)'
        >>> git_get_semver("F", "release/module/0.2")
        '0.2.0-rc2-ghash(F)'
        >>> git_get_semver("G", "release/module/0.2")
        '0.2.1'
        >>> git_get_semver("H", "release/module/0.2")
        '0.2.2-rc1-ghash(H)'

        I is on the "dev" branch and PARENT-TAGGED from B
        >>> git_get_semver("I", "dev")
        '0.1.4-rc2-ghash(I)'

        J is a merge of the release branch into "dev", since there is no tag
        ancestor in the release branch, J is PARENT-TAGGED from B.
        The number of commits is calculated as count(J, I, E, C)
        K, L, M, and N follows J
        >>> git_get_semver("J", "dev")
        '0.1.4-rc4-ghash(J)'
        >>> git_get_semver("K", "dev")
        '0.1.4-rc5-ghash(K)'
        >>> git_get_semver("L", "feat/amazing")
        '0.1.4-rc6-ghash(L)'
        >>> git_get_semver("M", "feat/amazing")
        '0.1.4-rc7-ghash(M)'
        >>> git_get_semver("N", "feat/amazing")
        '0.1.4-rc8-ghash(N)'

        O is a merge of the release branch into "dev". In this case there
        is a tagged ancestor in the release branch, so O is PARENT-TAGGED from G

        The number of commits is calculated as count(O, K, J, I, C)
        >>> git_get_semver("O", "dev")
        '0.2.2-rc5-ghash(O)'

        >>> git_get_semver("P", "dev")
        '0.2.2-rc6-ghash(P)'

        Q is a merge of the "dev" branch into "feat/amazing". It inherits the
        tagged ancestor and is PARENT-TAGGED from G.
        The number of commits is calculated as count(Q, N, M, L, O, K, J, I, C)
        >>> git_get_semver("Q", "feat/amazing")
        '0.2.2-rc9-ghash(Q)'
        >>> git_get_semver("R")
        '0.2.2-rc3-ghash(R)'
    """

    git = tools.Git()
    git_root = git.run("rev-parse --show-toplevel")

    if branch is None:
        try:
            branch = git.get_branch()
        except:
            # Not in a git repo
            return VersionRep("0.0.0")

    try:
        ref = git.run(f"rev-parse --verify {ref_name}")
    except:
        return VersionRep("0.0.0")

    # Find nearest tag
    try:
        # If not in a git repo this command will output error to stderr.
        # So we redirect the error message to /dev/null
        prev_tag = git.run(f"describe --tags --abbrev=0 --match {name}/\\* {ref} 2> /dev/null")
        commits_behind_tag = int(git.run(f"rev-list --count {prev_tag}..{ref} -- {git_root}/{name}"))
    except:
        prev_tag = "0.0.0"
        commits_behind_tag = 0

    prefix = name + "/"
    if prev_tag.startswith(prefix):
        prev_tag = prev_tag[len(prefix):]
    if prev_tag.startswith("v"):
        prev_tag = prev_tag[1:]
    tag_version = VersionRep(prev_tag)

    # Find root of release branch, if any
    base_version = None
    commits_behind_branch = None
    release = None

    for prefix in [f"release/{name}/", f"origin/release/{name}"]:
        if branch.startswith(prefix):
            release = branch[len(prefix):]
            break

    if release:
        try:
            master_ref = "master"
            base_ref = None
            while git.run(f"rev-parse --verify {master_ref}"):
                base_candidate = git.run(f"merge-base {master_ref} {ref}")
                # print(base_candidate, ref, is_ancestor)
                if base_candidate != ref:
                    base_ref = base_candidate
                    commits_behind_branch = int(git.run(f"rev-list --count {base_ref}..{ref} -- {git_root}/{name}"))
                    release = branch[len(prefix):]
                    base_version = VersionRep(release)
                    break
                # Skip to previous master to avoid merges into master
                master_ref += "^"
        except:
            pass

    commits_behind = commits_behind_tag
    if commits_behind_branch:
        commits_behind = min(commits_behind, commits_behind_branch)

    # print(ref_name, prev_tag, commits_behind_tag, branch, str(base_version), str(commits_behind_branch), commits_behind, str(tag_version))

    if base_version and tag_version < base_version:
        version = base_version
        commits_behind = commits_behind_branch
    else:
        version = tag_version
        commits_behind = commits_behind_tag

    if commits_behind > 0:
        version.patch += 1
        version.prerelease = f"rc{commits_behind}-g{ref[:10]}"

    print(f"Calculated semantic version {version} from commit {ref} with tag {prev_tag} and branch {release}")

    return str(version)


class Pkg(ConanFile):
    name = "semver"
    license = "LICENSE"
    url = "git@bitbucket.org:zpt/conan.git"
    description = "Semantic Versions derived from Git tags and branches"

    def set_version(self):
        if self.version != None:
            return

        self.version = git_get_semver(self.name)

    pass

