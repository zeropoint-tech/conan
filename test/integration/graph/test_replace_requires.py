import json
import textwrap

import pytest

from conan.api.model import RecipeReference
from conan.test.assets.genconanfile import GenConanfile
from conan.test.utils.tools import TestClient


@pytest.mark.parametrize("require, pattern, alternative, pkg", [
    # PATTERN VERSIONS
    # override all dependencies to "dep" to a specific version,user and channel)
    # TODO: This is a version override, is this really wanted?
    ("dep/1.3", "dep/*", "dep/1.1", "dep/1.1"),
    ("dep/[>=1.0 <2]", "dep/*", "dep/1.1", "dep/1.1"),
    # override all dependencies to "dep" to the same version with other user, remove channel)
    ("dep/1.3", "dep/*", "dep/*@system", "dep/1.3@system"),
    ("dep/[>=1.0 <2]", "dep/*", "dep/*@system", "dep/1.1@system"),
    # override all dependencies to "dep" to the same version with other user, same channel)
    ("dep/1.3@comp/stable", "dep/*@*/*", "dep/*@system/*", "dep/1.3@system/stable"),
    ("dep/[>=1.0 <2]@comp/stable", "dep/*@*/*", "dep/*@system/*", "dep/1.1@system/stable"),
    # EXACT VERSIONS
    # replace exact dependency version for one in the system
    ("dep/1.1", "dep/1.1", "dep/1.1@system", "dep/1.1@system"),
    ("dep/[>=1.0 <2]", "dep/1.1", "dep/1.1@system", "dep/1.1@system"),
    ("dep/[>=1.0 <2]@comp", "dep/1.1@*", "dep/1.1@*/stable", "dep/1.1@comp/stable"),
    ("dep/1.1@comp", "dep/1.1@*", "dep/1.1@*/stable", "dep/1.1@comp/stable"),
    # PACKAGE ALTERNATIVES (zlib->zlibng)
    ("dep/1.0", "dep/*", "depng/*", "depng/1.0"),
    ("dep/[>=1.0 <2]", "dep/*", "depng/*", "depng/1.1"),
    ("dep/[>=1.0 <2]", "dep/1.1", "depng/1.2", "depng/1.2"),
    # NON MATCHING
    ("dep/1.3", "dep/1.1", "dep/1.1@system", "dep/1.3"),
    ("dep/1.3", "dep/*@comp", "dep/*@system", "dep/1.3"),
    ("dep/[>=1.0 <2]", "dep/2.1", "dep/2.1@system", "dep/1.1"),
    # PATTERN - PATTERN REPLACE
    ("dep/[>=1.3 <2]", "dep/*", "dep/[>=1.0 <1.9]", "dep/1.1"),
    # DIRECT REPLACE OF PINNED VERSIONS
    ("dep/1.3", "dep/1.3", "dep/1.5", "dep/1.5"),
])
@pytest.mark.parametrize("tool_require", [False, True])
class TestReplaceRequires:
    def test_alternative(self, tool_require, require, pattern, alternative, pkg):
        c = TestClient(light=True)
        conanfile = GenConanfile().with_tool_requires(require) if tool_require else \
            GenConanfile().with_requires(require)
        profile_tag = "replace_requires" if not tool_require else "replace_tool_requires"
        c.save({"dep/conanfile.py": GenConanfile(),
                "pkg/conanfile.py": conanfile,
                "profile": f"[{profile_tag}]\n{pattern}: {alternative}"})
        ref = RecipeReference.loads(pkg)
        user = f"--user={ref.user}" if ref.user else ""
        channel = f"--channel={ref.channel}" if ref.channel else ""
        c.run(f"create dep --name={ref.name} --version={ref.version} {user} {channel}")
        rrev = c.exported_recipe_revision()
        c.run("profile show -pr=profile")
        assert profile_tag in c.out
        c.run("install pkg -pr=profile")
        assert profile_tag in c.out
        c.assert_listed_require({f"{pkg}#{rrev}": "Cache"}, build=tool_require)

        # Check lockfile
        c.run("lock create pkg -pr=profile")
        lock = c.load("pkg/conan.lock")
        assert f"{pkg}#{rrev}" in lock

        # c.run("create dep2 --version=1.2")
        # with lockfile
        c.run("install pkg -pr=profile")
        c.assert_listed_require({f"{pkg}#{rrev}": "Cache"}, build=tool_require)

    def test_diamond(self, tool_require, require, pattern, alternative, pkg):
        c = TestClient(light=True)
        conanfile = GenConanfile().with_tool_requires(require) if tool_require else \
            GenConanfile().with_requires(require)
        profile_tag = "replace_requires" if not tool_require else "replace_tool_requires"

        c.save({"dep/conanfile.py": GenConanfile(),
                "libb/conanfile.py": conanfile,
                "libc/conanfile.py": conanfile,
                "app/conanfile.py": GenConanfile().with_requires("libb/0.1", "libc/0.1"),
                "profile": f"[{profile_tag}]\n{pattern}: {alternative}"})
        ref = RecipeReference.loads(pkg)
        user = f"--user={ref.user}" if ref.user else ""
        channel = f"--channel={ref.channel}" if ref.channel else ""
        c.run(f"create dep --name={ref.name} --version={ref.version} {user} {channel}")
        rrev = c.exported_recipe_revision()

        c.run("export libb --name=libb --version=0.1")
        c.run("export libc --name=libc --version=0.1")

        c.run("install app -pr=profile", assert_error=True)
        assert "ERROR: Missing binary: libb/0.1" in c.out
        assert "ERROR: Missing binary: libc/0.1" in c.out

        c.run("install app -pr=profile --build=missing")
        c.assert_listed_require({f"{pkg}#{rrev}": "Cache"}, build=tool_require)

        # Check lockfile
        c.run("lock create app -pr=profile")
        lock = c.load("app/conan.lock")
        assert f"{pkg}#{rrev}" in lock

        # with lockfile
        c.run("install app -pr=profile")
        c.assert_listed_require({f"{pkg}#{rrev}": "Cache"}, build=tool_require)


@pytest.mark.parametrize("pattern, replace", [
    ("pkg", "pkg/0.1"),
    ("pkg/*", "pkg"),
    ("pkg/*:pid1", "pkg/0.1"),
    ("pkg/*:pid1", "pkg/0.1:pid2"),
    ("pkg/*", "pkg/0.1:pid2"),
    (":", ""),
    ("pkg/version:pid", ""),
    ("pkg/version:pid", ":")
])
def test_replace_requires_errors(pattern, replace):
    c = TestClient(light=True)
    c.save({"pkg/conanfile.py": GenConanfile("pkg", "0.1"),
            "app/conanfile.py": GenConanfile().with_requires("pkg/0.2"),
            "profile": f"[replace_requires]\n{pattern}: {replace}"})
    c.run("create pkg")
    c.run("install app -pr=profile", assert_error=True)
    assert "ERROR: Error reading 'profile' profile: Error in [replace_xxx]" in c.out


def test_replace_requires_invalid_requires_errors():
    """
    replacing for something incorrect not existing is not an error per-se, it is valid that
    a recipe requires("pkg/2.*"), and then it will fail because such package doesn't exist
    """
    c = TestClient(light=True)
    c.save({"app/conanfile.py": GenConanfile().with_requires("pkg/0.2"),
            "profile": f"[replace_requires]\npkg/0.2: pkg/2.*"})
    c.run("install app -pr=profile", assert_error=True)
    assert "pkg/0.2: pkg/2.*" in c.out  # The replacement happens
    assert "ERROR: Package 'pkg/2.*' not resolved" in c.out


def test_replace_requires_json_format():
    c = TestClient(light=True)
    c.save({"pkg/conanfile.py": GenConanfile("pkg", "0.2"),
            "app/conanfile.py": GenConanfile().with_requires("pkg/0.1"),
            "profile": f"[replace_requires]\npkg/0.1: pkg/0.2"})
    c.run("create pkg")
    c.run("install app -pr=profile --format=json")
    assert "pkg/0.1: pkg/0.2" in c.out  # The replacement happens
    graph = json.loads(c.stdout)
    assert graph["graph"]["replaced_requires"] == {"pkg/0.1": "pkg/0.2"}
    assert graph["graph"]["nodes"]["0"]["dependencies"]["1"]["ref"] == "pkg/0.2"
    assert graph["graph"]["nodes"]["0"]["dependencies"]["1"]["require"] == "pkg/0.1"


def test_replace_requires_test_requires():
    c = TestClient(light=True)
    c.save({"gtest/conanfile.py": GenConanfile("gtest", "0.2"),
            "app/conanfile.py": GenConanfile().with_test_requires("gtest/0.1"),
            "profile": f"[replace_requires]\ngtest/0.1: gtest/0.2"})
    c.run("create gtest")
    c.run("install app -pr=profile")
    assert "gtest/0.1: gtest/0.2" in c.out  # The replacement happens


# We test even replacing by itself, not great, but shouldn't crash
@pytest.mark.parametrize("name, version", [("zlib", "0.1"), ("zlib", "0.2"), ("zlib-ng", "0.1")])
def test_replace_requires_consumer_references(name, version):
    c = TestClient()
    # IMPORTANT: The replacement package must be target-compatible
    dep = textwrap.dedent(f"""
        from conan import ConanFile
        class ZlibNG(ConanFile):
            name = "{name}"
            version = "{version}"
            def package_info(self):
                self.cpp_info.set_property("cmake_file_name", "ZLIB")
                self.cpp_info.set_property("cmake_target_name", "ZLIB::ZLIB")
        """)
    conanfile = textwrap.dedent("""
        from conan import ConanFile
        class App(ConanFile):
            name = "app"
            version = "0.1"
            settings = "build_type"
            requires = "zlib/0.1"
            generators = "CMakeDeps"

            def generate(self):
                self.output.info(f"DEP ZLIB generate: {self.dependencies['zlib'].ref.name}!")
            def build(self):
                self.output.info(f"DEP ZLIB build: {self.dependencies['zlib'].ref.name}!")
            def package_info(self):
                self.output.info(f"DEP ZLIB package_info: {self.dependencies['zlib'].ref.name}!")
                self.cpp_info.requires = ["zlib::zlib"]
        """)
    c.save({"dep/conanfile.py": dep,
            "app/conanfile.py": conanfile,
            "profile": f"[replace_requires]\nzlib/0.1: {name}/{version}"})
    c.run("create dep")
    c.run("build app -pr=profile")
    assert f"zlib/0.1: {name}/{version}" in c.out
    assert f"conanfile.py (app/0.1): DEP ZLIB generate: {name}!" in c.out
    assert f"conanfile.py (app/0.1): DEP ZLIB build: {name}!" in c.out
    # Check generated CMake code. If the targets are NOT compatible, then the replacement
    # Cannot happen
    assert "find_package(ZLIB)" in c.out
    assert "target_link_libraries(... ZLIB::ZLIB)" in c.out
    cmake = c.load("app/ZLIBTargets.cmake")
    assert "add_library(ZLIB::ZLIB INTERFACE IMPORTED)" in cmake
    c.run("create app -pr=profile")
    assert f"zlib/0.1: {name}/{version}" in c.out
    assert f"app/0.1: DEP ZLIB generate: {name}!" in c.out
    assert f"app/0.1: DEP ZLIB build: {name}!" in c.out


def test_replace_requires_consumer_references_error_multiple():
    # https://github.com/conan-io/conan/issues/17407
    c = TestClient()
    # IMPORTANT: The replacement package must be target-compatible
    zlib = textwrap.dedent("""
        from conan import ConanFile
        class ZlibNG(ConanFile):
            name = "zlib"
            version = "0.2"
            def package_info(self):
                self.cpp_info.set_property("cmake_file_name", "ZLIB")
                self.cpp_info.set_property("cmake_target_name", "ZLIB::ZLIB")
        """)
    conanfile = textwrap.dedent("""
        from conan import ConanFile
        class App(ConanFile):
            name = "app"
            version = "0.1"
            settings = "build_type"
            requires = "zlib/0.1", "bzip2/0.1"
            generators = "CMakeDeps"

            def generate(self):
                self.output.info(f"DEP ZLIB generate: {self.dependencies['zlib'].ref.name}!")
                self.output.info(f"DEP BZIP2 generate: {self.dependencies['bzip2'].ref.name}!")
            def build(self):
                self.output.info(f"DEP ZLIB build: {self.dependencies['zlib'].ref.name}!")
                self.output.info(f"DEP BZIP2 build: {self.dependencies['bzip2'].ref.name}!")
            def package_info(self):
                self.output.info(f"DEP ZLIB package_info: {self.dependencies['zlib'].ref.name}!")
                self.cpp_info.requires = ["zlib::zlib", "bzip2::bzip2"]
        """)
    c.save({"zlib/conanfile.py": zlib,
            "app/conanfile.py": conanfile,
            "profile": "[replace_requires]\nzlib/0.1: zlib/0.2\nbzip2/0.1: zlib/0.2"})
    c.run("create zlib")
    c.run("build app -pr=profile")
    assert "zlib/0.1: zlib/0.2" in c.out
    assert "conanfile.py (app/0.1): DEP ZLIB generate: zlib!" in c.out
    assert "conanfile.py (app/0.1): DEP ZLIB build: zlib!" in c.out
    assert "conanfile.py (app/0.1): DEP BZIP2 generate: zlib!" in c.out
    assert "conanfile.py (app/0.1): DEP BZIP2 build: zlib!" in c.out
    # Check generated CMake code. If the targets are NOT compatible, then the replacement
    # Cannot happen
    assert "find_package(ZLIB)" in c.out
    assert "target_link_libraries(... ZLIB::ZLIB ZLIB::ZLIB)" in c.out
    cmake = c.load("app/ZLIBTargets.cmake")
    assert "add_library(ZLIB::ZLIB INTERFACE IMPORTED)" in cmake
    c.run("create app -pr=profile")
    assert "zlib/0.1: zlib/0.2" in c.out
    assert "app/0.1: DEP ZLIB generate: zlib!" in c.out
    assert "app/0.1: DEP ZLIB build: zlib!" in c.out


def test_replace_requires_consumer_components_options():
    c = TestClient()
    # IMPORTANT: The replacement package must be target-compatible
    zlib_ng = textwrap.dedent("""
        from conan import ConanFile
        class ZlibNG(ConanFile):
            name = "zlib-ng"
            version = "0.1"
            options = {"compat": [False, True]}
            default_options = {"compat": False}
            def package_info(self):
                self.cpp_info.set_property("cmake_file_name", "ZLIB")
                self.cpp_info.set_property("cmake_target_name", "ZLIB::ZLIB")
                if self.options.compat:
                    self.cpp_info.components["myzlib"].set_property("cmake_target_name",
                                                                    "ZLIB::zmylib")
        """)
    conanfile = textwrap.dedent("""
        from conan import ConanFile
        class App(ConanFile):
            name = "app"
            version = "0.1"
            settings = "build_type"
            requires = "zlib/0.1"
            generators = "CMakeDeps"

            def generate(self):
                self.output.info(f"DEP ZLIB generate: {self.dependencies['zlib'].ref.name}!")
            def build(self):
                self.output.info(f"DEP ZLIB build: {self.dependencies['zlib'].ref.name}!")
            def package_info(self):
                self.output.info(f"zlib in deps?: {'zlib' in self.dependencies}")
                self.output.info(f"zlib-ng in deps?: {'zlib-ng' in self.dependencies}")
                self.output.info(f"DEP ZLIB package_info: {self.dependencies['zlib'].ref.name}!")
                self.cpp_info.requires = ["zlib::myzlib"]
        """)
    profile = textwrap.dedent("""
        [options]
        zlib-ng/*:compat=True

        [replace_requires]
        zlib/0.1: zlib-ng/0.1
        """)
    c.save({"zlibng/conanfile.py": zlib_ng,
            "app/conanfile.py": conanfile,
            "profile": profile})

    c.run("create zlibng -o *:compat=True")
    c.run("build app -pr=profile")
    assert "zlib/0.1: zlib-ng/0.1" in c.out
    assert "conanfile.py (app/0.1): DEP ZLIB generate: zlib-ng!" in c.out
    assert "conanfile.py (app/0.1): DEP ZLIB build: zlib-ng!" in c.out
    # Check generated CMake code. If the targets are NOT compatible, then the replacement
    # Cannot happen
    assert "find_package(ZLIB)" in c.out
    assert "target_link_libraries(... ZLIB::ZLIB)" in c.out
    cmake = c.load("app/ZLIBTargets.cmake")
    assert "add_library(ZLIB::ZLIB INTERFACE IMPORTED)" in cmake
    cmake = c.load("app/ZLIB-Target-none.cmake")
    assert "set_property(TARGET ZLIB::ZLIB APPEND PROPERTY INTERFACE_LINK_LIBRARIES ZLIB::zmylib)" \
           in cmake

    c.run("create app -pr=profile")
    assert "zlib/0.1: zlib-ng/0.1" in c.out
    assert "app/0.1: DEP ZLIB generate: zlib-ng!" in c.out
    assert "app/0.1: DEP ZLIB build: zlib-ng!" in c.out
    assert "find_package(ZLIB)" in c.out
    assert "target_link_libraries(... ZLIB::ZLIB)" in c.out
    assert "zlib in deps?: True" in c.out
    assert "zlib-ng in deps?: False" in c.out


def test_replace_requires_multiple():
    conanfile = textwrap.dedent("""
        from conan import ConanFile

        class EpoxyConan(ConanFile):
            name = "libepoxy"
            version = "0.1"

            def requirements(self):
                self.requires("opengl/system")
                self.requires("egl/system")

            def generate(self):
                for r, d in self.dependencies.items():
                    self.output.info(f"DEP: {r.ref.name}: {d.ref.name}")

            def package_info(self):
                self.cpp_info.requires.append("opengl::opengl")
                self.cpp_info.requires.append("egl::egl")
        """)
    profile = textwrap.dedent("""
        [replace_requires]
        opengl/system: libgl/1.0
        egl/system: libgl/1.0
        """)
    c = TestClient()
    c.save({"dep/conanfile.py": GenConanfile(),
            "app/conanfile.py": conanfile,
            "profile": profile})
    c.run("create dep --name=libgl --version=1.0")
    c.run("create app -pr=profile")
    # There are actually 2 dependencies, pointing to the same node
    assert "libepoxy/0.1: DEP: opengl: libgl" in c.out
    assert "libepoxy/0.1: DEP: egl: libgl" in c.out


class TestReplaceRequiresTransitiveGenerators:
    """ Generators are incorrectly managing replace_requires
    # https://github.com/conan-io/conan/issues/17557
    """

    @pytest.mark.parametrize("diamond", [True, False])
    def test_no_components(self, diamond):
        c = TestClient()
        zlib_ng = textwrap.dedent("""
            from conan import ConanFile
            class ZlibNG(ConanFile):
                name = "zlib-ng"
                version = "0.1"
                package_type = "static-library"
                def package_info(self):
                    self.cpp_info.libs = ["zlib"]
                    self.cpp_info.type = "static-library"
                    self.cpp_info.location = "lib/zlib.lib"
                    self.cpp_info.set_property("cmake_file_name", "ZLIB")
                    self.cpp_info.set_property("cmake_target_name", "ZLIB::ZLIB")
                    self.cpp_info.set_property("pkg_config_name", "ZLIB")
            """)
        openssl = textwrap.dedent("""
            from conan import ConanFile
            class openssl(ConanFile):
                name = "openssl"
                version = "0.1"
                package_type = "static-library"
                requires = "zlib/0.1"
                def package_info(self):
                    self.cpp_info.libs = ["crypto"]
                    self.cpp_info.type = "static-library"
                    self.cpp_info.location = "lib/crypto.lib"
                    self.cpp_info.requires = ["zlib::zlib"]
            """)
        zlib = '"zlib/0.1"' if diamond else ""
        conanfile = textwrap.dedent(f"""
            from conan import ConanFile
            class App(ConanFile):
                name = "app"
                version = "0.1"
                settings = "build_type", "arch"
                requires = "openssl/0.1", {zlib}
                package_type = "application"
                generators = "CMakeDeps", "PkgConfigDeps", "MSBuildDeps"
            """)
        profile = textwrap.dedent("""
            [settings]
            build_type = Release
            arch=x86_64

            [replace_requires]
            zlib/0.1: zlib-ng/0.1
            """)
        c.save({"zlibng/conanfile.py": zlib_ng,
                "openssl/conanfile.py": openssl,
                "app/conanfile.py": conanfile,
                "profile": profile})

        c.run("create zlibng")
        c.run("create openssl -pr=profile")
        c.run("install app -pr=profile -c tools.cmake.cmakedeps:new=will_break_next")
        assert "zlib/0.1: zlib-ng/0.1" in c.out

        pc_content = c.load("app/ZLIB.pc")
        assert 'Libs: -L"${libdir}" -lzlib' in pc_content
        pc_content = c.load("app/openssl.pc")
        assert 'Requires: ZLIB' in pc_content

        cmake = c.load("app/ZLIB-Targets-release.cmake")
        assert "add_library(ZLIB::ZLIB STATIC IMPORTED)" in cmake

        cmake = c.load("app/openssl-Targets-release.cmake")
        assert "find_dependency(ZLIB REQUIRED CONFIG)" in cmake
        assert "add_library(openssl::openssl STATIC IMPORTED)" in cmake
        assert "set_property(TARGET openssl::openssl APPEND PROPERTY INTERFACE_LINK_LIBRARIES\n" \
               '             "$<$<CONFIG:RELEASE>:ZLIB::ZLIB>")' in cmake

        # checking MSBuildDeps
        zlib_ng_props = c.load("app/conan_zlib-ng.props")
        assert 'Project="conan_zlib-ng_release_x64.props"' in zlib_ng_props
        props = c.load("app/conan_openssl_release_x64.props")
        assert "<Import Condition=\"'$(conan_zlib-ng_props_imported)' != 'True'\"" \
               " Project=\"conan_zlib-ng.props\"/>" in props

    @pytest.mark.parametrize("diamond", [True, False])
    def test_openssl_components(self, diamond):
        c = TestClient()
        zlib_ng = textwrap.dedent("""
            from conan import ConanFile
            class ZlibNG(ConanFile):
                name = "zlib-ng"
                version = "0.1"
                package_type = "static-library"
                def package_info(self):
                    self.cpp_info.libs = ["zlib"]
                    self.cpp_info.type = "static-library"
                    self.cpp_info.location = "lib/zlib.lib"
                    self.cpp_info.set_property("cmake_file_name", "ZLIB")
                    self.cpp_info.set_property("cmake_target_name", "ZLIB::ZLIB")
                    self.cpp_info.set_property("pkg_config_name", "ZLIB")
            """)
        openssl = textwrap.dedent("""
            from conan import ConanFile
            class openssl(ConanFile):
                name = "openssl"
                version = "0.1"
                package_type = "static-library"
                requires = "zlib/0.1"
                def package_info(self):
                    self.cpp_info.components["crypto"].libs = ["crypto"]
                    self.cpp_info.components["crypto"].type = "static-library"
                    self.cpp_info.components["crypto"].location = "lib/crypto.lib"
                    self.cpp_info.components["crypto"].requires = ["zlib::zlib"]
            """)
        zlib = '"zlib/0.1"' if diamond else ""
        conanfile = textwrap.dedent(f"""
            from conan import ConanFile
            class App(ConanFile):
                name = "app"
                version = "0.1"
                settings = "build_type", "arch"
                requires = "openssl/0.1", {zlib}
                package_type = "application"
                generators = "CMakeDeps", "PkgConfigDeps", "MSBuildDeps"
            """)
        profile = textwrap.dedent("""
            [settings]
            build_type = Release
            arch=x86_64

            [replace_requires]
            zlib/0.1: zlib-ng/0.1
            """)
        c.save({"zlibng/conanfile.py": zlib_ng,
                "openssl/conanfile.py": openssl,
                "app/conanfile.py": conanfile,
                "profile": profile})

        c.run("create zlibng")
        c.run("create openssl -pr=profile")
        c.run("install app -pr=profile -c tools.cmake.cmakedeps:new=will_break_next")
        assert "zlib/0.1: zlib-ng/0.1" in c.out

        pc_content = c.load("app/ZLIB.pc")
        assert 'Libs: -L"${libdir}" -lzlib' in pc_content
        pc_content = c.load("app/openssl-crypto.pc")
        assert 'Requires: ZLIB' in pc_content

        cmake = c.load("app/ZLIB-Targets-release.cmake")
        assert "add_library(ZLIB::ZLIB STATIC IMPORTED)" in cmake

        cmake = c.load("app/openssl-Targets-release.cmake")
        assert "find_dependency(ZLIB REQUIRED CONFIG)" in cmake
        assert "add_library(openssl::crypto STATIC IMPORTED)" in cmake
        assert "set_property(TARGET openssl::crypto APPEND PROPERTY INTERFACE_LINK_LIBRARIES\n" \
               '             "$<$<CONFIG:RELEASE>:ZLIB::ZLIB>")' in cmake

        # checking MSBuildDeps
        zlib_ng_props = c.load("app/conan_zlib-ng.props")
        assert 'Project="conan_zlib-ng_release_x64.props"' in zlib_ng_props

        props = c.load("app/conan_openssl_crypto_release_x64.props")
        assert "<Import Condition=\"'$(conan_zlib-ng_props_imported)' != 'True'\"" \
               " Project=\"conan_zlib-ng.props\"/>" in props

    @pytest.mark.parametrize("diamond", [True, False])
    @pytest.mark.parametrize("explicit_requires", [True, False])
    def test_zlib_components(self, diamond, explicit_requires):
        c = TestClient()
        zlib_ng = textwrap.dedent("""
            from conan import ConanFile
            class ZlibNG(ConanFile):
                name = "zlib-ng"
                version = "0.1"
                package_type = "static-library"
                def package_info(self):
                    self.cpp_info.components["myzlib"].libs = ["zlib"]
                    self.cpp_info.components["myzlib"].type = "static-library"
                    self.cpp_info.components["myzlib"].location = "lib/zlib.lib"
                    self.cpp_info.set_property("cmake_file_name", "ZLIB")
                    self.cpp_info.components["myzlib"].set_property("pkg_config_name", "ZLIB")
                    self.cpp_info.components["myzlib"].set_property("cmake_target_name",
                                                                    "ZLIB::ZLIB")
            """)
        openssl = textwrap.dedent(f"""
            from conan import ConanFile
            class openssl(ConanFile):
                name = "openssl"
                version = "0.1"
                package_type = "static-library"
                requires = "zlib/0.1"
                def package_info(self):
                    self.cpp_info.libs = ["crypto"]
                    self.cpp_info.type = "static-library"
                    self.cpp_info.location = "lib/crypto.lib"
                    if {explicit_requires}:
                        self.cpp_info.requires = ["zlib::zlib"]
            """)
        zlib = '"zlib/0.1"' if diamond else ""
        conanfile = textwrap.dedent(f"""
            from conan import ConanFile
            class App(ConanFile):
                name = "app"
                version = "0.1"
                settings = "build_type", "arch"
                requires = "openssl/0.1", {zlib}
                package_type = "application"
                generators = "CMakeDeps", "PkgConfigDeps", "MSBuildDeps"
            """)
        profile = textwrap.dedent("""
            [settings]
            build_type = Release
            arch = x86_64

            [replace_requires]
            zlib/0.1: zlib-ng/0.1
            """)
        c.save({"zlibng/conanfile.py": zlib_ng,
                "openssl/conanfile.py": openssl,
                "app/conanfile.py": conanfile,
                "profile": profile})

        c.run("create zlibng")
        c.run("create openssl -pr=profile")
        c.run("install app -pr=profile -c tools.cmake.cmakedeps:new=will_break_next")
        assert "zlib/0.1: zlib-ng/0.1" in c.out

        pc_content = c.load("app/zlib-ng.pc")
        assert 'Requires: ZLIB' in pc_content
        pc_content = c.load("app/ZLIB.pc")
        assert 'Libs: -L"${libdir}" -lzlib' in pc_content
        pc_content = c.load("app/openssl.pc")
        assert 'Requires: zlib-ng' in pc_content

        cmake = c.load("app/ZLIB-Targets-release.cmake")
        assert "add_library(ZLIB::ZLIB STATIC IMPORTED)" in cmake

        cmake = c.load("app/openssl-Targets-release.cmake")
        assert "find_dependency(ZLIB REQUIRED CONFIG)" in cmake
        assert "add_library(openssl::openssl STATIC IMPORTED)" in cmake
        # It should access the generic zlib-ng target
        assert "set_property(TARGET openssl::openssl APPEND PROPERTY INTERFACE_LINK_LIBRARIES\n" \
               '             "$<$<CONFIG:RELEASE>:zlib-ng::zlib-ng>")' in cmake

        # checking MSBuildDeps
        zlib_ng_props = c.load("app/conan_zlib-ng.props")
        assert "<Import Condition=\"'$(conan_zlib-ng_myzlib_props_imported)' != 'True'\" " \
               "Project=\"conan_zlib-ng_myzlib.props\"/" in zlib_ng_props

        props = c.load("app/conan_openssl_release_x64.props")
        assert "<Import Condition=\"'$(conan_zlib-ng_props_imported)' != 'True'\"" \
               " Project=\"conan_zlib-ng.props\"/>" in props

    @pytest.mark.parametrize("diamond", [True, False])
    @pytest.mark.parametrize("package_requires", [False, True])
    def test_both_components(self, diamond, package_requires):
        c = TestClient()
        zlib_ng = textwrap.dedent("""
            from conan import ConanFile
            class ZlibNG(ConanFile):
                name = "zlib-ng"
                version = "0.1"
                package_type = "static-library"
                def package_info(self):
                    self.cpp_info.components["myzlib"].libs = ["zlib"]
                    self.cpp_info.components["myzlib"].type = "static-library"
                    self.cpp_info.components["myzlib"].location = "lib/zlib.lib"
                    self.cpp_info.set_property("cmake_file_name", "ZLIB")
                    self.cpp_info.components["myzlib"].set_property("pkg_config_name", "ZLIB")
                    self.cpp_info.components["myzlib"].set_property("cmake_target_name",
                                                                    "ZLIB::ZLIB")
            """)
        openssl = textwrap.dedent(f"""
            from conan import ConanFile
            class openssl(ConanFile):
                name = "openssl"
                version = "0.1"
                package_type = "static-library"
                requires = "zlib/0.1"
                def package_info(self):
                    self.cpp_info.components["crypto"].libs = ["crypto"]
                    self.cpp_info.components["crypto"].type = "static-library"
                    self.cpp_info.components["crypto"].location = "lib/crypto.lib"
                    if {package_requires}:
                        self.cpp_info.components["crypto"].requires = ["zlib::zlib"]
                    else:
                        self.cpp_info.components["crypto"].requires = ["zlib::myzlib"]
            """)
        zlib = '"zlib/0.1"' if diamond else ""
        conanfile = textwrap.dedent(f"""
            from conan import ConanFile
            class App(ConanFile):
                name = "app"
                version = "0.1"
                settings = "build_type", "arch"
                requires = "openssl/0.1", {zlib}
                package_type = "application"
                generators = "CMakeDeps", "PkgConfigDeps", "MSBuildDeps"
            """)
        profile = textwrap.dedent("""
            [settings]
            build_type = Release
            arch = x86_64

            [replace_requires]
            zlib/0.1: zlib-ng/0.1
            """)
        c.save({"zlibng/conanfile.py": zlib_ng,
                "openssl/conanfile.py": openssl,
                "app/conanfile.py": conanfile,
                "profile": profile})

        c.run("create zlibng")
        c.run("create openssl -pr=profile")
        c.run("install app -pr=profile -c tools.cmake.cmakedeps:new=will_break_next")
        assert "zlib/0.1: zlib-ng/0.1" in c.out

        pc_content = c.load("app/zlib-ng.pc")
        assert 'Requires: ZLIB' in pc_content
        pc_content = c.load("app/ZLIB.pc")
        assert 'Libs: -L"${libdir}" -lzlib' in pc_content
        pc_content = c.load("app/openssl-crypto.pc")
        assert f'Requires: {"zlib-ng" if package_requires else "ZLIB"}' in pc_content

        cmake = c.load("app/ZLIB-Targets-release.cmake")
        assert "add_library(ZLIB::ZLIB STATIC IMPORTED)" in cmake

        cmake = c.load("app/openssl-Targets-release.cmake")
        assert "find_dependency(ZLIB REQUIRED CONFIG)" in cmake
        assert "add_library(openssl::crypto STATIC IMPORTED)" in cmake
        if package_requires:
            # The generic package requirement uses the package name zlib-ng
            assert "set_property(TARGET openssl::crypto APPEND PROPERTY INTERFACE_LINK_LIBRARIES\n" \
                   '             "$<$<CONFIG:RELEASE>:zlib-ng::zlib-ng>")' in cmake
        else:
            assert "set_property(TARGET openssl::crypto APPEND PROPERTY INTERFACE_LINK_LIBRARIES\n" \
                   '             "$<$<CONFIG:RELEASE>:ZLIB::ZLIB>")' in cmake

        # checking MSBuildDeps
        zlib_ng_props = c.load("app/conan_zlib-ng.props")
        assert "<Import Condition=\"'$(conan_zlib-ng_myzlib_props_imported)' != 'True'\" " \
               "Project=\"conan_zlib-ng_myzlib.props\"/" in zlib_ng_props

        props = c.load("app/conan_openssl_crypto_release_x64.props")
        if package_requires:
            assert "<Import Condition=\"'$(conan_zlib-ng_props_imported)' != 'True'\"" \
                   " Project=\"conan_zlib-ng.props\"/>" in props
        else:
            assert "<Import Condition=\"'$(conan_zlib-ng_myzlib_props_imported)' != 'True'\"" \
                   " Project=\"conan_zlib-ng_myzlib.props\"/>" in props
