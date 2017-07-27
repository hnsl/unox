## UPGRADE / BREAKING CHANGE!
With version 0.2 the layout of the repo has changed to merge the setuptools standard. This way pip install now is working, including homebrew.
If you have used the old repo layout in automation, you will need to either switch to homebrew / pip install ( both recommanded ) or change the src of your symlink to `src/unox/unox.py`. It does though not make a lot of sense still doing it the old way - it is not supported and will probably break in the future anyway.

## unox
Author: Hannes Landeholm <hannes.landeholm@gmail.com>

The Unison beta (2.48) comes with file system change monitoring (repeat = watch)
through an abstract `unison-fsmonitor` adapter that integrates with each respective
OS file update watch interface. This allows responsive dropbox like master-master sync
of files over SSH. The Unison beta comes with an adapter for Windows and Linux but
unfortunately lacks one for OS X.

This script implements the Unison fswatch protocol (see `/src/fswatch.ml`)
and is intended to be installed as `unison-fsmonitor` in the PATH in OS X. This is the
missing puzzle piece for repeat = watch support for Unison in in OS X.

### Installation via homebrew

    brew tap eugenmayer/dockersync
    brew install eugenmayer/dockersync/unox

### Manual installation:
```
git clone https://github.com/hnsl/unox
cd unox
pip install .
```

### License

Licence: MPLv2 (https://www.mozilla.org/MPL/2.0/)
