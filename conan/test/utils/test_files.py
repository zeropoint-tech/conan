import copy
import os
import platform
import shutil
import tarfile
import tempfile

import time
from io import BytesIO

from conan.internal.api.uploader import gzopen_without_timestamps
from conan.tools.files.files import untargz
from conan.internal.subsystems import get_cased_path
from conan.errors import ConanException
from conan.internal.paths import PACKAGE_TGZ_NAME


def wait_until_removed(folder):
    latest_exception = None
    for _ in range(50):  # Max 5 seconds
        time.sleep(0.1)
        try:
            shutil.rmtree(folder)
            break
        except Exception as e:
            latest_exception = e
    else:
        raise Exception("Could remove folder %s: %s" % (folder, latest_exception))


CONAN_TEST_FOLDER = os.getenv('CONAN_TEST_FOLDER', None)
if CONAN_TEST_FOLDER and not os.path.exists(CONAN_TEST_FOLDER):
    os.makedirs(CONAN_TEST_FOLDER)


def temp_folder(path_with_spaces=True, create_dir=True):
    t = tempfile.mkdtemp(suffix='conans', dir=CONAN_TEST_FOLDER)
    # Make sure that the temp folder is correctly cased, as tempfile return lowercase for Win
    t = get_cased_path(t)
    # necessary for Mac OSX, where the temp folders in /var/ are symlinks to /private/var/
    t = os.path.realpath(t)
    # FreeBSD and Solaris do not use GNU Make as a the default 'make' program which has trouble
    # with spaces in paths generated by CMake
    if not path_with_spaces or platform.system() == "FreeBSD" or platform.system() == "SunOS":
        path = "pathwithoutspaces"
    else:
        path = "path with spaces"
    nt = os.path.join(t, path)
    if create_dir:
        os.makedirs(nt)
    return nt


def uncompress_packaged_files(paths, pref):
    rev = paths.get_last_revision(pref.ref).revision
    _tmp = copy.copy(pref)
    _tmp.revision = None
    prev = paths.get_last_package_revision(_tmp).revision
    pref.revision = prev

    package_path = paths.package(pref)
    if not(os.path.exists(os.path.join(package_path, PACKAGE_TGZ_NAME))):
        raise ConanException("%s not found in %s" % (PACKAGE_TGZ_NAME, package_path))
    tmp = temp_folder()
    untargz(os.path.join(package_path, PACKAGE_TGZ_NAME), tmp)
    return tmp


def scan_folder(folder):
    scanned_files = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        relative_path = os.path.relpath(root, folder)
        for f in files:
            if f.endswith(".pyc"):
                continue
            relative_name = os.path.normpath(os.path.join(relative_path, f)).replace("\\", "/")
            scanned_files.append(relative_name)

    return sorted(scanned_files)


def tgz_with_contents(files, output_path=None):
    folder = temp_folder()
    file_path = output_path or os.path.join(folder, "myfile.tar.gz")

    with open(file_path, "wb") as tgz_handle:
        tgz = gzopen_without_timestamps("myfile.tar.gz", fileobj=tgz_handle)

        for name, content in files.items():
            info = tarfile.TarInfo(name=name)
            data = content.encode('utf-8')
            info.size = len(data)
            tgz.addfile(tarinfo=info, fileobj=BytesIO(data))

        tgz.close()

    return file_path
