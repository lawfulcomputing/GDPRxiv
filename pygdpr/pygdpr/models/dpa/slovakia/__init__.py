import os
import math
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
import docx2txt
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy
from selenium.webdriver.common.keys import Keys
import time

class Slovakia(DPA):
    def __init__(self, path=os.curdir):
        country_code='sk'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://dataprotection.gov.sk",
            "start_path": "/uoou/sk/main-content/metodiky-uradu"
        }
        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pager = page_soup.find('ul', class_='pager')
            if pager is not None:
                for li in pager.find_all('li', class_='pager-item'):
                    page_link = li.find('a')
                    if page_link is None:
                        continue
                    page_href = page_link.get('href')
                    pagination.add_item(host + page_href)
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
        added_docs += self.get_docs_fineAndReports(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_opinions(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_fineAndReports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Slovakia Fine And Reports =========================")
        iteration = 1
        existed_docs = []
        source = {
            'host': 'https://dataprotection.gov.sk/',
            'start_path': '/uoou/sk/content/vyrocne-spravy',
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        content_clearfix = results_soup.find('div', class_='content clearfix')
        # print(content_clearfix)
        assert content_clearfix

        for document in content_clearfix.find_all('div', class_='filefield-file'):
            valid_document = True
            document_href = document.find('a').get('href')
            document_title = document.find('a').get_text()
            # check the document date. Ignore all the documents released before 2018
            document_title_list = document_title.split()
            for i in range(len(document_title_list)):
                # ignore all the documents contain word which is digit && smaller than 2018
                if document_title_list[i].isdigit() and int(document_title_list[i]) < 2018:
                    valid_document = False
                    break
                # future check whether a word contain digit which is smaller than 2018
                sub_word = document_title_list[i].split('-')[0]
                if sub_word < '2018':
                    valid_document = False
                    break
            if valid_document:
                document_url = document_href

                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                print("\tdocument_url:\t", document_url)
                print("\tdocument_title:\t", document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                year_of_release = document_title_list[-1]
                print('\tyear: ', year_of_release)
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
                document_folder = dpa_folder + '/' + 'Fine & Reports' + '/' + document_hash
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
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': year_of_release,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
        return existed_docs

    def get_docs_opinions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Slovakia Opinions =========================")
        iteration = 1
        existed_docs = []
        pagination = self.update_pagination()
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
            view_content_index = 1
            region_content = results_soup.find('div', class_='region-content')
            assert region_content
            content = region_content.find('div', class_='content')
            assert content
            # s1. Results
            for node_file in content.find_all('div', class_='node-file'):
                b = node_file.find('b')
                assert b
                date_str = b.get_text().split(' - ')[0]
                date_str = date_str.strip()
                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                h2 = node_file.find('h2')
                assert h2
                result_link = h2.find('a')
                assert result_link
                # s2. Documents
                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                document_title = result_link.get_text()
                print('\tdocument_title:\t', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                host = "https://dataprotection.gov.sk"
                document_url = host + document_href
                if to_print:
                    print("\tDocument:\t", document_hash)
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
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Opinions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    document_soup = BeautifulSoup(document_response.text, 'html.parser')
                    assert document_soup
                    content_clearfix = document_soup.find('div', class_='content clearfix')
                    number = 0
                    for field_file in content_clearfix.find_all('div', class_='filefield-file'):
                        number += 1
                        assert len(field_file) > 0
                        article_url = field_file.find('a').get('href')
                        print('\tarticle_url: ', article_url)
                        file_number = ('_' + str(number)) if number > 0 else ''
                        # article is a docx file. Downloaded location "/documents/docx_files"
                        if article_url.endswith('.docx'):
                            # set a download path. Use selenium to download it
                            exec_path = WebdriverExecPolicy().get_system_path()
                            options = webdriver.ChromeOptions()
                            prefs = {"download.default_directory": document_folder}
                            options.add_argument('headless')
                            options.add_experimental_option("prefs", prefs)
                            driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                            # open google search, and put the document_url into search box, and press enter
                            driver_doc.get('https://www.google.com/')
                            box = driver_doc.find_element_by_xpath(  # google search box xpath
                                '/html/body/div[1]/div[3]/form/div[1]/div[1]/div[1]/div/div[2]/input')
                            box.send_keys(article_url)
                            box.send_keys(Keys.ENTER)
                            # the first result in the search is the file we need. Click the link to download it
                            download_section = driver_doc.find_element_by_class_name('tF2Cxc')
                            button = download_section.find_element_by_tag_name('h3').click()
                            time.sleep(5)
                            files = os.listdir(document_folder)
                            for index, file in enumerate(files):
                                os.rename(os.path.join(document_folder, file),
                                          os.path.join(document_folder, self.language_code + '.docx'))
                            document_content = docx2txt.process(document_folder + '/' + self.language_code + '.docx')
                            with open(
                                    document_folder + '/' + self.language_code + '.txt', 'w') as f:
                                f.write(document_content)
                        else:
                            document_response = None
                            try:
                                document_response = requests.request('GET', article_url)
                                document_response.raise_for_status()
                            except requests.exceptions.HTTPError as error:
                                if to_print:
                                    print(error)
                                pass
                            if document_response is None:
                                continue
                            document_content = document_response.content
                            with open(document_folder + '/' + self.language_code + file_number + '.pdf', 'wb') as f:
                                f.write(document_content)

                            with open(document_folder + '/' + self.language_code + file_number + '.txt', 'wb') as f:
                                document_text = textract.process(document_folder + '/' + self.language_code + file_number + '.pdf')
                                document_text = document_text.strip()
                                f.write(document_text)

                        with open(document_folder + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': document_title,
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
            print('\n')
        return existed_docs




