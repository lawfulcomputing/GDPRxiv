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
from pygdpr.models.dpa import DPA
from bs4 import BeautifulSoup
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy
import textract

class Netherlands(DPA):
    def __init__(self, path=os.curdir):
        country_code='nl'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path=None):

        source = {
            'host': 'https://autoriteitpersoonsgegevens.nl',
            'start_path_Opinions': '/wetgevingsadviezen',
            'start_path_Decisions': '/boetes-en-andere-sancties',
            'start_path_PublicDisclosure': '/woowob-besluiten'
        }
        host = source['host']
        if start_path == "Decisions":
            start_path = source['start_path_Decisions']
        elif start_path == "PublicDisclosure":
            start_path = source['start_path_PublicDisclosure']
        else:
            start_path = source['start_path_Opinions']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pager = page_soup.find('nav', class_='pager')
            if pager is not None:
                ul_pager = pager.find('ul')
                pager_item = ul_pager.find('li', class_='pager__item pager__item--next')
                if pager_item is None:
                    return pagination
                page_link = pager_item.find('a')
                if page_link is None:
                    return pagination
                page_href = page_link.get('href')
                pagination.add_item(host + start_path + page_href)
        return pagination

    def get_source(self, page_url=None, driver=None):
        assert (page_url is not None)
        results_response = None
        try:
            results_response = requests.request('GET', page_url)
            results_response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            if to_print:
                print(error)
            pass
        return results_response

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_Decisions(existing_docs=[], overwrite=False, to_print=True)
        # added_docs += self.get_docs_Reports(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Opinions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_publicDisclosure(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Netherlands Decision Documents =========================")
        iteration = 1
        existed_docs = []
        pagination = self.update_pagination(start_path="Decisions")
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            article_list = results_soup.find('div', class_='view-search-onpage-publications-sanction-overview__content')
            assert article_list
            # s1. Results
            for row in article_list.find_all('div', class_='node-publication-card__content'):
                time.sleep(2)
                date_card = row.find('div', class_='node-publication-card__submitted')
                assert date_card
                date_str = date_card.get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue

                result_link = row.find('a', class_='node-publication-card__link')
                assert result_link

                title = row.find('h1', class_='node-publication-card__title')
                assert title

                # s2. Documents
                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                document_title = title.get_text().strip()
                print('\tdocument_title:\t', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href

                host = 'https://autoriteitpersoonsgegevens.nl'
                document_url = host + document_href

                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                except requests.exceptions.ConnectionError as error:
                    if to_print:
                        print("\tError:", error)
                    pass

                if document_response is None:
                    continue

                file_soup = BeautifulSoup(document_response.text, 'html.parser')
                file_item = file_soup.find('div', class_='node-publication-full__files-item')
                file_href = file_item.find('a').get('href')
                if not file_href.endswith('pdf'):
                    continue
                file_url = host + file_href
                print('\tdocument url: ', file_url)
                print('\tdocument hash: ', document_hash)

                try:
                    file_response = requests.request('GET', file_url)
                    file_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                except requests.exceptions.ConnectionError as error:
                    if to_print:
                        print("\tError:", error)
                    pass
                if file_response is None:
                    continue

                file_content = file_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(file_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        try:
                            file_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(file_text)
                        except:
                            print('Failed to convert PDF to text')
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': document_title,
                            'md5': document_hash,
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': file_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

            # s1. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup, start_path="Decisions")
        return existed_docs


    def get_docs_Reports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Netherlands Reports =========================")
        iteration = 1
        existed_docs = []
        source = {
            'host': 'https://autoriteitpersoonsgegevens.nl',
            'start_path': '/nl/publicaties/rapportages',
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        main_content = results_soup.find('div', class_='main-content-article')
        for ul in main_content.find_all('ul'):
            for li in ul.find_all('li'):
                year = li.get_text().split()[-1]
                if int(year) < 2018:
                    continue

                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1
                document_title = li.find('a').get_text()
                print("\tDocument:\t", document_title)
                document_href = li.find('a').get('href')
                document_url = host + document_href
                print("\tDocument_url:\t", document_url)
                print('\tdate:\t', year)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Reports' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        document_text = document_text.strip()
                        f.write(document_text)
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': document_title,
                            'md5': document_hash,
                            'releaseDate': year,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
        return existed_docs

    def get_docs_Opinions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Netherlands Opinions =========================")
        iteration = 1
        existed_docs = []
        pagination = self.update_pagination(start_path="Opinions")
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup
            article_list = results_soup.find('div', class_='view-search-onpage-publications-legislation-advise-overview__content')
            assert article_list
            # s1. Results
            for card in article_list.find_all('div', class_='node-publication-card__content'):
                time.sleep(2)
                date_card = card.find('div', class_='node-publication-card__submitted')
                assert date_card
                date_str = date_card.get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue

                result_link = card.find('a', class_='node-publication-card__link')
                assert result_link

                title = card.find('h1', class_='node-publication-card__title')
                assert title

                # s2. Documents
                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                document_title = title.get_text().strip()
                print('\tdocument_title:\t', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href

                host = 'https://autoriteitpersoonsgegevens.nl'
                document_url = host + document_href

                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                except requests.exceptions.ConnectionError as error:
                    if to_print:
                        print("\tError:", error)
                    pass

                if document_response is None:
                    continue

                file_soup = BeautifulSoup(document_response.text, 'html.parser')
                file_item = file_soup.find('div', class_='node-publication-full__files-item')
                file_href = file_item.find('a').get('href')
                if not file_href.endswith('pdf'):
                    continue
                file_url = host + file_href
                print('\tdocument url: ', file_url)
                print('\tdocument hash: ', document_hash)

                try:
                    file_response = requests.request('GET', file_url)
                    file_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                except requests.exceptions.ConnectionError as error:
                    if to_print:
                        print("\tError:", error)
                    pass
                if file_response is None:
                    continue

                file_content = file_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Opinions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(file_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        try:
                            file_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(file_text)
                        except:
                            print('Failed to convert PDF to text')
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': document_title,
                            'md5': document_hash,
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': file_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

            # s1. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup, start_path="Opinions")
        return existed_docs

    def get_docs_publicDisclosure(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Netherlands public disclosure =========================")
        iteration = 1
        existed_docs = []

        pagination = self.update_pagination(start_path="PublicDisclosure")
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup
            article_list = results_soup.find('div', class_='view-search-onpage-publications-agreement-overview__content')
            assert article_list
            # s1. Results
            for card in article_list.find_all('div', class_='node-publication-card__content'):
                time.sleep(2)
                date_card = card.find('div', class_='node-publication-card__submitted')
                assert date_card
                date_str = date_card.get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue

                result_link = card.find('a', class_='node-publication-card__link')
                assert result_link

                title = card.find('h1', class_='node-publication-card__title')
                assert title

                # s2. Documents
                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                document_title = title.get_text().strip()
                print('\tdocument_title:\t', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href

                host = 'https://autoriteitpersoonsgegevens.nl'
                document_url = host + document_href

                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                except requests.exceptions.ConnectionError as error:
                    if to_print:
                        print("\tError:", error)
                    pass

                if document_response is None:
                    continue

                file_soup = BeautifulSoup(document_response.text, 'html.parser')
                file_item = file_soup.find('div', class_='node-publication-full__files-item')
                file_href = file_item.find('a').get('href')
                if not file_href.endswith('pdf'):
                    continue
                file_url = host + file_href
                print('\tdocument url: ', file_url)
                print('\tdocument hash: ', document_hash)

                try:
                    file_response = requests.request('GET', file_url)
                    file_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                except requests.exceptions.ConnectionError as error:
                    if to_print:
                        print("\tError:", error)
                    pass
                if file_response is None:
                    continue

                file_content = file_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Public Disclosure' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(file_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        try:
                            file_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(file_text)
                        except:
                            print('Failed to convert PDF to text')
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': document_title,
                            'md5': document_hash,
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': file_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

            # s1. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup, start_path="PublicDisclosure")
        return existed_docs

