import os
import math
import requests
import json
import datetime
import hashlib
from pygdpr.models.dpa import DPA
from bs4 import BeautifulSoup
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy

class Estonia(DPA):
    def __init__(self, path=os.curdir):
        country_code='EE'
        super().__init__(country_code, path)


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
        added_docs += self.get_docs_Prescriptions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Instructions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Prescriptions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Estonia Prescriptions ===========================")
        iteration = 1
        existed_docs = []
        dict_hashcode = {}
        source = {
            "host": "https://www.aki.ee",
            "start_path": "/et/inspektsioon-kontaktid/menetlusotsused/ettekirjutused"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print('page not exist')
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        region_inner = results_soup.find('div', class_='region-sidebar-first-inner')
        menu = region_inner.find('ul', class_='menu')
        for li in menu.find_all('li'):
            result_href = li.find('a').get('href')
            result_link = host + result_href
            result_text = li.find('a').get_text()
            result_year = result_text.split()[-1]
            if result_year < '2018':
                continue
            result_source = self.get_source(page_url=result_link)
            if result_source is None:
                continue
            pages_soup = BeautifulSoup(result_source.text, 'html.parser')
            assert pages_soup
            region_content_inner = pages_soup.find('div', class_='region-content-inner')
            block_system = region_content_inner.find('div', class_='block-system')

            # get year
            page_title = region_content_inner.find(id="page-title")
            page_title = page_title.get_text()
            document_year = page_title.split()[1]

            field_item_even = block_system.find('div', class_='field-item even')
            for p in field_item_even.find_all('p'):

                document = p.find('a')
                if document is None:
                    continue

                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                document_href = document.get('href')
                if document_href.startswith('https'):
                    document_url = document_href
                else:
                    document_url = host + document_href
                if document_href.endswith('pdf') is False:
                    continue
                document_title = document.get_text()
                print('document_title: ', document_title)
                print('\tdocument_url: ', document_url)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                if document_hash in dict_hashcode and dict_hashcode[document_hash] == date:
                    print('\tSkipping existing document:\t', document_hash)

                # get the date from title or href,
                # documents before 2023 have date, while documents after 2023 don't have date
                # Set default date as the document year
                date = document_year
                if document_year == '2023':
                    date = "2023"
                else:
                    for i in range(len(document_title)):
                        if document_title[i].isdigit():
                            date_str = document_title[i: i+10]
                            break
                    try:
                        tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                        date = datetime.date(tmp.year, tmp.month, tmp.day)
                        if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                            continue
                        date = date.strftime('%d/%m/%Y')
                    except ValueError:
                        print("\tnot format date in document title, use default date")
                        pass
                print('\tdocument_date: ', date)
                print('\tdocument_hash: ', document_hash)

                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass

                # Bad pdf file, ignore it
                if document_hash == "6bfd730bfc5d592ba92af457299a9358":
                    continue

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Prescriptions' + '/' + document_hash
                # document_folder = dpa_folder + '/estonia' + '/' + 'Prescriptions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    if document_response is None:
                        continue

                    document_content = document_response.content
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_content)

                    with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        try:
                            document_text = PDFToTextService().text_from_pdf_path(
                                document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                        except FileNotFoundError:
                            print("can't convert pdf to txt file")

                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': date,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(document_hash)
                    dict_hashcode[document_hash] = date
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

        return existed_docs

    def get_docs_Instructions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Estonia Instructions ===========================")
        existed_docs = []
        source = {
            "host": "https://www.aki.ee",
            "start_path": "/et/koik-juhised-loetelus"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print('page not exist')
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        block_main = results_soup.find('div', class_='block-system-main')
        content_clearfix = block_main.find('div', class_='content clearfix')
        # type 1 files
        field_name_body = content_clearfix.find('div', class_='field-name-body')
        field_item = field_name_body.find('div', class_='field-item even')
        tbody = field_item.find('tbody')
        for tr in tbody.find_all('tr'):

            year_list = []
            for td in tr.find_all('td'):

                if td.get_text() == 'Teiste asutustega koostöös loodud juhendid':
                    break
                # find the year of document
                if td.find('a') == None:
                    candidate_year = td.get_text()
                    if candidate_year.isdigit():
                        year_list.append(candidate_year)
                    continue
                document_href = td.find('a').get('href')
                document_title = td.find('a').get_text()
            if len(year_list) == 0:
                continue
            year = year_list[-1]
            if year < '2018':
                continue
            print('document_title:', document_title)
            if document_href.startswith('https'):
                document_url = document_href
            else:
                document_url = host + document_href
            print('\tdocument_url:', document_url)
            print('\tyear: ',year)
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            print('\tdocument_hash: ', document_hash)
            if document_hash in existing_docs and overwrite == False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Instructions' + '/' + document_hash
            # document_folder = dpa_folder + '/estonia' + '/' + 'Instructions' + '/' + document_hash
            try:
                os.makedirs(document_folder)
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
                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_content)
                with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                    document_text = PDFToTextService().text_from_pdf_path(
                        document_folder + '/' + self.language_code + '.pdf')
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
                print("\tDirectory path already exists, continue.")
        # type 2 files
        field_name_field = content_clearfix.find('div', class_='field-name-field-files')
        field_item = field_name_field.find('div', class_='field-item even')
        tbody = field_item.find('tbody')
        for tr in tbody.find_all('tr', class_='odd'):

            year_str = tr.find('td', class_='extended-file-field-table-date').get_text()
            document_section = tr.find('td', class_='extended-file-field-table-filename')
            document_url = document_section.find('a').get('href')
            document_title = document_section.find('a').get_text()
            year = year_str.split()[0].split('.')[-1]
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if year < '2018':
                continue
            print('document_title:', document_title)
            print('\tdocument_url:', document_url)
            print('\tdocument_hash: ',document_hash)

            if document_hash in existing_docs and overwrite == False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            existed_docs.append(document_hash)
            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Instructions' + '/' + document_hash
            # document_folder = dpa_folder + '/estonia' + '/' + 'Instructions' + '/' + document_hash
            try:
                os.makedirs(document_folder)
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
                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_content)
                with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                    document_text = PDFToTextService().text_from_pdf_path(
                        document_folder + '/' + self.language_code + '.pdf')
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
                print("\tDirectory path already exists, continue.")
        return existed_docs

    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Estonia Annual Reports ===========================")
        existed_docs = []
        page_url = 'https://aastaraamat.aki.ee/'
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print('page not exist')
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        # get the newest annual report
        region_content = results_soup.find('div', class_='region region-content')
        block_core = region_content.find('div', class_='block-core')
        document_title = block_core.get_text().strip()
        print('document_title: ', document_title)
        document_hash = hashlib.md5(document_title.encode()).hexdigest()
        year = document_title.split()[-1].strip()
        block_views = region_content.find('div', class_='block-views')
        view_content = block_views.find('div', class_='view-content')
        for div in view_content.find_all('div', class_='views-row'):
            document = div.find('div', class_='views-field-title')
            title = document.get_text()
            document_href = document.find('a').get('href')
            if title != 'Aastaraamatu PDF':
                continue
            document_url = page_url + document_href
            document_source = self.get_source(page_url=document_url)
            if document_source is None:
                print('page not exist')
            document_soup = BeautifulSoup(document_source.text, 'html.parser')
            assert document_soup
            node_content = document_soup.find('div', class_='node__content')
            text_formatted = node_content.find('div', class_='text-formatted')
            article_href = text_formatted.find('a').get('href')
            article_url = page_url + article_href
            print('\turl: ', article_url)
            if document_hash in existing_docs and overwrite == False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue
            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Annual Reports' + '/' + document_hash
            # document_folder = dpa_folder + '/estonia' + '/' + 'Annual Reports' + '/' + document_hash
            try:
                os.makedirs(document_folder)
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
                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_content)
                with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                    document_text = PDFToTextService().text_from_pdf_path(
                        document_folder + '/' + self.language_code + '.pdf')
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

        # older annual reports
        exec_path = WebdriverExecPolicy().get_system_path()
        options = webdriver.ChromeOptions()
        options.add_argument('headless')
        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
        driver_doc.get(page_url)
        for i in range(1, 3):
            document = driver_doc.find_element_by_xpath('//*[@id="block-aastaraamat-main-menu"]/ul/li[3]/ul/li['+str(i)+']/a')
            document_href = document.get_attribute("href")
            page_source = self.get_source(page_url=document_href)
            if page_source is None:
                print('page not exist')
            document_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert document_soup
            region_content = document_soup.find('div', class_='region region-content')
            block_core = region_content.find('div', class_='block-core')
            document_title = block_core.get_text().strip()
            year_str = document_title.split()[-1].strip()
            # 2019 annual report
            if year_str == '2019':
                year = year_str
                print('document_title: ', document_title)
                print('\turl: ', document_href)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                block_views = region_content.find('div', class_='block-views')
                view_content = block_views.find('div', class_='view-content')
                for div in view_content.find_all('div', class_='views-row'):
                    document = div.find('div', class_='views-field-title')
                    title = document.get_text()
                    document_href = document.find('a').get('href')
                    if title != 'Aastaraamatu PDF':
                        continue
                    document_url = page_url + document_href
                    document_source = self.get_source(page_url=document_url)
                    if document_source is None:
                        print('page not exist')
                    document_soup = BeautifulSoup(document_source.text, 'html.parser')
                    assert document_soup
                    node_content = document_soup.find('div', class_='node__content')
                    text_formatted = node_content.find('div', class_='text-formatted')
                    article_href = text_formatted.find('a').get('href')
                    article_url = page_url + article_href
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
            # older than 2019
            else:
                block_system = region_content.find('div', class_='block-system')
                node_content = block_system.find('div', class_='node__content')
                for li in node_content.find('ul').find('li'):
                    article_title = li.get_text().strip()
                    document_title = article_title
                    year = article_title.split()[-1].strip()
                    if year < '2018':
                        continue
                    article_href = li.get('href')
                    document_hash = hashlib.md5(article_title.encode()).hexdigest()
                    print('document_title: ',  article_title)
                    article_url = page_url + article_href
                    print('\turl: ', article_url)
                    if document_hash in existing_docs and overwrite == False:
                        if to_print:
                            print('\tSkipping existing document:\t', document_hash)
                        continue
            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Annual Reports' + '/' + document_hash
            # document_folder = dpa_folder + '/estonia' + '/' + 'Annual Reports' + '/' + document_hash
            try:
                os.makedirs(document_folder)
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
                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_content)
                with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                    document_text = PDFToTextService().text_from_pdf_path(
                        document_folder + '/' + self.language_code + '.pdf')
                    f.write(document_text)
                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                                self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': year,
                        'url': article_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                existed_docs.append(document_hash)
            except FileExistsError:
                print("Directory path already exists, continue.")
        return existed_docs
