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

class Lithuania(DPA):
    def __init__(self, path=os.curdir):
        country_code='lt'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://vdai.lrv.lt",
            "start_path": "/lt/naujienos/exportPublicData?export_data_type=csv&download=1"
        }
        host = source["host"]
        start_path = source["start_path"]
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        return pagination

    def get_source(self, page_url=None, driver=None):
        assert (page_url is not None)
        results_response = None
        # headers = {
        #    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36"
        # }
        try:
            # results_response = requests.get(page_url, headers=headers, timeout=10)
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
        added_docs += self.get_docs_Guidelines(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_InspectionReports(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://vdai.lrv.lt",
            "start_path": "/lt/naudinga-informacija/vdai-sprendimai-baudos-nurodymai-ir-kt"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)

        # HTTPError: 503 Server Error: Service Temporarily Unavailable for url
        page_source = self.get_source(page_url=page_url)

        # try to use selenium, but failed
        # exec_path = WebdriverExecPolicy().get_system_path()
        # options = webdriver.ChromeOptions()
        # options.add_argument('headless')
        # driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
        # driver_doc.get(page_url)
        # print(driver_doc.page_source)

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        content = results_soup.find('div', class_='content text')
        year_list = []
        for p in content.find_all('p'):
            potential_year = p.get_text().strip()
            if potential_year.isdigit():
                year = potential_year
                year_list.append(year)
            document_section = p.find('a')
            if document_section is None:
                continue
            for documents in p.find_all('a'):
                document_href = documents.get('href')
                document_title = documents.get_text()
                if not document_href.endswith('pdf'):
                    continue
                document_url = host + document_href
                #print('document_url: ', document_url)
                print('document_title: ', document_title)
                date_str = document_title.split()[-1]

                # check whether the title contain date
                # if not, use the default date: year-01-01
                if not date_str[0].isdigit():
                    date_str = year_list[-1] + '-01-01'
                else:
                    date_str = date_str
                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                print('\tdate: ', date)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if document_response is None:
                    continue
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                except FileExistsError:
                    pass
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
                        'releaseDate': date.strftime('%d/%m/%Y'),
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                existed_docs.append(document_hash)
        return existed_docs

    def get_docs_Guidelines(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://vdai.lrv.lt",
            "start_path": "/lt/naudinga-informacija/rekomendacijos-gaires-ir-kt"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        panel = results_soup.find('div', class_='panel-group')
        for p in panel.find_all('p'):
            for documents in p.find_all('a'):
                time.sleep(5)
                document_href = documents.get('href')
                document_title = documents.get_text()
                if not document_href.endswith('pdf') and not document_href.endswith('docx'):
                    continue
                if document_href.startswith('https'):
                    document_url = document_href
                else:
                    document_url = host + document_href
                print('document_title: ', document_title)
                print('\tdocument_url: ', document_url)
                # get the date from the document_url
                potential_date_str = ''
                for i in range(len(document_url)):
                    if document_url[i].isdigit() or document_url[i] == '-':
                        potential_date_str += document_url[i]
                if len(potential_date_str) > 10:
                    potential_date_str = potential_date_str[-10:]
                # add the default day and month if needed to complete the date format
                if len(potential_date_str) == 0:
                    potential_date_str = '2018-05-25'
                elif len(potential_date_str) == 4:  # only contain year
                    potential_date_str = potential_date_str + '-05-25'
                elif len(potential_date_str) == 7:  # only contain year and month
                    potential_date_str = potential_date_str + '-25'
                elif '-' not in potential_date_str:  # only contain digit without '-'
                    potential_date_str = potential_date_str[-8:]
                    potential_date_str = potential_date_str[:4] + '-' + potential_date_str[4:6] + '-' + potential_date_str[6:]

                date_str = potential_date_str
                print('\tdate_str: ', date_str)
                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                print('\tdate: ', date)
                # In this link, all files are sorted from newest to oldest.
                # So just break the loop if one file not satisfied by date
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print('all the files after will not satisfied by date')
                    return existed_docs
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if document_response is None:
                    continue
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Guidelines' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                except FileExistsError:
                    pass
                if document_url.endswith('.docx'):
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
                    box.send_keys(document_url)
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
                        'releaseDate': date.strftime('%d/%m/%Y'),
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                existed_docs.append(document_hash)
        return existed_docs

    def get_docs_InspectionReports(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://vdai.lrv.lt",
            "start_path": "/lt/naudinga-informacija/patikrinimu-rezultatu-apibendrinimai"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        body = results_soup.find('div', class_='panel-body text')
        for p in body.find_all('p'):
            for documents in p.find_all('a'):
                document_href = documents.get('href')
                document_title = documents.get_text().splitlines()[-1]
                if not document_href.endswith('pdf') and not document_href.endswith('docx'):
                    continue
                document_url = host + document_href
                print('document_title: ', document_title)
                print('document_url: ', document_url)
                potential_date_str = document_url.split('.')[-2]
                # get the date from the url
                potential_date_str = potential_date_str.split('.')[0]
                potential_date_str = potential_date_str[-10:]

                # check whether the date_str is vaild date
                date_str = ''
                for i in range(len(potential_date_str)):
                    if potential_date_str[i].isdigit() or potential_date_str[i] == '-':
                        date_str += potential_date_str[i]
                # some date_str need to add the '-' to have a correct format
                if len(date_str) == 8:
                    date_str = date_str[0:4] + '-' + date_str[4:6] + '-' + date_str[6:]
                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                print('\tdate: ', date)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
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
                    pass
                if document_response is None:
                    continue
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Inspection Reports' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                except FileExistsError:
                    pass
                if to_print:
                    print("\tDocument:\t", document_hash)
                if document_url.endswith('.docx'):
                    # set a download path. Use selenium to download it
                    exec_path = WebdriverExecPolicy().get_system_path()
                    options = webdriver.ChromeOptions()
                    prefs = {"download.default_directory": document_folder}
                    options.add_argument('headless')
                    options.add_experimental_option("prefs", prefs)
                    driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                    # open google search, and put the document_url into search box, and press enter
                    driver_doc.get('https://www.google.com/')
                    box = driver_doc.find_element_by_xpath('/html/body/div[1]/div[3]/form/div[1]/div[1]/div[1]/div/div[2]/input')
                    box.send_keys(document_url)
                    box.send_keys(Keys.ENTER)
                    # the first result in the search is the file we need. Click the link to download it
                    download_section = driver_doc.find_element_by_class_name('tF2Cxc')
                    button = download_section.find_element_by_tag_name('h3').click()
                    time.sleep(5)
                    files = os.listdir(document_folder)
                    for index, file in enumerate(files):
                        os.rename(os.path.join(document_folder, file), os.path.join(document_folder, self.language_code + '.docx'))
                    document_content = docx2txt.process(document_folder + '/' + self.language_code + '.docx')
                    with open(
                            document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        f.write(document_content)
                else:
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
                        'releaseDate': date.strftime('%d/%m/%Y'),
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                existed_docs.append(document_hash)
        return existed_docs






