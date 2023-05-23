import os
import sys
import platform
from pygdpr.specifications.reachable_node_specification import ReachableNodeSpecification
from pygdpr.specifications.dpa_node_type_specification import DPANodeTypeSpecification
from pygdpr.services.github_issue_service import GithubIssueService
from pygdpr.services.markdown_formatting_service import MarkdownFormattingService
from pygdpr.services.py_line_inspector_service import PyLineInspectorService
from pygdpr.services.github_permalink_service import GithubPermalinkService
from pygdpr.services.github_commit_service import GithubCommitService

class ReportReachabilityIssueService:
    def get_title(self, dpa):
        country = dpa.country
        title = f"Unable to get docs from the DPA of {country}"
        return title

    def get_permalink(self, dpa):
        country = dpa.country
        github_commit = GithubCommitService()
        path = f"pygdpr/models/dpa/{country.lower()}/__init__.py"
        commit = github_commit.latest_commit(params={'path': path})
        if commit is None:
            return None
        py_line_inspector = PyLineInspectorService()
        lines = py_line_inspector.for_type_and_name(os.path.abspath(path), 'def', 'get_docs')
        github_permalink = GithubPermalinkService()
        permalink = github_permalink.generate(
            repo_owner=os.environ['gh-owner'],
            repo_name=os.environ['gh-name'],
            commit_id=commit['sha'],
            project_path=path,
            start_line=lines[0],
            end_line=lines[1]
        )
        return permalink

    def get_body(self, dpa):
        markdown_formatting = MarkdownFormattingService()
        print('permalink :: GITHUB')
        print(self.get_permalink(dpa))
        body = markdown_formatting.format_markdown(
            path=os.path.abspath('pygdpr/assets/gh-reachability-issue.md'),
            values=[
                ('host', 'https://wikileaks.org'),
                ('start_path', '/path'),
                ('country', dpa.country_code),
                ('major', sys.version_info.major),
                ('minor', sys.version_info.minor),
                ('micro', sys.version_info.micro),
                ('system', platform.system()),
                ('release', platform.release()),
                ('tests', 'Not written at the moment'),
                ('permalink', self.get_permalink(dpa))
            ],
            prefix='{{',
            suffix='}}'
        )
        return body

    def for_dpa_node_if_needed(self, dpa_node):
        dpa_node_type = DPANodeTypeSpecification()
        reachable_node = ReachableNodeSpecification()
        if dpa_node_type.is_satisfied_by(dpa_node) == False:
            raise ValueError("dpa_node argument is not of type 'DPANode'. Can only report a reachability issue for a dpa node")
        if reachable_node.is_satisfied_by(dpa_node):
            return None
        dpa = dpa_node.dpa
        github_issue = GithubIssueService()
        issue = None
        try:
            issue = github_issue.new_issue({
                "title": self.get_title(dpa),
                "body": self.get_body(dpa)
            })
        except:
            pass
        return issue
