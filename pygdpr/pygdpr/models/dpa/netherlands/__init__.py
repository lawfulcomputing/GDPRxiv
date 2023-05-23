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

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            'host': 'https://autoriteitpersoonsgegevens.nl',
            'start_path': '/nl/wetgevingsadviezen',
        }
        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pager = page_soup.find('div', class_='pager')
            if pager is not None:
                ul_pager = pager.find('ul')
                for li in ul_pager.find_all('li'):
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
        added_docs += self.get_docs_Decisions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Reports(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Opinions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_publicDisclosure(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Netherlands Decision Documents =========================")
        existed_docs = []
        iteration = 1
        source = {
            'host': 'https://autoriteitpersoonsgegevens.nl',
            'start_path': '/nl/publicaties/boetes-en-sancties',
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
                time.sleep(2)
                # get the date: strip all the irrelevant char from the day and year
                date_str_list = li.get_text().split()[-3:]
                new_date = ''
                new_year = ''
                for i in range(len(date_str_list[0])):
                    if date_str_list[0][i].isdigit():
                        new_date += date_str_list[0][i]
                for i in range(len(date_str_list[2])):
                    if date_str_list[2][i].isdigit():
                        new_year += date_str_list[2][i]
                date_str = new_date + ' ' + date_str_list[1] + ' ' + new_year

                tmp = dateparser.parse(date_str, languages=[self.language_code])

                # one exception
                if tmp == None:
                    date_str = "16 juli 2020"
                    tmp = dateparser.parse(date_str, languages=[self.language_code])

                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue

                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                document_title = li.find('a').get_text()
                if date_str == "16 juli 2020":
                    document_title = li.get_text().split('575.000')[0]

                print("\tDocument:\t", document_title)
                document_href = li.find('a').get('href')
                document_url = host + document_href
                if document_href.startswith('https'):
                    document_url = document_href
                print("\tDocument_url:\t", document_url)
                print('\tdate:\t', date)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print('\tdocument_hash:\t', document_hash)
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    file_response = None
                    try:
                        file_response = requests.request('GET', document_url)
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

                    # get document full pdf
                    content_bar = file_soup.find_all('div', id='side-content-publications')
                    if content_bar is not None:
                        document_pdf_iter = 1
                        for j in range(len(content_bar)):
                            article_list = content_bar[j].find('ul', class_='article-list')
                            total_document_pdf = article_list.find_all('li')
                            for i in range(0, len(total_document_pdf)):
                                file_url = total_document_pdf[i].find('a').get('href')
                                try:
                                    file_response = requests.request('GET', file_url)
                                    file_response.raise_for_status()
                                except requests.exceptions.HTTPError as error:
                                    if to_print:
                                        print(error)
                                    pass
                                if file_response is None:
                                    continue
                                if len(total_document_pdf) == 1:
                                    document_path = document_folder + '/' + self.language_code
                                else:
                                    document_path = document_folder + '/' + self.language_code + '_' + str(
                                        document_pdf_iter)
                                with open(document_path + '.pdf', 'wb') as f:
                                    f.write(file_response.content)

                                with open(document_path + '.txt', 'wb') as f:
                                    try:
                                        file_text = textract.process(
                                            document_path + '.pdf')
                                        f.write(file_text)
                                    except:
                                        pass
                                document_pdf_iter += 1

                    elif date_str == "16 juli 2020":
                        main_content = file_soup.find('div', class_='rs-panel rs-panel-type-1')
                        main_text = main_content.get_text()
                        with open(
                                document_folder + '/' + self.language_code + '.txt', 'w') as f:
                            f.write(main_text)
                    # if don't have full pdf, get the document summary
                    else:
                        main_content = file_soup.find('div', class_='main-content-article')
                        main_text = main_content.get_text()
                        with open(
                                document_folder + '/' + self.language_code + '_summary.txt', 'w') as f:
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
            article_list = results_soup.find('ul', class_='article-list')
            assert article_list
            # s1. Results
            for li in article_list.find_all('li'):
                date_span = li.find('span', class_='date')
                assert date_span
                date_str = date_span.get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue

                result_link = li.find('a', class_='download')
                assert result_link
                linktitle = li.find('span', class_='linktitle')
                assert linktitle
                # s2. Documents
                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                document_title = linktitle.get_text().strip()
                print('\tdocument_title:\t', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                if document_href.endswith('.pdf') is False:
                    continue

                document_url = document_href
                print('\tdocument_url:\t', document_url)
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
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Opinions' + '/' + document_hash
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
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(document_hash)
                except FileExistsError:
                    print("Directory path already exists, continue.")

            # s1. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs

    def get_docs_publicDisclosure(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Netherlands public disclosure =========================")
        iteration = 1
        existed_docs = []
        source = {
            'host': 'https://autoriteitpersoonsgegevens.nl',
            'start_path': '/nl/publicaties/wob-besluiten',
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        page_source = self.get_source(page_url=page_url)
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        main_content = results_soup.find('div', class_='main-content-article')
        default_year_list = ['2021', '2020', '2019', '2018']
        for ul in main_content.find_all('ul'):
            default_year = ul.find('li').get_text().split()[-1]
            for li in ul.find_all('li'):
                li_list = li.get_text().split()
                date_str = ' '.join(li_list[-3:])
                # check whether date_str is a valid date
                if not date_str[0].isdigit() or not date_str[-1].isdigit():
                    # check whether date is title's other position
                    # if not in other position, then use the default_date: '05 mei ' + default_year
                    for i in range(len(li_list)):
                        if li_list[i] in default_year_list:
                            date_str = ' '.join(li_list[i - 2:i + 1])
                            break
                        else:
                            date_str = '05 mei ' + default_year
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue

                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                document_title = li.find('a').get_text()
                print("\tDocument:\t", document_title)
                document_href = li.find('a').get('href')
                document_url = host + document_href
                print("\tDocument_url:\t", document_url)
                print("\tdate_str:\t", date_str)

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
                        print("\tThe error is: ", error)
                    pass
                if document_response is None:
                    continue
                file_soup = BeautifulSoup(document_response.text, 'html.parser')
                if file_soup.find('div', class_='main-content-article') is not None:
                    main_text = file_soup.find('div', class_='main-content-article').get_text()
                    if "kon niet worden gevonden" in main_text:
                        print("\t404 Error, Not found for url")
                        continue
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Public Disclosure' + '/' + document_hash
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
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
        return existed_docs