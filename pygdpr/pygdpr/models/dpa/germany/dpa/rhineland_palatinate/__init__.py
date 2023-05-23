import os
import math
import time

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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy

import textract

class RhinelandPalatinate(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://www.datenschutz.rlp.de/",
            "start_path": "de/aktuelles/"
        }

        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pagination = page_soup.find('ul', class_='tx-pagebrowse')
            if pagination is not None:
                page_link = pagination.find('li', class_='tx-pagebrowse-next')

                if page_link is not None:
                    page_href = page_link.find('a').get('href')
                    pagination = Pagination()
                    pagination.add_item(host + page_href)
        return pagination

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Rhineland Palatinate ===========================")
        iterator = 1
        language_code = 'de'
        existed_docs = []

        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name

        pagination = self.update_pagination()

        while pagination.has_next():

            page_url = pagination.get_next()
            print('page_url:', page_url)
            results_response = requests.request('GET', page_url)
            results_content = results_response.content
            results_soup = BeautifulSoup(results_content, 'html.parser')
            content = results_soup.find('div', class_='news-list-content-view')
            if content is None:
                return existed_docs

            for article in content.find_all('article', role='article'):
                time.sleep(2)

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1

                document_section = article.find('div', class_='header').find('h4')
                document_title = document_section.get_text().strip()
                print('\tDocument Title:\t', document_title)

                document_href = document_section.find('a').get('href')
                host =  'https://www.datenschutz.rlp.de/'
                document_url = host + document_href

                date_section = article.find('p')
                date_str = date_section.get_text().strip()
                # ex: 18.10.2019
                print('\tdocument_url:\t', document_url)

                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                print('\tdate:\t', date)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("Before GDPR adopted, stop.")
                    return existed_docs

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print("\tdocument_hash:\t", document_hash)

                try:
                    exec_path = WebdriverExecPolicy().get_system_path()
                    options = webdriver.ChromeOptions()
                    options.add_argument('headless')
                    driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                    driver_doc.get(document_url)
                    document_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')

                    dpa_folder = path
                    dirpath = dpa_folder + '/' + 'rhineland_palatinate' + '/' + document_hash
                    # dirpath = root_path + '/' + 'rhineland_palatinate' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        text = document_soup.find('div',class_='row inhaltsseite')
                        if text is None:
                            print('\tSomething went wrong getting document.')
                            continue
                        # print('text: ', text)
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
                        print('\tDirectory path already exists, continue.')
                except:
                    print('\tsomething went wrong getting the doc.')
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs