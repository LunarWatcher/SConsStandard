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

# TODO: Add support for cross compiling to a different platform (options + returning platform)

class CompilerType(Enum):
    # Argument style: -whatever
    # examples: Clang, GCC
    POSIX = 1

    # Argument style: /whatever
    # Examples: clang-cl, MSVC
    MSVC_COMPATIBLE = 2

class ZEnv:

    def __init__(self, environment: Environment, path: str, debug: bool, compiler: str, argType: CompilerType):
        self.environment = environment;
        self.path = path;
        self.debug = debug;
        self.compiler = compiler;
        self.argType = argType;

        self.sourceFlags = environment["CXXFLAGS"]

        self.sanitizers = []
        self.libraries = []
        self.compilerFlags = []
        self.variantDir = ""

        self.stdlib = None

    def Program(self, name: str, sources, **kwargs):
        return self.environment.Program("bin/" + name, sources, **kwargs)

    def Library(self, name: str, sources, **kwargs):
        return self.environment.Library("bin/" + name, sources, **kwargs)

    def SharedLibrary(self, name: str, sources, **kwargs):
        return self.environment.SharedLibrary("bin/" + name, sources, **kwargs)

    def StaticLibrary(self, name: str, sources, **kwargs):
        return self.environment.StaticLibrary("bin/" + name, sources, **kwargs)

    def VariantDir(self, target: str, source: str, **kwargs):
        self.environment.VariantDir(target, source)

    def Flavor(self, name: str, source = None, **kwargs):
        if source is None:
            # Used as a fallback to only type in once. Especially useful for lazy naming
            source = name
        self.environment.VariantDir(self.path + "/" + name, source, **kwargs)

    def Glob(self, pattern, **kwargs):
        """
        Wrapper around SCon's Glob method.
        Note that this is NOT recursive!
        folder/*.cpp means folder/*.cpp, not
        folder/subfolder/*.cpp.
        This is a limitation of SCons, and one I'll
        have to figure out a workaround for Some Day:tm:
        """
        return self.environment.Glob(pattern, **kwargs)

    def CGlob(self, sourceDir, pattern = "**/*.cpp"):
        paths = []
        for path in Path(sourceDir).glob(pattern):
            paths.append(str(path))
        return paths

    def FlavorSConscript(self, flavorName, script, **kwargs):
        return self.SConscript(self.path + "/" + flavorName + "/" + script, **kwargs)

    def SConscript(self, script, variant_dir = None, **kwargs):
        if variant_dir is not None:
            # Patches the variant dir
            variant_dir = self.path + "/" + variant_dir
        else:
            # Automatic variant detection
            r = script.rsplit("/", 1)
            if (len(r) == 2):
                variant_dir = self.path + r[0]
            else:
                variant_dir = self.path
        self.variantDir = variant_dir
        exports = {"env": self}
        if "exports" in kwargs:
            exports.update(kwargs["exports"])
            del kwargs["exports"]

        return self.environment.SConscript(script, exports = exports, variant_dir = variant_dir, **kwargs)

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
            self.environment.Append(LIBS = aLibs)
        else:
            self.environment.Prepend(LIBS = aLibs)

    def getBinPath(self):
        """
        Utility method for cross-environment stuff, like for cases where you
        have a Program depending on a Library
        """
        return (self.path if self.variantDir == "" else self.variantDir) + "/bin/"

    def appendLibPath(self, libPath: str):
        if type(libPath) is not str:
            raise RuntimeError("You can only append strings, not " + str(type(libPath)))
        self.environment.Append(LIBPATH = [libPath])


    def appendSourcePath(self, sourcePath: str):
        if type(sourcePath) is not str:
            raise RuntimeError("You can only append strings, not " + str(type(sourcePath)))
        self.environment.Append(CPPPATH = [sourcePath])

    def withConan(self, options = None, settings = None, enableUpdateFlag = True):

        from conans.client.conan_api import ConanAPIV1 as conan_api
        from conans import __version__ as conan_version

        conan, _, _ = conan_api.factory()

        buildDirectory = os.path.join(os.getcwd(), self.path)
        if not os.path.exists(buildDirectory):
            os.makedirs(buildDirectory)

        data = {
            "modified": 0
        }
        if os.path.isfile(self.path + "EnvMod.json"):
            with open(self.path + "EnvMod.json", "r") as f:
                data = json.load(f)

        conanfilePath = os.path.join(os.getcwd(), "conanfile.txt")
        lastMod = os.path.getmtime(conanfilePath)
        if data["modified"] < lastMod:
            profile = self.environment["profile"] if "profile" in self.environment else "default"
            if "settings" in self.environment:
                settings = self.environment["settings"].split(",")
            if "options" in self.environment:
                options = sself.environment["options"].split(",")
            conan.install(conanfilePath,
                    generators = ["scons"],
                    install_folder = buildDirectory,
                    options = options,
                    settings = settings,
                    build = [ "missing" ],
                    profile_names = [ profile ])
            data["modified"] = lastMod
            with open(self.path + "EnvMod.json", "w") as f:
                json.dump(data, f)

        conan = self.environment.SConscript(self.path + "SConscript_conan")

        self.environment.MergeFlags(conan["conan"])

    def withCompilationDB(self, output = ""):
        """
        @param output    Defines the output folder. Dumps into root if None.
        """

        if self.compiler == "clang":
            self.environment.Append(CXXFLAGS = [ "-MJ" + output + "compile_info.json" ])

    # Configuration utilities
    def configure(self):
        return utils.ConfigContext(self)

    def Clone(self):
        newEnv = ZEnv(self.environment.Clone(), self.path, self.debug, self.compiler,
                    self.argType)
        newEnv.sanitizers = self.sanitizers
        newEnv.libraries = self.libraries
        newEnv.compilerFlags = self.compilerFlags
        newEnv.variantDir = self.variantDir
        newEnv.stdlib = self.stdlib
        return newEnv

    def getEnvVar(self, key: str):
        return self.environment[key]

    def includeSysVars(self, *keys, **kwargs):
        if ("all" in kwargs and kwargs["all"] == True):
            for key, value in os.environ.items():
                self.environment["ENV"][key] = value;
            return;
        for key in keys:
            try:
                self.environment["ENV"][key] = os.environ[key]
            except:
                pass


# TODO: Implement cross compilation support
def determinePath(env, compiler, debug, crossCompile = False):
    """
    Determines the path for the build output.
    This is enabled to support multi-compiler attempts, and it's later
    meant to faciliate for cross-compilation, if I find a need to add it.
    """
    arch = platform.architecture()
    pf = env["PLATFORM"]
    path = f"{compiler}.{pf}.{arch[0]}."

    path += f"{'dbg' if debug == True else 'release'}/"
    return path

def normalizeCompilerName(name: str):
    """
    This function attempts to normalize compiler inputs (through CXX)
    into a uniform variant usable by the code.

    This risks breaking unknown compilers, which is an unfortunate side-effect,
    but it allows for the build code to run compatibility settings against
    the individual compilers.

    I'll rather add any other compilers here if necessary.
    """
    if (name.startswith("gcc") or name.startswith("g++")):
        return "gcc"
    elif name.startswith("clang") or name.startswith("clang++"):
        return "clang"
    elif name.startswith("msvc") or name == "cl":
        return "msvc"
    elif name.startswith("clang-cl"):
        return "clang-cl" # Silence the failure warning.
    print("WARNING: Unknown compiler detected ({}). Normalization failed. Usage of this compiler may have unintended side-effects.".format(name))
    return name

def getCompiler(env):
    """ Gets the compiler, along with its predicted type.
    Note that this makes an educated guess based on my knowledge of compilers.
    Any edge cases deviating from either of the two standards will need to be
    added explicitly, but that's something I'll need to do on a per-case basis.
    """

    # Check for system overrides.
    if (env["systemCompiler"] == True):
        cxxAttempt = os.getenv("CXX")
        ccAttempt = os.getenv("CC")

        if (cxxAttempt != None and cxxAttempt.strip() != ""): env["CXX"] = cxxAttempt
        if (ccAttempt != None and ccAttempt.strip() != ""): env["CC"] = ccAttempt
    # now, get the compiler
    it1 = env["CXX"]
    if (it1 == "$CC" or it1 == "cl"):
        # If the compiler equals $CC, then (my condolences,) you're running MSVC.
        # According to the docs, this should be the case.
        return ("msvc", CompilerType.MSVC_COMPATIBLE)

    # if the environment variable CXX is used, this may not be a single word.
    # A manual override (such as `clang++ -target x86_64-pc-windows-gnu` would break later detection as well).
    it2 = it1.split(" ", maxsplit=1)

    if (it2[0] == "clang-cl"):
        # clang-cl is still Clang, but takes MSVC-style input.
        return ("clang-cl", CompilerType.MSVC_COMPATIBLE)

    # For undefined cases, we'll assume it's a POSIX-compatible compiler.
    # (Note that this doesn't care what the target system is. This is just to detect the compiler being used,
    # and by extension which arguments to use)
    return (normalizeCompilerName(it2[0]), CompilerType.POSIX)


def getEnvironment(defaultDebug: bool = True, libraries: bool = True, stdlib: str = "c++17", useSan = True, customVariables = None):
    variables = Script.Variables()
    variables.AddVariables(
        BoolVariable("debug", "Build with the debug flag and reduced optimization.", True),
        BoolVariable("systemCompiler", "Whether to use CXX/CC from the environment variables.", True),
        ("profile", "Which profile to use for Conan, if Conan is enabled", "default"),
        ("settings", "Settings for Conan.", None),
        ("options", "Options for Conan", None),
        BoolVariable("coverage", "Adds the --coverage option", False)
    )

    if (customVariables != None):
        if (type(customVariables) is not list):
            raise RuntimeError("customVariables has to be a list");
        for variable in customVariables:
            variables.Add(variable)

    envVars = {
        "PATH": os.environ["PATH"]
    }
    if "TEMP" in os.environ:
        envVars["TEMP"] = os.environ["TEMP"]

    tools = []
    if "windows" in platform.platform().lower():
        if "CXX" in os.environ and os.environ["CXX"] in ["clang++", "g++"]:
            tools.append("mingw") # Preliminary MinGW mitigation
        else:
            tools = None;
    else: tools = None;
    env = Environment(variables = variables,
                      ENV = envVars, tools = tools)
    (compiler, argType) = getCompiler(env)
    print("Detected compiler: {}. Running debug: {}".format(compiler, env["debug"]))

    if "TERM" in os.environ:
        env["ENV"]["TERM"] = os.environ["TERM"]

    if (env["PLATFORM"] == "win32"
            and compiler != "clang-cl"
            and compiler != "msvc"):
        print("Forcing MinGW mode")
        # We also need to normalize the compiler afterwards.
        # MinGW forces GCC
        CXX = env["CXX"]
        CC = env["CC"]
        Tool("mingw")(env)
        env["CXX"] = CXX
        env["CC"] = CC

    path = "build/" + determinePath(env, compiler, env["debug"])

    compileFlags = ""

    if (argType == CompilerType.POSIX):
        compileFlags += "-std=" + stdlib + " -pedantic -Wall -Wextra -Wno-c++11-narrowing"
        if env["debug"] == True:
            compileFlags += " -g -O0 "
            if env["coverage"] == True:
                compileFlags += " -fprofile-arcs -ftest-coverage "
                env.Append(LINKFLAGS=["-lgcov", "-coverage"])

        else:
            compileFlags += " -O3 "
    else:

        # Note to self: /W4 and /Wall spews out warnings for dependencies. Roughly equivalent to -Wall -Wextra on stereoids
        compileFlags += "/std:" + stdlib + " /W3 /EHsc "
        if env["debug"] == True:
            env.Append(LINKFLAGS = ["/DEBUG"])
            env.Append(CPPFLAGS=["/MTd", "/Zi"])
        else:
            compileFlags += " /O2 "

    env.Append(CXXFLAGS = compileFlags)

    if env["debug"] == True and useSan:

        if argType == CompilerType.POSIX:
            env.Append(CPPFLAGS = ["-fsanitize=undefined"])

        zEnv = ZEnv(env, path, env["debug"], compiler, argType)

        if env["PLATFORM"] != "win32":
            env.Append(LINKFLAGS=["-fsanitize=undefined"])

        elif (compiler != "msvc"):
            print("WARNING: Windows detected. MinGW doesn't have libubsan. Using crash instead (-fsanitize-undefined-trap-on-error)")
            env.Append(CPPFLAGS = ["-fsanitize-undefined-trap-on-error"])
        return zEnv

    return ZEnv(env, path, env["debug"], compiler, argType)


