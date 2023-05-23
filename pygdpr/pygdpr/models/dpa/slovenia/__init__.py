import os
import math
import socket

import requests
import json
import datetime
import hashlib
import dateparser
import re
import csv
import sys
import urllib3.exceptions

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

class Slovenia(DPA):
    def __init__(self, path=os.curdir):
        country_code='SL'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://www.ip-rs.si",
            "start_path": "/mnenja-gdpr/"
        }
        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        elif page_soup is not None:
            nav = page_soup.find('div', class_='page pr')
            assert nav

            article = nav.find('article', class_='c9')
            assert article

            advsea_next = article.find('span', class_='advsea-next')
            assert advsea_next

            a_tag = advsea_next.find('a')
            assert a_tag

            href = a_tag.get('href')
            next_url = 'https://www.ip-rs.si/' + href
            #print("\nAdding page: " + next_url + " to pagination object")
            pagination.add_item(next_url)
        else:
            print("update_pagination() added zero links")

        return pagination

    def get_source(self, page_url=None, driver=None):
        assert page_url is not None
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
        added_docs += self.get_docs_Opinions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Reports(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Guidelines(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Opinions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Slovenia Opinions =========================")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        added_docs = []
        pagination = self.update_pagination()

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)

            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            nav = results_soup.find('div', class_='page pr')
            assert nav

            article = nav.find('article', class_='c9')
            assert article

            advsea = article.find('div', class_='advsea-results-list')
            assert advsea

            for tr in advsea.find_all('tr')[1:]:
                assert tr

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                td_date = tr.find('td', align='center')
                assert td_date

                document_date = td_date.get_text()
                assert document_date

                print('\tDocument Date: ' + document_date)

                tmp = datetime.datetime.strptime(document_date, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print('Remaining documents are out of date')
                    return added_docs

                td = tr.find('td', align='left')
                assert td

                a = td.find('a')
                assert a

                href = a.get('href')
                assert href

                # THE HREF'S IN THE HTML ARE MISSING THE BEGINNING '/', SO IT MUST BE ADDED HERE
                document_url = 'https://www.ip-rs.si/' + href
                assert document_url

                print("\tDocument Link: " + document_url)

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
                        print(error)
                    pass
                except urllib3.exceptions.MaxRetryError as error:
                    if to_print:
                        print(error)
                    pass
                except urllib3.exceptions.NewConnectionError as error:
                    if to_print:
                        print(error)
                    pass
                except socket.gaierror as error:
                    if to_print:
                        print(error)
                    pass

                if document_response is None:
                    continue

                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                article = document_soup.find('article', class_='c9')
                assert article

                h1 = article.find('header').find('h1')
                assert h1

                document_title = h1.get_text()
                print('\tDocument Title: ' + document_title)

                # Get the document text
                article_text = article.get_text()

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Opinions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        f.write(article_text)
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': document_date,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return added_docs

    def get_docs_Guidelines(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Slovenia Guidelines =========================")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        added_docs = []

        page_url = 'https://www.ip-rs.si/publikacije/priro%C4%8Dniki-in-smernice/'
        if to_print:
            print('\nPage:\t', page_url)

        page_source = self.get_source(page_url=page_url)

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        nav = results_soup.find('div', class_='page pr')
        assert nav

        article = nav.find('article', class_='c9')
        assert article

        table = article.find('table', class_='contenttable')
        assert table

        tr = table.find('tr', class_='holder')
        assert tr

        iteration = 1
        for td in tr.find_all('td'):
            assert td

            a_tag = td.find_all('a')[1]
            assert a_tag

            print('\n------------ Document ' + str(iteration) + ' ------------')
            iteration += 1

            document_title = a_tag.get_text()
            print('\tDocument Title: ' + document_title)

            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            document_href = a_tag.get('href')
            assert document_href

            document_url = 'https://www.ip-rs.si/' + document_href

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

            # Now download the pdf
            pdf_article = document_soup.find('article', class_='c9')
            assert pdf_article

            # Get the document date
            table = pdf_article.find('table', class_='contenttable')
            assert table

            tr_table = table.find_all('tr')
            assert tr_table

            date_tr = tr_table[4]
            assert date_tr

            date_td = date_tr.find_all('td')[1]
            assert date_td

            date_p = date_td.find('p')

            document_date = date_p.get_text()
            print('\tDocument Date: ' + document_date)

            tmp = datetime.datetime.strptime(document_date, '%d.%m.%Y')
            date = datetime.date(tmp.year, tmp.month, tmp.day)

            if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                print('Before GDPR adopted')
                continue

            # Skip old reports
            if int(document_date[-4:]) < 2018:
                print('Skipping outdated document')
                return added_docs

            # Find the pdf link
            pdf_p = pdf_article.find('p', align='center')
            assert pdf_p

            pdf_a = pdf_p.find('a')
            assert pdf_a

            pdf_href = pdf_a.get('href')
            assert pdf_href

            # Sometimes the href doesn't start with a '/'
            if pdf_href.startswith('/'):
                pdf_url = 'https://www.ip-rs.si' + pdf_href
            else:
                pdf_url = 'https://www.ip-rs.si/' + pdf_href

            print("\tPDF Link: " + pdf_url)

            pdf_response = None
            try:
                pdf_response = requests.request('GET', pdf_url)
                pdf_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                if to_print:
                    print(error)
                pass
            if pdf_response is None:
                continue

            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Guidelines' '/' + document_hash

            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(pdf_response.content)
                try:
                    with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        document_text = PDFToTextService().text_from_pdf_path(document_folder + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                except:
                    print('Failed to convert PDF to text')
                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': document_date,
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                added_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")
        return added_docs

    def get_docs_Reports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Slovenia Reports =========================")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        added_docs = []

        page_url = 'https://www.ip-rs.si/publikacije/letna-poro%C4%8Dila/'
        if to_print:
            print('\nPage:\t', page_url)

        page_source = self.get_source(page_url=page_url)

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        nav = results_soup.find('div', class_='page pr')
        assert nav

        article = nav.find('article', class_='c9')
        assert article

        table = article.find('table', class_='contenttable')
        assert table

        tr = table.find('tr', class_='holder')
        assert tr

        iteration = 1
        for td in tr.find_all('td'):
            assert td

            a_tag = td.find_all('a')[1]
            assert a_tag

            print('\n------------ Document ' + str(iteration) + ' ------------')
            iteration += 1

            document_title = a_tag.get_text()
            print('\tDocument Title: ' + document_title)

            document_date = document_title[-4:]
            print('\tDocument Date: ' + document_date)

            # Skip old reports
            if int(document_date[-4:]) < 2018:
                print('Skipping outdated document')
                return added_docs

            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            document_href = a_tag.get('href')
            assert document_href

            if document_href.startswith('http'):
                document_url = document_href
            else:
                document_url = 'https://www.ip-rs.si/' + document_href
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

            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Reports' '/' + document_hash

            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_response.content)

                try:
                    with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        document_text = PDFToTextService().text_from_pdf_path(document_folder + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                except:
                    print('Failed to convert PDF to text')

                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': document_date,
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                added_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        return added_docs
