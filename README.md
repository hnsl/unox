## unox

Author: Hannes Landeholm <hannes@jumpstarter.io>

The Unison beta (2.48) comes with file system change monitoring (repeat = watch)
through an abstract "unison-fsmonitor" adapter that integrates with each respective
OS file update watch interface. This allows responsive dropbox like master-master sync
of files over SSH. The Unison beta comes with an adapter for Windows and Linux but
unfortunately lacks one for OS X.

This script implements the Unison fswatch protocol (see `/src/fswatch.ml`)
and is intended to be installed as unison-fsmonitor in the PATH in OS X. This is the
missing puzzle piece for repeat = watch support for Unison in in OS X.

Dependencies: pip3 install macfsevents

Licence: MPLv2 (https://www.mozilla.org/MPL/2.0/)
