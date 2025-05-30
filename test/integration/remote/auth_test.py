import copy
import os
import textwrap
import unittest
import pytest

from requests.models import Response

from conan.internal.api.remotes.localdb import LocalDB
from conan.api.model import RecipeReference
from conan.internal.paths import CONANFILE
from conan.test.assets.genconanfile import GenConanfile
from conan.test.utils.test_files import temp_folder
from conan.test.utils.tools import TestClient
from conan.test.utils.tools import TestRequester
from conan.test.utils.tools import TestServer
from conan.test.utils.env import environment_update
from conan.internal.util.files import save

conan_content = """
from conan import ConanFile

class OpenSSLConan(ConanFile):
    name = "openssl"
    version = "2.0.1"
    files = '*'
"""


class AuthorizeTest(unittest.TestCase):

    def setUp(self):
        self.servers = {}
        self.ref = RecipeReference.loads("openssl/2.0.1@lasote/testing")
        # Create a default remote. R/W is not authorized for ref,
        # just for pepe, nacho and owner
        self.test_server = TestServer([(str(self.ref), "pepe,nacho@gmail.com")],  # read permissions
                                      [(str(self.ref), "pepe,nacho@gmail.com")],  # write permissions
                                      users={"lasote": "mypass",
                                             "pepe": "pepepass",
                                             "nacho@gmail.com": "nachopass"})  # exported creds
        self.servers["default"] = self.test_server

    def test_retries(self):
        """Bad login 2 times"""
        self.conan = TestClient(servers=self.servers, inputs=["bad", "1",
                                                              "bad2", "2",
                                                              "nacho@gmail.com", "nachopass"])
        save(os.path.join(self.conan.current_folder, CONANFILE), conan_content)
        self.conan.run("export . --user=lasote --channel=testing")
        errors = self.conan.run("upload %s -r default --only-recipe" % str(self.ref))
        # Check that return was  ok
        self.assertFalse(errors)
        # Check that upload was granted
        rev = self.test_server.server_store.get_last_revision(self.ref).revision
        ref = copy.copy(self.ref)
        ref.revision = rev
        self.assertTrue(os.path.exists(self.test_server.server_store.export(ref)))
        self.assertIn("Please enter a password for user 'bad'", self.conan.out)
        self.assertIn("Please enter a password for user 'bad2'", self.conan.out)
        self.assertIn("Please enter a password for user 'nacho@gmail.com'", self.conan.out)

    def test_auth_with_env(self):

        def _upload_with_credentials(credentials, assert_error=False):
            cli = TestClient(servers=self.servers)
            save(os.path.join(cli.current_folder, CONANFILE), conan_content)
            cli.run("export . --user=lasote --channel=testing")
            with environment_update(credentials):
                cli.run("upload %s -r default --only-recipe" % str(self.ref),
                        assert_error=assert_error)
            return cli

        # Try with remote name in credentials
        client = _upload_with_credentials({"CONAN_PASSWORD_DEFAULT": "pepepass",
                                           "CONAN_LOGIN_USERNAME_DEFAULT": "pepe"})
        self.assertIn("Got username 'pepe' from environment", client.out)
        self.assertIn("Got password '******' from environment", client.out)

        # Try with generic password and login
        client = _upload_with_credentials({"CONAN_PASSWORD": "pepepass",
                                           "CONAN_LOGIN_USERNAME_DEFAULT": "pepe"})
        self.assertIn("Got username 'pepe' from environment", client.out)
        self.assertIn("Got password '******' from environment", client.out)

        # Try with generic password and generic login
        client = _upload_with_credentials({"CONAN_PASSWORD": "pepepass",
                                           "CONAN_LOGIN_USERNAME": "pepe"})
        self.assertIn("Got username 'pepe' from environment", client.out)
        self.assertIn("Got password '******' from environment", client.out)

        # Bad pass raise
        client = _upload_with_credentials({"CONAN_PASSWORD": "bad",
                                           "CONAN_LOGIN_USERNAME": "pepe"}, assert_error=True)
        self.assertIn("Authentication error in remote 'default'", client.out)

    def test_max_retries(self):
        """Bad login 3 times"""
        client = TestClient(servers=self.servers, inputs=["baduser", "badpass",
                                                          "baduser", "badpass2",
                                                          "baduser3", "badpass3"])
        save(os.path.join(client.current_folder, CONANFILE), conan_content)
        client.run("export . --user=lasote --channel=testing")
        errors = client.run("upload %s -r default --only-recipe" % str(self.ref), assert_error=True)
        # Check that return was not ok
        self.assertTrue(errors)
        # Check that upload was not granted
        rev = self.servers["default"].server_store.get_last_revision(self.ref)
        self.assertIsNone(rev)

        # Check that login failed all times
        self.assertIn("Too many failed login attempts, bye!", client.out)

    def test_no_client_username_checks(self):
        """Checks whether client username checks are disabled."""

        # Try with a load of names that contain special characters
        client = TestClient(servers=self.servers, inputs=["some_random.special!characters",
                                                          "badpass",
                                                          "nacho@gmail.com", "nachopass"])

        save(os.path.join(client.current_folder, CONANFILE), conan_content)
        client.run("export . --user=lasote --channel=testing")
        client.run("upload %s -r default --only-recipe" % str(self.ref))

        # Check that upload was granted
        rev = self.test_server.server_store.get_last_revision(self.ref).revision
        ref = copy.copy(self.ref)
        ref.revision = rev
        self.assertTrue(os.path.exists(self.test_server.server_store.export(ref)))
        self.assertIn("Please enter a password for user 'some_random.special!characters' on remote 'default'",
                      client.out)

    def test_authorize_disabled_remote(self):
        tc = TestClient(servers=self.servers)
        # Sanity check, this should not fail
        tc.run("remote login default pepe -p pepepass")
        tc.run("remote logout default")
        # This used to fail when the authentication was not possible for disabled remotes
        tc.run("remote disable default")
        tc.run("remote login default pepe -p pepepass")
        self.assertIn("Changed user of remote 'default' from 'None' (anonymous) to 'pepe' (authenticated)", tc.out)


class TestAuthenticationTest:

    def test_unauthorized_during_capabilities(self):

        class RequesterMock(TestRequester):
            @staticmethod
            def get(url, **kwargs):
                resp_basic_auth = Response()
                resp_basic_auth.status_code = 200
                if "authenticate" in url:
                    assert kwargs["auth"].password == "PASSWORD!"
                    resp_basic_auth._content = b"TOKEN"
                    resp_basic_auth.headers = {"Content-Type": "text/plain"}
                elif "ping" in url:
                    resp_basic_auth.headers = {"Content-Type": "application/json",
                                               "X-Conan-Server-Capabilities": "revisions"}
                    bearer = getattr(kwargs["auth"], "bearer", None)
                    password = getattr(kwargs["auth"], "password", None)
                    assert bearer == "Bearer TOKEN" or password
                else:
                    assert "search" in url
                    assert kwargs["auth"].bearer == "Bearer TOKEN"
                    resp_basic_auth._content = b'{"results": []}'
                    resp_basic_auth.headers = {"Content-Type": "application/json"}
                return resp_basic_auth

        client = TestClient(requester_class=RequesterMock, default_server_user=True)
        client.run("remote login default user -p PASSWORD!")
        assert "Changed user of remote 'default' from 'None' (anonymous) to 'user'" in client.out
        client.run("search pkg -r=default")
        assert "ERROR: Recipe 'pkg' not found" in client.out


@pytest.mark.xfail(reason="This test is randomly failing")
def test_token_expired():
    server_folder = temp_folder()
    server_conf = textwrap.dedent("""
       [server]
       jwt_expire_minutes: 0.02
       authorize_timeout: 0
       disk_authorize_timeout: 0
       disk_storage_path: ./data
       updown_secret: 12345
       jwt_secret: mysecret
       port: 12345
       [read_permissions]
       */*@*/*: *
       [write_permissions]
       */*@*/*: admin
       """)
    save(os.path.join(server_folder, ".conan_server", "server.conf"), server_conf)
    server = TestServer(base_path=server_folder, users={"admin": "password", "other": "pass"})

    c = TestClient(servers={"default": server}, inputs=["admin", "password", "other", "pass"])
    c.save({"conanfile.py": GenConanfile()})
    c.run("create . --name=pkg --version=0.1 --user=user --channel=stable")
    c.run("upload * -r=default -c")
    localdb = LocalDB(c.cache_folder)
    user, token, _ = localdb.get_login(server.fake_url)
    assert user == "admin"
    assert token is not None

    import time
    time.sleep(3)
    c.users = {}
    c.run("remove * -c")
    c.run("install --requires=pkg/0.1@user/stable")
    assert "Remote 'default' needs authentication, obtaining credentials" in c.out
    user, token, _ = localdb.get_login(server.fake_url)
    assert user == "other"
    assert token is not None


def test_auth_username_space():
    server = TestServer(users={"super admin": "password"})
    c = TestClient(servers={"default": server}, inputs=["super admin", "password"])
    c.save({"conanfile.py": GenConanfile("pkg", "0.1")})
    c.run("export .")
    c.run("upload * -r=default -c")
    # it doesn't crash, it accepts user with space
