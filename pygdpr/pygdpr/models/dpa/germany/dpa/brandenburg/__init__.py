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

class Brandenburg(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path="decisions"):
        source = {
            "host": "https://www.lda.brandenburg.de",
            "start_path": "/lda/de/service/presseinformationen/"
        }

        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
            # print('link: ', host + start_path)
        else:
            # add all the following pages start from page 2 at one time
            paginationlist = page_soup.find_all('li', class_='paginationpage')
            for pageIndex in range(1,len(paginationlist)):
                page = paginationlist[pageIndex]
                # print('page: ',page)
                potential_href = page.find('a').get('href')
                if potential_href is None:
                    # print("page href is none")
                    continue
                if len(potential_href) == 1:
                    continue
                page_href = potential_href
                add_page = host + page_href
                pagination.add_item(host + page_href)
                # print('add_page: ', add_page)
        return pagination

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Brandenburg ===========================")
        iterator = 1
        page_count = 1
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
            content = results_soup.find('div', class_='bb-text-justify-xx')
            if content is None:
                return existed_docs

            for trennung in content.find_all('article', class_='trennung'):
                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1
                time.sleep(2)
                document_section = trennung.find('h3')
                document_title = document_section.find('span', class_='bb-readmore')
                document_title = document_title.get_text().strip()

                document_href = trennung.find('a').get('href')
                host =  'https://www.lda.brandenburg.de'
                document_url = host + document_href

                date_str = trennung.find('time', class_='bb-teaser-meta').get_text()
                # ex: 18.10.2019
                if document_title.startswith(date_str) is True:
                    document_title = document_title.replace(date_str, '')
                print('\tDocument Title:\t', document_title)
                print('\tdocument_url:\t', document_url)

                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tBefore GDPR adopted, stop.")
                    continue # try another result_link # should be continue
                print('\tdate:\t', date)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print("\tdocument_hash:\t", document_hash)

                try:
                    document_response = requests.request('GET', document_url)
                    document_content = document_response.content
                    document_soup = BeautifulSoup(document_content, 'html.parser')

                    dpa_folder = path
                    dirpath = dpa_folder + '/' + 'brandenburg' + '/' + document_hash
                    # dirpath = root_path + '/' + 'brandenburg' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        text = document_soup.find('div', class_='columns text-justifyxx')
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
                    print('\tsomething went wrong getting the doc.')
            # s0. Pagination
            # only need to call update_pagination() method one time
            if page_count == 1:
                pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
            page_count += 1
        return existed_docs
