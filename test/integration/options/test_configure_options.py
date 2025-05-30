import os
import textwrap

from parameterized import parameterized

from conan.test.assets.genconanfile import GenConanfile
from conan.test.utils.tools import TestClient


class TestConfigureOptions:
    """
    Test config_options(), configure() and package_id() methods can manage shared, fPIC and
    header_only options automatically.
    """

    @parameterized.expand([
        ["Linux", False, False, False, [False, False, False]],
        ["Windows", False, False, False, [False, None, False]],
        ["Windows", True, False, False, [True, None, False]],
        ["Windows", False, False, True, [None, None, True]],
        ["Linux", False, False, True, [None, None, True]],
        ["Linux", True, True, False, [True, None, False]],
        ["Linux", True, False, False, [True, None, False]],
        ["Linux", True, True, True, [None, None, True]],
        ["Linux", True, True, True, [None, None, True]],
        ["Linux", False, True, False, [False, True, False]],
        ["Linux", False, True, False, [False, True, False]],
    ])
    def test_methods_not_defined(self, settings_os, shared, fpic, header_only, result):
        """
        Test that options are managed automatically when methods config_options and configure are not
        defined and implements = ["auto_shared_fpic", "auto_header_only"].
        Check that header only package gets its unique package ID.
        """
        client = TestClient()
        conanfile = textwrap.dedent(f"""\
           from conan import ConanFile

           class Pkg(ConanFile):
               settings = "os", "compiler", "arch", "build_type"
               options = {{"shared": [True, False], "fPIC": [True, False], "header_only": [True, False]}}
               default_options = {{"shared": {shared}, "fPIC": {fpic}, "header_only": {header_only}}}
               implements = ["auto_shared_fpic", "auto_header_only"]

               def build(self):
                   shared = self.options.get_safe("shared")
                   fpic = self.options.get_safe("fPIC")
                   header_only = self.options.get_safe("header_only")
                   self.output.info(f"shared: {{shared}}, fPIC: {{fpic}}, header only: {{header_only}}")
            """)
        client.save({"conanfile.py": conanfile})
        client.run(f"create . --name=pkg --version=0.1 -s os={settings_os}")
        result = f"shared: {result[0]}, fPIC: {result[1]}, header only: {result[2]}"
        assert result in client.out
        if header_only:
            assert "Package 'da39a3ee5e6b4b0d3255bfef95601890afd80709' created"in client.out

    @parameterized.expand([
        ["Linux", False, False, False, [False, False, False]],
        ["Linux", False, False, True, [False, False, True]],
        ["Linux", False, True, False, [False, True, False]],
        ["Linux", False, True, True, [False, True, True]],
        ["Linux", True, False, False, [True, False, False]],
        ["Linux", True, False, True, [True, False, True]],
        ["Linux", True, True, False, [True, True, False]],
        ["Linux", True, True, True, [True, True, True]],
        ["Windows", False, False, False, [False, False, False]],
        ["Windows", False, False, True, [False, False, True]],
        ["Windows", False, True, False, [False, True, False]],
        ["Windows", False, True, True, [False, True, True]],
        ["Windows", True, False, False, [True, False, False]],
        ["Windows", True, False, True, [True, False, True]],
        ["Windows", True, True, False, [True, True, False]],
        ["Windows", True, True, True, [True, True, True]],
    ])
    def test_optout(self, settings_os, shared, fpic, header_only, result):
        """
        Test that options are not managed automatically when methods are defined even if implements = ["auto_shared_fpic", "auto_header_only"]
        Check that header only package gets its unique package ID.
        """
        client = TestClient()
        conanfile = textwrap.dedent(f"""\
           from conan import ConanFile

           class Pkg(ConanFile):
               settings = "os", "compiler", "arch", "build_type"
               options = {{"shared": [True, False], "fPIC": [True, False], "header_only": [True, False]}}
               default_options = {{"shared": {shared}, "fPIC": {fpic}, "header_only": {header_only}}}
               implements = ["auto_shared_fpic", "auto_header_only"]

               def config_options(self):
                   pass

               def configure(self):
                   pass

               def build(self):
                   shared = self.options.get_safe("shared")
                   fpic = self.options.get_safe("fPIC")
                   header_only = self.options.get_safe("header_only")
                   self.output.info(f"shared: {{shared}}, fPIC: {{fpic}}, header only: {{header_only}}")
            """)
        client.save({"conanfile.py": conanfile})
        client.run(f"create . --name=pkg --version=0.1 -s os={settings_os}")
        result = f"shared: {result[0]}, fPIC: {result[1]}, header only: {result[2]}"
        assert result in client.out
        if header_only:
            assert "Package 'da39a3ee5e6b4b0d3255bfef95601890afd80709' created"in client.out

    def test_header_package_type_pid(self):
        """
        Test that we get the pid for header only when package type is set to header-library
        """
        client = TestClient()
        conanfile = textwrap.dedent(f"""\
               from conan import ConanFile

               class Pkg(ConanFile):
                   settings = "os", "compiler", "arch", "build_type"
                   package_type = "header-library"
                   implements = ["auto_shared_fpic", "auto_header_only"]

                """)
        client.save({"conanfile.py": conanfile})
        client.run(f"create . --name=pkg --version=0.1")
        assert "Package 'da39a3ee5e6b4b0d3255bfef95601890afd80709' created" in client.out


def test_config_options_override_behaviour():
    tc = TestClient(light=True)
    tc.save({"conanfile.py": textwrap.dedent("""
    from conan import ConanFile

    class Pkg(ConanFile):
        name = "pkg"
        version = "1.0"

        options = {"foo": [1, 2, 3]}
        default_options = {"foo": 1}

        def config_options(self):
            self.options.foo = 2

        def build(self):
            self.output.info(f"Foo: {self.options.foo}")
    """)})

    tc.run("create .")
    assert "Foo: 2" in tc.out

    tc.run("create . -o=&:foo=3")
    assert "Foo: 3" in tc.out


def test_configure_transitive_option():
    c = TestClient(light=True)
    c.save({"conanfile.py": GenConanfile("zlib", "0.1").with_shared_option(False)})
    c.run("create . -o *:shared=True")

    boost = textwrap.dedent("""
        from conan import ConanFile

        class BoostConan(ConanFile):
            name = "boostdbg"
            version = "1.0"
            options = {"shared": [True, False]}
            default_options ={"shared": False}
            requires = "zlib/0.1"

            def configure(self):
                self.options["zlib/*"].shared = self.options.shared
        """)

    c.save({"conanfile.py": boost}, clean_first=True)
    c.run("create .  -o boostdbg/*:shared=True")
    # It doesn't fail due to missing binary, as it assigned dependency shared=True
    pkg_folder = c.created_layout().package()
    conaninfo = c.load(os.path.join(pkg_folder, "conaninfo.txt"))
    assert "shared=True" in conaninfo
