import os

from conan.internal.rest.client_routes import ClientV2Router
from conan.internal.util.files import sha1sum


def add_urls(package_list, remote, backup_files, upload_url):
    router = ClientV2Router(remote.url.rstrip("/"))
    for ref, bundle in package_list.refs().items():
        for f, fp in bundle.get("files", {}).items():
            bundle.setdefault("urls", {})[f] = {
                'url': router.recipe_file(ref, f), 'checksum': sha1sum(fp)
            }
        for pref, prev_bundle in package_list.prefs(ref, bundle).items():
            for f, fp in prev_bundle.get("files", {}).items():
                prev_bundle.setdefault("urls", {})[f] = {
                    'url': router.package_file(pref, f), 'checksum': sha1sum(fp)
                }

    if upload_url:
        url = upload_url if upload_url.endswith("/") else upload_url + "/"
        if backup_files:
            for file in backup_files:
                basename = os.path.basename(file)
                package_list.recipes.setdefault('backup_sources', {})[basename] = {
                    'file_path': file, 'url': url + basename, 'checksum': sha1sum(file)
                }
