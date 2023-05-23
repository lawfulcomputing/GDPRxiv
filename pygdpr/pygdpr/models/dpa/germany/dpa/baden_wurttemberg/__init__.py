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

class BadenWurttemberg(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Baden Württemberg ===========================")
        existed_docs = []
        iterator = 1

        source = {
            "host": "https://www.baden-wuerttemberg.datenschutz.de",
            "start_path": "/pressemitteilungen"
        }
        host = source['host']
        start_path = source['start_path']

        language_code = 'de'

        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name
        results_url = host + start_path

        exec_path = WebdriverExecPolicy.get_system_path(self)

        options = webdriver.ChromeOptions()
        options.add_argument('headless')

        driver = webdriver.Chrome(options=options, executable_path=exec_path)
        driver.get(results_url)
        try:
            # print('page_source', results_url)
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # document_soup = BeautifulSoup(driver.page_source, 'html.parser')
            results_content = driver.page_source
            results_soup = BeautifulSoup(results_content, 'html.parser')
            # print(results_soup)
            post_content = results_soup.find('div', class_='et_pb_text_inner')
            if post_content is None:
                return existed_docs
            paragraphs = post_content.find_all('strong')
            paragraphs = list(filter(lambda p: len(p.get_text().strip()) > 0, paragraphs))

            tables = post_content.find_all('table')
            if len(paragraphs) != len(tables):
                return existed_docs

            for i in range(len(tables)):
                p = paragraphs[i]
                table = tables[i]
                year_str = p.get_text().strip()
                # print("year: ",year_str)

                if int(year_str) < 2018:
                    return existed_docs
                for tr in table.find_all('tr'):
                    print('\n------------ Document: ' + str(iterator) + ' ------------')
                    iterator += 1
                    time.sleep(2)
                    tds = tr.find_all('td')

                    date_index = 0
                    doc_index = 1

                    if len(tds) != max(date_index, doc_index) + 1:
                        return existed_docs

                    part_date_str = tds[date_index].get_text()
                    if part_date_str.endswith('.') is False:
                        part_date_str += '.'
                    date_str = part_date_str + year_str
                    tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                    date = datetime.date(tmp.year, tmp.month, tmp.day)

                    if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                        return existed_docs  # try another result_link # should be continue

                    document_td = tds[doc_index]
                    document_a = document_td.find('a')
                    if document_a is None:
                        return existed_docs

                    document_title = document_a.get_text()
                    document_folder = document_title
                    document_folder_md5 = hashlib.md5(document_folder.encode()).hexdigest()

                    document_href = document_a.get('href')
                    document_url = document_href
                    print("\tDocument Title:\t", document_title)
                    print("\tdocument_href:\t", document_href)
                    print("\tdocument_hash:\t", document_folder_md5)
                    print("\tdate:\t", date)

                    dpa_folder = path
                    dirpath = dpa_folder + '/' + 'baden_wurttemberg' + '/' + document_folder_md5
                    # dirpath = root_path + '/' + 'baden_wurttemberg' + '/' + document_folder_md5

                    if document_href.endswith('.pdf') is False:
                        try:
                            document_response = requests.request('GET', document_url)
                            document_content = document_response.content
                            document_soup = BeautifulSoup(document_content, 'html.parser')
                            try:
                                os.makedirs(dirpath)
                                text = document_soup.find('div', class_='et_pb_extra_column_main')
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
                                        'md5': document_folder_md5,
                                        'releaseDate': date.strftime('%d/%m/%Y'),
                                        'url': document_url
                                    }
                                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                                existed_docs.append(document_folder_md5)
                            except FileExistsError:
                                print('\tDirectory path already exists, continue.')
                        except:
                            print('\tSomething went wrong getting the doc.')

                    else:
                        document_response = requests.request('GET', document_url)
                        document_content = document_response.content

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
                                    'md5': document_folder_md5,
                                    'releaseDate': date.strftime('%d/%m/%Y'),
                                    'url': document_href
                                }
                                json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                            existed_docs.append(document_folder_md5)
                        except FileExistsError:
                            print('\tDirectory path already exists, continue.')
        finally:
            driver.quit()
        return existed_docs
