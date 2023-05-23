import os
import json
import math
import nltk
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from collections import Counter
from .preprocess_words_service import PreprocessWordsService

class DPAStopwordsService():
    def __init__(self, path):
        self.path = path
        f = open(os.path.abspath("gdpr/assets/eu-members.json"), 'r')
        self.eu_members = json.load(f)
        f.close()

    def lookup_code(self, name):
        name = name.lower().replace(' ', '-')
        code = None
        for cand_code, cand_name in self.eu_members.items():
            if name == cand_name.lower().replace(' ', '-'):
                code = cand_code.lower()
                break
        if code is None:
            raise ValueError('Country code for country with name \'%s\' not found.' % name)
        return code

    def for_code(self, country_code, n=35, to_save=True):
        # precondition on self.path
        country_code = country_code.lower()
        lemmatizer = WordNetLemmatizer()
        tmp_word_count_docs, word_occ_docs, num_docs = {}, {}, {}
        for root, dirs, files in os.walk(self.path, topdown=True):
            split = root.split('/')
            if len(split) < 5:
                continue
            if len(split) == 5 and country_code != self.lookup_code(split[-2]):
                continue
            country_code_ = self.lookup_code(split[-2])
            country_code_ = country_code_.lower()
            if country_code_ not in tmp_word_count_docs.keys():
                tmp_word_count_docs[country_code_] = []
                word_occ_docs[country_code_] = {}
                num_docs[country_code_] = 0
            text_index = -1
            try:
                text_index = files.index('en.txt')
            except:
                pass
            if text_index == -1:
                continue
            f = open(root + '/' + files[text_index], 'r')
            text = f.read()
            f.close()
            words = word_tokenize(text)
            words = PreprocessWordsService().for_words(words)
            words = [lemmatizer.lemmatize(w) for w in words]
            tmp_word_count_docs[country_code_].extend(words)
            for w in set(words):
                if w not in word_occ_docs[country_code_].keys():
                    word_occ_docs[country_code_][w] = 1
                else:
                    word_occ_docs[country_code_][w] += 1
            num_docs[country_code_] += 1
        if bool(tmp_word_count_docs) is False:
            return {}
        word_count_docs = {}
        for country_code_ in tmp_word_count_docs.keys():
            country_code_ = country_code_.lower()
            x_min, x_max = 1, num_docs[country_code_]
            norm_word_occ_docs = {country_code_: {}}
            for k, v in word_occ_docs[country_code_].items():
                norm_word_occ_docs[country_code_][k] = (v - x_min) / (x_max - x_min)
            word_count_docs[country_code_] = {}
            for k, v in Counter(tmp_word_count_docs[country_code_]).items():
                word_count_docs[country_code_][k] = math.floor(
                    v * norm_word_occ_docs[country_code_][k]
                )
        stopwords = {}
        for k,v in word_count_docs.items():
            dpa_counter = Counter(v)
            dpa_counter += Counter()
            stopwords[k] = dict(dpa_counter.most_common(n))
            """pareto_princ = 0.8
            n = num_docs[k] - (math.ceil(num_docs[k] * (1.0-pareto_princ)))
            if n == 0:
                stopwords[k] = dict(Counter(v).most_common(5))
            else:
                #for w, freq in Counter(v).items():
                    #if freq >= n:
                    #    stopwords[k][w] = freq
                for w in sorted(dpa_counter, key=dpa_counter.get, reverse=True):
                    freq = dpa_counter[w]
                    if freq < n:
                        break
                    stopwords[k][w] = freq"""
        if to_save:
            filename = "dpa-stopwords.json"
            f = open(os.path.abspath("gdpr/assets/" + filename), 'r')
            dpa_stopwords = json.load(f)
            f.close()
            dpa_stopwords.update(stopwords)
            with open(os.path.abspath("gdpr/assets/" + filename), 'w') as outfile:
                json.dump(dpa_stopwords, outfile, indent=4, sort_keys=False)
        return stopwords[country_code]
