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

class Bavaria_PublicSector(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def get_archive_docs(self, path):
        iterator = 1
        language_code = 'de'
        existed_docs = []
        source = {
            "host": "https://www.datenschutz-bayern.de",
            "start_path": "/nav/0305.html"
        }

        host = source['host']
        start_path = source['start_path']
        source_url = host + start_path
        print('\n==============Bavaria Press Archive===================')
        pagination = Pagination()
        pagination.add_item(source_url)

        while pagination.has_next():
            page_url = pagination.get_next()
            print('page_url:', page_url)
            results_response = requests.request('GET', page_url)
            results_content = results_response.content
            results_soup = BeautifulSoup(results_content, 'html.parser')

            content = results_soup.find('div', class_='page-content')
            for div in content.find_all('div'):
                if div is None:
                    return existed_docs
                ul = div.find('ul', class_='level3')
                for li in div.find_all('li', class_='level3'):
                    time.sleep(2)
                    document_section = li.get_text().split(':')
                    date_str = document_section[0].strip('')
                    tmp = dateparser.parse(date_str, languages=[language_code])
                    date = datetime.date(tmp.year, tmp.month, tmp.day)
                    # print('\tdate: ', date)

                    if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                        print("\nBefore GDPR adopted, stop.")
                        return existed_docs  # try another result_link # should be continue

                    print('\n------------ Document: ' + str(iterator) + ' ------------')
                    iterator += 1

                    document_title = document_section[1].strip()
                    print('\tDocument Title:\t', document_title)
                    document_folder = document_title
                    document_hash = hashlib.md5(document_folder.encode()).hexdigest()
                    print("\tdocument_hash:\t", document_hash)
                    print('\tdate:\t', date)

                    document_links = li.find_all('a')

                    dirpath = path + '/' + 'bavaria_publicsector' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        for a in document_links:
                            href = a.get('href')
                            if not href.endswith('.pdf'):
                                continue
                            document_url = href.replace('..', host)

                            print('\tdocument_url:\t ', document_url)
                            try:
                                document_response = requests.request('GET', document_url)
                                document_content = document_response.content

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
                            except:
                                print('\tSomething went wrong getting document.')
                    except FileExistsError:
                        print('\tDirectory path already exists, continue.')
        return existed_docs


    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Bavaria Public Sector ===========================")
        iterator = 1
        existed_docs = []
        source = {
            "host": "https://www.datenschutz-bayern.de",
            "start_path": "/nav/0301.html"
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

            content = results_soup.find('div', class_='page-content')
            level3 = content.find('ul', class_='level3')

            for li in level3.find_all('li', class_='level3'):
                time.sleep(2)

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1

                document_section = li.get_text().split(':')
                date_str = document_section[0].strip('')
                tmp = dateparser.parse(date_str, languages=[language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tBefore GDPR adopted, stop.")
                    break

                document_title = document_section[1].strip()
                print('\tDocument Title: ', document_title)
                document_folder = document_title
                document_hash = hashlib.md5(document_folder.encode()).hexdigest()
                print("\tdocument_hash:\t", document_hash)
                print('\tdate\t: ', date)

                document_links = li.find_all('a')

                dpa_folder = path
                dirpath = dpa_folder + '/' + 'bavaria_publicsector' + '/' + document_hash
                # dirpath = root_path + '/' + 'bavaria_publicsector' + '/' + document_hash
                try:
                    os.makedirs(dirpath)
                    for a in document_links:
                        href = a.get('href')
                        if not href.endswith('.pdf'):
                            continue
                        document_url= href.replace('..', host)

                        print('\tdocument_url: ', document_url)
                        try:
                            document_response = requests.request('GET', document_url)
                            document_content = document_response.content

                            with open(dirpath + '/' + language_code + '.pdf', 'wb') as f:
                                f.write(document_content)

                            document_text = textract.process(dirpath +  '/' + language_code + '.pdf')
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
                        except:
                            print('\tSomething went wrong getting document.')
                except FileExistsError:
                    print('\tDirectory path already exists, continue.')
            # 2. find all archive docs
            existed_docs += self.get_archive_docs(path)
        return existed_docs
