# Deprecation notice

SCons made it incredibly hard to use dynamic libraries for a (failed) project I had a few months ago (at the time of writing). Consequently, I've switched to CMake, and I find it easier to deal with for C and C++ in general.

As a consequence, this repo is now deprecated. Feel free to continue using it, or taking inspiration from it into your own SConstruct or default SCons implementation, but the project won't be receiving further patches.

# SCons Standard

This is my standard implementation of the basic components in a SConstruct. This is to save time and not have to re-write code every time I have a project. This will expand with new features as I stumble over a need for them, so it will not be a 100% perfect implementation for all cases. It's also based on my project standard. 

Note that this is still SCons, just with a bit of added code on top so I don't have to re-write all my code from scratch every time I start a project. SCons' own features have not been hidden - the modded environment has an `environment` field, which is a standard SCons environment.

# Usage

```
git submodule add git@github.com:LunarWatcher/SConsStandard.git
```

```python
# Imports the project.
# For full functionality, only import SConsStandard - don't import ZEnv.
# __init__.py contains several of the core wrapper functions that build
# basic library functionality, such as compiler detection and compiler flag 
# resolution.
import SConsStandard as scstd

# Envmod has a single method called getEnvironment. This handles all the preprocessing
# of the environment, including processing of variables.
env = scstd.getEnvironment()
# type(env) = ZEnv(), a wrapper around environment. Note that it's a wrapper, not a child class.
# For access to unimplemented behavior, `env.environment` returns the SCons.Script.Environment. 

# Create a program!  
env.SConscript("src/SConscript", duplicate = 0)
```

Where src/SConscript is a file at that location. This wrapper builds heavily on the use of SConscript files (because VariantDir was a complete pain in the ass to set up, and the entire thing is overall confusing).

# Compatibility

The first labeled release (v1.0.0) includes complete forwarding of methods. Any methods not present in ZEnv are forwarded to an SCons Environment are forwarded to the underlying (and exposed) `environment` object. This means the environment is now completely compatible with the standard Environment implementation.

Missing calls are forwarded due to a bit of SCons weirdness that prevents simple things like Program and SConscript from being included in the instance. I wasn't able to track down the reason behind this, so forwarding was the obvious option.

Note that the forwarding prioritizes the functions defined in ZEnv over the ones defined in Environment. If you need to use the default, unmodified methods, use `env.environment` (where env is a ZEnv).

This means you can use the fancy methods in your object, but also forward it to SConscript files and let other scripts use the primitive methods. This should theoretically not break stuff, but hasn't been tested on a large scale.
