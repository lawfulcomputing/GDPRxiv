import os
from pygdpr.models.document.text import *
from pygdpr.models.document.metadata import *

class Document(object):
    def __init__(self, text, metadata):
        self.text = text
        self.metadata = metadata

    def read(self, path):
        return None

    def write(self, path):
        return None
