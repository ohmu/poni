"""
automatically maintains the latest git tag + revision info in a python file

"""

import imp
import subprocess

def get_project_version(version_file):
    try:
        module = imp.load_source("verfile", version_file)
        file_ver = module.__version__
    except:
        file_ver = None

    try:
        proc = subprocess.Popen(["git", "describe"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        proc.stderr.close()
        git_ver = proc.stdout.readline().strip()
        if git_ver and ((git_ver != file_ver) or not file_ver):
            file(version_file, "wt").write("__version__ = '%s'\n" % git_ver)
            return git_ver
    except:
        pass

    if not file_ver:
        raise Exception("version not available from git or from file %r"
                        % version_file)

    return file_ver
