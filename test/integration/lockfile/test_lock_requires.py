import json
import os
import textwrap
import time

import pytest

from conan.api.model import RecipeReference
from conan.test.assets.genconanfile import GenConanfile
from conan.test.utils.tools import TestClient


@pytest.mark.parametrize("requires", ["requires", "tool_requires"])
def test_conanfile_txt_deps_ranges(requires):
    """
    conanfile.txt locking it dependencies (with version ranges)
    """
    client = TestClient(light=True)
    client.save({"pkg/conanfile.py": GenConanfile(),
                 "consumer/conanfile.txt": f"[{requires}]\npkg/[>0.0]@user/testing"})
    client.run("create pkg --name=pkg --version=0.1 --user=user --channel=testing")
    client.run("lock create consumer/conanfile.txt")
    assert "pkg/0.1@user/testing#" in client.out

    client.run("create pkg --name=pkg --version=0.2 --user=user --channel=testing")

    client.run("install consumer/conanfile.txt")
    assert "pkg/0.1@user/testing#" in client.out
    assert "pkg/0.2" not in client.out

    os.remove(os.path.join(client.current_folder, "consumer/conan.lock"))
    client.run("install consumer/conanfile.txt")
    assert "pkg/0.2@user/testing#" in client.out
    assert "pkg/0.1" not in client.out


@pytest.mark.parametrize("command", ["install", "create", "graph info", "export-pkg"])
def test_lockfile_out(command):
    # Check that lockfile out is generated for different commands
    c = TestClient(light=True)
    c.save({"dep/conanfile.py": GenConanfile("dep", "0.1"),
            "pkg/conanfile.py": GenConanfile("pkg", "0.1").with_requires("dep/[*]")})
    c.run("create dep")
    c.run(f"{command} pkg --lockfile-out=conan.lock")
    lock = c.load("conan.lock")
    assert "dep/0.1" in lock


def test_lockfile_out_export():
    # Check that lockfile out is generated for "conan export"
    c = TestClient(light=True)
    c.save({"pkg/conanfile.py": GenConanfile("pkg", "0.1")})
    c.run("export pkg --lockfile-out=conan.lock")
    lock = c.load("conan.lock")
    assert "pkg/0.1" in lock


@pytest.mark.parametrize("requires", ["requires", "tool_requires"])
def test_conanfile_txt_deps_ranges_transitive(requires):
    """
    conanfile.txt locking it dependencies and its transitive dependencies (with version ranges)
    """
    client = TestClient(light=True)
    client.save({"dep/conanfile.py": GenConanfile(),
                 "pkg/conanfile.py": GenConanfile().with_requires("dep/[>0.0]@user/testing"),
                 "consumer/conanfile.txt": f"[{requires}]\npkg/[>0.0]@user/testing"})
    client.run("create dep --name=dep --version=0.1 --user=user --channel=testing")
    client.run("create pkg --name=pkg --version=0.1 --user=user --channel=testing")

    client.run("lock create consumer/conanfile.txt")
    assert "dep/0.1@user/testing#" in client.out
    assert "pkg/0.1@user/testing#" in client.out

    client.run("create dep --name=dep --version=0.2 --user=user --channel=testing")

    client.run("install consumer/conanfile.txt")
    assert "dep/0.1@user/testing#" in client.out
    assert "dep/0.2" not in client.out

    os.remove(os.path.join(client.current_folder, "consumer/conan.lock"))
    client.run("install consumer/conanfile.txt", assert_error=True)
    assert "dep/0.2@user/testing#" in client.out
    assert "dep/0.1" not in client.out


@pytest.mark.parametrize("requires", ["requires", "tool_requires"])
def test_conanfile_txt_strict(requires):
    """
    conanfile.txt locking it dependencies (with version ranges)
    """
    client = TestClient(light=True)
    client.save({"pkg/conanfile.py": GenConanfile(),
                 "consumer/conanfile.txt": f"[{requires}]\npkg/[>0.0]@user/testing"})
    client.run("create pkg --name=pkg --version=0.1 --user=user --channel=testing")
    client.run("lock create consumer/conanfile.txt")
    assert "pkg/0.1@user/testing#" in client.out

    client.run("create pkg --name=pkg --version=0.2 --user=user --channel=testing")
    client.run("create pkg --name=pkg --version=1.2 --user=user --channel=testing")

    # Not strict mode works
    client.save({"consumer/conanfile.txt": f"[{requires}]\npkg/[>1.0]@user/testing"})

    client.run("install consumer/conanfile.txt", assert_error=True)
    kind = "build_requires" if requires == "tool_requires" else "requires"
    assert f"Requirement 'pkg/[>1.0]@user/testing' not in lockfile '{kind}'" in client.out

    client.run("install consumer/conanfile.txt --lockfile-partial")
    assert "pkg/1.2@user/testing" in client.out
    assert "pkg/1.2" not in client.load("consumer/conan.lock")

    # test it is possible to capture new changes too, when not strict, mutating the lockfile
    client.run("install consumer/conanfile.txt --lockfile-partial --lockfile-out=conan.lock")
    assert "pkg/1.2@user/testing" in client.out
    lock = client.load("conan.lock")
    assert "pkg/1.2" in lock
    assert "pkg/0.1" in lock  # both versions are locked now
    # clean legacy versions
    client.run("lock create consumer/conanfile.txt --lockfile-out=conan.lock --lockfile-clean")
    lock = client.load("conan.lock")
    assert "pkg/1.2" in lock
    assert "pkg/0.1" not in lock


@pytest.mark.parametrize("requires", ["requires", "tool_requires"])
def test_conditional_os(requires):
    """
    conanfile.txt can lock conditional dependencies (conditional on OS for example),
    with consecutive calls to "conan lock create", augmenting the lockfile
    """
    client = TestClient(light=True)

    pkg_conanfile = textwrap.dedent(f"""
        from conan import ConanFile
        class Pkg(ConanFile):
            settings = "os"
            def requirements(self):
                if self.settings.os == "Windows":
                    self.requires("win/[>0.0]")
                else:
                    self.requires("nix/[>0.0]")
        """)
    client.save({"dep/conanfile.py": GenConanfile(),
                 "pkg/conanfile.py": pkg_conanfile,
                 "consumer/conanfile.txt": f"[{requires}]\npkg/0.1"})
    client.run("create dep --name=win --version=0.1")
    client.run("create dep --name=nix --version=0.1")

    client.run("create pkg --name=pkg --version=0.1 -s os=Windows")
    client.run("create pkg --name=pkg --version=0.1 -s os=Linux")

    client.run("lock create consumer/conanfile.txt  --lockfile-out=consumer.lock -s os=Windows"
               " -s:b os=Windows")
    assert "win/0.1#" in client.out
    assert "pkg/0.1#" in client.out
    client.run("lock create consumer/conanfile.txt  --lockfile=consumer.lock "
               "--lockfile-out=consumer.lock -s os=Linux -s:b os=Linux")
    assert "nix/0.1#" in client.out
    assert "pkg/0.1#" in client.out

    # New dependencies will not be used if using the lockfile
    client.run("create dep --name=win --version=0.2")
    client.run("create dep --name=nix --version=0.2")
    client.run("create pkg --name=pkg --version=0.1 -s os=Windows")
    client.run("create pkg --name=pkg --version=0.1 -s os=Linux")

    client.run("install consumer --lockfile=consumer.lock -s os=Windows -s:b os=Windows")
    assert "win/0.1#" in client.out
    assert "win/0.2" not in client.out
    client.run("install consumer -s os=Windows -s:b os=Windows")
    assert "win/0.2#" in client.out
    assert "win/0.1" not in client.out
    assert "nix/0.1" not in client.out

    client.run("install consumer --lockfile=consumer.lock -s os=Linux -s:b os=Linux")
    assert "nix/0.1#" in client.out
    assert "nix/0.2" not in client.out
    client.run("install consumer -s os=Linux -s:b os=Linux")
    assert "nix/0.2#" in client.out
    assert "nix/0.1" not in client.out
    assert "win/" not in client.out


@pytest.mark.parametrize("requires", ["requires", "tool_requires"])
def test_conditional_same_package(requires):
    # What happens when a conditional requires different versions of the same package?
    client = TestClient(light=True)

    pkg_conanfile = textwrap.dedent("""
        from conan import ConanFile
        class Pkg(ConanFile):
            settings = "os"
            def requirements(self):
                if self.settings.os == "Windows":
                    self.requires("dep/0.1")
                else:
                    self.requires("dep/0.2")
        """)
    client.save({"dep/conanfile.py": GenConanfile(),
                 "pkg/conanfile.py": pkg_conanfile,
                 "consumer/conanfile.txt": f"[{requires}]\npkg/0.1"})
    client.run("create dep --name=dep --version=0.1")
    client.run("create dep --name=dep --version=0.2")

    client.run("create pkg --name=pkg --version=0.1 -s os=Windows")
    client.run("create pkg --name=pkg --version=0.1 -s os=Linux")

    client.run("lock create consumer/conanfile.txt  --lockfile-out=conan.lock -s os=Windows"
               " -s:b os=Windows")
    assert "dep/0.1#" in client.out
    assert "dep/0.2" not in client.out
    client.run("lock create consumer/conanfile.txt  --lockfile=conan.lock "
               "--lockfile-out=conan.lock -s os=Linux -s:b os=Linux")
    assert "dep/0.2#" in client.out
    assert "dep/0.1" not in client.out

    client.run("install consumer --lockfile=conan.lock --lockfile-out=win.lock -s os=Windows"
               " -s:b os=Windows")
    assert "dep/0.1#" in client.out
    assert "dep/0.2" not in client.out

    client.run("install consumer --lockfile=conan.lock --lockfile-out=linux.lock -s os=Linux"
               " -s:b os=Linux")
    assert "dep/0.2#" in client.out
    assert "dep/0.1" not in client.out


@pytest.mark.parametrize("requires", ["requires", "build_requires"])
def test_conditional_incompatible_range(requires):
    client = TestClient(light=True)

    pkg_conanfile = textwrap.dedent("""
        from conan import ConanFile
        class Pkg(ConanFile):
            settings = "os"
            def requirements(self):
                if self.settings.os == "Windows":
                    self.requires("dep/[<1.0]")
                else:
                    self.requires("dep/[>=1.0]")
        """)
    client.save({"dep/conanfile.py": GenConanfile(),
                 "pkg/conanfile.py": pkg_conanfile,
                 "consumer/conanfile.txt": "[requires]\npkg/0.1"})
    client.run("create dep --name=dep --version=0.1")
    client.run("create dep --name=dep --version=1.1")

    client.run("create pkg --name=pkg --version=0.1 -s os=Windows")
    client.run("create pkg --name=pkg --version=0.1 -s os=Linux")

    client.run("lock create consumer/conanfile.txt  --lockfile-out=conan.lock -s os=Windows"
               " -s:b os=Windows")
    assert "dep/0.1#" in client.out
    assert "dep/1.1" not in client.out
    # The previous lock was locking dep/0.1. This new lock will not use dep/0.1 as it is outside
    # of its range, can't lock to it and will depend on dep/1.1. Both dep/0.1 for Windows and
    # dep/1.1 for Linux now coexist in the lock
    client.run("lock create consumer/conanfile.txt  --lockfile=conan.lock "
               "--lockfile-out=conan.lock -s os=Linux -s:b os=Linux")
    assert "dep/1.1#" in client.out
    assert "dep/0.1" not in client.out
    lock = client.load("conan.lock")
    assert "dep/0.1" in lock
    assert "dep/1.1" in lock

    # These will not be used, lock will avoid them
    client.run("create dep --name=dep --version=0.2")
    client.run("create dep --name=dep --version=1.2")

    client.run("install consumer --lockfile=conan.lock --lockfile-out=win.lock -s os=Windows"
               " -s:b os=Windows")
    assert "dep/0.1#" in client.out
    assert "dep/1.1" not in client.out

    client.run("install consumer --lockfile=conan.lock --lockfile-out=linux.lock -s os=Linux"
               " -s:b os=Linux")
    assert "dep/1.1#" in client.out
    assert "dep/0.1" not in client.out


@pytest.mark.parametrize("requires", ["requires", "tool_requires"])
def test_conditional_compatible_range(requires):
    client = TestClient(light=True)

    pkg_conanfile = textwrap.dedent("""
        from conan import ConanFile
        class Pkg(ConanFile):
            settings = "os"
            def requirements(self):
                if self.settings.os == "Windows":
                    self.requires("dep/[<0.2]")
                else:
                    self.requires("dep/[>0.0]")
        """)
    client.save({"dep/conanfile.py": GenConanfile(),
                 "pkg/conanfile.py": pkg_conanfile,
                 "consumer/conanfile.txt": f"[{requires}]\npkg/0.1"})
    client.run("create dep --name=dep --version=0.1")
    client.run("create dep --name=dep --version=0.2")

    client.run("create pkg --name=pkg --version=0.1 -s os=Windows")
    client.run("create pkg --name=pkg --version=0.1 -s os=Linux")

    client.run("lock create consumer/conanfile.txt  --lockfile-out=conan.lock -s os=Linux"
               " -s:b os=Linux")
    assert "dep/0.2#" in client.out
    assert "dep/0.1" not in client.out
    client.run("lock create consumer/conanfile.txt  --lockfile=conan.lock "
               "--lockfile-out=conan.lock -s os=Windows -s:b os=Windows")
    assert "dep/0.1#" in client.out
    assert "dep/0.2" not in client.out

    # These will not be used, lock will avoid them
    client.run("create dep --name=dep --version=0.1.1")
    client.run("create dep --name=dep --version=0.3")

    client.run("install consumer --lockfile=conan.lock --lockfile-out=win.lock -s os=Windows"
               " -s:b os=Windows")
    assert "dep/0.1#" in client.out
    assert "dep/0.2" not in client.out
    assert "dep/0.1.1" not in client.out

    client.run("install consumer --lockfile=conan.lock --lockfile-out=linux.lock -s os=Linux "
               " -s:b os=Linux")
    assert "dep/0.2#" in client.out
    assert "dep/0.1" not in client.out
    assert "dep/0.3" not in client.out


def test_partial_lockfile():
    """
    make sure that a partial lockfile can be applied anywhere downstream without issues,
    as lockfiles by default are not strict
    """
    c = TestClient(light=True)
    c.save({"pkga/conanfile.py": GenConanfile("pkga"),
            "pkgb/conanfile.py": GenConanfile("pkgb", "0.1").with_requires("pkga/[*]"),
            "pkgc/conanfile.py": GenConanfile("pkgc", "0.1").with_requires("pkgb/[*]"),
            "app/conanfile.py": GenConanfile("app", "0.1").with_requires("pkgc/[*]")})
    c.run("create pkga --version=0.1")
    c.run("lock create pkgb --lockfile-out=b.lock")
    c.run("create pkga --version=0.2")
    c.run("create pkgb --lockfile=b.lock")
    assert "pkga/0.1" in c.out
    assert "pkga/0.2" not in c.out
    c.run("install pkgc --lockfile=b.lock --lockfile-partial")
    assert "pkga/0.1" in c.out
    assert "pkga/0.2" not in c.out
    c.run("create pkgc  --lockfile=b.lock --lockfile-partial")
    assert "pkga/0.1" in c.out
    assert "pkga/0.2" not in c.out
    c.run("create app --lockfile=b.lock --lockfile-partial")
    assert "pkga/0.1" in c.out
    assert "pkga/0.2" not in c.out
    c.run("create app --lockfile=b.lock", assert_error=True)
    assert "ERROR: Requirement 'pkgc/[*]' not in lockfile" in c.out


def test_ux_defaults():
    # Make sure the when explicit ``--lockfile`` argument, the file must exist, even if is conan.lock
    c = TestClient(light=True)
    c.save({"conanfile.txt": ""})
    c.run("install . --lockfile=conan.lock", assert_error=True)
    assert "ERROR: Lockfile doesn't exist" in c.out


class TestLockTestPackage:

    @pytest.fixture()
    def client(self):
        c = TestClient()
        test_package = textwrap.dedent("""
            from conan import ConanFile

            class TestPackageConan(ConanFile):
                settings = "os", "compiler", "arch", "build_type"
                def build_requirements(self):
                    self.tool_requires("cmake/[*]")
                def requirements(self):
                    self.requires(self.tested_reference_str)
                def test(self):
                    print("package tested")
            """)

        c.save({"cmake/conanfile.py": GenConanfile("cmake"),
                "dep/conanfile.py": GenConanfile("dep"),
                "app/conanfile.py": GenConanfile("app", "1.0").with_requires("dep/[*]"),
                "app/test_package/conanfile.py": test_package})

        c.run("create cmake --version=1.0")
        c.run("create dep --version=1.0")
        return c

    def test_lock_tool_requires_test(self, client):
        # https://github.com/conan-io/conan/issues/11763
        c = client
        with c.chdir("app"):
            c.run("lock create .")
            lock = c.load("conan.lock")
            assert "cmake/1.0" not in lock
            assert "dep/1.0" in lock
            c.run("lock create test_package --lockfile=conan.lock --lockfile-out=conan.lock")
            lock = c.load("conan.lock")
            assert "cmake/1.0" in lock
            assert "dep/1.0" in lock

        c.run("create cmake --version=2.0")
        c.run("create dep --version=2.0")
        with c.chdir("app"):
            c.run("create . --lockfile=conan.lock")
            assert "cmake/1.0" in c.out
            assert "dep/1.0" in c.out
            assert "cmake/2.0" not in c.out
            assert "dep/2.0" not in c.out
            assert "package tested" in c.out

    def test_partial_approach(self, client):
        """ do not include it in the lockfile, but apply it partially, so the tool_require is
        free, will freely upgrade
        """
        c = client
        # https://github.com/conan-io/conan/issues/11763
        with c.chdir("app"):
            c.run("lock create .")
            lock = c.load("conan.lock")
            assert "cmake/1.0" not in lock
            assert "dep/1.0" in lock

        c.run("create cmake --version=2.0")
        c.run("create dep --version=2.0")
        with c.chdir("app"):
            c.run("create . --lockfile=conan.lock --lockfile-partial")
            assert "cmake/2.0" in c.out  # because it is in test_package and not locked
            assert "dep/1.0" in c.out
            assert "cmake/1.0" not in c.out
            assert "dep/2.0" not in c.out
            assert "package tested" in c.out

        # or to be more guaranteed
        with c.chdir("app"):
            c.run("create . --lockfile=conan.lock -tf=\"\"")
            assert "cmake" not in c.out
            assert "dep/1.0" in c.out
            assert "dep/2.0" not in c.out
            assert "package tested" not in c.out

            c.run("test test_package app/1.0 --lockfile=conan.lock --lockfile-partial")
            assert "cmake/1.0" not in c.out
            assert "cmake/2.0" in c.out
            assert "dep/1.0" in c.out
            assert "dep/2.0" not in c.out
            assert "package tested" in c.out

    def test_create_lock_tool_requires_test(self, client):
        """ same as above, but the full lockfile including the "test_package" can be
        obtained with a "conan test"
        """
        c = client
        with c.chdir("app"):
            c.run("create . --lockfile-out=conan.lock -tf=")
            lock = c.load("conan.lock")
            assert "cmake/1.0" not in lock
            assert "dep/1.0" in lock
            c.run("test test_package app/1.0 --lockfile-partial --lockfile=conan.lock "
                  "--lockfile-out=conan.lock")
            lock = c.load("conan.lock")
            assert "cmake/1.0" in lock
            assert "dep/1.0" in lock

        c.run("create cmake --version=2.0")
        c.run("create dep --version=2.0")
        with c.chdir("app"):
            c.run("create . --lockfile=conan.lock")
            assert "cmake/1.0" in c.out
            assert "dep/1.0" in c.out
            assert "cmake/2.0" not in c.out
            assert "dep/2.0" not in c.out
            assert "package tested" in c.out

    def test_test_package_lockfile(self):
        c = TestClient(light=True)
        test = textwrap.dedent("""
            from conan import ConanFile
            class TestBasicConanfile(ConanFile):
                def requirements(self):
                    self.requires(self.tested_reference_str)
                    self.requires("pkga/1.0")
                def test(self):
                    pass
            """)
        c.save({"pkga/conanfile.py": GenConanfile("pkga", "1.0"),
                "pkgb/conanfile.py": GenConanfile("pkgb", "1.0"),
                "pkgb/test_package/conanfile.py": test})
        c.run("create pkga")
        c.run("lock create pkgb")

        # alternative 1, relax lockfile
        c.run("create pkgb --lockfile-partial")

        # alternative 2, do not run test_package with same lockfile
        c.run("create pkgb --test-folder=")
        # the test_package can be tested later, so the lockfile-partial only affects the test_package
        c.run("test pkgb/test_package pkgb/1.0 --lockfile=pkgb/conan.lock --lockfile-partial")
        assert "Using lockfile:" in c.out

        # alternative 3, create the lockfile in the test_package
        c.run("lock create pkgb/test_package --lockfile=pkgb/conan.lock "
              "--lockfile-out=pkgb/test_package/conan.lock")
        lockfile = c.load("pkgb/test_package/conan.lock")
        assert "pkga/1.0" in lockfile
        c.run("test pkgb/test_package pkgb/1.0 --lockfile=pkgb/test_package/conan.lock "
              "--lockfile-partial")

        # alternative 4, add the test_package dependencies to the main lockfile
        c.run("lock create pkgb/test_package --lockfile=pkgb/conan.lock "
              "--lockfile-out=pkgb/conan.lock")
        lockfile = c.load("pkgb/conan.lock")
        assert "pkga/1.0" in lockfile
        c.run("create pkgb --lockfile=pkgb/conan.lock")


class TestErrorDuplicates:
    def test_error_duplicates(self):
        """ the problem is having 2 different, almost identical requires that will point to the same
        thing, with different traits and not colliding.
        Lockfiles do a ``require.ref`` update and that alters some dictionaries iteration, producing
        an infinite loop and blocking
        """
        c = TestClient(light=True)
        pkg = textwrap.dedent("""
            from conan import ConanFile
            class Pkg(ConanFile):
                name = "pkg"
                version = "0.1"
                def requirements(self):
                    self.requires("dep/0.1#f8c2264d0b32a4c33f251fe2944bb642", headers=False, libs=False,
                                visible=False)
                    self.requires("dep/0.1", headers=True, libs=False, visible=False)
                """)
        c.save({"dep/conanfile.py": GenConanfile("dep", "0.1"),
                "pkg/conanfile.py": pkg})
        c.run("create dep --lockfile-out=conan.lock")
        c.run("create pkg", assert_error=True)
        assert "Duplicated requirement: dep/0.1" in c.out
        c.run("create pkg --lockfile=conan.lock", assert_error=True)
        assert "Duplicated requirement: dep/0.1" in c.out

    def test_error_duplicates_reverse(self):
        """ Same as above, but order requires changed
        """
        c = TestClient(light=True)
        pkg = textwrap.dedent("""
            from conan import ConanFile
            class Pkg(ConanFile):
                name = "pkg"
                version = "0.1"
                def requirements(self):
                    self.requires("dep/0.1", headers=True, libs=False, visible=False)
                    self.requires("dep/0.1#f8c2264d0b32a4c33f251fe2944bb642", headers=False, libs=False,
                                visible=False)
                """)
        c.save({"dep/conanfile.py": GenConanfile("dep", "0.1"),
                "pkg/conanfile.py": pkg})
        c.run("create dep --lockfile-out=conan.lock")
        c.run("create pkg", assert_error=True)
        assert "Duplicated requirement: dep/0.1" in c.out
        c.run("create pkg --lockfile=conan.lock", assert_error=True)
        assert "Duplicated requirement: dep/0.1" in c.out

    def test_error_duplicates_revisions(self):
        """ 2 different revisions can be added without conflict, if they are not visible and not
        other conflicting traits
        """
        c = TestClient(light=True)
        pkg = textwrap.dedent("""
            from conan import ConanFile
            class Pkg(ConanFile):
                name = "pkg"
                version = "0.1"
                def requirements(self):
                    self.requires("dep/0.1#f8c2264d0b32a4c33f251fe2944bb642", headers=False,
                                  libs=False, visible=False)
                    self.requires("dep/0.1#7b91e6100797b8b012eb3cdc5544800b", headers=True,
                                  libs=False, visible=False)
                """)
        c.save({"dep/conanfile.py": GenConanfile("dep", "0.1"),
                "dep2/conanfile.py": GenConanfile("dep", "0.1").with_class_attribute("potato=42"),
                "pkg/conanfile.py": pkg})
        c.run("create dep --lockfile-out=conan.lock")
        c.run("create dep2 --lockfile=conan.lock --lockfile-out=conan.lock")

        c.run("create pkg")
        assert "dep/0.1#f8c2264d0b32a4c33f251fe2944bb642 - Cache" in c.out
        assert "dep/0.1#7b91e6100797b8b012eb3cdc5544800b - Cache" in c.out
        c.run("create pkg --lockfile=conan.lock")
        assert "dep/0.1#f8c2264d0b32a4c33f251fe2944bb642 - Cache" in c.out
        assert "dep/0.1#7b91e6100797b8b012eb3cdc5544800b - Cache" in c.out


def test_revision_timestamp():
    """
    https://github.com/conan-io/conan/issues/14108
    """
    c = TestClient(default_server_user=True)

    c.save({"pkg/conanfile.py": GenConanfile("pkg", "0.1")})
    # revision 0
    c.run("export pkg")
    c.save({"pkg/conanfile.py": GenConanfile("pkg", "0.1").with_class_attribute("_my=1")})
    # revision 1
    c.run("export pkg")
    rrev = c.exported_recipe_revision()
    c.run("upload *#* -r=default -c")
    c.save({"pkg/conanfile.py": GenConanfile("pkg", "0.1").with_class_attribute("_my=2")})
    # revision 2
    time.sleep(1)
    c.run("export pkg")
    latest_rrev = c.exported_recipe_revision()
    c.run("upload * -r=default -c")
    c.run("remove * -c")
    c.run("list *#* -r=default --format=json")
    list_json = json.loads(c.stdout)
    server_timestamp = list_json["default"]["pkg/0.1"]["revisions"][latest_rrev]["timestamp"]

    time.sleep(2)
    ref = RecipeReference.loads(f"pkg/0.1#{rrev}")
    # we force the lock to include the 2nd revision
    c.save({"conanfile.txt": f"[requires]\n{repr(ref)}"}, clean_first=True)

    c.run("lock create .")
    lock = c.load("conan.lock")
    lock = json.loads(lock)
    locked_ref = RecipeReference.loads(lock["requires"][0])
    assert locked_ref == ref
    assert locked_ref.timestamp and locked_ref.timestamp != server_timestamp


class TestLockfileUpdate:
    """
    Check that --update works
    """

    @pytest.mark.parametrize("requires", ["requires", "tool_requires"])
    def test_conanfile_txt_deps_ranges(self, requires):
        """
        conanfile.txt locking it dependencies (with version ranges)
        """
        c = TestClient(default_server_user=True)
        c.save({"pkg/conanfile.py": GenConanfile("pkg"),
                "consumer/conanfile.txt": f"[{requires}]\npkg/[>0.0]"})
        c.run("create pkg --version=0.1")
        c.run("create pkg --version=0.2")
        c.run("upload pkg/0.2 -r=default -c")
        c.run("remove pkg/0.2 -c")
        c.run("list *")
        assert "pkg/0.2" not in c.out
        c.run("lock create consumer/conanfile.txt --update")
        assert "pkg/0.1" not in c.out
        assert "pkg/0.2" in c.out
        lock = c.load("consumer/conan.lock")
        assert "pkg/0.1" not in lock
        assert "pkg/0.2" in lock


def test_error_test_explicit():
    # https://github.com/conan-io/conan/issues/14833
    client = TestClient(light=True)
    test = GenConanfile().with_test("pass").with_class_attribute("test_type = 'explicit'")
    client.save({"conanfile.py": GenConanfile("pkg", "0.1"),
                 "test_package/conanfile.py": test})
    client.run("lock create conanfile.py --lockfile-out=my.lock")
    client.run("create . --lockfile=my.lock")


def test_lock_error_create():
    # https://github.com/conan-io/conan/issues/15801
    c = TestClient(light=True)
    c.save({"conanfile.py": GenConanfile("pkg", "0.1").with_package_type("build-scripts")})
    c.run("lock create . -u --lockfile-out=none.lock")
    lock = json.loads(c.load("none.lock"))
    assert lock["requires"] == []
    assert lock["build_requires"] == []
    c.run("create . --lockfile=none.lock --lockfile-out=none_updated.lock")
    # It doesn't crash, it used to
    lock = json.loads(c.load("none_updated.lock"))
    assert lock["requires"] == []
    assert len(lock["build_requires"]) == 1
    assert "pkg/0.1#4e9dba5c3041ba4c87724486afdb7eb4" in lock["build_requires"][0]


def test_lock_error():
    # https://github.com/conan-io/conan/issues/17363
    c = TestClient()
    transitive_dep = textwrap.dedent("""
        # recipes/transitive_dep/conanfile.py
        from conan import ConanFile

        class TransitiveDepConan(ConanFile):
            name = "transitive_dep"
            version = "2.0.0"
            settings = "build_type"
            """)
    build_tool = textwrap.dedent("""
        # recipes/build_tool/conanfile.py
        from conan import ConanFile

        class BuildToolConan(ConanFile):
            name = "build_tool"
            version = "1.0.0"
            settings = "build_type"

            def requirements(self):
                self.requires("transitive_dep/2.0.0")
        """)
    build_tool_test = textwrap.dedent("""
        # recipes/build_tool/test_package/conanfile.py
        from conan import ConanFile

        class TestPackageConan(ConanFile):
            settings = "build_type"
            test_type = "explicit"

            def requirements(self):
                self.requires(self.tested_reference_str)

            def test(self):
                pass
        """)
    runtime_dep = textwrap.dedent("""
        # recipes/runtime_dep/conanfile.py
        from conan import ConanFile

        class RuntimeDepConan(ConanFile):
            name = "runtime_dep"
            version = "1.2.3"
            settings = "build_type"

            def build_requirements(self):
                self.tool_requires("build_tool/1.0.0")
        """)
    consumer = textwrap.dedent("""
        # recipes/consumer/conanfile.py
        from conan import ConanFile

        class ConsumerConan(ConanFile):
            name = "consumer"
            version = "0.0.1"
            settings = "build_type"

            def requirements(self):
                self.requires("runtime_dep/1.2.3")
        """)
    c.save({"recipes/transitive_dep/conanfile.py": transitive_dep,
            "recipes/build_tool/conanfile.py": build_tool,
            "recipes/build_tool/test_package/conanfile.py": build_tool_test,
            "recipes/runtime_dep/conanfile.py": runtime_dep,
            "recipes/consumer/conanfile.py": consumer,
            })
    c.run("export recipes/transitive_dep")
    c.run("export recipes/build_tool")
    c.run("export recipes/runtime_dep")

    settings = "-s:b build_type=Release -s:h build_type=Debug"
    c.run(f"lock create recipes/consumer --no-remote {settings}")

    c.run(f"graph build-order recipes/consumer {settings} --build=missing --order-by=configuration "
          "--reduce  --format=json", redirect_stdout="build_order.json")
    assert "Using lockfile:" in c.out

    ref = "transitive_dep/2.0.0"
    c.run(f"install --tool-requires={ref} {settings} --build={ref} "
          "--lockfile=recipes/consumer/conan.lock ")
    # The test of ``trantisive_dep`` doesn't have the test_package

    ref = "build_tool/1.0.0"
    c.run(f"install --tool-requires={ref} {settings} --build={ref} "
          "--lockfile=recipes/consumer/conan.lock ")

    ref = "runtime_dep/1.2.3"
    c.run(f"install --requires={ref} {settings} --build={ref} "
          "--lockfile=recipes/consumer/conan.lock ")

