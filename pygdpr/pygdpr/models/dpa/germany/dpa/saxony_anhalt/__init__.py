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

class SaxonyAnhalt(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def get_archive_docs(self, page_url, path):
        language_code = 'de'
        existed_docs = []
        iterator = 1
        results_response = requests.request('GET', page_url)
        print('========Press Archive===================')
        results_content = results_response.content
        results_soup = BeautifulSoup(results_content, 'html.parser')
        # print("results_soup: ", results_soup)
        bodytext = results_soup.find('div', class_='ce-bodytext')
        for li in bodytext.find_all('li'):

            print('\n------------ Document: ' + str(iterator) + ' ------------')
            iterator += 1

            document_title = li.find('a').get_text()
            print('\tDocument Title\t: ', document_title)
            document_href = li.find('a').get('href')
            host = 'https://datenschutz.sachsen-anhalt.de'
            document_url = host + document_href
            date_str = ''
            # find the date inside document_title
            for i in range(len(document_title) - 1, 0, -1):
                # print('document_title[i]: ', document_title[i])
                if document_title[i].isdigit():
                    date_str = document_title[i - 9:i + 1]
                    break
            # ex: 18.10.2019
            print('\tdocument_url:\t', document_url)

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

                dirpath = path + '/' + 'saxony_anhalt' + '/' + document_hash
                try:
                    os.makedirs(dirpath)
                    with open(dirpath + '/' + language_code + '.pdf', 'wb') as f:
                        f.write(document_content)

                    document_text = textract.process(
                        dirpath + '/' + language_code + '.pdf')
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
            except:
                print('\tSomething went wrong getting the doc.')
        return existed_docs


    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Saxony Anhalt ===========================")
        iterator = 1
        language_code = 'de'
        existed_docs = []

        # folder_name = self.country.replace(' ', '-').lower()
        # self_path = self.path[:-1]
        # root_path = self_path + '/' + folder_name

        source = {
            "host": "https://datenschutz.sachsen-anhalt.de",
            "start_path": "/landesbeauftragter/pressemitteilungen/"
        }

        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        print('page_url:', page_url)

        results_response = requests.request('GET', page_url)
        results_content = results_response.content
        results_soup = BeautifulSoup(results_content, 'html.parser')
        content = results_soup.find('div', id='content')
        if content is None:
            return existed_docs

        for bodytext in content.find_all('div', class_='ce-bodytext'):
            time.sleep(2)
            print('\n------------ Document: ' + str(iterator) + ' ------------')
            iterator += 1

            document_section = bodytext.find('li')
            if document_section is not None:
                document_title = document_section.find('a').get_text()
                print('\tDocument Title:\t', document_title)
                document_href = document_section.find('a').get('href')
                document_url = host + document_href
                date_str = ''
                # find the date inside document_title
                for i in range(len(document_title)-1, 0, -1):
                    # print('document_title[i]: ', document_title[i])
                    if document_title[i].isdigit():
                        date_str = document_title[i-9:i+1]
                        break
                # ex: 18.10.2019
                print('\tdocument_url:\t', document_url)

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

                    dpa_folder = path
                    dirpath = dpa_folder + '/' + 'saxony_anhalt' + '/' + document_hash
                    # dirpath = root_path + '/' + 'saxony_anhalt' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        with open(dirpath + '/' + language_code + '.pdf', 'wb') as f:
                            f.write(document_content)

                        document_text = textract.process(
                            dirpath + '/' + language_code + '.pdf')
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
                except:
                    print('\tSomething went wrong getting the doc.')
            else:
                archive_href = bodytext.find('a').get('href')
                archive_url = host + archive_href
                print('\narchive_url: ',  archive_url)

                archive_docs = self.get_archive_docs(archive_url, path)
                existed_docs += archive_docs
        return existed_docs

