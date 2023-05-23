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

import textract
import time

class Hamburg(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://datenschutz-hamburg.de",
            "start_path": "/pressemitteilungen/"
        }

        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pagination = page_soup.find('ul', class_='pagination')
            if pagination is not None:
                pager_bar = pagination.find_all('li', class_='page-item')
                page_link = pager_bar[2].find('a')
                if page_link is not None:
                    page_href = page_link.get('href')
                    pagination = Pagination()
                    pagination.add_item(host + page_href)
        return pagination

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True ,path=None):
        print("\n========================= Germany Press Release -- Hamburg ===========================")
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
            content = results_soup.find('div', class_='content-block')
            if content is None:
                return existed_docs

            for publication in content.find_all('div', class_='publication'):
                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1
                time.sleep(2)

                container = publication.find('div', class_='container-fluid')
                document_section = container.find_all('div', class_='row')
                document_title = document_section[1].find('h2').get_text()
                print('\tDocument Title:\t', document_title)

                document_href = document_section[1].find('a').get('href')
                host =  'https://datenschutz-hamburg.de'
                document_url = host + document_href

                date_section = document_section[0].find('span')
                date_str = date_section.get_text()
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
                    document_response = requests.request('GET', document_url)
                    document_content = document_response.content
                    document_soup = BeautifulSoup(document_content, 'html.parser')

                    dpa_folder = path
                    dirpath = dpa_folder + '/' + 'hamburg' + '/' + document_hash
                    # dirpath = root_path + '/' + 'hamburg' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        text = document_soup.find('article', id='page-content')
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
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs