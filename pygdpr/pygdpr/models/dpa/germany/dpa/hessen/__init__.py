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

class Hessen(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://datenschutz.hessen.de",
            # "start_path": "/pressemitteilungen"
            "start_path": "/infothek/taetigkeitsberichte"
        }

        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pagination = page_soup.find('ul', class_='pager clearfix')
            if pagination is not None:
                pager_next = pagination.find('li', class_='pager-next')
                page_link = pager_next.find('a')
                if page_link is not None:
                    page_href = page_link.get('href')
                    pagination = Pagination()
                    pagination.add_item(host + page_href)
        return pagination

    def get_source(self, page_url=None, driver=None):
        assert (page_url is not None)
        page_source = None
        try:
            page_source = requests.request('GET', page_url)
            page_source.raise_for_status()
        except requests.exceptions.HTTPError as error:
            pass
        return page_source

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n======================== Germany -- Hessen Activity Reports =========================")
        iteration = 1
        language_code = 'de'
        existed_docs = []

        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name
        source = {
            "host": "https://datenschutz.hessen.de",
            "start_path": "/infothek/taetigkeitsberichte"
        }

        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        print('page_url:', page_url)

        page_source = self.get_source(page_url=page_url)
        page_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert page_soup

        article = page_soup.find('article', class_='box links my-lg-5 my-25')
        assert article
        for views_row in article.find_all('div', class_='document__field-media-document'):
            print('\n------------ Document: ' + str(iteration) + ' ------------')
            iteration += 1
            time.sleep(2)
            result_link = views_row.find('a')
            if result_link is None:
                continue
            document_href = result_link.get('href')
            document_url = host + document_href
            document_title = views_row.find('span', class_='link-text').get_text()
            print('Document Title: ' + document_title)
            print('\tDocument URL: ' + document_url)
            year = document_title.split("(PDF")[0][-6:-2]
            print('\tYear: ', year)
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            print('\tdocument_hash: ', document_hash)
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:', document_hash)
                continue
            if year < "2018":
                print("\tBefore GDPR adopted, stop.")
                return existed_docs

            document_response = None
            try:
                document_response = requests.request('GET', document_url)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                if to_print:
                    print(error)
                pass
            if document_response is None:
                continue
            document_content = document_response.content

            dpa_folder = path
            dirpath = dpa_folder + '/' + 'hessen' + '/' + document_hash
            # dirpath = root_path + '/' + 'hessen' + '/' + document_hash
            try:
                os.makedirs(dirpath)
                with open(dirpath + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_content)
                with open(dirpath + '/' + self.language_code + '.txt', 'wb') as f:
                    try:
                        document_text = textract.process(dirpath + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                    except:
                        print('Failed to convert PDF to text')
                with open(dirpath + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': year,
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                existed_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")
        return existed_docs



    # Below code crawling "press release" link, but the link is stopped.
    def get_docs_oldDesign(self, existing_docs=[], overwrite=False, to_print=True):
        language_code = 'de'
        existed_docs = []

        folder_name = self.country.replace(' ', '-').lower()
        self_path = self.path[:-1]
        root_path = self_path + '/' + folder_name

        pagination = self.update_pagination()

        while pagination.has_next():

            page_url = pagination.get_next()
            print('page_url:', page_url)

            exec_path = WebdriverExecPolicy().get_system_path()
            options = webdriver.ChromeOptions()
            options.add_argument('headless')
            driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
            driver_doc.get(page_url)
            results_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')
            content = results_soup.find('div', class_='view-content')
            if content is None:
                return existed_docs

            for view in content.find_all('div', class_='views-row'):
                time.sleep(5)
                document_section = view.find('div', class_='field-name-field-teaser-title')
                document_title = document_section.get_text()
                print('document_title: ', document_title)

                url_section = view.find('div', class_='group-bottom')
                document_href = url_section.find('a').get('href')
                host =  'https://datenschutz.hessen.de'
                document_url = host + document_href

                date_section = view.find('div', class_='group-right')
                date_str = date_section.find('span', class_='date-display-single').get_text()
                # ex: 18.10.2019
                print('\tdocument_url: ', document_url)
                print('\tdate_str: ', date_str)
                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tBefore GDPR adopted, stop.")
                    return existed_docs

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print("\tdocument_hash:\t", document_hash)
                try:
                    document_response = requests.request('GET', document_url)
                    document_content = document_response.content
                    document_soup = BeautifulSoup(document_content, 'html.parser')
                    dirpath = root_path + '/' + 'hessen' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        content_inner = document_soup.find('div', class_='content-inner')
                        text = content_inner.find('div', id='region-main-content')
                        if text is None:
                            print('\tSomething went wrong getting document.')
                            continue

                        document_text = text.get_text()
                        with open(dirpath + '/' + language_code + '.txt', 'w') as f:
                            f.write(document_text)
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
                        print('Directory path already exists, continue.')
                except:
                    print('\tSomething went wrong getting the doc.')
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs