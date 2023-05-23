import os
import json
import requests

class GithubIssueService:
    def get_auth(self):
        username, password = os.environ['gh-username'], os.environ['gh-password']
        return username, password

    def get_repo(self):
        owner, name = os.environ['gh-owner'], os.environ['gh-name']
        return owner, name

    def new_issue(self, content):
        session = requests.Session()
        username, password = self.get_auth()
        session.auth = (username, password)
        issue = {
            'title': content['title'],
            'body': content['body'] if 'body' in content else None,
            'milestone': content['milestone'] if 'milestone' in content else None,
            'labels': content['labels'] if 'labels' in content else [],
            'assignees': content['assignees'] if 'assignees' in content else []
        }
        print(json.dumps(issue))
        owner, name = self.get_repo()
        url = f"https://api.github.com/repos/{owner}/{name}/issues"
        response = session.post(url, json.dumps(issue))
        status_code = response.status_code
        print(status_code)
        if status_code != 201:
            raise ValueError('Could not create Github Issue with title: "%s"' % content['title'])
        return issue
