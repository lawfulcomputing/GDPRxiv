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

class FederalDPA(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://www.bfdi.bund.de/",
            "start_path": "DE/DerBfDI/Presse/Pressemitteilungen/pressemitteilungen_node.html"
        }

        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            news_section = page_soup.find('nav', class_="navIndex")
            pager_next = news_section.find('ul')
            if pager_next is not None:
                page_link = pager_next.find('a', class_='forward button')
                if page_link is not None:
                    page_href = page_link.get('href')
                    pagination = Pagination()
                    pagination.add_item(host + page_href)
        return pagination

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True, path=None):
        print("\n========================= Germany Press Release -- Federal DPA ===========================")
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
            content = results_soup.find('div', class_='wrapperTable')
            tbody = content.find('tbody')
            if tbody is None:
                return existed_docs

            for tr in tbody.find_all('tr'):
                time.sleep(2)

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1

                document_section = tr.find_all('td', class_=['odd','even'])
                document_title = document_section[1].find('a').get_text()
                document_title = document_title.strip()
                print('\tDocument Title: ', document_title)
                document_href = document_section[1].find('a').get('href')
                host =  'https://www.bfdi.bund.de/'
                document_url = host + document_href

                date_str = document_section[0].get_text().strip()
                # ex: 18.10.2019
                print('\tdocument_url: ', document_url)
                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                print('\tdate: ', date)

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
                    dirpath = dpa_folder + '/' + 'federal_DPA' + '/' + document_hash

                    # dirpath = root_path + '/' + 'federal_DPA' + '/' + document_hash
                    try:
                        os.makedirs(dirpath)
                        text = document_soup.find('main', class_='main row')
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