import os
import platform 
from enum import Enum 
from pathlib import Path

# SCons imports
import SCons
import SCons.Script as Script
from SCons.Script import Variables, BoolVariable, EnumVariable, Environment, Tool

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
        print(self.sourceFlags)

        self.sanitizers = []
        self.libraries = []
        self.compilerFlags = []

    def Program(self, name: str, sources, **kwargs):
        self.environment.Program("bin/" + name, sources, **kwargs)

    def Library(self, name: str, sources, variantSource = "", **kwargs):
        self.environment.Library(self.path + "bin/" + name, sources, **kwargs)

    def VariantDir(self, target: str, source: str, **kwargs):
        self.environment.VariantDir(target, source)
    
    def Glob(self, sourceDir, pattern = "**/*.cpp"):
        paths = []
        for path in Path(sourceDir).glob(pattern):
            paths.append(str(path))
        return paths

    def SConscript(self, script, variant_dir = None, **kwargs):
        if variant_dir is not None:
            # Patches the variant dir 
            variant_dir = self.path + variant_dir
        else:
            # Automatic variant detection
            r = script.rsplit("/", 1)
            if (len(r) == 2):
                variant_dir = self.path + r[0]
            else:
                variant_dir = self.path
        exports = {"env": self}
        if "exports" in kwargs:
            exports += kwargs["exports"]
        
        self.environment.SConscript(script, exports = exports, variant_dir = variant_dir, **kwargs)
    
    def withLibraries(self, libraries: list, append: bool = True):
        """
        Specifies libraries to link. Note that this should not be used for dependencies imported through conan,
        as those are set when the import is handled. 
        """
        if append:
            self.environment.Append(LIBS = libraries)
        else:
            self.environment.Prepend(LIBS = libraries)

    def getBinPath(self):
        """
        Utility method for cross-environment stuff, like for cases where you
        have a Program depending on a Library
        """
        return self.path + "bin/"

    def appendLibPath(self, libPath: str):
        if type(libPath) is not str:
            raise RuntimeError("You can only append strings, not " + str(type(libPath)))
        self.environment.Append(LIBPATH = [libPath])
        

# TODO: Implement cross compilation support
def determinePath(env, compiler, debug, crossCompile = False):
    arch = platform.architecture()
    pf = env["PLATFORM"]
    path = f"{compiler}.{pf}.{arch[0]}."

    path += f"{'dbg' if debug == True else 'release'}/" 
    return path

def normalizeCompilerName(name: str):
    if (name == "gcc" or name == "g++"):
        return "gcc"
    elif name == "clang" or name == "clang++":
        return "clang"
    elif name == "msvc" or name == "cl":
        return "msvc"
    elif name == "clang-cl":
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
    if (it1 == "$CC"):
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


def getEnvironment(defaultDebug: bool = True, libraries: bool = True, stdlib: str = "c++17", useSan = True):
    variables = Script.Variables()
    variables.AddVariables(
        BoolVariable("debug", "Build with the debug flag and reduced optimization.", True),
        BoolVariable("systemCompiler", "Whether to use CXX/CC from the environment variables.", True),

    )
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
            and compiler is not "clang-cl" 
            and compiler is not "msvc"):
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
        else:
            compileFlags += " -O3 "
    else:
        # Note to self: /W4 and /Wall spews out warnings for dependencies. Roughly equivalent to -Wall -Wextra on stereoids 
        compileFlags += "/std:" + stdlib + " /W3 "
        if env["debug"] == True:
            env.Append(LINKFLAGS = ["/DEBUG"])
        else:
            compileFlags += " /O2 "

    env.Append(CXXFLAGS = compileFlags)

    if env["debug"] == True:
        baseLibs = []
        if useSan and argType == CompilerType.POSIX:
            env.Append(CPPFLAGS = ["-fsanitize=undefined"])
            baseLibs = ["ubsan"]
            if env["PLATFORM"] != "win32":
                env.Append(CPPFLAGS = ["-fsanitize=memory"])
                baseLibs.append("msan")
        zEnv = ZEnv(env, path, env["debug"], compiler, argType)
        
        if env["PLATFORM"] != "win32":
            zEnv.withLibraries(baseLibs)
        else:
            print("WARNING: Windows detected. MinGW doesn't have libubsan. Using crash instead (-fsanitize-undefined-trap-on-error)")
            env.Append(CPPFLAGS = ["-fsanitize-undefined-trap-on-error"])
        return zEnv()

    return ZEnv(env, path, env["debug"], compiler, argType)


