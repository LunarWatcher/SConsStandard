# Package reference

## Quirks

### Output paths

A major feature of SConsStandard is its use of paths. Specifically, it prefers creating output directories following a specific format: 

```
<project root directory>/build/<compiler>.<env["PLATFORM"]>.<platform.architecture()[0].<dbg/release>`
```

## Environment variables

Environment variables refers to system variables consumed by the wrapper.

### `CUSTOM_CONAN`
Type: path

Defines where Conan is. This is mainly useful if you [installed conan from source](https://docs.conan.io/en/latest/installation.html#install-from-source). Keep in mind that SConsStandard directly interfaces with the Conan API, so just adding a conan script isn't enough.

This is also fully compatible with virtualenvs if set up properly.

## SCons variables

SCons variables refers to variables managed by SCons, passed in as command line arguments in the format:
```
scons <other parameters> variable=value
```

### `profile`
Type: string

Defines what profile Conan should use to download packages. Equivalent to `conan install --profile <name>`

### `settings`
Type: string list (comma separated)

Defines what settings to pass to Conan. See [Conan's documentation][setopt]

### `options`
Type: string list (comma separated)

Defines what options to pass to Conan. See [Conan's documentation][setopt]

### `coverage`
Type: boolean

Defines whether or not to add `--coverage` to Clang/GCC. Not currently compatible with MSVC

### `systemCompiler`
Type: boolean

Whether or not to use CXX/CC from environment variables. If false, sources from SCons.

### `debug`
Type: boolean

Whether or not to build in debug mode. If debug isn't defined on the command line, it'll fall back to a default option. Unless otherwise specified when calling `getEnvironment()`, said default option will build a debug build.

## Classes

### `EnvMod.ZEnv`

Contains the core. This class wraps around SCons' own pre-built environment.

#### Functions

##### `Program(name: str, sources: list, **kwargs)`
Wraps around SCons' `env.Program`, but prepends `bin/` to the output path for the program. Note that the path is relative to the variant directory, if one is used.

##### `Library(name: str, sources: list, **kwargs)`
Wraps around SCons' `env.Library`. Like `Program`, it prepends `bin/` to the output path for the library. Note that the path is relative to the variant directory, if one is used.

##### `SharedLibrary(name: str, sources, **kwargs)`
Wraps around SCons' `env.SharedLibrary`. Prepends `bin/` to the output path for the shared library. Note that the path is relative to the variant directory, if one is used.

##### `StaticLibrary(name: str, sources, **kwargs)`
Wraps around SCons' `env.StaticLibrary`. Prepends `bin/` to the output path for the static library. Note that the path is relative to the variant directory, if one is used.

##### `VariantDir(target: str, source: str, **kwargs)`
Wraps around SCons' `env.VariantDir`. Its use is not recommended - using `SConscript` with the `variant_dir` parameter should be preferred.

##### `Glob(pattern: str, **kwargs)`

Wrapper around SCons' `env.Glob`. This doesn't add anything fancy to it - it just forwards the call directly. Note that this isn't recursive

##### `CGlob(sourceDir: str, pattern: str)`
Uses Python's `Path` to recursively glob paths. Its use is not recommended - it's unable to traverse SCons build tree of uncopied files.

##### `SConscript(script: str, variant_dir: str = None, **kwargs)`
Wraps around SCons' `env.SConscript`. Note that the `variant_dir` only needs to be a name; this wrapper takes care of the path. See: [Output paths](#output-paths). Additionally, there doesn't have to be a variant_dir supplied, but it's highly recommended. Building in the active tree is often a bad idea and shouldn't be done.

##### `withLibraries(libraries: list, append: bool = True)`

Adds libraries to SCons. If `libraries` isn't a list, it's forcibly converted to one.

If `append` is True, the function uses `self.environment.Append(LIBS = ...)`. Otherwise, it uses `self.environment.Prepend(LIBS = ...)`.

##### `getBinPath()`
Returns the binary path for the current environment.

##### `appendLibPath(libPath: str)`
Appends a lib path. Equivalent to adding `-L<path>` to the compiler, or calling SCons' `env.Append(LIBPATH= ["<path>"])`.

##### `appendSourcePath(sourcePath: str)`
Appends a source path to `CPPPATH`.

##### `withConan(options: list = [], settings: list = [])`

Enables conan support. Works with both `conanfile.py` and `conanfile.txt`.

This function uses the [`CUSTOM_CONAN`](#custom-conan) environment variable. This function uses the [`options`](#options) and [`#settings`](#settings) SCons variables. 

options: hard-coded options. Should be included in the conanfile instead of in the buildscript. Prefer the SCons variable for per-user configuration.

settings: hard-coded settings. Should be included in the conanfile instead of in the buildscript. Prefer the SCons variable for per-user configuration.

##### `withCompilationDB(output = "compile_commands.json")`
Requires: SCons 4.0.0

Wrapper around SCons' CompulationDatabase tool. 

##### `configure`

Returns a [`utils.ConfigContext`](#utils.configcontext).

##### `Clone(*args, **kwargs)`

Clones the environment. Note that the arguments passed to this function ONLY modifies SCons' environment, and not the ZEnv.

##### `getEnvVar`
Returns an environment variable

##### `includeSysVars(*keys, **kwargs)`


SCons "sandboxes" the variables. This means that if your tests or other programs you execute from SCons need specific environment variables, they'll be excluded. 

This method includes a select set of environment variables,
or all.

Usage for singular variables:

    includeSysVars("envVar1", "envVar2", ...)
Usage for all variables:

    includeSysVars(all=True)
Usage for all, but some excluded:

    includeSysVars("thisVarWillBeExcluded", "soWillThis", all=True)

Note that including all system variables may negatively affect SCons, and could potentially break the build.

##### `define(variable: str)`

Equivalent to SCons' `env.Append(CPPDEFINES = [ variable ])`

### [`utils.ConfigContext`]

#### Functions

##### `__enter__`

Used to enable `with` for the ConfigContext. Adds the built-in tests for `detectStdlib` and `detectFilesystem` (used for `<filesystem>`) to an instance of SCons' `Configure` class. Reading the [documentation on autoconf functionality in SCons](https://scons.org/doc/latest/HTML/scons-user.html#chap-sconf) is highly recommended.

##### `addTest(name: str, function)`
Adds a single test, but doesn't execute it. Equivalent to `config.AddTest(name, function)`.

##### `addTests(testMap)`
Adds multiple tests, and doesn't execute any. Equivalent to `config.AddTest(testMap)`.

`testMap` is a map of names and functions:
```python
testMap = { "testSomething": myMethod, "testSomethingElse": myOtherMethod }
```

##### `test(name: str, *args, **kwargs)`

Executes a test, or adds a new one and runs it.

To execute a test:

```python
test("testName")
```

To add a test:

```python
test("testName", callback = myFunction)
```

##### `configureFilesystem()`

Automatically configures `filesystem` based on the standard I use. This function also links the filesystem library, if the compiler needs it. Note that it throws an error if filesystem is unsupported, or the stdlib uses `<experimental/filesystem>` -- make your own function if you don't want this.

##### `__exit__(type, value, traceback)`

Required to enable `with` for the class. All it does is call `Finish()` on the underlaying `Configuration` class, as well as deleting it.

#### Examples

```python
from sys import platform

zEnv = getEnvironment()

# Note, in case you didn't read SCons' documentation: 
# all methods doing configure must take at least one argument; the context.
# Methods can also take additional args, which are passed without names to `config.test`:
#    config.test("multiArgFunction", "this string would get passed as the second argument", callback = func)
def checkSecure(context):
    """
    Checks whether secure_getenv is present or not
    """
    context.Message("Checking secure_getenv... ")

    secureProbe = """
    #define _GNU_SOURCE
    #include <stdlib.h>
    int main() {
        secure_getenv("fakeVar");
    }
    """

    compiled = context.TryCompile(secureProbe, ".cpp")

    context.Result("yes" if compiled else "no")
    return compiled

with env.configure() as config:
    config.test("CheckCXX")
    config.configureFilesystem()

    if platform != "win32":
        if config.test("CheckSecureGetEnv", callback=checkSecure):
            env.define("HAS_SECURE_GETENV")

```

[setopt]: https://docs.conan.io/en/latest/mastering/conditional.html
