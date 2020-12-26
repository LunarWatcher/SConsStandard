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


