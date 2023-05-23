import os

class DefaultGDPRPathPolicy:
    def get(self):
        gdpr_path = os.path.abspath('/tmp/gpdr')
        return gdpr_path
