import os
import textwrap

import pytest

from conan import __version__
from conan.test.utils.test_files import temp_folder
from conan.test.utils.tools import TestClient
from conan.internal.util.files import save


class TestNewCommand:
    def test_new_cmake_lib(self):
        client = TestClient(light=True)
        client.run("new cmake_lib -d name=pkg -d version=1.3")
        conanfile = client.load("conanfile.py")
        assert "CMakeToolchain" in conanfile
        conanfile = client.load("test_package/conanfile.py")
        assert "CMakeToolchain" in conanfile
        cmake = client.load("test_package/CMakeLists.txt")
        assert "find_package" in cmake

        # Test at least it exports correctly
        client.run("export . --user=myuser --channel=testing")
        assert "pkg/1.3@myuser/testing" in client.out

    def test_new_cmake_exe(self):
        client = TestClient(light=True)
        client.run("new cmake_exe -d name=pkg -d version=1.3")
        conanfile = client.load("conanfile.py")
        assert "CMakeToolchain" in conanfile
        conanfile = client.load("test_package/conanfile.py")
        assert "def test(self):" in conanfile

        # Test at least it exports correctly
        client.run("export . --user=myuser --channel=testing")
        assert "pkg/1.3@myuser/testing" in client.out

    def test_new_basic_template(self):
        tc = TestClient(light=True)
        tc.run("new basic")
        assert '# self.requires("zlib/1.2.13")' in tc.load("conanfile.py")

        tc.run("new basic -d name=mygame -d requires=math/1.0 -d requires=ai/1.0 -f")
        conanfile = tc.load("conanfile.py")
        assert 'self.requires("math/1.0")' in conanfile
        assert 'self.requires("ai/1.0")' in conanfile
        assert 'name = "mygame"' in conanfile

    def test_new_defaults(self):
        c = TestClient(light=True)
        for t in ("cmake_lib", "cmake_exe", "meson_lib", "meson_exe", "msbuild_lib", "msbuild_exe",
                  "bazel_lib", "bazel_exe", "autotools_lib", "autotools_exe"):
            c.run(f"new {t} -f")
            conanfile = c.load("conanfile.py")
            assert 'name = "mypkg"' in conanfile
            assert 'version = "0.1"' in conanfile

            c.run(f"new {t} -d name=mylib -f")
            conanfile = c.load("conanfile.py")
            assert 'name = "mylib"' in conanfile
            assert 'version = "0.1"' in conanfile


class TestNewCommandUserTemplate:

    @pytest.mark.parametrize("folder", ("mytemplate", "sub/mytemplate"))
    def test_user_template(self, folder):
        client = TestClient(light=True)
        template1 = textwrap.dedent("""
            class Conan(ConanFile):
                name = "{{name}}"
                version = "{{version}}"
                conan_version = "{{conan_version}}"
        """)
        save(os.path.join(client.cache_folder, f"templates/command/new/{folder}/conanfile.py"),
             template1)
        client.run(f"new {folder} -d name=hello -d version=0.1")
        conanfile = client.load("conanfile.py")
        assert 'name = "hello"' in conanfile
        assert 'version = "0.1"' in conanfile
        assert 'conan_version = "{}"'.format(__version__) in conanfile

    def test_user_template_abs(self):
        tmp_folder = temp_folder()
        client = TestClient(light=True)
        template1 = textwrap.dedent("""
            class Conan(ConanFile):
                name = "{{name}}"
        """)
        save(os.path.join(tmp_folder, "conanfile.py"), template1)
        client.run(f'new "{tmp_folder}" -d name=hello -d version=0.1')
        conanfile = client.load("conanfile.py")
        assert 'name = "hello"' in conanfile

    def test_user_template_filenames(self):
        client = TestClient(light=True)
        save(os.path.join(client.cache_folder, "templates/command/new/mytemplate/{{name}}"), "Hi!")
        client.run(f"new mytemplate -d name=pkg.txt")
        assert "Hi!" == client.load("pkg.txt")

    def test_skip_files(self):
        client = TestClient(light=True)
        template1 = textwrap.dedent("""
            class Conan(ConanFile):
                name = "{{name}}"
                version = "{{version}}"
                conan_version = "{{conan_version}}"
        """)
        path = os.path.join(client.cache_folder, f"templates/command/new/mytemplate")
        save(os.path.join(path, "conanfile.py"), template1)
        save(os.path.join(path, "file.h"), "{{header}}")

        client.run(f"new mytemplate -d name=hello -d version=0.1 -d header=")
        assert not os.path.exists(os.path.join(client.current_folder, "file.h"))
        assert not os.path.exists(os.path.join(client.current_folder, "file.cpp"))
        client.run(f"new mytemplate -d name=hello -d version=0.1 -d header=xxx -f")
        assert os.path.exists(os.path.join(client.current_folder, "file.h"))
        assert not os.path.exists(os.path.join(client.current_folder, "file.cpp"))

    def test_template_image_files(self):
        """ problematic files that we dont want to render with Jinja, like PNG or other binaries,
        have to be explicitly excluded from render"""
        client = TestClient(light=True)
        template_dir = "templates/command/new/t_dir"
        png = "$&(){}{}{{}{}"
        save(os.path.join(client.cache_folder, template_dir, "myimage.png"), png)
        client.run("new t_dir -d name=hello -d version=0.1", assert_error=True)
        assert "TemplateSyntaxError" in client.out

        save(os.path.join(client.cache_folder, template_dir, "not_templates"), "*.png")
        client.run("new t_dir -d name=hello -d version=0.1")
        myimage = client.load("myimage.png")
        assert myimage == png
        assert not os.path.exists(os.path.join(client.current_folder, "not_templates"))


class TestNewErrors:
    def test_template_errors(self):
        client = TestClient(light=True)
        client.run("new mytemplate", assert_error=True)
        assert "ERROR: Template doesn't exist" in client.out

    def test_forced(self):
        client = TestClient(light=True)
        client.run("new cmake_lib -d name=hello -d version=0.1")
        client.run("new cmake_lib -d name=hello -d version=0.1", assert_error=True)
        client.run("new cmake_lib -d name=bye -d version=0.2 --force")
        conanfile = client.load("conanfile.py")
        assert 'name = "bye"' in conanfile
        assert 'version = "0.2"' in conanfile

    def test_duplicated(self):
        client = TestClient(light=True)
        client.run("new cmake_lib -d name=hello -d name=0.1", assert_error=True)
        assert "ERROR: name argument can't be multiple: ['hello', '0.1']" in client.out

        # It will create a list and assign to it, but it will not fail ugly
        client.run("new cmake_lib -d name=pkg -d version=0.1 -d version=0.2", assert_error=True)
        assert "ERROR: version argument can't be multiple: ['0.1', '0.2']" in client.out

    def test_name_uppercase(self):
        client = TestClient(light=True)
        client.run("new cmake_lib -d name=Hello", assert_error=True)
        assert "ERROR: name argument must be lowercase: Hello" in client.out

    def test_new_change_folder(self):
        client = TestClient(light=True)
        client.run("new cmake_lib -d name=hello -d version=0.1 -o=myfolder")
        assert os.path.exists(os.path.join(client.current_folder, "myfolder", "conanfile.py"))
