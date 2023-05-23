import os
import math
import requests
import json
import datetime
import hashlib
import dateparser
import re
import csv

from ... import DPA

from bs4 import BeautifulSoup

from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService

from pygdpr.specifications import pdf_file_extension_specification

from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification

from pygdpr.models.common.pagination import Pagination

from pygdpr.policies.gdpr_policy import GDPRPolicy

import textract
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy
import time

class Thuringia(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_new(existing_docs=[], overwrite=False, to_print=True, path=path)
        added_docs += self.get_docs_archive(existing_docs=[], overwrite=False, to_print=True, path=path)

        return added_docs

    def get_docs_archive(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print('========Press Archive===================')
        iterator = 1

        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name

        source = {
            "host": "https://www.tlfdi.de",
            "start_path": "/presse/pressearchiv/"
        }

        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        print('page_url:', page_url)

        language_code = 'de'
        existed_docs = []
        results_response = requests.request('GET', page_url)

        results_content = results_response.content
        results_soup = BeautifulSoup(results_content, 'html.parser')
        # print("results_soup: ", results_soup)
        list_view = results_soup.find('div', class_='news-list-view')
        if list_view is None:
            return existed_docs
        list = list_view.find('div', class_='news-list')
        host = 'https://www.tlfdi.de'
        for group in list.find_all('div', role='group'):
            for item in group.find_all('div', role='listitem'):
                time.sleep(2)
                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1

                document_section = item.find('div', class_='item-inner')

                document_title = document_section.find('a', class_='headline').get_text().strip()
                print('document_title: ', document_title)
                document_href = document_section.find('a', class_='headline').get('href')
                document_url = host + document_href

                # ex: 18.10.2019
                print('\tdocument_url: ', document_url)
                footer = document_section.find('div', class_='footer')
                date_str = footer.find('p').get_text().strip()
                print('\tdate_str: ', date_str)
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tBefore GDPR adopted, stop.")
                    return existed_docs
                if document_url == (host + '/'):
                    print('\tDocument not exist, continue')
                    continue

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print("\tdocument_hash:\t", document_hash)
                try:
                    document_response = requests.request('GET', document_url)
                    document_content = document_response.content
                    document_soup = BeautifulSoup(document_content, 'html.parser')
                    teaser_text = document_soup.find('div', class_='article')
                    article_href = teaser_text.find('a').get('href')
                    if article_href.startswith('http'):
                        article_url = article_href
                    else:
                        article_url = host + article_href
                    if article_href.endswith('.png'):
                        print('\tThis a an image, continue')
                        continue
                    print('\tarticle_url: ', article_url)

                    dpa_folder = path
                    dirpath = dpa_folder + '/' + 'thuringia' + '/' + document_hash
                    # dirpath = root_path + '/' + 'thuringia' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        article_response = requests.request('GET', article_url)
                        article_content = article_response.content
                        if not article_url.endswith('.pdf'):
                            article_soup = BeautifulSoup(article_content, 'html.parser')
                            text = article_soup.find('div', id='content')
                            if text is None:
                                print('\tSomething went wrong getting document.')
                                continue
                            article_text = text.get_text()
                            with open(dirpath + '/' + language_code + '.txt', 'w') as f:
                                f.write(article_text)
                        else:
                            with open(dirpath + '/' + language_code + '.pdf', 'wb') as f:
                                f.write(article_content)

                            article_text = textract.process(
                                dirpath + '/' + language_code + '.pdf')
                            with open(dirpath + '/' + language_code + '.txt', 'wb') as f:
                                f.write(article_text)

                        with open(dirpath + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': {
                                    self.language_code: document_title
                                },
                                'md5': document_hash,
                                'releaseDate': date.strftime('%d/%m/%Y'),
                                'url': document_url
                            }
                            json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                        existed_docs.append(document_hash)
                    except FileExistsError:
                        print('\tDirectory path already exists, continue.')
                except:
                    print('\tSomething went wrong getting the doc.')
        return existed_docs


    def get_docs_new(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Thuringia ===========================")
        iterator = 1
        language_code = 'de'
        existed_docs = []

        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name

        source = {
            "host": "https://www.tlfdi.de",
            "start_path": "/presse/pressemitteilungen/"
        }

        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        print('page_url:', page_url)

        exec_path = WebdriverExecPolicy().get_system_path()
        options = webdriver.ChromeOptions()
        options.add_argument('headless')
        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
        driver_doc.get(page_url)
        results_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')

        # 1. find all current docs
        list_view = results_soup.find('div', class_='news-list-view')
        # print('list_view: ', list_view)
        if list_view is None:
            return existed_docs
        list = list_view.find('div', class_='news-list')
        host = 'https://www.tlfdi.de'
        for group in list.find_all('div', role='group'):
            for item in group.find_all('div', role='listitem'):

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1

                time.sleep(2)
                document_section = item.find('div', class_='item-inner')

                document_title = document_section.find('a', class_='headline').get_text().strip()
                print('\tDocument Title:\t', document_title)
                document_href = document_section.find('a', class_='headline').get('href')
                document_url = host + document_href

                # ex: 18.10.2019
                print('\tdocument_url:\t', document_url)
                footer = document_section.find('div', class_='footer')
                date_str = footer.find('p').get_text().strip()

                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                print('\tdate:\t', date)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tBefore GDPR adopted, stop.")
                    return existed_docs
                if document_url == (host + '/'):
                    print('\tDocument not exist, continue')
                    continue
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print("\tdocument_hash:\t", document_hash)
                try:
                    document_response = requests.request('GET', document_url)
                    document_content = document_response.content
                    document_soup = BeautifulSoup(document_content, 'html.parser')
                    teaser_text = document_soup.find('div', class_='article')
                    article_href = teaser_text.find('a').get('href')
                    if article_href.startswith('http'):
                        article_url = article_href
                    else:
                        article_url = host + article_href
                    if article_href.endswith('.png'):
                        print('\tThis a an image, continue')
                        continue

                    print('\tarticle_url: ', article_url)

                    dpa_folder = path
                    dirpath = dpa_folder + '/' + 'thuringia' + '/' + document_hash
                    #dirpath = root_path + '/' + 'thuringia' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        article_response = requests.request('GET', article_url)
                        article_content = article_response.content
                        if article_url.endswith('.html'):
                            article_soup = BeautifulSoup(article_content, 'html.parser')
                            text = article_soup.find('article', id='meldung')
                            if text is None:
                                print('\tSomething went wrong getting document.')
                                continue

                            article_text = text.get_text()
                            with open(dirpath + '/' + language_code + '.txt', 'w') as f:
                                f.write(article_text)
                        else:
                            with open(dirpath + '/' + language_code + '.pdf', 'wb') as f:
                                f.write(article_content)
                            article_text = textract.process(
                                dirpath + '/' + language_code + '.pdf')
                            with open(dirpath + '/' + language_code + '.txt', 'wb') as f:
                                f.write(article_text)

                        with open(dirpath + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': {
                                    self.language_code: document_title
                                },
                                'md5': document_hash,
                                'releaseDate': date.strftime('%d/%m/%Y'),
                                'url': document_url
                            }
                            json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                        existed_docs.append(document_hash)
                    except FileExistsError:
                        print('\tDirectory path already exists, continue.')
                except:
                    print('\tSomething went wrong getting the doc.')

        return existed_docs