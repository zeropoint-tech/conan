import os
import unittest
import mock

from conan import __version__
from conan.test.utils.test_files import temp_folder
from conan.test.utils.tools import TestClient
from conan.internal.util.files import save


class RequiredVersionTest(unittest.TestCase):

    @mock.patch("conan.__version__", "1.26.0")
    def test_wrong_version(self):
        required_version = "1.23.0"
        client = TestClient()
        client.save_home({"global.conf": f"core:required_conan_version={required_version}"})
        client.run("help", assert_error=True)
        self.assertIn("Current Conan version (1.26.0) does not satisfy the defined "
                      "one ({})".format(required_version), client.out)

    @mock.patch("conan.__version__", "1.22.0")
    def test_exact_version(self):
        required_version = "1.22.0"
        client = TestClient()
        client.save_home({"global.conf": f"core:required_conan_version={required_version}"})
        client.run("--help")

    @mock.patch("conan.__version__", "2.1.0")
    def test_lesser_version(self):
        required_version = "<3.0"
        client = TestClient()
        client.save_home({"global.conf": f"core:required_conan_version={required_version}"})
        client.run("--help")

    @mock.patch("conan.__version__", "1.0.0")
    def test_greater_version(self):
        required_version = ">0.1.0"
        client = TestClient()
        client.save_home({"global.conf": f"core:required_conan_version={required_version}"})
        client.run("--help")

    def test_bad_format(self):
        required_version = "1.0.0.0-foobar"
        cache_folder = temp_folder()
        save(os.path.join(cache_folder, "global.conf"),
             f"core:required_conan_version={required_version}")
        c = TestClient(cache_folder)
        c.run("version", assert_error=True)
        self.assertIn("Current Conan version ({}) does not satisfy the defined one ({})"
                      .format(__version__, required_version), c.out)
