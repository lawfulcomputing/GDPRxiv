import os
import math
import requests
import json
import datetime
import hashlib
import dateparser
import re
import csv
import time

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

class MecklenburgVorpommern(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://www.datenschutz-mv.de",
            "start_path": "/presse/"
            # "start_path": '/presse/?pager.page.nr=1&pager.items.offset=30'
        }

        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            page = page_soup.find('div', class_='result_bottom_pager')
            if page is not None:
                page_link = page.find('a', class_='next')
                if page_link is not None:
                    page_href = page_link.get('href')
                    # print('\tpage_href', page_href)
                    pagination = Pagination()
                    pagination.add_item(host + page_href)
        return pagination

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Mecklenburg Vorpommern ===========================")
        iterator = 1
        language_code = 'de'
        existed_docs = []
        dict_hashcode = {}

        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name

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

            result_list = results_soup.find('div', class_='resultlist')
            if result_list is None:
                return existed_docs

            for teaser_text in result_list.find_all('div', class_='teaser_text'):
                # print("teaser_text: ", teaser_text)

                time.sleep(2)
                teaser_meta = teaser_text.find('div', class_='teaser_meta')
                date_str = teaser_meta.find('span', class_='dtstart').get_text()
                # ex: 18.10.2019
                # print('\tdate_str: ', date_str)
                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("Before GDPR adopted, stop.")
                    return existed_docs

                document_section = teaser_text.find('h3')
                document_href = document_section.find('a').get('href')
                host =  'https://www.datenschutz-mv.de'
                document_url = host + document_href
                # print('url: ', document_url)

                try:

                    exec_path = WebdriverExecPolicy().get_system_path()
                    options = webdriver.ChromeOptions()
                    options.add_argument('headless')
                    driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                    driver_doc.get(document_url)
                    document_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')

                    text = document_soup.find('div', class_='element_holder holder_75 center')
                    if text is None:
                        print('\tSomething went wrong getting document.')
                        continue

                    print('\n------------ Document: ' + str(iterator) + ' ------------\n')
                    iterator += 1

                    document_section = text.find('div', class_='dvz-contenttype-pagetitle')
                    document_title =  document_section.get_text().strip()
                    document_title = document_title.replace('\n', '--')

                    print('\tDocument Title:\t', document_title)
                    document_hash = hashlib.md5(document_title.encode()).hexdigest()

                    if document_hash in existing_docs and overwrite is False:
                        if to_print:
                            print('\tSkipping existing document:\t', document_hash)
                        continue

                    # documents have the same hashcode, but different dates
                    date_part = date_str.replace('-', '_')
                    if document_hash in dict_hashcode:
                        document_hash = document_hash + '-' + date_part

                    print('\tDocument hash: ' + document_hash)
                    print('\tdate:\t', date)
                    print('\tdocument_url:\t', document_url)

                    document_text = text.get_text()
                    dpa_folder = path
                    dirpath = dpa_folder + '/' + 'mecklenburg_vorpommern' + '/' + document_hash
                    # dirpath = root_path + '/' + 'mecklenburg_vorpommern' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
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
                        dict_hashcode[document_hash] = date_part

                    except FileExistsError:
                        print('\tDirectory path already exists, continue.')

                except:
                    print('\tsomething went wrong getting the doc.')

            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs