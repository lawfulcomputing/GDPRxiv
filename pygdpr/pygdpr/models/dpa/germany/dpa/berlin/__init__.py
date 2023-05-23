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
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy

class Berlin(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Berlin ===========================")
        iterator = 1
        existed_docs = []
        source = {
            "host": "https://www.datenschutz-berlin.de",
            "start_path": "/pressemitteilungen/"
        }

        host = source['host']
        start_path = source['start_path']

        language_code = 'de'
        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name

        source_url = host + start_path

        pagination = Pagination()
        pagination.add_item(source_url)

        while pagination.has_next():
            page_url = pagination.get_next()
            print('page_url:', page_url)

            results_response = requests.request('GET', page_url)
            results_content = results_response.content
            results_soup = BeautifulSoup(results_content, 'html.parser')

            sections = results_soup.find_all('section', class_='causes-single-wrapper')
            for i in range(1, len(sections)):
                section = sections[i]

                press_date = section.find('div', class_='press-date')
                if press_date is None:
                    continue

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1
                time.sleep(2)
                date_str = press_date.get_text().strip('')
                tmp = dateparser.parse(date_str, languages=[language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tBefore GDPR adopted, stop.")
                    return existed_docs # try another result_link # should be continue

                h3 = section.find('h3')
                if h3 is None:
                    return existed_docs

                document_title = h3.get_text()
                print('\tDocument Title:\t', document_title)
                document_folder = document_title
                document_hash = hashlib.md5(document_folder.encode()).hexdigest()
                print("\tdocument_hash:\t", document_hash)
                print('\tdate:\t', date)

                sidebar = section.find('div', class_='sidebar')
                if sidebar is None:
                    print('\tNo document inside it, continue')
                    continue

                document_links = sidebar.find_all('a')
                if len(document_links) == 0:
                    return existed_docs

                dpa_folder = path
                dirpath = dpa_folder + '/' + 'berlin' + '/' + document_hash
                # dirpath = root_path + '/' + 'berlin' + '/' + document_hash
                try:
                    os.makedirs(dirpath)
                    document_count = 1
                    for a in document_links:
                        document_href = a.get('href')
                        a_text = a.get_text().strip()
                        # overwrite language code
                        # depending on document language title suffix labels: (englisch) | (deutsch).
                        if a_text.endswith('(englisch)') is True:
                            language_code = 'en'
                        else:
                            language_code = 'de'

                        document_url = host + document_href
                        print('\tdocument_url: ', document_url)
                        try:
                            document_response = requests.request('GET', document_url)
                            document_content = document_response.content

                            with open(dirpath + '/' + language_code + '_' + str(document_count) + '.pdf', 'wb') as f:
                                f.write(document_content)

                            document_text = textract.process(dirpath + '/' + language_code + '_' + str(document_count) + '.pdf')
                            with open(dirpath + '/' + language_code + '_' + str(document_count) + '.txt', 'wb') as f:
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
                        except:
                            print('\tSomething went wrong getting document.')
                        document_count = document_count + 1
                except FileExistsError:
                    print('\tDirectory path already exists, continue.')

        return existed_docs
