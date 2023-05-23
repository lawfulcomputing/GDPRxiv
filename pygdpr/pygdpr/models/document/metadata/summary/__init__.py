from pygdpr.models.document.text import *

class Summary(Text):
    def __init__(self, language_code, text):
        super().__init__(language_code, text)
