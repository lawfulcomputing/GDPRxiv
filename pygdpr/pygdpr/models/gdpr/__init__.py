from pygdpr.models.common.eu_member import EUMember
from pygdpr.models.dpa.austria import Austria
from pygdpr.models.dpa.belgium import Belgium
from pygdpr.models.dpa.bulgaria import Bulgaria
from pygdpr.models.dpa.croatia import Croatia
from pygdpr.models.dpa.cyprus import Cyprus
from pygdpr.models.dpa.czech_republic import CzechRepublic
from pygdpr.models.dpa.denmark import Denmark
from pygdpr.models.dpa.estonia import Estonia
from pygdpr.models.dpa.finland import Finland
from pygdpr.models.dpa.france import France
from pygdpr.models.dpa.germany import Germany
from pygdpr.models.dpa.greece import Greece
from pygdpr.models.dpa.hungary import Hungary
from pygdpr.models.dpa.ireland import Ireland
from pygdpr.models.dpa.italy import Italy
from pygdpr.models.dpa.latvia import Latvia
from pygdpr.models.dpa.lithuania import Lithuania
from pygdpr.models.dpa.luxembourg import Luxembourg
from pygdpr.models.dpa.malta import Malta
from pygdpr.models.dpa.netherlands import Netherlands
from pygdpr.models.dpa.poland import Poland
from pygdpr.models.dpa.portugal import Portugal
from pygdpr.models.dpa.romania import Romania
from pygdpr.models.dpa.slovakia import Slovakia
from pygdpr.models.dpa.slovenia import Slovenia
from pygdpr.models.dpa.spain import Spain
from pygdpr.models.dpa.sweden import Sweden
from pygdpr.models.dpa.united_kingdom import UnitedKingdom
import numpy as np
import os
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import PCA
from sklearn.pipeline import Pipeline
from sklearn.cluster import KMeans
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
from imblearn.under_sampling import RandomUnderSampler
from imblearn.pipeline import make_pipeline as make_pipeline_imb
from imblearn.metrics import classification_report_imbalanced
from sklearn.model_selection import train_test_split # not sure if should keep this.
import sys
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn import metrics
from scipy.spatial.distance import cdist
from pygdpr.services.list_eu_members_service import ListEUMembersService
from pygdpr.policies.dpa_path_policy import DPAPathPolicy

class GDPR(object): # acts as a mediator/facade pattern :: find su:ku slides.
    """
    A class used to represent GDPR (General Data Protection Regulation).

    Attributes
    ----------
    path : str
        the path where the documents will be stored (default is os.cwd())

    Methods
    -------
    get_dpa(country_code)
        Returns an instance of a DPA corresponding to the country_code
    """
    def __init__(self, path=os.curdir):
        self.path = path

    def set_path(self):
        self.path = path

    def get_path(self):
        return self.path

    def get_dpa(self, country_code):
        """Returns an instance of a DPA corresponding to the country_code.

        Parameters
        ----------
        country_code : str
            The country code corresponding to a given country.

        Raises
        ------
        ValueError
            If country code parameter does not correspond to a valid EU Member state country.

        Returns
        -------
        DPA
            an instance of a DPA class corresponding to the country code
        """
        gdpr_path = self.get_path()
        dpa_path = DPAPathPolicy().extend_gdpr_path(gdpr_path, country_code)
        if country_code == EUMember.AUSTRIA.value:
            return Austria(dpa_path)
        elif country_code == EUMember.BELGIUM.value:
            return Belgium(dpa_path)
        elif country_code == EUMember.BULGARIA.value:
            return Bulgaria(dpa_path)
        elif country_code == EUMember.CROATIA.value:
            return Croatia(dpa_path)
        elif country_code == EUMember.CYPRUS.value:
            return Cyprus(dpa_path)
        elif country_code == EUMember.CZECH_REPUBLIC.value:
            return CzechRepublic(dpa_path)
        elif country_code == EUMember.DENMARK.value:
            return Denmark(dpa_path)
        elif country_code == EUMember.ESTONIA.value:
            return Estonia(dpa_path)
        elif country_code == EUMember.FINLAND.value:
            return Finland(dpa_path)
        elif country_code == EUMember.FRANCE.value:
            return France(dpa_path)
        elif country_code == EUMember.GREECE.value:
            return Greece(dpa_path)
        elif country_code == EUMember.HUNGARY.value:
            return Hungary(dpa_path)
        elif country_code == EUMember.IRELAND.value:
            return Ireland(dpa_path)
        elif country_code == EUMember.ITALY.value:
            return Italy(dpa_path)
        elif country_code == EUMember.LATVIA.value:
            return Latvia(dpa_path)
        elif country_code == EUMember.LITHUANIA.value:
            return Lithuania(dpa_path)
        elif country_code == EUMember.LUXEMBOURG.value:
            return Luxembourg(dpa_path)
        elif country_code == EUMember.MALTA.value:
            return Malta(dpa_path)
        elif country_code == EUMember.NETHERLANDS.value:
            return Netherlands(dpa_path)
        elif country_code == EUMember.POLAND.value:
            return Poland(dpa_path)
        elif country_code == EUMember.PORTUGAL.value:
            return Portugal(dpa_path)
        elif country_code == EUMember.ROMANIA.value:
            return Romania(dpa_path)
        elif country_code == EUMember.SLOVAKIA.value:
            return Slovakia(dpa_path)
        elif country_code == EUMember.SLOVENIA.value:
            return Slovenia(dpa_path)
        elif country_code == EUMember.SPAIN.value:
            return Spain(dpa_path)
        elif country_code == EUMember.SWEDEN.value:
            return Sweden(dpa_path)
        elif country_code == EUMember.GERMANY.value:
            return Germany(dpa_path)
        elif country_code == EUMember.UNITED_KINGDOM.value:
            return UnitedKingdom(dpa_path)
        else:
            raise ValueError(f"Could not instantiate instance of DPA for country_code: {country_code}")

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        list_eu_members = ListEUMembersService()
        eu_members = list_eu_members.get()
        for eu_member in eu_members:
            country_code = eu_member.value
            dpa = self.get_dpa(country_code)
            try:
                added_docs += dpa.get_docs(
                    existing_docs=existing_docs,
                    overwrite=overwrite,
                    to_print=to_print
                )
            except:
                pass
        return added_docs

    def translate_docs(self, target_languages, docs=[], overwrite=False, price_terminate_usd=0.0, quota_service=None, to_print=True):
        translated_docs = []
        list_eu_members = ListEUMembersService()
        eu_members = list_eu_members.get()
        for eu_member in eu_members:
            country_code = eu_member.value
            dpa = gdpr.get_dpa(country_code)
            translated_docs += dpa.translate_docs(
                target_languages,
                docs,
                overwrite,
                price_terminate_usd,
                quota_service,
                to_print
            )
        return translated_docs

    def classify_docs(self, docs=[], download_if_needed=True, to_print=True):
        print('Classifying docs...')
        f = open('gdpr/assets/gdpr-stopwords.txt', 'r')
        gdpr_stopwords = f.read().split('\n')
        f.close()
        stop_words = set(stopwords.words('english')).union(gdpr_stopwords)
        ps = PorterStemmer()
        tmp_X = []
        n_docs = 0
        for root, dirs, files in os.walk('../data/11-21-2019', topdown=True):
            split = root.split('/')
            if len(split) < 5:
                continue
            dochash = split[-1]
            country = split[-2]
            country = country.replace('-', ' ')
            country = country.capitalize()
            print('\tFor:', country)
            try:
                text_index = files.index('en.txt')
            except:
                continue
            f = open(root + '/' + files[text_index], 'r')
            document_text = f.read()
            f.close()
            words = nltk.word_tokenize(document_text)
            words = [w.lower() for w in words]
            words = [w for w in words if w.isalpha()]
            words = [w for w in words if w not in stop_words]
            words = [ps.stem(word) for word in words]
            # X = np.concatenate((X, np.array([[dochash, ' '.join(words)]])), axis=0)
            tmp_X.append([dochash, ' '.join(words)])
            n_docs += 1
        #if n_docs == 0 and download_if_needed:
        #    self.get_docs()
        #    self.classify_docs(docs, download_if_needed, to_print)
        X = np.array(tmp_X)
        assert n_docs > 0
        np.set_printoptions(threshold=sys.maxsize) # tmp for dev purposes.
        pipeline = Pipeline([
            ('vect', CountVectorizer()),
            ('tfidf', TfidfTransformer()),
        ])
        X_fit = pipeline.fit_transform(X[:,1]).todense()
        kmeans = KMeans(n_clusters=4, max_iter=1000, random_state=3425)
        labels = kmeans.fit_predict(X_fit)
        labels = np.column_stack((X[:,0], labels))
        if to_print:
            pca = PCA(n_components=2).fit(X_fit)
            centers2D = pca.transform(kmeans.cluster_centers_)
            data2D = pca.transform(X_fit)
            plt.plot()
            plt.title('Dataset')
            plt.scatter(data2D[:,0], data2D[:,1], c=kmeans.labels_.tolist())
            plt.scatter(centers2D[:,0], centers2D[:,1],
                        marker='x', s=200, linewidths=3, c='r')
            plt.show()
            # k means determine k
            distortions = []
            K = range(1,10)
            for k in K:
                kmeanModel = KMeans(n_clusters=k).fit(data2D) # on data2d instead?
                kmeanModel.fit(data2D)
                distortions.append(sum(np.min(cdist(data2D, kmeanModel.cluster_centers_, 'euclidean'), axis=1)) / data2D.shape[0])
            print(distortions)
            # Plot the elbow
            plt.plot(K, distortions, 'bx-')
            plt.xlabel('k')
            plt.ylabel('Distortion')
            plt.title('The Elbow Method showing the optimal k')
            plt.show()
        if len(docs) > 0:
            num_rows, num_cols = labels.shape[0], labels.shape[1]
            row_indices = []
            for i in range(num_rows):
                for j in range(num_cols):
                    if j == 0 and labels[i, j] in docs:
                        row_indices.append([i])
            assert len(row_indices) == len(docs)
            labels = labels[row_indices,:].reshape((len(docs), 2))
        return labels
