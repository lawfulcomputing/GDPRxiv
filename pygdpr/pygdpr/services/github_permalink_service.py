class GithubPermalinkService():
    def generate(self, repo_owner, repo_name, commit_id, project_path, start_line, end_line=None):
        lines = "L%d" % start_line
        if end_line is not None:
            lines += "-L%d" % end_line

        return f"https://github.com/{repo_owner}/{repo_name}/blob/{commit_id}/{project_path}#{lines}"
