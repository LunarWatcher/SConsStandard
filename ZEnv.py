import os
import platform
import json
from enum import Enum
from pathlib import Path

# SCons imports

import SCons
import SCons.Script as Script
from SCons.Script import Variables, BoolVariable, EnumVariable, Environment, Tool, Configure
# Lib imports
from . import utils

class CompilerType(Enum):
    # Argument style: -whatever
    # examples: Clang, GCC
    POSIX = 1

    # Argument style: /whatever
    # Examples: clang-cl, MSVC
    MSVC_COMPATIBLE = 2

class ZEnv(DefaultEnvironment):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def inject(self, path: str, debug: bool, compiler: str, argType: CompilerType,
                 variables: Variables):
        self.path = path;
        self.debug = debug;
        self.compiler = compiler;
        self.argType = argType;
        self.variables = variables;

        self.sourceFlags = self["CXXFLAGS"]

        self.sanitizers = []
        self.libraries = []
        self.compilerFlags = []
        self.variantDir = ""

        self.stdlib = None

    def EProgram(self, name: str, sources, **kwargs):
        return super().Program("bin/" + name, sources, **kwargs)

    def ELibrary(self, name: str, sources, **kwargs):
        return super().Library("bin/" + name, sources, **kwargs)

    def ESharedLibrary(self, name: str, sources, **kwargs):
        return super().SharedLibrary("bin/" + name, sources, **kwargs)

    def EStaticLibrary(self, name: str, sources, **kwargs):
        return super().StaticLibrary("bin/" + name, sources, **kwargs)

    def EVariantDir(self, target: str, source: str, **kwargs):
        super().VariantDir(target, source)

    def EFlavor(self, name: str, source = None, **kwargs):
        if source is None:
            # Used as a fallback to only type in once. Especially useful for lazy naming
            source = name
        super().VariantDir(os.path.join(self.path, name), source, **kwargs)

    def CGlob(self, sourceDir, pattern = "**/*.cpp"):
        paths = []
        for path in Path(sourceDir).glob(pattern):
            paths.append(str(path))
        return paths

    def FlavorSConscript(self, flavorName, script, **kwargs):
        return self.SConscript(os.path.join(self.path, flavorName, script), **kwargs)

    def ESConscript(self, script, variant_dir = None, **kwargs):
        if variant_dir is not None:
            # Patches the variant dir
            variant_dir = os.path.join(self.path, variant_dir)
        else:
            # Automatic variant detection
            r = script.rsplit("/", 1)
            if (len(r) == 2):
                variant_dir = os.path.join(self.path, r[0])
            else:
                variant_dir = self.path
        self.variantDir = variant_dir
        exports = {"env": self}
        if "exports" in kwargs:
            exports.update(kwargs["exports"])
            del kwargs["exports"]

        return super().SConscript(script, exports = exports, variant_dir = variant_dir, **kwargs)

    def withLibraries(self, libraries: list, append: bool = True):
        """
        Specifies libraries to link. Note that this should not be used for dependencies imported through conan,
        as those are set when the import is handled.
        """
        aLibs = []
        if (type(libraries) is list):
            aLibs = libraries
        else:
            aLibs.append(libraries)

        if append:
            super().Append(LIBS = aLibs)
        else:
            super().Prepend(LIBS = aLibs)

    def getBinPath(self):
        """
        Utility method for cross-environment stuff, like for cases where you
        have a Program depending on a Library
        """
        return os.path.join((self.path if self.variantDir == "" else self.variantDir), "bin/")

    def appendLibPath(self, libPath: str):
        if type(libPath) is not str:
            raise RuntimeError("You can only append strings, not " + str(type(libPath)))
        super().Append(LIBPATH = [libPath])


    def appendSourcePath(self, sourcePath: str):
        if type(sourcePath) is not str:
            raise RuntimeError("You can only append strings, not " + str(type(sourcePath)))
        super().Append(CPPPATH = [sourcePath])

    def withConan(self, conanfile: str = None, options: list = [], settings: list = [], remotes = []):
        if options is None:
            options = []
        elif type(options) is str:
            options = [options]

        if settings is None:
            settings = []
        elif type(settings) is str:
            settings = [settings]

        if "CUSTOM_CONAN" in os.environ:
            # Utility for Conan versions installed from source
            import sys
            sys.path.append(os.environ["CUSTOM_CONAN"])

        from conans.client.conan_api import ConanAPIV1 as conan_api
        from conans import __version__ as conan_version

        conan, _, _ = conan_api.factory()

        if type(remotes) == list and len(remotes) != 0:
            for remote in remotes:
                name = remote["remote_name"]
                url = remote["url"]
                existingRemotes = conan.remote_list()

                filterByUrl = [eRem for eRem in existingRemotes if eRem.url == url]
                if len(filterByUrl) > 0:
                    continue

                filterByName = [eRem for eRem in existingRemotes if eRem.name.lower() == name.lower()]
                if (len(filterByName) > 0):
                    import random
                    remote["remote_name"] = remote["remote_name"] + str(random.randint(0, 99999))

                conan.remote_add(**remote)

        buildDirectory = os.path.join(os.getcwd(), self.path)
        if not os.path.exists(buildDirectory):
            os.makedirs(buildDirectory)

        data = {
            "modified": 0
        }
        if os.path.isfile(os.path.join(self.path, "EnvMod.json")):
            with open(os.path.join(self.path, "EnvMod.json"), "r") as f:
                data = json.load(f)

        conanfilePath = os.path.join(os.getcwd(), "conanfile.txt") if conanfile is None else conanfile
        if not os.path.isfile(conanfilePath):
            conanfilePath = os.path.join(os.getcwd(), "conanfile.py")

        lastMod = os.path.getmtime(conanfilePath)
        if data["modified"] < lastMod:
            profile = self["profile"] if "profile" in self else "default"
            if "settings" in self:
                settings = settings + self["settings"].split(",")
            if "options" in self:
                options = options + self["options"].split(",")
            conan.install(conanfilePath,
                    generators = ["scons"],
                    install_folder = buildDirectory,
                    options = options,
                    settings = settings,
                    build = [ "missing" ],
                    profile_names = [ profile ])
            data["modified"] = lastMod
            with open(os.path.join(self.path, "EnvMod.json"), "w") as f:
                json.dump(data, f)

        conan = self.SConscript(os.path.join(self.path, "SConscript_conan"))

        self.MergeFlags(conan["conan"])

    def withCompilationDB(self, output = "compile_commands.json"):
        """
        @param output    Defines the output folder. Dumps into root if None.

        Note that custom targeting may break the compilation database; if you use aliases,
        specify Default, or otherwise declare specific targets, you may have a bad time:tm:
        with compilation databases.
        This can easily be fixed with Depends(target, database).

        This method returns the database, which you can use to target stuff.
        """
        self.EnsureSConsVersion(4, 0, 0)
        self.Tool('compilation_db')
        return self.CompilationDatabase(output)

    # Configuration utilities
    def configure(self):
        """
        Returns a configuration context.
        """
        return utils.ConfigContext(self)

    def Clone(self, *args, **kwargs):
        """
        Clones the environment.

        Any args and/or kwargs are forwarded to the environment provided by SCons.
        These have no effect on the ZEnv, for various implementation reasons.
        """
        newEnv = ZEnv(self.Clone(*args, **kwargs), self.path, self.debug, self.compiler,
                    self.argType, self.variables)
        newEnv.sanitizers = self.sanitizers
        newEnv.libraries = self.libraries
        newEnv.compilerFlags = self.compilerFlags
        newEnv.variantDir = self.variantDir
        newEnv.stdlib = self.stdlib
        return newEnv

    def getEnvVar(self, key: str):
        return self[key]

    def includeSysVars(self, *keys, **kwargs):
        """
        SCons "sandboxes" the variables. This means that if your tests need specific
        environment variables, they'll be excluded.

        This method includes a select set of environment variables,
        or all.

        Usage for singular variables:
            includeSysVars("envVar1", "envVar2", ...)
        Usage for all variables:
            includeSysVars(all=True)
        Usage for all, but some excluded:
            includeSysVars("thisVarWillBeExcluded", "soWillThis", all=True)

        Note that including all system variables may negatively affect SCons, and could
        potentially break compiling.
        """
        if ("all" in kwargs and kwargs["all"] == True):
            for key, value in os.environ.items():
                # Skip registered keys.
                if key in keys:
                    continue

                self["ENV"][key] = value;
            return;
        for key in keys:
            try:
                self["ENV"][key] = os.environ[key]
            except:
                pass

    def define(self, variable: str):
        """
        This method wraps environment.Append(CPPDEFINES).
        """
        self.Append(CPPDEFINES = [ variable ])

    def addHelp(self, string: str):
        self.Help(string)

    def addVariableHelp(self):
        self.Help(self.variables.GenerateHelpText(self))
