import nltk
import datetime
class AbsoluteDateSpecification():
    def day_is_present(self, words, date):
        return (
            date.strftime('%d') in words or\
            date.strftime('%-d') in words
        )
    def month_is_present(self, words, date):
        return (
            date.strftime('%b').lower() in words or\
            date.strftime('%B').lower() in words or\
            date.strftime('%m').lower() in words or\
            date.strftime('%-m').lower() in words
        )
    def year_is_present(self, words, date):
        return (
            date.strftime('%y') in words or\
            date.strftime('%Y') in words
        )
    def date_tokenize(self, words):
        tmp = []
        delimiters = ['-', '/']
        for w in words:
            dash_split = w.split('-')
            slash_split = w.split('/')
            if len(dash_split) > 1:
                tmp.extend(dash_split)
            elif len(slash_split) > 1:
                tmp.extend(slash_split)
            else:
                tmp.append(w)
        return tmp
    def is_satisfied_by(self, cand): # cand signature: (str, datetime)
        snippet, date = cand
        ws = nltk.word_tokenize(snippet)
        ws = [w.lower() for w in ws]
        ws = self.date_tokenize(ws)
        if len(ws) < 3:
            return False
        return (
            self.day_is_present(ws, date) and\
            self.month_is_present(ws, date) and\
            self.year_is_present(ws, date)
        )
