# Source: https://learn.microsoft.com/en-us/cpp/overview/compiler-versions?view=msvc-170
PREMAKE_VS_VERSION = {
    '190': '2015',
    '191': '2017',
    '192': '2019',
    '193': '2022',
    '194': '2022',  # still 2022
}


class Premake:
    """
    Premake cli wrapper
    """

    def __init__(self, conanfile):
        self._conanfile = conanfile

        self.action = None              # premake5 action to use (Autogenerated)
        self.luafile = 'premake5.lua'   # Path to the root (premake5) lua file
        # (key value pairs. Will translate to "--{key}={value}")
        self.arguments = {}             # https://premake.github.io/docs/Command-Line-Arguments/

        if "msvc" in self._conanfile.settings.compiler:
            msvc_version = PREMAKE_VS_VERSION.get(str(self._conanfile.settings.compiler.version))
            self.action = f'vs{msvc_version}'
        else:
            self.action = 'gmake2'

    @staticmethod
    def _expand_args(args):
        return ' '.join([f'--{key}={value}' for key, value in args.items()])

    def configure(self):
        premake_options = dict()
        premake_options["file"] = self.luafile

        premake_command = f'premake5 {self._expand_args(premake_options)} {self.action} ' \
                          f'{self._expand_args(self.arguments)}'
        self._conanfile.run(premake_command)
