import os
import platform
import shutil

import pytest

from conan.tools.env.environment import environment_wrap_command
from conan.tools.files import replace_in_file
from conan.test.utils.mocks import ConanFileMock
from conan.test.utils.tools import TestClient


@pytest.mark.skipif(platform.system() != "Linux", reason="Only Linux")
@pytest.mark.tool("cmake")
@pytest.mark.parametrize("nosoname_property", [
    True,  # without SONAME
    False  # By default, with SONAME
])
def test_no_soname_flag(nosoname_property):
    """ This test case is testing this graph structure:
            *   'Executable' -> 'LibB' -> 'LibNoSoname'
        Where:
            *   LibNoSoname: is a package built as shared and without the SONAME flag.
            *   LibB: is a package which requires LibNoSoname.
            *   Executable: is the final consumer building an application and depending on OtherLib.
        How:
            1- Creates LibNoSoname and upload it to remote server
            2- Creates LibB and upload it to remote server
            3- Remove the Conan cache folder
            4- Creates an application and consume LibB
        Goal:
            * If `self.cpp_info.set_property("nosoname", True), then the `Executable` runs OK.
            * If `self.cpp_info.set_property("nosoname", False), then the `Executable` fails.
    """
    client = TestClient(default_server_user=True)
    # Creating nosoname/0.1 library
    client.run("new cmake_lib -d name=nosoname -d version=0.1")

    replace_in_file(ConanFileMock(), os.path.join(client.current_folder, "conanfile.py"),
                    'self.cpp_info.libs = ["nosoname"]',
                    f'self.cpp_info.libs = ["nosoname"]\n        self.cpp_info.set_property("nosoname", {nosoname_property})')
    replace_in_file(ConanFileMock(), os.path.join(client.current_folder, "CMakeLists.txt"),
                    'target_include_directories(nosoname PUBLIC include)',
                    'target_include_directories(nosoname PUBLIC include)\nset_target_properties(nosoname PROPERTIES NO_SONAME 1)')
    client.run("create . -o nosoname/*:shared=True -tf=")
    # Creating lib_b/0.1 library (depends on nosoname/0.1)
    client.save({}, clean_first=True)
    client.run("new cmake_lib -d name=lib_b -d version=0.1 -d requires=nosoname/0.1")
    client.run("create . -o lib_b/*:shared=True -o nosoname/*:shared=True -tf=")
    # Creating app/0.1 application (depends on lib_b/0.1)
    client.save({}, clean_first=True)
    client.run("new cmake_exe -d name=app -d version=0.1 -d requires=lib_b/0.1")
    client.run("create . -o nosoname/*:shared=True -o lib_b/*:shared=True -tf=")
    client.run("upload * -c -r default")
    # Removing everything from the .conan2/p to ensure that we don't have anything saved in the cache
    shutil.rmtree(client.cache.store)

    client = TestClient(servers=client.servers)
    client.run("install --requires=app/0.1@ -o nosoname*:shared=True -o lib_b/*:shared=True")
    # This only finds "app" executable because the "app/0.1" is declaring package_type="application"
    # otherwise, run=None and nothing can tell us if the conanrunenv should have the PATH.
    command = environment_wrap_command(ConanFileMock(), "conanrun", client.current_folder, "app")

    # If `nosoname_property` is False, and we have a library without the SONAME flag,
    # then it should fail
    if nosoname_property is False:
        client.run_command(command, assert_error=True)
        assert "libnosoname.so: cannot open shared object file: " \
               "No such file or directory" in client.out
    else:
        client.run_command(command)
        assert "nosoname/0.1: Hello World Release!" in client.out
        assert "lib_b/0.1: Hello World Release!" in client.out
        assert "app/0.1: Hello World Release!" in client.out
