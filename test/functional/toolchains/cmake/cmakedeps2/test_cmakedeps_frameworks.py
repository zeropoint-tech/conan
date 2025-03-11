import platform
import textwrap

import pytest

from conan.test.assets.sources import gen_function_cpp
from conan.test.utils.tools import TestClient

new_value = "will_break_next"


@pytest.fixture
def client():
    lib_conanfile = textwrap.dedent("""
        from conan import ConanFile

        class FooLib(ConanFile):
            name = "foolib"
            version = "1.0"

            def package_info(self):
                self.cpp_info.frameworks.extend(['Foundation', 'CoreServices', 'CoreFoundation'])
    """)

    t = TestClient()
    t.save({'conanfile.py': lib_conanfile})
    t.run("create .")
    return t


# needs at least 3.23.3 because of error with "empty identity"
#https://stackoverflow.com/questions/72746725/xcode-14-beta-cmake-not-able-to-resolve-cmake-c-compiler-and-cmake-cxx-compiler
@pytest.mark.skipif(platform.system() != "Darwin", reason="Only OSX")
# @pytest.mark.tool("cmake", "3.23")
def test_apple_framework_xcode(client):
    app_cmakelists = textwrap.dedent("""
        cmake_minimum_required(VERSION 3.15)
        project(Testing CXX)
        find_package(foolib REQUIRED)
    """)

    app_conanfile = textwrap.dedent("""
        from conan import ConanFile
        from conan.tools.cmake import CMake

        class App(ConanFile):
            requires = "foolib/1.0"
            generators = "CMakeDeps", "CMakeToolchain"
            settings = "build_type", "os", "arch"

            def build(self):
                cmake = CMake(self)
                cmake.configure()
    """)

    client.save({'conanfile.py': app_conanfile,
                 'CMakeLists.txt': app_cmakelists})

    client.run(f"build . -c tools.cmake.cmaketoolchain:generator=Xcode -c tools.cmake.cmakedeps:new={new_value}")
    breakpoint()
    assert "/System/Library/Frameworks/Foundation.framework;" in client.out
    assert "/System/Library/Frameworks/CoreServices.framework;" in client.out
    assert "/System/Library/Frameworks/CoreFoundation.framework" in client.out
