import os
import math
import requests
import json
import datetime
import hashlib
import dateparser
import re
import csv
import time
from pygdpr.models.dpa import DPA
from bs4 import BeautifulSoup
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy
import textract
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy
import sys


class Malta(DPA):
    def __init__(self, path=os.curdir):
        country_code='mt'
        super().__init__(country_code, path)

    # Method never called
    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://idpc.org.mt",
            "start_path": "https://idpc.org.mt"
        }
        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            page_url = host + start_path
            exec_path = WebdriverExecPolicy().get_system_path()
            options = webdriver.ChromeOptions()
            options.add_argument('headless')
            driver = webdriver.Chrome(options=options, executable_path=exec_path)
            driver.get(page_url)
            pagination = Pagination()
            pagination.add_item(driver)
        else:
            news_pagination = driver.find_element_by_id('news-pagination')
            page_btn = news_pagination.find_element_by_class_name('page-btn')
            old_news_entries = driver.find_elements_by_class_name('news-entry')
            page_btn.click()
            time.sleep(20)
            news_entries = driver.find_elements_by_class_name('news-entry')
            if len(news_entries) > len(old_news_entries):
                pagination = Pagination()
                pagination.add_item(driver)
        return pagination

    def get_source(self, page_url=None, driver=None, to_print=True):
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
        added_docs += self.get_docs_Guidelines(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_NewsArticles(existing_docs=[], overwrite=False, to_print=True)

        return added_docs

    def get_docs_Guidelines(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Malta Guidelines =========================")
        added_docs = []

        page_url = 'https://idpc.org.mt/for-organisations/guidelines/'
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit("Couldn't connect to base url")

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        body = results_soup.find('body')
        assert body

        vce_text = body.find('div', class_='vce-text-block-wrapper', id='el-88463f26')
        assert vce_text

        iteration = 1
        for p_tag in vce_text.find_all('p'):
            assert p_tag

            # Check if the p_tag leads to link
            try:
                a_tag = p_tag.find('a')
                assert a_tag
            except:
                continue

            print('\n------------ Document: ' + str(iteration) + '-------------')
            iteration += 1

            # Concatenate p_tag and a_tag text as there is some inconsistency regarding which tag gets the title text
            document_title = p_tag.get_text()
            print('\tDocument Title: ' + document_title)
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            document_href = a_tag.get('href')
            assert document_href

            # Check if the href contains the full link address
            if document_href.startswith('http') is False:
                # Remove the unnecessary first 5 characters from document_href
                href_stripped = document_href[4:]
                document_url = 'https://idpc.org.mt' + href_stripped
            else:
                document_url = document_href

            print('\tDocument URL: ' + document_url)
            if to_print:
                print("\tDocument: ", document_hash)

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
            document_folder = dpa_folder + '/' + 'Guidelines' + '/' + document_hash

            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_response.content)

                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                    try:
                        document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                    except:
                        pass

                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': 'Date not available',
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                added_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        return added_docs

    def get_docs_NewsArticles(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Malta News Articles =========================")
        added_docs = []

        # old link:
        # page_url = 'https://idpc.org.mt/news/'

        # new link:
        page_url = 'https://idpc.org.mt/news-latest/'
        if to_print:
            print('Page:\t', page_url)

        # Use selenium to get html parse object in order to show ALL html elements
        exec_path = WebdriverExecPolicy().get_system_path()
        options = webdriver.ChromeOptions()
        options.add_argument('headless')
        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
        driver_doc.get(page_url)

        # The new link don't have "show more button", ignore below code
        '''
        # Click the show more button on the page
        show_button = driver_doc.find_element_by_class_name('page-btn')
        while show_button.text != 'No More posts':
            show_button.click()
            show_button = driver_doc.find_element_by_class_name('page-btn')

        time.sleep(5)
        '''

        # Now that we have view of all news articles, create parse object
        results_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')
        assert results_soup

        body = results_soup.find('body')
        assert body

        container = body.find('div', class_='news-list-container')
        assert container

        iteration = 1
        for div in container.find_all('div', Recursive=False):
            assert div

            a_tag = div.find('a', class_='link')
            # Some div's don't have a_tag that contains href -> they are random webpage display elements
            try:
                assert a_tag
            except:
                continue

            print('\n------------ Document: ' + str(iteration) + '-------------')
            iteration += 1

            document_href = a_tag.get('href')
            assert document_href

            # Check if the href contains the full link address
            if document_href.startswith('http') is False:

                document_url = 'https://idpc.org.mt' + document_href
            else:
                document_url = document_href

            print('\tDocument URL: ' + document_url)

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

            document_soup = BeautifulSoup(document_response.text, 'html.parser')
            assert document_soup

            document_title = ''
            document_text = ''

            document_body = document_soup.find('body')
            assert document_body

            entry_content = document_body.find('div', class_='entry-content')
            assert entry_content

            # Want the second tag with class vce-row-container
            vce_row_list = entry_content.find_all('div', class_='vce-row-container')
            vce_row = vce_row_list[1]
            assert vce_row

            # This tag is what contains the entire document text
            vce_row_content = vce_row.find('div', class_='vce-row-content')
            assert vce_row_content

            # Now get the document title
            vce_row_two = vce_row_list[0]
            assert vce_row_two

            vce_content = vce_row_two.find('div', class_='vce-row-content')
            assert vce_content

            text_wrapper = vce_content.find('div', class_='vce-text-block-wrapper vce')
            assert text_wrapper

            # Set doc title and text
            document_title = text_wrapper.get_text()
            document_text = vce_row_content.get_text()

            print('\tDocument Title: ' + document_title)
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            if to_print:
                print("\tDocument: ", document_hash)

            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'News Letters' + '/' + document_hash

            try:
                os.makedirs(document_folder)

                # Examine the document page for pdf links and download those encountered
                pdf_iteration = 1
                for p_tag in vce_row_content.find_all('p'):
                    assert p_tag
                    if p_tag.find('a') is not None:
                        a_tag = p_tag.find('a')
                        assert a_tag

                        href = a_tag.get('href')
                        assert href

                        # If we find a pdf link -> get the pdf
                        if href.endswith('.pdf'):
                            pdf_response = None
                            try:
                                pdf_response = requests.request('GET', href)
                                pdf_response.raise_for_status()
                            except requests.exceptions.HTTPError as error:
                                if to_print:
                                    print(error)
                                pass
                            if pdf_response is None:
                                continue

                            print("\tDownloading PDF: " + href)


                            with open(document_folder + '/' + self.language_code + str(pdf_iteration) + '.pdf', 'wb') as f:
                                f.write(pdf_response.content)
                            with open(document_folder + '/' + self.language_code + str(pdf_iteration) + '.txt', 'wb') as f:
                                link_text = textract.process(document_folder + '/' + self.language_code + str(pdf_iteration)
                                                             + '.pdf')
                                f.write(link_text)
                            pdf_iteration += 1
                    # No <a tags
                    else:
                        pass

                # Now download the document (summary) text
                with open(document_folder + '/' + self.language_code + 'Summary' + '.txt', 'wb') as f:
                    f.write(document_text.encode())

                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': 'Date not available',
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                added_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        return added_docs
