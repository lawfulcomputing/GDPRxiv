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

class Bavaria_PrivateSector(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Bavaria Private Sector ===========================")
        iterator = 1
        existed_docs = []
        source = {
            "host": "https://www.lda.bayern.de",
            "start_path": "/de/pressemitteilungen.html"
        }

        host = source['host']
        start_path = source['start_path']

        language_code = 'de'
        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name
        source_url = host + start_path
        results_response = requests.request('GET', source_url)
        results_content = results_response.content
        results_soup = BeautifulSoup(results_content, 'html.parser')

        for card in results_soup.find_all('div', class_='card-block'):

            time.sleep(2)
            year_str = card.find('h1', class_='text-dark').get_text()
            year = year_str.strip()[-4:]
            #print('year: ', year)
            card_container = card.find('div', class_='articles-container')

            for articles in card_container.find_all('div', class_='article border-bottom'):

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1
                part_date_str = articles.find('div', class_='col-xl-1 center_icon_block').get_text()
                part_date = part_date_str.strip().split()
                date_str = part_date[0] + part_date[1] + year
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                # print('tmp: ', tmp)
                # tmp = datetime.datetime.strptime(tmp, '%d%b%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                # print('date: ', date)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tBefore GDPR adopted, stop.")
                    return existed_docs # try another result_link # should be continue

                document_folder = articles.find('a', class_='text-dark font-weight-bold')
                document_title = document_folder.get_text()
                print('\tDocument Title\t: ', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print("\tdocument_hash:\t", document_hash)

                href = ""
                href = document_folder.get('href')
                #print('href: ', href)
                if href.endswith('.pdf') is False:
                    continue
                document_url = href.replace('..', host)
                if len(document_url) == 0:
                    return existed_docs
                print('\tdocument_url: ', document_url)
                document_response = requests.request('GET', document_url)
                document_content = document_response.content

                dpa_folder = path
                dirpath = dpa_folder + '/' + 'bavaria_privatesector' + '/' + document_hash
                # dirpath = root_path + '/' + 'bavaria_privatesector' + '/' + document_hash
                try:
                    os.makedirs(dirpath)

                    with open(dirpath + '/' + language_code + '.pdf', 'wb') as f:
                        f.write(document_content)

                    document_text = textract.process(dirpath + '/' + language_code + '.pdf')
                    with open(dirpath + '/' + language_code + '.txt', 'wb') as f:
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

        return existed_docs
