from path import path
import git

class VersionControl:
    def __init__(self, repo_dir):
        self.repo_dir = repo_dir


class GitVersionControl(VersionControl):
    def __init__(self, repo_dir, init=False):
        VersionControl.__init__(self, repo_dir)
        if init:
            self.git = git.Repo.init(repo_dir)
            self.commit_all("initial commit")
        else:
            self.git = git.Repo(repo_dir)

        self.add = self.git.index.add
        self.commit = self.git.index.commit

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

