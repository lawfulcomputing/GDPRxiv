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

class LowerSaxony(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Lower Saxony ===========================")
        iterator = 1
        language_code = 'de'
        existed_docs = []

        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name

        source = {
            "host": "https://lfd.niedersachsen.de/startseite",
            "start_path": "/infothek/presseinformationen/"
        }

        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path

        exec_path = WebdriverExecPolicy().get_system_path()
        options = webdriver.ChromeOptions()
        options.add_argument('headless')
        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
        driver_doc.get(page_url)
        # clear the default date and set the start day as GDPR adopted date, and set the end day
        driver_doc.find_element_by_xpath('//*[@id="press"]/div/span[1]/input').clear()
        driver_doc.find_element_by_xpath('//*[@id="press"]/div/span[1]/input').send_keys('25.05.2018')
        driver_doc.find_element_by_xpath('//*[@id="press"]/div/span[2]/input').clear()
        driver_doc.find_element_by_xpath('//*[@id="press"]/div/span[2]/input').send_keys('12.04.2023')
        # click the seek button
        driver_doc.find_element_by_class_name('suchen').click()
        time.sleep(3)
        # load all article first, only need to load once, but in case more article comes in future

        for i in range(3):
            driver_doc.refresh()
            driver_doc.find_element_by_xpath('//*[@id="loadMoreResults"]').click()
            time.sleep(3)

        # print('text: ', driver_doc.find_element_by_xpath('//*[@id="loadMoreResults"]').text())
        page_source = driver_doc.page_source
        # print(page_source)
        results_soup = BeautifulSoup(page_source, 'html.parser')
        search_results = results_soup.find('div', id = 'search_results')
        if search_results is None:
            return existed_docs

        # print('here: ',search_results.find_all('div', class_='group section span3of4 singleResult'))
        for section in search_results.find_all('div', class_='group section span3of4 singleResult'):
            time.sleep(2)

            print('\n------------ Document: ' + str(iterator) + ' ------------')
            iterator += 1

            document_section = section.find('div', class_='content')

            document_title = document_section.find('a').get_text()
            print('\tDocument Title:\t', document_title)

            document_url = document_section.find('a').get('href')
            date_str =section.find('div', class_='datum').get_text()
            # ex: 18.10.2019
            print('\tdocument_url: ', document_url)

            tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
            date = datetime.date(tmp.year, tmp.month, tmp.day)
            print('\tdate:\t', date)

            if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                print("\tBefore GDPR adopted, stop.")
                return existed_docs

            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            print("\tdocument_hash:\t", document_hash)
            try:
                document_response = requests.request('GET', document_url)
                document_content = document_response.content
                document_soup = BeautifulSoup(document_content, 'html.parser')

                dpa_folder = path
                dirpath = dpa_folder + '/' + 'lower_saxony' + '/' + document_hash
                # dirpath = root_path + '/' + 'lower_saxony' + '/' + document_hash
                try:
                    os.makedirs(dirpath)
                    maincontent = document_soup.find('div', class_='maincontent group')
                    text = maincontent.find('div', class_='articleContent')
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
                    print('\tDirectory path already exists, continue.')
            except:
                print('\tSomething went wrong getting the doc.')
        return existed_docs