#!/usr/bin/env python
#
# unox
#
# Author: Hannes Landeholm <hannes.landeholm@gmail.com>
#
# The Unison beta (2.48) comes with file system change monitoring (repeat = watch)
# through an abstract "unison-fsmonitor" adapter that integrates with each respective
# OS file update watch interface. This allows responsive dropbox like master-master sync
# of files over SSH. The Unison beta comes with an adapter for Windows and Linux but
# unfortunately lacks one for OS X.
#
# This script implements the Unison fswatch protocol (see /src/fswatch.ml)
# and is intended to be installed as unison-fsmonitor in the PATH in OS X. This is the
# missing puzzle piece for repeat = watch support for Unison in in OS X.
#
# Dependencies: pip install watchdog
#
# Licence: MPLv2 (https://www.mozilla.org/MPL/2.0/)

import sys
import os
import traceback
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import signal

# Import depending on python version
if sys.version_info.major < 3:
    from urllib import quote, unquote
else:
    from urllib.parse import quote, unquote


def sigint_handler(signal, frame):
    sys.exit(0)


signal.signal(signal.SIGINT, sigint_handler)

my_log_prefix = "[unox]"

_in_debug = "--debug" in sys.argv
_in_debug_plus = False

# Global watchdog observer.
observer = Observer()
observer.start()

# Dict of monitored replicas.
# Replica hash mapped to watchdog.observers.api.ObservedWatch objects.
replicas = {}

# Dict of pending replicas that are beeing waited on.
# Replica hash mapped to True if replica is pending.
pending_reps = {}

# Dict of triggered replicas.
# Replica hash mapped to recursive dict where keys are path tokens or True for pending leaf.
triggered_reps = {}


def format_exception(e):
    # Thanks for not bundling this function in the Python library Guido. *facepalm*
    exception_list = traceback.format_stack()
    exception_list = exception_list[:-2]
    exception_list.extend(traceback.format_tb(sys.exc_info()[2]))
    exception_list.extend(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
    exception_str = "Traceback (most recent call last):\n"
    exception_str += "".join(exception_list)
    exception_str = exception_str[:-1]
    return exception_str


def _debug_triggers():
    global pending_reps, triggered_reps
    if not _in_debug_plus:
        return
    wait_info = ""
    if len(pending_reps) > 0:
        wait_info = " | wait=" + str(pending_reps)
    sys.stderr.write(my_log_prefix + "[DEBUG+]: trig=" + str(triggered_reps) + wait_info + "\n")


def _debug(msg):
    sys.stderr.write(my_log_prefix + "[DEBUG]: " + msg.strip() + "\n")


def warn(msg):
    sys.stderr.write(my_log_prefix + "[WARN]: " + msg.strip() + "\n")


def sendCmd(cmd, args):
    raw_cmd = cmd
    for arg in args:
        raw_cmd += " " + quote(arg);
    if _in_debug: _debug("sendCmd: " + raw_cmd)
    sys.stdout.write(raw_cmd + "\n")


# Safely injects a command to send from non-receive context.
def injectCmd(cmd, args):
    sendCmd(cmd, args)
    sys.stdout.flush()


def sendAck():
    sendCmd("OK", [])


def sendError(msg):
    sendCmd("ERROR", [msg])
    os._exit(1)


def recvCmd():
    # We flush before stalling on read instead of
    # flushing every write for optimization purposes.
    sys.stdout.flush()
    try:
        line = sys.stdin.readline()
    except KeyboardInterrupt:
        sys.exit(0)

    if not line.endswith("\n"):
        # End of stream means we're done.
        if _in_debug: _debug("stdin closed, exiting")
        sys.exit(0)
    if _in_debug: _debug("recvCmd: " + line)
    # Parse cmd and args. Args are url encoded.
    words = line.strip().split(" ")
    args = []
    for word in words[1:]:
        args.append(unquote(word))
    return [words[0], args]


def pathTokenize(path):
    path_toks = []
    for path_tok in path.split("/"):
        if len(path_tok) > 0:
            path_toks.append(path_tok)
    return path_toks


def triggerReplica(replica, local_path_toks):
    global pending_reps, triggered_reps
    if replica in pending_reps:
        # Got event for pending replica, notify and reset wait.
        injectCmd("CHANGES", [replica])
        pending_reps = {}
    # Handle root.
    if len(local_path_toks) == 0:
        triggered_reps[replica] = True
        return
    elif not replica in triggered_reps:
        cur_lvl = {}
        triggered_reps[replica] = cur_lvl
    else:
        cur_lvl = triggered_reps[replica]
    # Iterate through branches.
    for branch_path_tok in local_path_toks[:len(local_path_toks) - 1]:
        if cur_lvl == True:
            return
        if not branch_path_tok in cur_lvl:
            new_lvl = {}
            cur_lvl[branch_path_tok] = new_lvl
        else:
            new_lvl = cur_lvl[branch_path_tok]
        cur_lvl = new_lvl
    # Handle leaf.
    if cur_lvl == True:
        return
    leaf_path_tok = local_path_toks[len(local_path_toks) - 1]
    cur_lvl[leaf_path_tok] = True
    _debug_triggers()


class Handler(FileSystemEventHandler):
    def __init__(self, fspath, replica):
        self.replica = replica
        self.fspath = fspath

    def dispatch(self, event):
        path = event.src_path
        try:
            if not path.startswith(self.fspath):
                return warn("unexpected file event at path [" + path + "] for [" + self.fspath + "]")
            local_path = path[len(self.fspath):]
            local_path_toks = pathTokenize(local_path)
            if _in_debug: _debug("replica:[" + self.replica + "] file event @[" + local_path + "] (" + path + ")")
            triggerReplica(self.replica, local_path_toks)
        except Exception as e:
            # Because python is a horrible language it has a special behavior for non-main threads that
            # fails to catch an exception. Instead of crashing the process, only the thread is destroyed.
            # We fix this with this catch all exception handler.
            sys.stderr.write(format_exception(e))
            sys.stderr.flush()
            os._exit(1)


# Starts monitoring of a replica.
def startReplicaMon(replica, fspath, path):
    global replicas, observer
    if not replica in replicas:
        # Ensure fspath has trailing slash.
        fspath = os.path.join(fspath, "")
        if _in_debug: _debug("start monitoring of replica [" + replica + "] [" + fspath + "]")
        try:
            # OS X has no interface for "file level" events. You would have to implement this manually in userspace,
            # and compare against a snapshot. This means there's no point in us doing it, better leave it to Unison.
            if _in_debug: _debug("replica:[" + replica + "] watching path [" + fspath + "]")
            handler = Handler(fspath, replica)
            watch = observer.schedule(handler, fspath, recursive=True)
        except Exception as e:
            sendError(str(e))
        replicas[replica] = {
            "watch": watch,
            "fspath": fspath
        }
    sendAck()
    while True:
        [cmd, args] = recvCmd();
        if cmd == "DIR":
            sendAck()
        elif cmd == "LINK":
            sendError("link following is not supported by unison-watchdog, please disable this option (-links)")
        elif cmd == "DONE":
            return
        else:
            sendError("unexpected cmd in replica start: " + cmd)


def reportRecursiveChanges(local_path, cur_lvl):
    if (cur_lvl == True):
        sendCmd("RECURSIVE", [local_path])
        return
    for path_tok, new_lvl in cur_lvl.items():
        reportRecursiveChanges(os.path.join(local_path, path_tok), new_lvl);


def main():
    global replicas, pending_reps, triggered_reps, _in_debug
    # Version handshake.
    sendCmd("VERSION", ["1"])
    [cmd, args] = recvCmd();
    if cmd != "VERSION":
        sendError("unexpected version cmd: " + cmd)
    [v_no] = args
    if v_no != "1":
        warn("unexpected version: " + v_no)
    # Start watch operation.
    _debug_triggers()
    while True:
        [cmd, args] = recvCmd();
        # Cancel pending waits when any other command is received.
        if cmd != "WAIT":
            pending_reps = {}
        # Check command.
        if cmd == "DEBUG":
            _in_debug = True
        elif cmd == "START":
            # Start observing replica.
            if len(args) >= 3:
                [replica, fspath, path] = args
            else:
                # No path, only monitoring fspath.
                [replica, fspath] = args
                path = ""
            startReplicaMon(replica, fspath, path)
        elif cmd == "WAIT":
            # Start waiting for another replica.
            [replica] = args
            if not replica in replicas:
                sendError("unknown replica: " + replica)
            if replica in triggered_reps:
                # Is pre-triggered replica.
                sendCmd("CHANGES", replica)
                pending_reps = {}
            else:
                pending_reps[replica] = True
            _debug_triggers()
        elif cmd == "CHANGES":
            # Get pending replicas.
            [replica] = args
            if not replica in replicas:
                sendError("unknown replica: " + replica)
            if replica in triggered_reps:
                reportRecursiveChanges("", triggered_reps[replica])
                del triggered_reps[replica]
            sendCmd("DONE", [])
            _debug_triggers()
        elif cmd == "RESET":
            # Stop observing replica.
            [replica] = args
            if not replica in replicas:
                warn("unknown replica: " + replica)
                continue
            watch = replicas[replica]["watch"]
            if watch is not None:
                observer.unschedule(watch)
            del replicas[replica]
            if replica in triggered_reps:
                del triggered_reps[replica]
            _debug_triggers()
        else:
            sendError("unexpected root cmd: " + cmd)


if __name__ == '__main__':
    try:
        main()
    finally:
        for replica in replicas:
            observer.unschedule(replicas[replica]["watch"])
        observer.stop()
        observer.join()
