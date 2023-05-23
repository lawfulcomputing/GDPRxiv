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

class Bremen(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Bremen ===========================")
        iterator = 1
        existed_docs = []
        source = {
            "host": "https://www.datenschutz.bremen.de/",
            "start_path": "publikationen/pressemitteilungen-17873"
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

            article_wrapper = results_soup.find('div', class_='entry-wrapper-normal')
            for article in article_wrapper.find_all('div', class_='news_article'):

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1
                time.sleep(2)
                default_date = '25.05.2018'
                date_field = article.find('p')
                if date_field is None:
                    date_str = default_date
                else:
                    date_str = date_field.find('em').get_text().split()[0]

                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tBefore GDPR adopted, stop.")
                    return existed_docs

                h2 = article.find('h2')
                if h2 is None:
                    return existed_docs

                document_title = h2.get_text()
                print('\tDocument Title:\t', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print("\tdocument_hash:\t", document_hash)
                print('\tdate:\t', date)

                dpa_folder = path
                dirpath = dpa_folder + '/' + 'bremen' + '/' + document_hash
                # dirpath = root_path + '/' + 'bremen' + '/' + document_hash
                try:
                    os.makedirs(dirpath)
                    document_href = h2.find('a').get('href')
                    pdf_flag = True
                    # end with .pdf
                    if document_href.endswith('.pdf'):
                        host = "https://www.datenschutz.bremen.de"
                        document_url = host + document_href
                        print('\tdocument_url:\t', document_url)
                    # not end with .pdf
                    else:
                        document_url = document_href
                        pdf_flag = False
                    try:
                        document_response = requests.request('GET', document_url)
                        document_content = document_response.content
                        if pdf_flag:
                            with open(dirpath + '/' + language_code + '.pdf', 'wb') as f:
                                f.write(document_content)
                            document_text = textract.process(dirpath + '/' + language_code + '.pdf')
                            with open(dirpath + '/' + language_code + '.txt', 'wb') as f:
                                f.write(document_text)
                        else:
                            document_soup = BeautifulSoup(document_content, 'html.parser')
                            document_section = document_soup.find('div', id = 'main')
                            document_text = document_section.get_text()
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
                    except:
                        print('\tSomething went wrong getting document.')
                except FileExistsError:
                    print('\tDirectory path already exists, continue.')

        return existed_docs