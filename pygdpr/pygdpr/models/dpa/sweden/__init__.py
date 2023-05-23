import os
import math
import requests
import json
import time
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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy
import urllib3


class Sweden(DPA):
    def __init__(self, path=os.curdir):
        country_code='se'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path=None, current_page=1):
        source = {
            "host": "https://www.imy.se",
            "start_path_decisionsAndJudgements": "/tillsyner/",
            "start_path_publications": "/publikationer/"
        }
        host = source['host']
        if start_path == "decisionsAndJudgements":
            start_path = source['start_path_decisionsAndJudgements']
        else:
            start_path = source['start_path_publications']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path + "?query=&page=1")
        else:
            pagination = Pagination()
            for i in range(current_page, 1000):
                page_href = "?query=&page={}".format(i)
                pagination.add_item(host + start_path + page_href)
        return pagination

    def get_source(self, page_url=None, driver=None):
        assert (page_url is not None)
        results_response = None
        try:
            results_response = requests.request('GET', page_url, verify=False)
            results_response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            pass
        return results_response

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_decisionsAndJudgements(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Publications(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Guidances(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_decisionsAndJudgements(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n=============== Sweden Decision And Judgements =========================")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        iteration = 1
        existed_docs = []
        pagination = self.update_pagination(start_path="decisionsAndJudgements")
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            current_page = int(page_url[-1])
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                return existed_docs
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup
            result_list = results_soup.find('ul', class_='imy-search__results-list')
            if result_list is None:
                print('End of the link')
                return existed_docs
            assert result_list
            # s1. Results
            for li in result_list.find_all('li', class_='imy-search__results-item'):
                time.sleep(2)
                item_header = li.find('h2', class_='imy-search-hit__heading')
                assert item_header

                # s2. Documents
                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1
                document_title = item_header.get_text().strip()
                print('\tdocument_title:\t', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                # get the date of the document
                hit_body = li.find('p', class_='imy-search-hit__body')
                assert hit_body
                document_summary = hit_body.get_text()
                if 'Beslut' not in document_summary:
                    print('\tThis is an ongoing decision')
                    continue
                date_str = document_summary.split()[-1:]
                date_str = ''.join(date_str)
                # date_str only contains year, set a default date
                if len(date_str) == 4:
                    date_str = date_str + '-01-01'
                tmp = dateparser.parse(date_str, date_formats=['%d %B %Y'])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                print('\tdate:\t', date)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue

                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                item_link = li.find('a')
                assert item_link
                document_href = item_link.get('href')
                assert document_href
                document_url = document_href
                if to_print:
                    print("\tDocument:\t", document_hash)
                    print("\tdocument_url:\t", document_url)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url, verify=False)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup
                body_content = document_soup.find('div', class_='imy-body imy-contentpage__main-content')
                assert body_content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + "Decisions & judgements" + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    file_href = None
                    file_links = [link for link in body_content.find_all('a') if link.get('href').endswith('.pdf')]
                    for i in range(len(file_links)):
                        file_number = i+1
                        file_href = file_links[i].get('href')
                        host = "https://www.imy.se"
                        file_url = host + file_href
                        print("\t\tfile_url:\t", file_url)
                        file_response = None
                        try:
                            file_response = requests.request('GET', file_url, verify=False)
                            file_response.raise_for_status()
                        except requests.exceptions.HTTPError as error:
                            pass
                        if file_response is None:
                            continue
                        file_content = file_response.content
                        try:
                            with open(document_folder + '/' + self.language_code + '_' + str(file_number) + '.pdf', 'wb') as f:
                                f.write(file_content)
                            with open(document_folder + '/' + self.language_code + '_' + str(file_number) + '.txt', 'wb') as f:
                                document_text = textract.process(document_folder + '/' + self.language_code + '_' + str(file_number) + '.pdf')
                                f.write(document_text)
                        except:
                            with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                                document_text = newspage.get_text().strip()
                                f.write(document_text)
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
            current_page += 1
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup, start_path='decisionsAndJudgements', current_page=current_page)
        return existed_docs

    def get_docs_Publications(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n=============== Sweden Publications =========================")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        iteration = 1
        existed_docs = []
        pagination = self.update_pagination(start_path="publications")
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            current_page = int(page_url[-1])
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup
            result_list = results_soup.find('ul', {'id': 'imy-search__results-list-initial'})
            if result_list is None:
                print('End of the link')
                return existed_docs
            assert result_list
            # s1. Results
            for li in result_list.find_all('li', class_='imy-search__results-item'):
                time.sleep(2)
                item_created = li.find('time', class_='imy-search-hit__detail-text')
                assert item_created
                date_str = item_created.get('datetime')
                tmp = dateparser.parse(date_str, date_formats=['%d %B %Y'])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                item_header = li.find('h2', class_='imy-search-hit__heading')
                assert item_header
                # s2. Documents
                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1
                document_title = item_header.get_text().strip()
                print('\tdocument_title:\t', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                item_link = li.find('a')
                assert item_link
                document_href = item_link.get('href')
                assert document_href
                document_url = document_href
                if to_print:
                    print("\tDocument:\t", document_hash)
                    print("\tdocument_url:\t", document_url)
                    print("\tdate:\t", date_str)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url, verify=False)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup
                body_content = document_soup.find_all('div', class_='imy-info-block__content-container')
                assert body_content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + "Publications" + '/' + document_hash
                file_href = None
                file_link = body_content[-1].find('a', class_='imy-button')
                file_href = file_link.get('href')
                host = "https://www.imy.se"
                file_url = host + file_href
                # print('\tfile_url: ', file_url)
                file_response = None
                try:
                    file_response = requests.request('GET', file_url, verify=False)
                    file_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if file_response is None:
                    continue
                try:
                    os.makedirs(document_folder)

                    file_content = file_response.content
                    try:
                        with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                            f.write(file_content)
                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                    except:
                        with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                            document_text = newspage.get_text().strip()
                            f.write(document_text)
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
            current_page += 1
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup, start_path="publications", current_page=current_page)
        return existed_docs

    def get_docs_Guidances(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n=============== Sweden Guidances =========================")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        iteration = 1
        existed_docs = []
        source = {
            'host': 'https://www.imy.se',
            'start_path': '/verksamhet/dataskydd/dataskydd-pa-olika-omraden/',
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        exec_path = WebdriverExecPolicy().get_system_path()
        options = webdriver.ChromeOptions()
        options.add_argument('headless')
        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
        driver_doc.get(page_url)
        guidance_section = driver_doc.find_element_by_xpath('//*[@id="readspeaker-content"]/div/div[2]/div[1]/nav/div/ul/li/ul/li[4]')
        for i in range(1, 9):
            guidance = guidance_section.find_element_by_xpath(
                '//*[@id="imy-content-menu__container-4a9aebd2-5a49-4b05-ab9c-ad1640c36a47"]/ul/li[' + str(i) + ']')
            title = guidance.find_element_by_xpath('//*[@id="imy-content-menu__container-4a9aebd2-5a49-4b05-ab9c-ad1640c36a47"]/ul/li['+ str(i)+']/div[1]/a/span')

            print('\n------------ Document ' + str(iteration) + ' ------------')
            iteration += 1

            document_title = title.get_attribute('textContent')
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            print("\tdocument title:\t", document_title)
            print("\tdocument hash:\t", document_hash)
            dpa_folder = self.path
            document_folder = dpa_folder + '/' + "Guidance" + '/' + document_hash
            try:
                os.makedirs(document_folder)

                elems = guidance.find_elements_by_tag_name('a')
                for j in range(len(elems)):
                    file_number = j+1
                    file_url = elems[j].get_attribute('href')
                    # the main url
                    exec_path = WebdriverExecPolicy().get_system_path()
                    options = webdriver.ChromeOptions()
                    options.add_argument('headless')
                    driver_file = webdriver.Chrome(options=options, executable_path=exec_path)
                    driver_file.get(file_url)
                    if j == 0:
                        document_url = file_url
                        print("\tdocument url:\t", document_url)
                        date_container = driver_file.find_element_by_class_name('imy-contentpage__date-container').get_attribute('textContent')
                        date_str = date_container.split(':')[-1].strip()
                        tmp = dateparser.parse(date_str, date_formats=['%d %B %Y'])
                        date = datetime.date(tmp.year, tmp.month, tmp.day)
                        print("\tdate:\t", date)
                        if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                            continue
                    try:
                        body_content = driver_file.find_element_by_xpath('//*[@id="readspeaker-content"]/div/div[2]/div[2]')
                    except:
                        body_content = driver_file.find_element_by_xpath('//*[@id="readspeaker-content"]/div[2]/div[2]/div/div[1]')
                    assert body_content
                    file_text = body_content.get_attribute('textContent')
                    with open(document_folder + '/' + self.language_code + '_' + str(file_number) + '.txt', 'w') as f:
                        f.write(file_text)
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
        return existed_docs


