# SCons Standard

This is my standard implementation of the basic components in a SConstruct. This is to save time and not have to re-write code every time I have a project. This will expand with new features as I stumble over a need for them, so it will not be a 100% perfect implementation for all cases. It's also based on my project standard. 

# Usage

```
git submodule add git@github.com:LunarWatcher/SConsStandard.git
```

```python
# Imports the EnvMod file. 
import SConsStandard.EnvMod

# Envmod has a single method called getEnvironment. This handles all the preprocessing
# of the environment, including processing of variables.
env = EnvMod.getEnvironment()
# type(env) = ZEnv(), a wrapper around environment. Note that it's a wrapper, not a child class.
# For access to unimplemented behavior, `env.env` returns the SCons.Script.Environment. 

# Create a program!  
env.SConscript("src/SConscript", duplicate = 0)
```

Where src/SConscript is a file at that location. This wrapper builds heavily on the use of SConscript files (because VariantDir was a complete pain in the ass to set up, and the entire thing is overall confusing).


