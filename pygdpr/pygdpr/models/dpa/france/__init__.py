import os
import math
import random

import requests
import json
import datetime
import hashlib
import dateparser
from pygdpr.models.dpa import DPA, MaxRetriesError
from bs4 import BeautifulSoup
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy
from striprtf.striprtf import rtf_to_text
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy
from urllib.parse import urlparse
from pygdpr.models.document import *
import time
import textract

class France(DPA):
    def __init__(self, path=os.curdir):
        country_code='FR'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path="decisions"):
        source = {
            "host": "https://www.cnil.fr",
            "start_path_decisions": "/fr/deliberations",
            "start_path_notices": "/thematique/cnil/mises-en-demeure",
            "start_path_guidelines": "/fr/decisions/lignes-directrices-recommandations-CNIL",
            "start_path_recommendation": "/fr/decisions/lignes-directrices-recommandations-CNIL?field_scald_collection_tid=1466",
            "start_path_reports": "/fr/tag/Rapport+annuel"
        }
        host = source['host']
        if start_path == "decisions":
            start_path = source['start_path_decisions']
        elif start_path == "notices":
            start_path = source['start_path_notices']
        elif start_path == "guidelines":
            start_path = source['start_path_guidelines']
        elif start_path == "recommendations":
            start_path = source['start_path_recommendation']
        else:
            start_path = source['start_path_reports']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pager_load_more = page_soup.find('ul', class_='pager-load-more')
            if pager_load_more is not None:
                pager_next = pager_load_more.find('li', class_='pager-next')
                page_link = pager_next.find('a')
                if page_link is not None:
                    page_href = page_link.get('href')
                    pagination = Pagination()
                    pagination.add_item(host + page_href)
        return pagination

    def get_source(self, page_url=None, driver=None):
        assert page_url is not None
        results_response = None
        try:
            results_response = requests.request('GET', page_url, timeout=1000)
            results_response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            pass
        return results_response

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_Decisions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Notices(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Guidelines(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Reports(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        pagination = self.update_pagination()
        print("\n========================= France Decision Documents ===========================")
        iterator = 1
        dict_hashcode = {}
        '''
        added_docs_set = set()
        url = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
        client_id = "6e3f9505-809f-45c6-9f93-02ac69f4b384"
        client_secret = "568524c8-8af7-4b48-9602-853882797fb6"
        #client_id = os.environ["PISTE_CLIENT_ID"]
        #client_secret = os.environ["PISTE_CLIENT_SECRET"]
        assert client_id and client_secret
        data = {
            "6c214ae3d2edc9c49a419f7870fe47f7": "1",
            "grant_type": "client_credentials",
            "client_id": "6e3f9505-809f-45c6-9f93-02ac69f4b384",
            "client_secret": "568524c8-8af7-4b48-9602-853882797fb6",
            #"client_id": os.environ["PISTE_CLIENT_ID"],
            #"client_secret": os.environ["PISTE_CLIENT_SECRET"],
            "scope": "openid"
        }
        payload = '&'.join([k + "=" + v for k, v in data.items()])
        headers = {
            'Content-Type': "application/x-www-form-urlencoded",
            'cache-control': "no-cache"
        }
        response = requests.request("GET", url, data=payload, headers=headers, timeout=1000)
        '''
        while pagination.has_next():
            page_url = pagination.get_next()
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            # s1. Results
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            # print(results_soup)
            assert results_soup
            view_content = results_soup.find('div', class_='view-content')
            assert view_content
            for views_row in view_content.find_all('div', class_='views-row'):
                time.sleep(2)
                result_link = views_row.find('a')
                document_href = result_link.get('href')

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1

                # use selenium to bypass incapsula protection
                exec_path = WebdriverExecPolicy().get_system_path()
                options = webdriver.ChromeOptions()
                options.add_argument('headless')
                driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                driver_doc.get(document_href)
                document_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')
                '''
                document_response = None
                try:
                    document_response = requests.request('GET', document_href, timeout=1000)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                # print(document_soup) will show "Request unsuccessful. Incapsula incident ID..."
                '''
                assert document_soup
                # print(document_soup)

                main_container = document_soup.find('div', class_='container main-container')
                if main_container is None:
                    print("\tNo content available in this doc")
                    continue
                head_code_page = main_container.find('div', class_='head-code-page')
                assert head_code_page

                if head_code_page.find('h1', class_='main-title') is None:
                    print("\tNo content available in this doc")
                    continue
                document_title = head_code_page.find('h1', class_='main-title').get_text()
                print("\tDocument Title", document_title)
                print("\tdocument_href: ", document_href)

                date_text = document_title.split()[-3:]
                date_str = ' '.join(date_text)
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                # print('date:', tmp.year, tmp.month, tmp.day)
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("Before GDPR , stop.")
                    # break
                    return existed_docs
                print("\tdate: ", date)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                # documents have the same hashcode, but different dates
                date_part = str(date).replace('-', '_')
                if document_hash in dict_hashcode:
                    document_hash = document_hash + '-' + date_part

                print('\tdocument_hash: ', document_hash)

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decisions & Deliberations' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    main_content = document_soup.find('div', class_='main-col cnil')
                    main_text = main_content.get_text()
                    # print(main_text)
                    with open(
                            document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        f.write(main_text)
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': document_href
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(document_hash)
                    dict_hashcode[document_hash] = date_part
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
                
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs

    def get_docs_Notices(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= France Notices ===========================")
        iterator = 1
        existed_docs = []
        pagination = self.update_pagination(start_path="notices")
        while pagination.has_next():
            page_url = pagination.get_next()
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            # s1. Results
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            # print(results_soup)
            assert results_soup
            view_content = results_soup.find('div', class_='view-content')
            assert view_content
            for views_row in view_content.find_all('div', class_='views-row'):
                time.sleep(2)
                print('\n------------ Document: ' + str(iterator) + ' ------------')
                iterator += 1

                result_link = views_row.find('a')
                document_href = result_link.get('href')
                host = "https://www.cnil.fr"
                document_url = host + document_href

                document_title = result_link.get_text()
                print("\tDocument Title: ", document_title)
                print("\tDocument URL: ", document_url)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_response = None
                try:
                    # document_response = requests.request('GET', document_href, timeout=1000)
                    document_response = requests.get(document_url, timeout=1000)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                main_wrapper = document_soup.find('div', class_='main-wrapper')
                content = main_wrapper.find('div', class_='region region-content')
                date_str = content.find('div', class_='ctn-gen-auteur').get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                # print('date:', tmp.year, tmp.month, tmp.day)
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("This document was published before the GDPR release")
                    continue
                print("\tdate: ", date)
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Notices' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    main_text = content.get_text()
                    # print(main_text)
                    with open(
                            document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        f.write(main_text)
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
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
                    print("\tDirectory path already exists, continue.")

            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs

    def get_docs_Guidelines(self, existing_docs=[], overwrite=False, to_print=True):
        existing_docs = []
        existing_docs += self.get_docs_Guidelines_part(existing_docs=[], overwrite=False, to_print=True)
        existing_docs += self.get_docs_Recommendations_part(existing_docs=[], overwrite=False, to_print=True)
        return existing_docs

    def get_docs_Guidelines_part(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= France Guidelines Part1 ===========================")
        existed_docs_guidelines_part = []
        pagination = self.update_pagination(start_path="guidelines")
        while pagination.has_next():
            page_url = pagination.get_next()
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            # s1. Results (guidelines)
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            # print(results_soup)
            assert results_soup
            view_content = results_soup.find('div', class_='view-content')
            assert view_content
            for views_row in view_content.find_all('div', class_='views-row'):
                time.sleep(5)
                result_link = views_row.find('a')
                document_href = result_link.get('href')
                print("document_href: ", document_href)
                document_title = result_link.get_text().strip()
                print("\tdocument_title: ", document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_response = None
                try:
                    document_response = requests.request('GET', document_href)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Guidelines' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': "05/25/2018",
                            'url': document_href
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs_guidelines_part.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs_guidelines_part

    def get_docs_Recommendations_part(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= France Guidelines Part2 ===========================")
        existed_docs_recommendations_part = []
        pagination = self.update_pagination(start_path="recommendations")
        while pagination.has_next():
            page_url = pagination.get_next()
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            # s1. Results (guidelines)
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            # print(results_soup)
            assert results_soup
            view_content = results_soup.find('div', class_='view-content')
            assert view_content
            for views_row in view_content.find_all('div', class_='views-row'):
                time.sleep(5)
                result_link = views_row.find('a')
                document_href = result_link.get('href')

                print("document_href: ", document_href)
                document_title = result_link.get_text().strip()
                print("\tdocument_title: ", document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_response = None
                try:
                    document_response = requests.request('GET', document_href)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Guidelines' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                                'md5': document_hash,
                                'releaseDate': "05/25/2018",
                                'url': document_href
                            }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs_recommendations_part.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs_recommendations_part

    def get_docs_Reports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= France Reports ===========================")
        existed_docs = []
        pagination = self.update_pagination(start_path="reports")
        while pagination.has_next():
            page_url = pagination.get_next()
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            # s1. Results
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            # print(results_soup)
            assert results_soup
            view_content = results_soup.find('div', class_='view-content')
            assert view_content
            for views_row in view_content.find_all('div', class_='views-row'):
                time.sleep(5)
                result_link = views_row.find('a')
                document_href = result_link.get('href')
                host = "https://www.cnil.fr"
                document_url = host + document_href
                print("document_url: ", document_url)
                document_title = result_link.get_text()
                print("\tdocument_title: ", document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_response = None
                try:
                    # document_response = requests.request('GET', document_href, timeout=1000)
                    document_response = requests.get(document_url, timeout=1000)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                main_wrapper = document_soup.find('div', class_='main-wrapper')
                content = main_wrapper.find('div', class_='region region-content')
                date_str = content.find('div', class_='ctn-gen-auteur').get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                # print('date:', tmp.year, tmp.month, tmp.day)
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("This document was published before the GDPR release")
                    continue
                print("\tdate: ", date)
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Reports' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                
                    main_text = content.get_text()
                    # print(main_text)
                    with open(
                            document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        f.write(main_text)
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
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
                    print("\tDirectory path already exists, continue.")

            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs