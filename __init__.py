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
from . import ZEnv as ZEnvFile

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
        return ("msvc", ZEnvFile.CompilerType.MSVC_COMPATIBLE)

    # if the environment variable CXX is used, this may not be a single word.
    # A manual override (such as `clang++ -target x86_64-pc-windows-gnu` would break later detection as well).
    it2 = it1.split(" ", maxsplit=1)

    if (it2[0] == "clang-cl"):
        # clang-cl is still Clang, but takes MSVC-style input.
        return ("clang-cl", ZEnvFile.CompilerType.MSVC_COMPATIBLE)

    # For undefined cases, we'll assume it's a POSIX-compatible compiler.
    # (Note that this doesn't care what the target system is. This is just to detect the compiler being used,
    # and by extension which arguments to use)
    return (normalizeCompilerName(it2[0]), ZEnvFile.CompilerType.POSIX)


def getEnvironment(defaultDebug: bool = True, libraries: bool = True, stdlib: str = "c++17", useSan = True, customVariables = None):
    variables = Script.Variables()
    variables.AddVariables(
        BoolVariable("debug", "Build with the debug flag and reduced optimization.", os.getenv("LUNASCONS_DEBUG", "False").lower() in ["true", "1", "yes"]),
        BoolVariable("systemCompiler", "Whether to use CXX/CC from the environment variables.", True),
        ("profile", "Which profile to use for Conan, if Conan is enabled", "default"),
        ("settings", "Settings for Conan.", None),
        ("options", "Options for Conan", None),
        ("buildDir", "Build directory. Defaults to build/. This variable CANNOT be empty", "build/"),
        ("dynamic", "(Windows only!) Whether to use /MT or /MD. False for MT, true for MD", False),
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

    path = env["buildDir"]
    if (path == ""):
        raise RuntimeError("buildDir cannot be empty.")
    print("Building in {}".format(path))

    compileFlags = ""

    if (argType == ZEnvFile.CompilerType.POSIX):
        compileFlags += "-std=" + stdlib + " -pedantic -Wall -Wextra -Wno-c++11-narrowing"
        if env["debug"] == True:
            compileFlags += " -g -O0 "
            if env["coverage"] == True:
                compileFlags += " --coverage "
                env.Append(LINKFLAGS=["--coverage"])

        else:
            compileFlags += " -O3 "
    else:
        # Note to self: /W4 and /Wall spews out warnings for dependencies. Roughly equivalent to -Wall -Wextra on stereoids
        compileFlags += "/std:" + stdlib + " /W3 /EHsc /FS "
        if env["debug"] == True:
            env.Append(LINKFLAGS = ["/DEBUG"])
            env.Append(CXXFLAGS=["/MTd" if not env["dynamic"] else "MDd", "/Zi"])
        else:
            compileFlags += " /O2 " + ("/MT" if not env["dynamic"] else "/MD") + " "
    env.Append(CXXFLAGS = compileFlags.split(" "))

    zEnv = ZEnvFile.ZEnv(env, path, env["debug"], compiler, argType, variables)
    if env["debug"] == True and useSan:
        if argType == ZEnvFile.CompilerType.POSIX:
            zEnv.environment.Append(CXXFLAGS = ["-fsanitize=undefined"])

        if env["PLATFORM"] != "win32":
            zEnv.environment.Append(LINKFLAGS=["-fsanitize=undefined"])
        elif (compiler != "msvc"):
            print("WARNING: Windows detected. MinGW doesn't have libubsan. Using crash instead (-fsanitize-undefined-trap-on-error)")
            zEnv.environment.Append(CXXFLAGS = ["-fsanitize-undefined-trap-on-error"])
    return zEnv
