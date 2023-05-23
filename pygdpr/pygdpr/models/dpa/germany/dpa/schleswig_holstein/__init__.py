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

class SchleswigHolstein(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://www.datenschutzzentrum.de",
            "start_path": "/kategorie/2-2-Pressemitteilungen"
        }

        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pagination = page_soup.find('div', id='pagination')

            if pagination is not None:
                clearfix = pagination.find('ul', class_='clearfix')
                page_link = clearfix.find('li', class_='next')
                if page_link is not None:
                    page_url = page_link.find('a').get('href')
                    pagination = Pagination()
                    pagination.add_item(page_url)
        return pagination

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Schleswig Holstein ===========================")
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
            content = results_soup.find('div', id='content')
            if content is None:
                return existed_docs
            for article_clearfix in content.find_all('div', class_='article clearfix'):
                time.sleep(2)
                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1

                document_title = article_clearfix.find('h2').get_text()
                print('\tDocument Title:\t', document_title)

                document_href = article_clearfix.find('a', class_='readmore').get('href')
                host =  'https://www.datenschutzzentrum.de'
                document_url = host + document_href

                date_section = article_clearfix.find('span', class_='time').get_text()
                date_text = date_section.split()[1:]
                date_str = ' '.join(date_text)
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                # ex: 18.10.2019
                print('\tdocument_url:\t', document_url)
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
                    dirpath = dpa_folder + '/' + 'schleswig_holstein' + '/' + document_hash
                    # dirpath = root_path + '/' + 'schleswig_holstein' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        content = document_soup.find('div', id='content')
                        text = content.find('div', class_='clearfix')
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
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs