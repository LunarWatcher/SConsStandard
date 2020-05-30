import SCons
import SCons.SConf
import SCons.Script as Script

from SCons.Script import Configure
from SCons.SConf import CheckContext

import platform

def detectStdlib(context: CheckContext, zenv):
    context.Message("Detecting stdlib... ")
    if (zenv.stdlib):
        context.Result("Detected stdlib (cached): " + zenv.stdlib)
        return zenv.stdlib

    cisoProbe = """
    #include <ciso646>
    int main() {}
    """

    hasCiso = context.TryCompile(cisoProbe, ".cpp")
    if not hasCiso:
        raise RuntimeError("This is gonna get worse before it gets better... ciso646 isn't present")

    # TODO: scrap ciso646 in favor of #include<version>
    # ciso646 has been ditched in C++20. Because SCons itself
    # doesn't support C++20 yet, it's fine for the time being,
    # but it needs to be done Eventually:tm:
    libstdcppTest = """
    #include <ciso646>
    #ifndef __GLIBCXX__
    #error "not libstdc++"
    #endif
    int main() {}
    """
    libcppTest = """
    #include <ciso646>
    #ifndef _LIBCPP_VERSION
    #error "not libc++"
    #endif
    int main() {}
    """
    msvcTest = """
    #include <ciso646>
    #ifndef _MSVC_STL_VERSION
    #error "not MSVC stl"
    #endif
    int main() {}
    """
    isLibstdcpp = context.TryCompile(libstdcppTest, ".cpp")
    isLibcpp = context.TryCompile(libcppTest, ".cpp")
    isMsvc = context.TryCompile(msvcTest, ".cpp")

    if (isLibstdcpp):
        stdlib = "libstdc++"
    elif isLibcpp:
        stdlib = "libc++"
    elif isMsvc:
        stdlib = "msvc-stl"
    else:
        raise RuntimeError("Failed to detect stdlib.")

    zenv.stdlib = stdlib
    context.Result(stdlib)
    return stdlib

def detectFilesystem(context: CheckContext, zenv):
    context.Message("Detecting filesystem... ")
    """
    This function makes two assumptions in its check:
    1. You (the developer) handles the flags
    2. supporting experimental/filesystem is the same as not supporting filesystem

    Additional checks for whether the experimental variant is supported can be
    made manually, but these aren't supported out of the box, because it's a lot
    easier adding simple checks for now.

    returns: a tuple containing whether <filesystem> is supported,
    and whether it needs to link an additional library.
    """
    if not zenv.stdlib:
        detectStdlib(context, zenv);

    supportsFilesystem = False
    needsLink = False

    if (zenv.stdlib == "libstdc++"):
        # libstdc++ is relatively straight-forward.
        linkProbe = """
        #include <ciso646>
        #if defined(_GLIBCXX_RELEASE) && _GLIBCXX_RELEASE >= 9
        #error "Doesn't need linking"
        #endif
        int main() {}
        """
        canUseProbe = """
        #include <ciso646>
        #if !defined(_GLIBCXX_RELEASE) || _GLIBCXX_RELEASE < 8
        #error "Filesystem not supported"
        #endif
        int main() {}
        """
        needsLink = context.TryCompile(linkProbe, ".cpp")
        supportsFilesystem = context.TryCompile(canUseProbe, ".cpp")
    elif zenv.stdlib == "libc++":
        # libc requires an exception for mac:

        if (platform.system() == "Darwin"):
            # macOS
            # Apple Clang disallows linking the library.
            needsLink = False
        else:
            linkProbe = """
            #include <ciso646>
            #if _LIBCPP_VERSION >= 9000
            #error "libc++ 9 and up doesn't need linking"
            #endif
            int main() {}
            """
            needsLink = context.TryCompile(linkProbe, ".cpp")

        canUseProbe = """
        #include <ciso646>
        #if _LIBCPP_VERSION < 7000
        #error "Filesystem not supported"
        #endif
        #include <iostream>
        int main() {}
        """
        supportsFilesystem = context.TryCompile(canUseProbe, ".cpp")

    else:
        # MSVC (hopefully :x)
        # MSVC doesn't need linking at all, /shrug
        needsLink = False
        # It still has a support-based system, so support has to be probed:
        canUseProbe = """
        #include <ciso646>
        #if !defined(_MSVC_STL_UPDATE) || _MSVC_STL_UPDATE < 201803
        #error "Filesystem is not supported on MSVC STL before 15.7"
        #endif
        int main() {}
        """
        supportsFilesystem = context.TryCompile(canUseProbe, ".cpp")

    context.Result("Supports filesystem? {}. Needs to link a library? {}."
                   .format(supportsFilesystem, needsLink))

    return (supportsFilesystem, needsLink)

class ConfigContext:
    def __init__(self, zenv):
        self.zenv = zenv;

    def __enter__(self):
        print("Configuring...")
        self.config = Configure(self.zenv.environment)
        # This adds some pre-added tests
        self.config.AddTests({
            "detectStdlib": detectStdlib,
            "detectFilesystem": detectFilesystem
        });
        return self

    def addTest(self, name: str, function):
        self.config.AddTest(name, function)

    def addTests(self, testMap):
        self.config.AddTests(testMap)

    def test(self, name: str, *args, **kwargs):
        """
        This function either executes an existing test, or adds a new one
        with a supplied callback.
        The callback has to be a named argument, or the call being:
        test("myNewTest", callback = someFunction)
        """
        callback = None
        if "callback" in kwargs:
            callback = kwargs["callback"]
            del kwargs["callback"]

        # See if the callback can be set
        if callback is not None:
            self.config.AddTest(name, callback)
        # Finally, before running, make sure the test exists,
        # regardless of whether it was just added or not
        if not hasattr(self.config, name):
            raise RuntimeError("Test not registered: " + name)
        getattr(self.config, name)(*args, **kwargs)

    def configureFilesystem(self):
        """
        This method configures the filesystem based on my preferred standard.
        """
        self.config.detectStdlib(self.zenv)
        (supportsFilesystem, needsLink) = self.config.detectFilesystem(self.zenv)

        if not supportsFilesystem:
            raise RuntimeError("This build doesn't support filesystem")
        if (needsLink):
            if self.zenv.stdlib == "libstdc++":
                self.zenv.withLibraries(["stdc++fs"])
            else:
                # libc++
                # MSVC doesn't require linking in any configurations, so it's
                # the only other alternative
                self.zenv.withLibraries(["c++fs"])

    def __exit__(self, type, value, traceback):
        print("Configuration done")
        self.config.Finish()
        self.config = None
