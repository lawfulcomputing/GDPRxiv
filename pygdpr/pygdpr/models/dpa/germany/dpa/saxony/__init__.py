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

class Saxony(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://www.datenschutz.sachsen.de",
            "start_path": "/neues.html",
            "page_href_2022": '/archiv-2022-6001.html',
            "page_href_2021": '/archiv-2021.html'
        }
        host = source['host']
        start_path = source['start_path']

        pagination = Pagination()
        pagination.add_item(host + start_path)
        pagination.add_item(host + source['page_href_2022'])
        pagination.add_item(host + source['page_href_2021'])
        return pagination


    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Saxony ===========================")
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

            content = results_soup.find('div', class_='content-col-wide')
            if content is None:
                return existed_docs

            list = content.find('ul', class_='list-unstyled')
            index = 0
            for section in list.find_all('article', class_='media media-teaser'):
                time.sleep(2)

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1
                document_section = section.find('div', class_='media-header')
                document_title = document_section.find('h3', class_='media-heading').get_text().strip()
                print('\tDocument Title:\t', document_title)
                document_href = section.find('a').get('href')
                host =  'https://www.datenschutz.sachsen.de'
                document_url = host + document_href

                date_part = document_section.get_text().strip()
                date_str = date_part[:10]
                # ex: 18.10.2019
                print('\tdocument_url:\t', document_url)

                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                print('\tdate:\t', date)
                index += 1

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
                    dirpath = dpa_folder + '/' + 'saxony' + '/' + document_hash
                    # dirpath = root_path + '/' + 'saxony' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)

                        # summary section
                        main_content = document_soup.find('main', id ='main-content')
                        text = main_content.find('div', class_='row')
                        if text is None:
                            print('\tSomething went wrong getting document.')
                            continue
                        document_text = text.get_text()
                        with open(dirpath + '/' + language_code + '_Summary' + '.txt', 'w') as f:
                            f.write(document_text)

                        # full PDF file
                        count = 0
                        for a in text.find_all('a', href = True):
                            href = a.get('href')
                            if href.endswith('pdf'):
                                count += 1
                                if href.startswith('https'):
                                    article_link = href
                                else:
                                    article_link = host + href
                                print('\tarticle_link: ', article_link)
                                article_response = requests.request('GET', article_link)
                                article_content = article_response.content

                                with open(dirpath + '/' + language_code + '_' + str(count) + '.pdf', 'wb') as f:
                                    f.write(article_content)

                                article_text = textract.process(
                                    dirpath + '/' + language_code + '_' + str(count) + '.pdf')
                                with open(dirpath + '/' + language_code + '_' + str(count) + '.txt', 'wb') as f:
                                    f.write(article_text)

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



