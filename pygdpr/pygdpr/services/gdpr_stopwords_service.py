import os
from collections import Counter
import json
from .dpa_stopwords_service import DPAStopwordsService

class GDPRStopwordsService():
    def __init__(self, path):
        self.path = path
        f = open(os.path.abspath("gdpr/assets/eu-members.json"), 'r')
        self.eu_members = json.load(f)
        f.close()

    def get(self, n=35, to_save=True):
        gdpr_stopwords = {}
        gdpr_counter = Counter()
        for code in self.eu_members.keys():
            dpa_stopwords = DPAStopwordsService(path=self.path).for_code(code, n=n, to_save=to_save)
            dpa_counter = Counter(dpa_stopwords)
            gdpr_counter = gdpr_counter + dpa_counter
        gdpr_stopwords = dict(gdpr_counter.most_common(n))
        if to_save:
            with open(os.path.abspath('gdpr/assets/gdpr-stopwords.txt'), 'w') as outfile:
                outfile.write('\n'.join(gdpr_stopwords.keys()))
            with open(os.path.abspath('gdpr/assets/gdpr-stopwords.json'), 'w') as outfile:
                json.dump(gdpr_stopwords, outfile, indent=4)
        return gdpr_stopwords
