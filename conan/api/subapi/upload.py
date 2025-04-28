import os
import time
from multiprocessing.pool import ThreadPool

from conan.api.output import ConanOutput
from conan.internal.conan_app import ConanApp
from conan.internal.api.uploader import PackagePreparator, UploadExecutor, UploadUpstreamChecker, \
    gather_metadata
from conans.client.pkg_sign import PkgSignaturesPlugin
from conans.client.rest.client_routes import ClientV2Router
from conans.client.rest.file_uploader import FileUploader
from conan.internal.errors import AuthenticationException, ForbiddenException
from conan.errors import ConanException
from conans.client.rest.rest_client_v2 import JWTAuth
from conans.util.files import sha1sum


class UploadAPI:

    def __init__(self, conan_api):
        self.conan_api = conan_api

    def check_upstream(self, package_list, remote, enabled_remotes, force=False):
        """Check if the artifacts are already in the specified remote, skipping them from
        the package_list in that case"""
        app = ConanApp(self.conan_api)
        for ref, bundle in package_list.refs().items():
            layout = app.cache.recipe_layout(ref)
            conanfile_path = layout.conanfile()
            conanfile = app.loader.load_basic(conanfile_path, remotes=enabled_remotes)
            if conanfile.upload_policy == "skip":
                ConanOutput().info(f"{ref}: Skipping upload of binaries, "
                                   "because upload_policy='skip'")
                bundle["packages"] = {}

        UploadUpstreamChecker(app).check(package_list, remote, force)

    def prepare(self, package_list, enabled_remotes, metadata=None):
        """Compress the recipes and packages and fill the upload_data objects
        with the complete information. It doesn't perform the upload nor checks upstream to see
        if the recipe is still there
        :param package_list:
        :param enabled_remotes:
        :param metadata: A list of patterns of metadata that should be uploaded. Default None
        means all metadata will be uploaded together with the pkg artifacts. If metadata is empty
        string (""), it means that no metadata files should be uploaded."""
        if metadata and metadata != [''] and '' in metadata:
            raise ConanException("Empty string and patterns can not be mixed for metadata.")
        app = ConanApp(self.conan_api)
        preparator = PackagePreparator(app, self.conan_api.config.global_conf)
        preparator.prepare(package_list, enabled_remotes)
        if metadata != ['']:
            gather_metadata(package_list, app.cache, metadata)
        signer = PkgSignaturesPlugin(app.cache, app.cache_folder)
        # This might add files entries to package_list with signatures
        signer.sign(package_list)

    def _dry_run(self, package_list, remote, enabled_remotes, metadata=None):
        output = ConanOutput()
        router = ClientV2Router(remote.url.rstrip("/"))
        self.prepare(package_list, enabled_remotes, metadata)
        _info = {}
        requester = self.conan_api.remotes.requester
        config = self.conan_api.config.global_conf
        uploader = FileUploader(requester, verify=True, config=config, source_credentials=True)
        _, token = ConanApp(self.conan_api).remote_manager._auth_manager._creds.get(remote)
        for ref, bundle in package_list.refs().items():
            if bundle.get("upload"):
                for fn, abs_path in bundle['files'].items():
                    full_url = router.recipe_file(ref, fn)
                    try:
                        if not uploader.exists(full_url, auth=JWTAuth(token)):
                            _info[abs_path] = {'file_name': fn, 'url': full_url, 'checksum': sha1sum(abs_path)}
                    except (AuthenticationException, ForbiddenException):
                        output.warning(f"Forbidden access to {remote.url}")
            for pref, prev_bundle in package_list.prefs(ref, bundle).items():
                if prev_bundle.get("upload"):
                    for fn, abs_path in prev_bundle['files'].items():
                        full_url = router.package_file(pref, fn)
                        try:
                            if not uploader.exists(full_url, auth=JWTAuth(token)):
                                _info[abs_path] = {'file_name': fn, 'url': full_url, 'checksum': sha1sum(abs_path)}
                        except (AuthenticationException, ForbiddenException):
                            output.warning(f"Forbidden access to {remote.url}")
        return _info

    def _dry_run_backup_sources(self, package_list):
        _info = {}
        backup_files = self.conan_api.cache.get_backup_sources(package_list)
        config = self.conan_api.config.global_conf
        url = config.get("core.sources:upload_url", check_type=str)
        if url:
            url = url if url.endswith("/") else url + "/"

            output = ConanOutput()
            if backup_files:
                requester = self.conan_api.remotes.requester
                uploader = FileUploader(requester, verify=True, config=config, source_credentials=True)
                # TODO: For Artifactory, we can list all files once and check from there instead
                #  of 1 request per file, but this is more general
                for file in backup_files:
                    basename = os.path.basename(file)
                    full_url = url + basename
                    is_summary = file.endswith(".json")
                    try:
                        if is_summary or not uploader.exists(full_url, auth=None):
                            _info[basename] = {'file_path': file, 'url': full_url, 'checksum': sha1sum(file)}
                        else:
                            output.info(f"File '{basename}' already in backup sources server, skipping upload")
                    except (AuthenticationException, ForbiddenException):
                        output.warning(f"Forbidden access to {url}")
        return {'backup_sources': _info}

    def _dry_run_output(self, package_list, dry_run_info):
        #  TODO: add _dry_run_backup_sources info
        for ref in package_list.recipes.keys():
            for rev, revision in package_list.recipes[ref]['revisions'].items():
                package_list.recipes[ref]['revisions'][rev]['upload_urls'] = {
                    file_name: {
                        'url': dry_run_info.get(full_path, {'url': None})['url'],
                        'checksum': dry_run_info.get(full_path, {'checksum': None})['checksum']
                    }
                    for file_name, full_path in revision['files'].items()
                }
                package_list.recipes[ref]['revisions'][rev]
                for package in revision['packages'].keys():
                    for prev in revision['packages'][package]['revisions'].keys():
                        package_list.recipes[ref]['revisions'][rev]['packages'][package]['revisions'][prev]['upload_urls'] = {
                            file_name: {
                                'url': dry_run_info.get(full_path, {'url': None})['url'],
                                'checksum': dry_run_info.get(full_path, {'checksum': None})['checksum']
                            }
                            for file_name, full_path in revision['packages'][package]['revisions'][prev]['files'].items()
                        }
        if dry_run_info.get('backup_sources'):
            package_list.recipes['backup_sources'] = dry_run_info['backup_sources']
        return package_list

    def upload(self, package_list, remote):
        app = ConanApp(self.conan_api)
        app.remote_manager.check_credentials(remote)
        executor = UploadExecutor(app)
        executor.upload(package_list, remote)

    def upload_full(self, package_list, remote, enabled_remotes, check_integrity=False, force=False,
                    metadata=None, dry_run=False):
        """ Does the whole process of uploading, including the possibility of parallelizing
        per recipe based on `core.upload:parallel`:
        - calls check_integrity
        - checks which revision already exist in the server (not necessary to upload)
        - prepare the artifacts to upload (compress .tgz)
        - execute the actual upload
        - upload potential sources backups
        """
        dry_run_info = {}

        def _upload_pkglist(pkglist, subtitle=lambda _: None):
            if check_integrity:
                subtitle("Checking integrity of cache packages")
                self.conan_api.cache.check_integrity(pkglist)
            # Check if the recipes/packages are in the remote
            subtitle("Checking server existing packages")
            self.check_upstream(pkglist, remote, enabled_remotes, force)
            subtitle("Preparing artifacts for upload")
            self.prepare(pkglist, enabled_remotes, metadata)

            if not dry_run:
                subtitle("Uploading artifacts")
                self.upload(pkglist, remote)
                backup_files = self.conan_api.cache.get_backup_sources(pkglist)
                self.upload_backup_sources(backup_files)
            else:
                dry_run_info.update(self._dry_run(pkglist, remote, enabled_remotes, metadata))
                dry_run_info.update(self._dry_run_backup_sources(pkglist))

        t = time.time()
        ConanOutput().title(f"Uploading to remote {remote.name}")
        parallel = self.conan_api.config.get("core.upload:parallel", default=1, check_type=int)
        thread_pool = ThreadPool(parallel) if parallel > 1 else None
        if not thread_pool or len(package_list.recipes) <= 1:
            _upload_pkglist(package_list, subtitle=ConanOutput().subtitle)
        else:
            ConanOutput().subtitle(f"Uploading with {parallel} parallel threads")
            thread_pool.map(_upload_pkglist, package_list.split())
        if thread_pool:
            thread_pool.close()
            thread_pool.join()
        elapsed = time.time() - t
        ConanOutput().success(f"Upload completed in {int(elapsed)}s\n")
        if dry_run:
            return self._dry_run_output(package_list, dry_run_info)
        return package_list

    def upload_backup_sources(self, files):
        config = self.conan_api.config.global_conf
        url = config.get("core.sources:upload_url", check_type=str)
        if url is None:
            return
        url = url if url.endswith("/") else url + "/"

        output = ConanOutput()
        output.subtitle("Uploading backup sources")
        if not files:
            output.info("No backup sources files to upload")
            return files

        requester = self.conan_api.remotes.requester
        uploader = FileUploader(requester, verify=True, config=config, source_credentials=True)
        # TODO: For Artifactory, we can list all files once and check from there instead
        #  of 1 request per file, but this is more general
        for file in files:
            basename = os.path.basename(file)
            full_url = url + basename
            is_summary = file.endswith(".json")
            file_kind = "summary" if is_summary else "file"
            try:
                if is_summary or not uploader.exists(full_url, auth=None):
                    output.info(f"Uploading {file_kind} '{basename}' to backup sources server")
                    uploader.upload(full_url, file, dedup=False, auth=None)
                else:
                    output.info(f"File '{basename}' already in backup sources server, "
                                "skipping upload")
            except (AuthenticationException, ForbiddenException) as e:
                if is_summary:
                    output.warning(f"Could not update summary '{basename}' in backup sources server. "
                                   "Skipping updating file but continuing with upload. "
                                   f"Missing permissions?: {e}")
                else:
                    raise ConanException(f"The source backup server '{url}' needs authentication"
                                         f"/permissions, please provide 'source_credentials.json': {e}")

        output.success("Upload backup sources complete\n")
        return files
