import os
import json
import time
from pygdpr.specifications.supported_dpa_specification import SupportedDPASpecification
from pygdpr.specifications.eu_member_specification import EUMemberSpecification
from pygdpr.services.translate_price_service import TranslatePriceService
from pygdpr.services.translate_quota_service import TranslateQuotaService
from pygdpr.specifications.root_document_specification import RootDocumentSpecification
from pygdpr.policies.translate_file_policy import TranslateFilePolicy
from pygdpr.specifications.price_terminate_translate_specification import PriceTerminateTranslateSpecification
from pygdpr.specifications.not_reached_daily_translate_quota_specification import NotReachedDailyTranslateQuotaSpec
from pygdpr.specifications.not_reached_100_secs_translate_quota_specification import NotReached100SecsTranslateQuotaSpec
from pygdpr.specifications.translate_document_specification import TranslateDocumentSpecification
from pygdpr.specifications.not_exists_file_language_specification import NotExistsFileLanguageSpecification
#from google.cloud import translate_v2 as translate
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter
from pygdpr.services.metadata.summary_metadata_service import *
from pygdpr.services.metadata.timeline_metadata_service import *
from pygdpr.services.metadata.citations_metadata_service import *
from pygdpr.services.metadata.citations_count_metadata_service import *
from pygdpr.services.metadata.keywords_metadata_service import *
from pygdpr.services.metadata.statistics_metadata_service import *
from pygdpr.services.metadata.est_read_time_metadata_service import *

nltk.download('punkt')
nltk.download('stopwords')
nltk.download('words')

supported_dpas = []
if os.path.isfile(os.path.abspath("pygdpr/assets/dpa-info.json")):
    with open(os.path.abspath("pygdpr/assets/dpa-info.json"), 'r') as f:
        supported_dpas = json.load(f)

class GoogleTranslatePriceError(Exception):
   """An exception class raised when the Google Translate price exceeds a predfined threshold (in usd)."""
   pass

class MaxRetriesError(Exception):
   """An exception class raised when maximum number of retries, trying to get docs, is exceeded."""
   pass

class DPA(object):
    """
    A class used to represent a DPA (Data Protection Authority).

    Attributes
    ----------
    country_code : str
        a two letter iso_code corresponding to a given country
    language_code : str
        a two letter iso_code referring to the written language 'preferred' by DPA
    name : str
        the official name of the DPA
    address : str
        formatted address string for the DPA
    phone : str
        formatted phone string for the DPA
    website : str
        official website of the DPA
    path : str
        the path where the documents, for this particular DPA, will be stored (default is os.cwd())
    translate_client : google.cloud.translate_v2.client.Client
        translate client for google-cloud-translate (see: https://googleapis.dev/python/translation/latest/client.html?highlight=client#module-google.cloud.translate_v2.client)

    Methods
    -------
    set_path(path)
        Sets the path to the given parameter. Stores documents at this path.
    set_translate_client(translate_client)
        Sets the translate_client to the given parameter. Client is used in :func:`~gdpr.dpa.DPA.translate_docs` to translate the DPA's documents at the specified path.
    get_docs(overwrite=False, to_print=True)
        Gets the documents for the DPA, stores them at the specified path and returns a list (md5 hashes) of documents added.
    translate_docs(target_languages, docs=[], overwrite=False, price_terminate_usd=0.0, quota_service=None, to_print=True)
        Translates the documents, located at the specified path, into the target languages and returns a list (md5 hashes) of documents translated.
    """
    def __init__(self, country_code, path):
        """
        Parameters
        ----------
        country_code : str
            The country_code for the country where the DPA has authority.
        """
        country_code = country_code.upper()
        if EUMemberSpecification().is_satisfied_by(country_code) is False:
            raise ValueError(f"Not found valid EU Member state for country code: {country_code}")
        if SupportedDPASpecification().is_satisfied_by(country_code) is False:
            raise ValueError(f"Not found supported DPA for country code: {country_code}")
        self.country_code = country_code
        dpa = supported_dpas[country_code]
        self.country = dpa['country']
        self.language_code = dpa['language_code']
        self.encoding = dpa['encoding'] if 'encoding' in dpa.keys() else None
        self.name = dpa['name']
        self.address = dpa['addressFormatted']
        self.phone = '({}) {}'.format(dpa['phone_code'], dpa['phone'])
        self.email = dpa['email']
        self.website = dpa['website']
        self.member = dpa['member']
        # Watch out for this path changing between users and the remote repo!!!
        self.path = path
        # self.path = '/Users/evanjacobs/Desktop/research_project/gdpr-sota/documents' + path
        # self.path = '/Users/chensun/PycharmProjects/gdpr-sota/documents' + path
        self.translate_client = None

    def set_path(self, path):
        self.path = path

    def set_translate_client(self, translate_client):
        self.translate_client = translate_client

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        """Updates and or creates a new pagination instance.

        Parameters
        ----------
        pagination : Pagination
            If pagination is None, a new pagination instance is created from scratch.
            Otherwise the pagination is updated with a new item.
        page_soup : Soup
            If page_soup is not None, this will be used to find and add the next item to the pagination.
        driver : Selenium
            If driver is not None, this will be used to find and add the next item to the pagination.

        Raises
        ------
        NotImplementedError
            If no subclass (ie. EU member state DPA) has implemented this method.

        Returns
        -------
        Pagination
            an updated pagination instance
        """
        raise NotImplementedError("'update_pagination' method not implemented.")

    def get_source(self, page_url=None, driver=None):
        """Returns a page source given either a page_url or a driver as input.

        Parameters
        ----------
        page_url : str
            If page_url is not None, this will be used to get the page source.
        driver : Selenium
            If driver is not None, this will be used to get the page source.

        Raises
        ------
        NotImplementedError
            If no subclass (ie. EU member state DPA) has implemented this method.

        Returns
        -------
        str
            a page source response from an html page.
        """
        raise NotImplementedError("'get_source' method not implemented.")

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        """Gets the documents for the DPA, stores them at the specified path and returns a list (md5 hashes) of documents added.

        Parameters
        ----------
        overwrite : bool
            If True, will overwrite the already existing documents at specified path.
            Otherwise will skip, if documents are already added.
        to_print : bool
            If True will print the progress of getting the documents.

        Raises
        ------
        NotImplementedError
            If no subclass (ie. EU member state DPA) has implemented this method.

        Returns
        -------
        [str]
            a list of documents (md5 hashes)
        """
        raise NotImplementedError("'get_docs' method not implemented.")

    def translate_docs(self, target_languages, docs=[], overwrite=False, price_terminate_usd=0.0, quota_service=None, to_print=True):
        """Translates the documents, located at the specified path, into the target languages and returns a list (md5 hashes) of documents translated.

        Parameters
        ----------
        target_languages : [str]
            A list of two letter iso_codes (language_codes) the documents will be translated into.
        docs : [str]
            A list of documents (md5 hashes) that needs to be translated. If list is empty it's assumed all documents at path should be translated.
        overwrite : bool
            If True, will overwrite the already existing documents at specified path.
            Otherwise will skip, if documents are already added.
        price_terminate_usd : float
            If price of translating the documents exceeds the price_terminate_usd parameter a GoogleTranslatePriceError will be raised.
            If price_terminate_usd is zero no GoogleTranslatePriceError will be raised.
        quota_service : TranslateQuotaService
            An instance of the TranslateQuotaService class which specifies the quota allowed for the google-cloud project with enabled google-cloud-translate api.
            If None is specified, default quota limits will be assumed. (See: https://cloud.google.com/translate/quotas)
        to_print : bool
            If True will print the progress of getting the documents.

        Returns
        -------
        [str]
            a list of translated documents (md5 hashes)
        """
        translated_docs = []
        target_languages = list(set(target_languages).difference(self.language_code))
        if self.translate_client is None:
            self.translate_client = translate.Client()
        price_service = TranslatePriceService()
        if quota_service is None:
            quota_service = TranslateQuotaService()
        agg_price = 0.0
        agg_quota = 0
        time_window_secs = 100
        for root,dirs,files in os.walk(self.path, topdown=True):
            if list(filter(lambda x: x.endswith('.txt'), files)) == 0:
                continue
            time.sleep(3)
            doc = root.split('/')[-1]
            if to_print and len(doc) > 0:
                print("Translating document:\t", doc)
                if doc in docs:
                    print("Progress:", docs.index(doc)/float(len(docs)))
            """if RootDocumentSpecification(root).is_satisfied_by(doc) is False:
                continue"""
            if TranslateDocumentSpecification(docs).is_satisfied_by(doc) is False:
                continue
            file_languages = list(filter(lambda x: len(x) == 2, [x.split('.')[0] for x in files]))
            for name in files:
                if TranslateFilePolicy().is_allowed(name) is False:
                    continue
                if PriceTerminateTranslateSpecification(price_terminate_usd).is_satisfied_by(agg_price):
                    raise GoogleTranslatePriceError(f"Estimated price of Google Translate exceeded value of {price_terminate_usd}.")
                with open(root + '/' + name, 'r', encoding='utf-8') as f:
                    document_text = f.read()
                    next_quota = agg_quota + len(document_text)
                    #if NotReachedDailyTranslateQuotaSpec(quota_service).is_satisfied_by(next_quota):
                    #    raise ValueError('Reached characters per day: %d. Please wait 24 hours until making another request.', agg_quota)
                    if NotReached100SecsTranslateQuotaSpec(quota_service).is_satisfied_by(next_quota):
                        if to_print:
                            print('Reached characters per 100 seconds per project per user: %d. sleeping %d secs before making next request.' % (agg_quota, time_window_secs))
                        time.sleep(time_window_secs+5)
                        agg_quota = 0
                    for target_language in target_languages:
                        if overwrite == True or\
                           NotExistsFileLanguageSpecification(file_languages).is_satisfied_by(target_language) == False:
                            continue
                        response = None
                        try:
                            # https://googleapis.dev/python/translation/latest/client.html
                            response = self.translate_client.translate(
                                document_text,
                                target_language=target_language,
                                format_='text' # text or html?
                            )
                        except:
                            if to_print:
                                print('Could not translate:\t', doc)
                            pass
                        if response is None:
                            continue
                        translated_text = response['translatedText']
                        with open(root + '/' + target_language + '.txt', 'w') as f:
                            f.write(translated_text)
                        agg_price += price_service.price_for_text(document_text)
                        agg_quota += len(document_text)
                        translated_docs.append(doc)
                        if to_print:
                            print('Translated:\t', doc)
                            print('\tFile:\t', name)
                            print('\tPrice:\t', agg_price)
        return translated_docs

    def extract_metadata(self, pipeline=[
        ('summary', SummaryMetadataService()),
        ('timeline', TimelineMetadataService()),
        ('citations', CitationsMetadataService()),
        ('citationsCount', CitationsCountMetadataService()),
        ('keywords', KeywordsMetadataService()),
        ('statistics', StatisticsMetadataService())
    ], docs=[], to_print=True):
        """Extracts the metadata from the documents.

        Parameters
        ----------
        pipeline : [tuple]
            A list of tuples where:
            First value in the tuple is a key of the metadata json file.
            Second value in the tuple is a value computed from the MetadataService method for_text
        docs : [str]
            A list of documents (md5 hashes) that requires metadata extraction. If list is empty it's assumed all documents at path should be translated.
        to_print : bool
            If True will print the progress of getting the documents.

        Returns
        -------
        [str]
            a list of documents (md5 hashes)
        """
        extracted_metadata = []
        for root, dirs, files in os.walk(self.path, topdown=True):
            print(root, dirs, files)
            split = root.split('/')
            if len(split) <= 4:
                continue
            country = split[-2]
            country = country.replace('-', ' ')
            country = ' '.join([word.capitalize() for word in country.split(' ')])
            if country != self.country:
                continue
            if 'en.txt' not in files:
                continue
            if 'metadata.json' not in files:
                continue
            if to_print:
                print('Country:\t', country)
            document_hash = split[-1]
            if document_hash not in docs:
                continue
            if to_print:
                print('Extracting metadata for:\t', document_hash)
            f = open(root + '/' + 'metadata.json', 'r')
            metadata = json.load(f)
            f.close()
            f = open(root + '/' + 'en.txt')
            document_text = f.read()
            f.close()
            for key, meta_service in pipeline:
                metadata[key] = meta_service.for_text(document_text)
            f = open(root + '/' + 'metadata.json', 'w')
            json.dump(metadata, f, indent=4, sort_keys=True)
            f.close()
            extracted_metadata.append(document_hash)
        return extracted_metadata
