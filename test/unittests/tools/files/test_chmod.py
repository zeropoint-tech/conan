import os
import platform
import stat
import pytest

from conan.tools.files import chmod
from conan.test.utils.mocks import ConanFileMock
from conan.test.utils.tools import temp_folder, save_files


@pytest.fixture
def no_permission_file():
    tmp = temp_folder()
    save_files(tmp, {"file.txt": "foobar"})
    file_path = os.path.join(tmp, "file.txt")
    os.chmod(file_path, 0o000)
    file_mode = os.stat(file_path).st_mode
    assert stat.S_IMODE(file_mode) == 0
    return file_path


@pytest.mark.skipif(platform.system() == "Windows", reason="chmod is not available in Windows")
@pytest.mark.parametrize("read,write,execute,expected", [
    (True, True, True, 0o777),
    (False, True, False, 0o222),
    (False, False, True, 0o111),
    (True, False, True, 0o555),
    (True, True, False, 0o666),
    (True, False, False, 0o444),
    (False, False, False, 0o000),])
def test_chmod_single_file(no_permission_file, read, write, execute, expected):
    """
    This test is to validate the function chmod.

    The function should change the file permissions to the expected value only.
    """
    conanfile = ConanFileMock()
    chmod(conanfile, no_permission_file, read=read, write=write, execute=execute, recursive=False)
    file_mode = os.stat(no_permission_file).st_mode
    assert stat.S_IMODE(file_mode) == expected


@pytest.mark.skipif(platform.system() == "Windows", reason="chmod is not available in Windows")
@pytest.mark.parametrize("read,write,execute,expected", [
    (True, True, True, 0o777),
    (False, True, False, 0o222),
    (False, False, True, 0o111),
    (True, False, True, 0o555),
    (True, True, False, 0o666),
    (True, False, False, 0o444),
    (False, False, False, 0o000),])
def test_chmod_recursive(read, write, execute, expected):
    """
    This test is to validate the function chmod.

    The function should change the file permissions to the expected value only.
    """
    tmp = temp_folder()
    save_files(tmp, {"foobar/qux/file.txt": "foobar",
                          "foobar/file.txt": "qux",
                          "foobar/foo/file.txt": "foobar"})
    folder_path = os.path.join(tmp, "foobar")
    conanfile = ConanFileMock()
    chmod(conanfile, folder_path, read=read, write=write, execute=execute, recursive=True)
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_mode = os.stat(os.path.join(root, file)).st_mode
            assert stat.S_IMODE(file_mode) == expected


@pytest.mark.skipif(platform.system() != "Windows", reason="Only to validate no breaking on Windows")
def test_chmod_windows():
    """
    This test is to validate that the function does not break on Windows only.

    The function is not expected to work on Windows, so it should not change the file permissions.
    """
    conanfile = ConanFileMock()
    chmod(conanfile, "invalid_path", read=True, write=True, execute=True, recursive=False)
