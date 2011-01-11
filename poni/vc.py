from path import path

try:
    import git
    if git.__version__ < '0.3':
        git = None
except ImportError:
    git = None

GIT_IGNORE = """\
*~
*.pyc
"""

class VersionControl:
    def __init__(self, repo_dir):
        self.repo_dir = repo_dir


class GitVersionControl(VersionControl):
    def __init__(self, repo_dir, init=False):
        assert git, "GitPython not installed or too old."
        VersionControl.__init__(self, repo_dir)
        if init:
            self.init_repo(repo_dir)
        else:
            self.git = git.Repo(repo_dir)

        self.add = self.git.index.add
        self.commit = self.git.index.commit

    def init_repo(self, repo_dir):
        self.git = git.Repo.init(repo_dir)
        (repo_dir / ".gitignore").write_bytes(GIT_IGNORE)
        self.git.index.add([".gitignore"])
        self.commit_all("initial commit")

    def commit_all(self, message):
        #self.git.index.add(self.git.untracked_files)
        self.git.index.add(["*"])
        self.git.index.commit(message)

    def status(self):
        diff = self.git.git.diff()
        if diff:
            yield "Changes:\n"
            yield diff

        untracked = self.git.untracked_files
        if untracked:
            yield "\n\nUntracked files:\n"
            for file_path in untracked:
                yield "  %s\n" % file_path


def create_vc(repo_dir):
    if (path(repo_dir) / ".git").exists():
        return GitVersionControl(repo_dir)
    else:
        return None

