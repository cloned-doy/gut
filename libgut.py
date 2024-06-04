import argparse
import collections
import configparser
import hashlib

from datetime import datetime
from fnmatch import fnmatch
from math import ceil

import grp, pwd, os, re, sys
import zlib

argparser = argparse.ArgumentParser(description="The stupidest content tracker")
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True

def main(argv=sys.argv[1:]):
	args = argparser.parse_args(argv)
	match args.command:
		case "hello"	: cmd_hello(args)
		case "init"		: cmd_init(args)
		case _ 			: print("Good enough. try again")

	"""the hell gate"""
	print("hello world")

class GitRepository(object):
	"""create a git repository"""

	worktree = None
	gitdir = None
	conf = None

	def __init__(self, path, force=False):
		self.worktree = path
		self.gitdir = os.path.join(path, ".git")

		if not (force or os.path.isdir(self.gitdir)):
			raise Exception("Not a git gut repository %s" % path)

		# read .git/config
		self.conf = configparser.ConfigParser()
		cf = repo_file(self, "config", True)

		if cf and os.path.exists(cf):
			self.conf.read([cf])
		elif not force:
			raise Exception("configuration file missing")

		if not force:
			vers = int(self.conf.get("core", "repositoryformatversion"))
			if vers != 0:
				raise Exception("unsupported repositoryformatversion %s" % vers)


def repo_path(repo, *path):
	"""compute path under repo's gitdir."""
	return os.path.join(repo.gitdir, *path)

def repo_file(repo, *path, mkdir=False):
    """same as repo_path, but create dirname(*path) if absent.
    for example, repo_file(r, /"refs", /"remotes", /"origin") will create
    .git/refs/remotes/origin."""	

    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)


def repo_dir(repo, *path, mkdir=False):
    """same as repo_path, but mkdir *path if absent if mkdir"""

    path = repo_path(repo, *path)

    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path
        else:
            raise Exception("not a directory %s" % path)

    if mkdir:
        os.makedirs(path)
        return path 
    else:
        return None


def repo_create(path):
	"""create a new repository at path"""

	repo = GitRepository(path, True)

	# first we make sure the path is either doesnt exist or is an empty dir

	if os.path.exists(repo.worktree):
		if not os.path.isdir(repo.worktree):
			raise Exception("%s is not a directory!" %path)
		if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
			raise Exception("%s is not empty!" % path)

	else:
		os.makedirs(repo.worktree)

	assert repo_dir(repo, "branches", mkdir=True)
	assert repo_dir(repo, "objects", mkdir=True)
	assert repo_dir(repo, "refs", "tags", mkdir=True)
	assert repo_dir(repo, "refs", "heads", mkdir=True)

	# .git/descripation
	with open(repo_file(repo, "description"), "w") as f:
		f.write("Unnamed repository; edit this file 'description' to name the repository.\n")

	# .git/HEAD
	with open(repo_file(repo, "HEAD"), "w") as f:
		f.write("ref: refs/heads/master\n")


	with open(repo_file(repo, "config"), "w") as f:
		config = repo_default_config()
		config.write(f)

	return repo 

def repo_default_config():
	ret = configparser.ConfigParser()

	ret.add_section("core")
	ret.set("core", "repositoryformatversion", "0")
	ret.set("core", "filemode", "false")
	ret.set("core", "bare", "false")

	return ret

argsp = argsubparsers.add_parser("init", help="Initialize a new, empty repository.")
argsp.add_argument("path",
                   metavar="directory",
                   nargs="?",
                   default=".",
                   help="Where to create the repository.")

def cmd_init(args):
    repo_create(args.path)


def repo_find(path=".", required=True):
    path = os.path.realpath(path)

    if os.path.isdir(os.path.join(path, ".git")):
        return GitRepository(path)

    # if we havent returned, recurse in parent, if w
    parent = os.path.realpath(os.path.join(path, ".."))

    if parent == path:
        # bottom case
        # os.path.join("/", "..") == "/":
        # if parent==path, then path is root
        if required:
            raise Exception("No git directory.")
        else:
            return None

    # recursive case
    return repo_find(parent, required)


class GitObject(object):
    def __init__(self, data=None):
        if data != None:
            self.deserialize()
        else:
            self.init()

    def serialize(self, repo):
        """This function MUST be implemented by subclasses.
        It must read the object's contents from self.data, a byte string, and do
        whatever it takes to convert it into a meaningful representation.  What exactly that means depend on each subclass."""
        raise Exception("Unimplemented!")

    def deserialize(self, data):
        raise Exception("Unimplemented!")

    def init(self):
        pass 

def object_read(repo, sha):
    """read object sha from git repository repo. 
    return a gitobject whose exact type depends on
    the object."""
    path = repo_file(repo, "objects", sha[0:2], sha[2:])

    if not os.path.isfile(path):
        return None

    with open(path, "rb") as f:
        raw = zlib.decompress(f.read())

    # read object type
    x = raw.find(b' ') #(b' ')
    fmt = raw[0:x]

    # read and validate object size
    y = raw.find(b'\x00', x)
    size = int(raw[x:y].decode("ascii"))
    if size != len(raw)-y-1:
        raise Exception("malformed object {0}: bad lenght".format(sha))

    match fmt:
        case b'commit'  : c=GitCommit
        case b'tree'    : c=GitTree
        case b'tag'     : c=GitTag
        case b'blob'    : c=GitBlob
        case _          :
            raise Exception("Unknown type {0} for object {1}".format(fmt.decode("ascii"), sha))

    # call constructor and return object 
    return c(raw[y+1:])

def object_write(obj, repo=None):
    # serialize object data
    data = obj.serialize()
    # add header
    result = obj.fmt + b' ' + str(len(data)).encode() + b'\x00' + data 
    # compute hash
    sha = hashlib.sha1(result).hexdigest()

    if repo:
        # compute path
        path=repo_file(repo, "objects", sha[0:2], sha[2:0], mkdir=True)

        if not os.path.exists(path):
            with open(path, 'wb') as f:
                # compress and write
                f.write(zlib.compress(result))

    return sha


class GitBlob(GitObject):
    fmt=b'blob'

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data     