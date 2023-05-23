import os
import math
import requests
import json
import datetime
from pygdpr.models.dpa import DPA
from bs4 import BeautifulSoup
from bs4.dammit import EncodingDetector
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from urllib.parse import urlparse
import hashlib
import textract
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy
import urllib3

class Bulgaria(DPA):
    def __init__(self, path=os.curdir):
        country_code='BG'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path=''):
        source = {
            'host': 'https://www.cpdp.bg/index.php',
            'start_path': start_path
        }
        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pages = page_soup.find('div', class_='pages')
            if pages is not None:
                for page_link in pages.find_all('a'):
                    page_href = page_link.get('href')
                    pagination.add_item('https://www.cpdp.bg' + page_href)
        return pagination

    def get_source(self, page_url=None, driver=None):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        assert (page_url is not None)
        results_response = None
        try:
            results_response = requests.request('GET', page_url, verify=False)

            results_response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            if to_print:
                print(error)
            pass
        return results_response

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_DecJudgeOpinion(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_DecJudgeOpinion(self, existing_docs=[], overwrite=False, to_print=True):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        print("\n========================= Bulgaria Decisions, Judgements and Opinions ===========================")
        existed_docs = []
        source = {
            'host': 'https://www.cpdp.bg',
            'start_path': '/index.php?p=rubric&aid=3'
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("This url is not exist.")
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        center_part = results_soup.find('div', class_='center-part')
        assert center_part
        for li in center_part.find_all('li'):
            time.sleep(1)
            href = li.find('a').get('href')
            document_type = li.find('a').get_text()
            document_host = 'https://www.cpdp.bg/index.php'

            year = ''
            for word in document_type.split():
                if word.isdigit():
                    year = str(word)
            # ignore all the documents before GDPR release
            if year < '2018':
                continue
            #print('document_type: ', document_type)
            #print('year: ', year)

            pagination = self.update_pagination(start_path=href)
            while pagination.has_next():
                page_url = pagination.get_next()
                if to_print:
                    print('\tPage: \t', page_url)
                page_soup = self.get_source(page_url=page_url)
                if page_soup is None:
                    continue
                document_soup = BeautifulSoup(page_soup.text, 'html.parser')
                assert document_soup
                center_part = document_soup.find('div', class_='center-part')
                dpa_folder = self.path
                # type 1 structure: Решения на ВАС
                time.sleep(1)
                if 'Решения на ВАС' in document_type:
                    print("SCA Descisons")
                    for articles in center_part.find_all('a'):
                        document_url = articles.get('href')
                        document_title = articles.get_text()
                        if len(document_title) != 1 and document_url.startswith('https:'):
                            print('\ndocument_title: ', document_title)
                            print('\tdocument_href: ', document_url)
                            document_hash = hashlib.md5(document_title.encode()).hexdigest()
                            print('\tdocument_hash: ', document_hash)
                            if document_hash in existed_docs:
                                continue
                            existed_docs.append(document_hash)
                            if document_hash in existing_docs and overwrite == False:
                                if to_print:
                                    print('\tSkipping existing document:\t', document_hash)
                                continue
                            document_folder = dpa_folder + '/' + 'SCA Decisions' + '/' + document_hash

                            try:
                                os.makedirs(document_folder)
                                exec_path = WebdriverExecPolicy().get_system_path()
                                options = webdriver.ChromeOptions()
                                options.add_argument('headless')
                                driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                                driver_doc.get(document_url)
                                lotusContent = driver_doc.find_element_by_class_name('lotusContent')
                                body_text = lotusContent.text
                                with open(
                                        document_folder + '/' + self.language_code + '.txt',
                                        'w') as f:
                                    f.write(body_text)
                                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                                    metadata = {
                                        'title': {
                                            self.language_code: document_title
                                        },
                                        'md5': document_hash,
                                        'releaseDate': 'Need to add',
                                        # 'releaseDate': date.strftime('%d/%m/%Y'),
                                        'url': document_url
                                    }
                                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                            except FileExistsError:
                                print("\tDirectory path already exists, continue.")

                # type 2 structure: Решения на административни съдилища
                elif 'административни съдилища' in document_type or 'Решения на АССГ' in document_type:
                    print('Courts Decisions')
                    for articles in center_part.find_all('a'):
                        if articles.get('href').endswith('.pdf'):
                            document_title = articles.get_text()

                            document_href = articles.get('href')
                            document_url = host + document_href
                            print('\ndocument_title: ', document_title)
                            print('\tdocument_url: ', document_url)
                            document_hash = hashlib.md5(document_title.encode()).hexdigest()
                            if document_hash in existed_docs:
                                continue
                            print('\tdocument_hash: ', document_hash)
                            existed_docs.append(document_hash)
                            if document_hash in existing_docs and overwrite == False:
                                if to_print:
                                    print('\tSkipping existing document:\t', document_hash)
                                continue

                            document_folder = dpa_folder + '/' + 'Courts Decisions' + '/' + document_hash
                            try:
                                os.makedirs(document_folder)
                                file_response = None
                                try:
                                    file_response = requests.request('GET', document_url, verify=False)
                                    file_response.raise_for_status()
                                except requests.exceptions.HTTPError as error:
                                    if to_print:
                                        print(error)
                                    pass
                                if file_response is None:
                                    continue
                                if len(file_response.text) == 0:
                                    continue
                                file_content = file_response.content
                                if file_content is None:
                                    continue
                                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                                    f.write(file_content)
                                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                                    document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                                    f.write(document_text)
                                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                                    metadata = {
                                        'title': {
                                            self.language_code: document_title
                                        },
                                        'md5': document_hash,
                                        'releaseDate': 'Need to add',
                                        # 'releaseDate': date.strftime('%d/%m/%Y'),
                                        'url': document_url
                                    }
                                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                            except FileExistsError:
                                print("\tDirectory path already exists, continue.")
                # type 3 Решения на КЗЛД по жалби, сигнали и други искания AND Становища на КЗЛД
                else:
                    print("CPDP Decisions or Opinion")
                    for div in center_part.find_all('div', class_='news-home'):
                        news_content = div.find('div', class_='news-content')
                        assert news_content
                        h6 = news_content.find('h6')
                        assert h6
                        result_link = h6.find('a')
                        assert result_link
                        document_title = result_link.get_text()
                        print('\ndocument title: ', document_title)
                
                        document_hash = hashlib.md5(document_title.encode()).hexdigest()
                        if document_hash in existed_docs:
                            continue
                        existed_docs.append(document_hash)
                        if document_hash in existing_docs and overwrite == False:
                            if to_print:
                                print('\tSkipping existing document:\t', document_hash)
                            continue
                        article_href = result_link.get('href')
                        article_url = document_host + article_href
                        print('\tdocument_url: ', article_url)
                        print('\tdocument_hash: ', document_hash)

                        document_folder = dpa_folder + '/' + 'CPDP Decisions or Opinion' + '/' + document_hash
                        try:
                            os.makedirs(document_folder)
                            file_response = None
                            try:
                                file_response = requests.request('GET', article_url, verify=False )
                                file_response.raise_for_status()
                            except requests.exceptions.HTTPError as error:
                                if to_print:
                                    print(error)
                                pass
                            if file_response is None:
                                continue
                            if len(file_response.text) == 0:
                                continue
                            file_soup = BeautifulSoup(file_response.text, 'html.parser')
                            body_content = file_soup.find('div', class_='center-part')
                            body_text = body_content.get_text()
                           
                            with open(
                                    document_folder + '/' + self.language_code + '.txt', 'w') as f:
                                f.write(body_text)
                            with open(document_folder + '/' + 'metadata.json', 'w') as f:
                                metadata = {
                                    'title': {
                                        self.language_code: document_title
                                    },
                                    'md5': document_hash,
                                    'releaseDate': 'Need to add',
                                    'url': article_url
                                }
                                json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                        except FileExistsError:
                            print("\tDirectory path already exists, continue.")
                print('\n')
                pagination = self.update_pagination(pagination=pagination, page_soup=document_soup, start_path=href)
        return existed_docs

    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        print("\n========================= Bulgaria Annual Reports ===========================")
        existed_docs = []
        source = {
            'host': 'https://www.cpdp.bg',
            'start_path': '/index.php?p=rubric&aid=14'
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("This url is not exist.")
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        center_part = results_soup.find('div', class_='center-part')
        assert center_part
        for ul in center_part.find_all('ul'):
            time.sleep(1)
            href = ul.find('a').get('href')
            document_title = ul.find('a').get_text()
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            host_2 = 'https://www.cpdp.bg/index.php'
            document_url = host_2 + href
            year = document_title.split(' ')[-2]
            if year < '2018':
                break
            print('\ndocument_title :', document_title)
            print('\tdocument_url: ', document_url)
            #print('year: ', year)
            page_soup = self.get_source(page_url=document_url)
            if page_soup is None:
                continue
            document_soup = BeautifulSoup(page_soup.text, 'html.parser')
            assert document_soup
            center_part = document_soup.find('div', class_='center-part')
            for a in center_part.find_all('a'):
                if 'PDF' in a.get_text():
                    article_href = a.get('href')
                    article_title = a.get_text()
                    #print('\tarticle_href: ', article_href)
                    print('\tarticle_title: ', article_title)
                    if article_href.startswith('download'):
                        file_url = host + '/' + article_href
                        print('\tfile_url: ', file_url)
                    file_response = None
                    try:
                        file_response = requests.request('GET', file_url, verify=False)
                        file_response.raise_for_status()
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if file_response is None:
                        continue
                    if len(file_response.text) == 0:
                        continue
                    file_content = file_response.content
                    if file_content is None:
                        continue
                    dpa_folder = self.path

                    document_folder = dpa_folder + '/' + 'Annual Reports' + '/' + document_hash
                    try:
                        os.makedirs(document_folder)
                        with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                            f.write(file_content)
                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                        with open(document_folder + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': {
                                    self.language_code: document_title
                                },
                                'md5': document_hash,
                                'releaseDate': year,
                                'url': document_url
                            }
                            json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                        print('\n')
                        existed_docs.append(document_hash)
                    except FileExistsError:
                        print("Directory path already exists, continue.")
        return existed_docs






