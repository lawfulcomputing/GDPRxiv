import os
import math
import time

import requests
import json
import datetime
import hashlib
import dateparser
import re
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

class Latvia(DPA):
    def __init__(self, path=os.curdir):
        country_code='LV'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://www.dvi.gov.lv",
            "start_path": "/lv/jaunumi"
        }
        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            ul_pagination = page_soup.find('ul', class_='pagination')
            if ul_pagination is not None:
                for page_item in ul_pagination.find_all('li', class_='page-item'):
                    page_link = page_item.find('a')
                    if page_link is None:
                        continue
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
            pass
        return results_response

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_Decisions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Violations(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Opinions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_guidance_1(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_guidance_2(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Guidances(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        added_docs += self.get_docs_guidance_1()
        added_docs += self.get_docs_guidance_2()
        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://www.dvi.gov.lv",
            "start_path": "/lv/lemumi"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)

        # There is a popup window, use selenium to interact
        exec_path = WebdriverExecPolicy().get_system_path()
        options = webdriver.ChromeOptions()
        options.add_argument('headless')
        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
        driver_doc.get(page_url)
        driver_doc.find_element_by_class_name('modal-popup-cancel').click()
        time.sleep(5)
        page_source = driver_doc.page_source
        results_soup = BeautifulSoup(page_source, 'html.parser')

        block_content = results_soup.find('div', class_='block-ministry-content')
        node = block_content.find('div', class_='node')
        content = node.find('div', class_='content')
        for accordion in content.find_all('div', class_='accordion'):
            card_year = accordion.find('button', class_='btn btn-link')
            year = card_year.get_text().strip()
            print("year: ", year)
            card_body = accordion.find('div', class_='card-body')
            tr_all = table = card_body.find_all('tr')
            assert tr_all
            tr_all = tr_all[1:] # skip the fst row
            for tr in tr_all:
                td_all = tr.find_all('td')
                if len(td_all) == 0:
                    continue
                # year_flag = '2021'
                if year == '2021' or year == '2022':
                    manager_index, remedy_index, pdf_index, date_index = 0, 1, 2, 3
                else:
                    manager_index, pdf_index, date_index, decision_status, court_judgment = 0, 1, 2, 3, 4
                    year_flag = '2020'
                td_date = td_all[date_index]
                assert td_date
                date_str = td_date.get_text().strip()
                if not date_str[0].isdigit():
                    continue
                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y.')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                # no document title shows in table, replace with manager + date
                document_title = td_all[manager_index].get_text().strip() + '-' + date_str
                print('document_title: ', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()

                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                td_pdf = td_all[pdf_index]
                assert td_pdf
                if td_pdf.find('a') == None:
                    continue
                document_href = td_pdf.find('a').get('href')
                document_url = host + document_href
                print('\tdocument_hash: ', document_hash)
                assert document_url
                print('\tdocument_url" ', document_url)

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash

                try:
                    # use selenium to download the pdf, since requests.request can't get the page content
                    os.makedirs(document_folder)
                    exec_path = WebdriverExecPolicy().get_system_path()
                    options = webdriver.ChromeOptions()
                    options.add_argument('headless')
                    dpa_folder = self.path
                    document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                    options.add_experimental_option('prefs', {
                        "download.default_directory": document_folder,  # Change default directory for downloads
                        "download.prompt_for_download": False,  # To auto download the file
                        "download.directory_upgrade": True,
                        "plugins.always_open_pdf_externally": True  # It will not show PDF directly in chrome
                    })
                    driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                    driver_doc.get(document_url)
                    time.sleep(5)

                    for root, dirs, files in os.walk(document_folder):
                        # change the pdf file name to "lv.pdf"
                        for name in files:
                            oldname = os.path.join(root, name)
                            newname = os.path.join(root, 'lv.pdf')
                            os.rename(oldname, newname)

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
                except FileExistsError:
                    print("Directory path already exists, continue.")
        return existed_docs

    def get_docs_Decisions_oldDesign(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://www.dvi.gov.lv",
            "start_path": "/lv/lemumi"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        block_content = results_soup.find('div', class_='block-ministry-content')
        node = block_content.find('div', class_='node')
        content = node.find('div', class_='content')
        for accordion in content.find_all('div', class_='accordion'):
            card_year = accordion.find('button', class_='btn btn-link')
            year = card_year.get_text().strip()
            print("year: ", year)
            card_body = accordion.find('div', class_='card-body')
            tr_all = table = card_body.find_all('tr')
            assert tr_all
            tr_all = tr_all[1:] # skip the fst row
            for tr in tr_all:
                td_all = tr.find_all('td')
                if len(td_all) == 0:
                    continue
                if year == '2021' or year == '2022':
                    manager_index, remedy_index, pdf_index, date_index = 0, 1, 2, 3
                else:
                    manager_index, pdf_index, date_index, decision_status, court_judgment = 0, 1, 2, 3, 4
                    year_flag = '2020'
                td_date = td_all[date_index]
                assert td_date
                date_str = td_date.get_text().strip()
                if not date_str[0].isdigit():
                    continue
                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y.')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                document_title = td_all[manager_index].get_text().strip() + '-' + date_str
                print('document_title: ', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()

                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                td_pdf = td_all[pdf_index]
                assert td_pdf
                if td_pdf.find('a') == None:
                    continue
                document_href = td_pdf.find('a').get('href')
                document_url = host + document_href
                print('\tdocument_hash: ', document_hash)
                assert document_url
                print('\tdocument_url" ', document_url)
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
                document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                # document_folder = dpa_folder + '/latvia' + '/' + 'Decisions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                    if year_flag == '2020':
                        judgement = td_all[court_judgment].find('a')
                        if judgement is not None:
                            judgement_href = td_all[court_judgment].find('a').get('href')
                            judgement_url = host + document_href
                            print('\tdocument_2_url: ', judgement_url)
                            judgement_response = None
                            try:
                                judgement_response = requests.request('GET', judgement_url)
                                judgement_response.raise_for_status()
                            except requests.exceptions.HTTPError as error:
                                if to_print:
                                    print(error)
                                pass
                            if judgement_response is None:
                                continue
                            judgement_content = judgement_response.content

                            with open(document_folder + '/' + self.language_code + '_Court Judgement' + '.pdf', 'wb') as f:
                                f.write(judgement_content)
                            with open(document_folder + '/' + self.language_code + '_Court Judgement' + '.txt', 'wb') as f:
                                judgement_text = textract.process(document_folder + '/' + self.language_code + '_Court Judgement' + '.pdf')
                                f.write(judgement_text)
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
                    print("Directory path already exists, continue.")
        return existed_docs

    def get_docs_Violations(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://www.dvi.gov.lv",
            "start_path": "/lv/saraksts-par-publisko-tiesibu-subjektu-pielautajiem-vdar-prasibu-parkapumiem-un-noversanu"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        print(page_source)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        block_content = results_soup.find('div', class_='block-ministry-content')
        node = block_content.find('div', class_='node')
        content = node.find('div', class_='content')
        for accordion in content.find_all('div', class_='accordion'):
            card_year = accordion.find('button', class_='btn btn-link')
            year = card_year.get_text().strip().split('.')[0]
            print("\nDocument Title: ", year)
            card_body = accordion.find('div', class_='card-body')
            document_href = card_body.find('a').get('href')
            document_url = host + document_href
            print('\tdocument_url: ', document_url)
            assert document_url

            # no title, so use year to be the title
            document_title = year
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            print("\tdocument_hash: ", document_hash)
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

            dpa_folder = "/Users/chensun/PycharmProjects/GDPRxiv/documents/latvia"
            #dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Violations' + '/' + document_hash
            # document_folder = dpa_folder + '/latvia' + '/' + 'Violations' + '/' + document_hash
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
                        'releaseDate': year,
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                existed_docs.append(document_hash)
            except FileExistsError:
                print("Directory path already exists, continue.")
        return existed_docs


    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://www.dvi.gov.lv",
            "start_path": "/lv/publikacijas-un-parskati"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        block_content = results_soup.find('div', class_='block-ministry-content')
        node = block_content.find('div', class_='node')
        content = node.find('div', class_='content')
        for paragraph in content.find_all('div', class_='paragraph--type--data'):
            year = paragraph.get_text().strip().split('.')[0]
            if year < '2018':
                continue
            print("year: ", year)
            document_href = paragraph.find('a').get('href')
            document_url = host + document_href
            print('document_url: ', document_url)
            assert document_url

            # no title, so use year to be the title
            document_title = year
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
            document_folder = dpa_folder + '/' + 'Annual Reports' + '/' + document_hash
            # document_folder = dpa_folder + '/latvia' + '/' + 'Annual Reports' + '/' + document_hash
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
                        'releaseDate': year,
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                existed_docs.append(document_hash)
            except FileExistsError:
                print("Directory path already exists, continue.")
        return existed_docs

    def get_docs_Opinions(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://www.dvi.gov.lv",
            "start_path": "/lv/dviskaidro"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        block_content = results_soup.find('div', class_='block-ministry-content')
        node = block_content.find('div', class_='node')
        content = node.find('div', class_='content')
        for paragraph in content.find_all('div', class_='paragraph--view-mode--default'):

            articles_wrapper = paragraph.find('div', class_='articles-wrapper')
            assert articles_wrapper
            article_details = articles_wrapper.find('div', class_='article-details')
            assert article_details
            date_div = article_details.find('div', class_='date')
            assert date_div
            date_str = date_div.get_text().strip()
            print('date_str:', date_str)
            tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y.')
            date = datetime.date(tmp.year, tmp.month, tmp.day)
            if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                continue
            # s1. Results
            article_title = articles_wrapper.find('div', class_='title')
            assert article_title
            a = article_title.find('a')
            # s2. Documents
            document_title = a.get_text()
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite == False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue
            host = 'https://www.dvi.gov.lv'
            result_link = a.get('href')
            document_href = result_link
            assert document_href
            document_url = host + document_href
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
            document_soup = BeautifulSoup(document_response.text, 'html.parser')
            content_area = document_soup.find('div', id='content-area')
            document_text = content_area.get_text()
            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Opinions' + '/' + document_hash
            # document_folder = dpa_folder + '/latvia' + '/' + 'Opinions' + '/' + document_hash
            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
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
                print("Directory path already exists, continue.")
        return existed_docs


    def get_docs_guidance_1(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://www.dvi.gov.lv",
            "start_path": "/lv/dvi"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        block_content = results_soup.find('div', class_='block-ministry-content')
        node = block_content.find('div', class_='node')
        content = node.find('div', class_='content')
        for paragraph in content.find_all('div', class_='paragraph--view-mode--default'):
            card_body = paragraph.find('div', class_='card-body')
            assert card_body
            file_links = card_body.find('div', class_='file-links')
            assert file_links
            icon_exclamation = file_links.find('span', class_='icon-exclamation')
            assert icon_exclamation
            date_str = icon_exclamation.get('title').split()[-1].rstrip('</p>')
            print('date: ', date_str)
            tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
            date = datetime.date(tmp.year, tmp.month, tmp.day)
            if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                continue
            a = file_links.find('a')
            document_href = a.get('href')
            document_url = host + document_href
            document_title = a.get_text()
            print('document_title: ', document_title)
            print('\tdocument_url: ', document_url)
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
            document_folder = dpa_folder + '/' + 'Guidance' + '/' + document_hash
            # document_folder = dpa_folder + '/latvia' + '/' + 'Guidance' + '/' + document_hash
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
                        'releaseDate': date.strftime('%d/%m/%Y'),
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                existed_docs.append(document_hash)
            except FileExistsError:
                print("Directory path already exists, continue.")
        return existed_docs

    # this method only scrape pdf files
    def get_docs_guidance_2(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://www.dvi.gov.lv",
            "start_path": "/lv/edak-pamatnostadnes"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        block_content = results_soup.find('div', class_='block-ministry-content')
        node = block_content.find('div', class_='node')
        content = node.find('div', class_='content')
        for paragraph in content.find_all('div', class_='paragraph--view-mode--default'):
            file_links = paragraph.find('div', class_='file-links')
            if file_links is None:
                continue
            icon_exclamation = file_links.find('span', class_='icon-exclamation')
            assert icon_exclamation
            date_str = icon_exclamation.get('title').split()[-1].rstrip('</p>')
            print('date: ', date_str)
            tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
            date = datetime.date(tmp.year, tmp.month, tmp.day)
            if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                continue
            a = file_links.find('a')
            document_href = a.get('href')
            document_url = host + document_href
            document_title = a.get_text()
            print('document_title: ', document_title)
            print('\tdocument_url: ', document_url)
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
            document_folder = dpa_folder + '/' + 'Guidance_2' + '/' + document_hash
            # document_folder = dpa_folder + '/latvia' + '/' + 'Guidance_2' + '/' + document_hash
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
                        'releaseDate': date.strftime('%d/%m/%Y'),
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                existed_docs.append(document_hash)
            except FileExistsError:
                print("Directory path already exists, continue.")
        return existed_docs