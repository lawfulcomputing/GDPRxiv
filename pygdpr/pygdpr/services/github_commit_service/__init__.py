import os
import requests
import json

class GithubCommitService():
    def get_auth(self):
        username, password = os.environ['gh-username'], os.environ['gh-password']
        return username, password

    def get_repo(self):
        owner, name = os.environ['gh-owner'], os.environ['gh-name']
        return owner, name

    def latest_commit(self, params={}):
        owner, name = self.get_repo()
        url = f"https://api.github.com/repos/{owner}/{name}/commits"
        session = requests.Session()
        username, password = self.get_auth()
        session.auth = (username, password)
        response = session.get(url, params=params)
        status_code = response.status_code
        if status_code != 200:
            raise ValueError('Could not get Github commits')
        commits = response.json()
        latest = commits[0] if len(commits) > 0 else None
        return latest
