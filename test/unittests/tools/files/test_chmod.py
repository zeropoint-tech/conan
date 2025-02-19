import os
import platform
import stat
import pytest

from conan.errors import ConanException
from conan.tools.files import chmod
from conan.test.utils.mocks import ConanFileMock
from conan.test.utils.tools import temp_folder, save_files


@pytest.mark.skipif(platform.system() == "Windows", reason="validate full permissions only in Unix")
@pytest.mark.parametrize("read,write,execute,expected", [
    (True, True, True, 0o755),
    (False, True, False, 0o200),
    (False, False, True, 0o111),
    (True, False, True, 0o555),
    (True, True, False, 0o644),
    (True, False, False, 0o444),
    (False, False, False, 0o000),])
def test_chmod_single_file(read, write, execute, expected):
    """
    This test is to validate the function chmod.

    The function should change the file permissions to the expected value only.
    """
    tmp = temp_folder()
    save_files(tmp, {"file.txt": "foobar"})
    file_path = os.path.join(tmp, "file.txt")
    os.chmod(file_path, 0o000)
    conanfile = ConanFileMock()
    chmod(conanfile, file_path, read=read, write=write, execute=execute, recursive=False)
    file_mode = os.stat(file_path).st_mode
    assert stat.S_IMODE(file_mode) == expected


@pytest.mark.skipif(platform.system() == "Windows", reason="validate full permissions only in Unix")
@pytest.mark.parametrize("read,write,execute,expected", [
    (True, True, True, 0o755),
    (False, True, False, 0o200),
    (False, False, True, 0o111),
    (True, False, True, 0o555),
    (True, True, False, 0o644),
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


def test_invalid_path():
    """
    This test is to validate the function chmod.

    The function should raise an exception if the path does not exist.
    """
    conanfile = ConanFileMock()
    with pytest.raises(ConanException) as error:
        chmod(conanfile, "invalid_path", read=True, write=True, execute=True, recursive=False)
    assert 'Could not change permission: Path "invalid_path" does not exist.' in str(error.value)


@pytest.mark.skipif(platform.system() != "Windows", reason="Validate read-only permissions only in Windows")
def test_chmod_windows():
    """
    This test is to validate the function chmod in Windows.
    """
    tmp = temp_folder()
    save_files(tmp, {"file.txt": "foobar"})
    file_path = os.path.join(tmp, "file.txt")
    os.chmod(file_path, 0o000)
    conanfile = ConanFileMock()
    chmod(conanfile, file_path, read=True, write=True, execute=True, recursive=False)
    assert os.access(file_path, os.W_OK)
