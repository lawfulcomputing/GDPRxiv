from pygdpr.models.document.text import *

class Title(Text):
    def __init__(self, language_code, text):
        super().__init__(language_code, text)
