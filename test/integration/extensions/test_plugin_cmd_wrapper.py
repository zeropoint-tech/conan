import os
import textwrap

from conan.test.assets.genconanfile import GenConanfile
from conan.test.utils.tools import TestClient
from conan.internal.util.files import save


def test_plugin_cmd_wrapper():
    c = TestClient()
    plugins = os.path.join(c.cache_folder, "extensions", "plugins")
    wrapper = textwrap.dedent("""
        def cmd_wrapper(cmd, **kwargs):
            return 'echo "{}"'.format(cmd)
        """)
    save(os.path.join(plugins, "cmd_wrapper.py"), wrapper)
    conanfile = textwrap.dedent("""
        from conan import ConanFile
        class Pkg(ConanFile):
            def generate(self):
                self.run("Hello world")
                self.run("Other stuff")
        """)
    c.save({"conanfile.py": conanfile})
    c.run("install .")
    assert 'Hello world' in c.out
    assert 'Other stuff' in c.out


def test_plugin_cmd_wrapper_conanfile():
    """
    we can get the name of the caller conanfile too
    """
    c = TestClient()
    plugins = os.path.join(c.cache_folder, "extensions", "plugins")
    wrapper = textwrap.dedent("""
        def cmd_wrapper(cmd, conanfile, **kwargs):
            return 'echo "{}!:{}!"'.format(conanfile.ref, cmd)
        """)
    save(os.path.join(plugins, "cmd_wrapper.py"), wrapper)
    conanfile = textwrap.dedent("""
        from conan import ConanFile
        class Pkg(ConanFile):
            def generate(self):
                self.run("Hello world")
        """)
    c.save({"conanfile.py": conanfile})
    c.run("install . --name=pkg --version=0.1")
    assert 'pkg/0.1!:Hello world!' in c.out


def test_plugin_profile_error_vs():
    c = TestClient()
    c.save({"conanfile.py": GenConanfile("pkg", "1.0")})
    c.run("create . -s compiler=msvc -s compiler.version=15 -s compiler.cppstd=14",
          assert_error=True)
    assert "The provided compiler.cppstd=14 is not supported by msvc 15. Supported values are: []" in c.out
    c.run("create . -s compiler=msvc -s compiler.version=170 -s compiler.cppstd=14",
          assert_error=True)
    assert "The provided compiler.cppstd=14 is not supported by msvc 170. Supported values are: []" in c.out
    c.run("create . -s compiler=msvc -s compiler.version=190 -s compiler.cppstd=14")
    assert "Installing packages" in c.out


def test_plugin_profile_error_vscstd():
    c = TestClient()
    c.save({"conanfile.py": GenConanfile("pkg", "1.0").with_class_attribute("languages = 'C'")})
    c.run("create . -s compiler=msvc -s compiler.version=190 -s compiler.cstd=23", assert_error=True)
    assert "The provided compiler.cstd=23 is not supported by msvc 190. Supported values are: []" in c.out
    c.run("create . -s compiler=msvc -s compiler.version=193 -s compiler.cstd=23", assert_error=True)
    assert "The provided compiler.cstd=23 is not supported by msvc 193. Supported values are: ['11', '17']" in c.out
    c.run("create . -s compiler=msvc -s compiler.version=193 -s compiler.cstd=17")
    assert "Installing packages" in c.out
