from pygdpr.services.metadata_service import *
from pygdpr.specifications.absolute_date_specification import *
import dateparser
from dateparser.search import search_dates
import datetime
import nltk

class TimelineMetadataService(MetadataService):
    def for_text(self, text):
        timeline = []
        language_code = 'en'
        date_formats = ['%d-%m-%Y', '%d %B %Y']
        dateparser.date._DateLocaleParser._try_freshness_parser = lambda self: False
        sents = nltk.sent_tokenize(text)
        for s in sents:
            words = nltk.word_tokenize(s)
            words = [w.lower() for w in words]
            words = [w for w in words if w.isdigit() or w.isalpha()]
            try:
                matches = search_dates(s, languages=['en'], settings={
                    'STRICT_PARSING': True,
                    'PREFER_DATES_FROM': 'past'
                })
                if matches is None:
                    continue
                if len(matches) == 0:
                    continue
                for m in matches:
                    if AbsoluteDateSpecification().is_satisfied_by(m) is False:
                        continue
                    date = m[1]
                    date_str = datetime.datetime.strftime(date, '%d/%m/%Y')
                    event = {
                        'date': date_str,
                        'language_code': language_code,
                        'text': s
                    }
                    timeline.append(event)
            except:
                pass
        return timeline
