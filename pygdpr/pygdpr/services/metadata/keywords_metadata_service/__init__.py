import re
import nltk
nltk.download('averaged_perceptron_tagger')
nltk.download('wordnet')
#nltk.download('stopwords')
from nltk.corpus import stopwords
from nltk.stem.porter import PorterStemmer
from nltk.tokenize import RegexpTokenizer
#nltk.download('wordnet')
from nltk.stem.wordnet import WordNetLemmatizer
from sklearn.feature_extraction.text import CountVectorizer
from pygdpr.services.metadata_service import *

class KeywordsMetadataService(MetadataService):
    def for_text(self, text, preprocess=True, n_keywords=20, custom_stopwords=[]):
        _stopwords = set(stopwords.words("english")).union(custom_stopwords)
        text = re.sub('[^a-zA-Z]', ' ', text)
        text = text.lower()
        text = re.sub("&lt;/?.*?&gt;"," &lt;&gt; ", text)
        text = re.sub("(\\d|\\W)+", " ", text)
        text = text.split()
        lem = WordNetLemmatizer()
        text = [lem.lemmatize(word) for word in text if not word in _stopwords]
        tags = nltk.pos_tag(text)
        text = [word for word, pos in tags if (pos != 'RB')]
        corpus = ' '.join(text)
        vec = CountVectorizer(ngram_range=(1,3)).fit([corpus])
        bag_of_words = vec.transform([corpus])
        sum_words = bag_of_words.sum(axis=0)
        words_freq = [(word, sum_words[0, idx]) for word, idx in
                       vec.vocabulary_.items()]
        words_freq = sorted(words_freq, key = lambda x: x[1], reverse=True)
        language_code = 'en'
        return [{ "name": w, "language_code": language_code } for w, freq in words_freq[:n_keywords]]
