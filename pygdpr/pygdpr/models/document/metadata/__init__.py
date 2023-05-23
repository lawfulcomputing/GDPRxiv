from pygdpr.models.document.metadata.title import *
from pygdpr.models.document.metadata.summary import *

class Metadata(object):
    def __init__(self, titles, summaries, md5, release_date, release_year, release_month, source_url):
        self.titles = titles
        self.summaries = summaries
        self.md5 = md5
        self.release_date = release_date
        self.release_year = release_year
        self.release_month = release_month
        self.source_url = source_url
