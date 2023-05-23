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
import sys
import time

class Luxembourg(DPA):
    def __init__(self, path=os.curdir):
        country_code='lu'
        super().__init__(country_code, path)

    # Passing this method a page parse object causes it to find ALL links to next page buttons visible at bottom of page
    # The visible page buttons only change every 5 page flips, so need to check that duplicates aren't being added
    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path="Decisions"):
        source = {
            "host": "https://cnpd.public.lu",
            "start_path_opinion": "/fr/decisions-avis.html?b=0",
            "start_path_decision": "/fr/decisions-sanctions.html?b=0"
        }
        if start_path != "Decisions":
            start_path = source['start_path_opinion']
        else:
            start_path = source['start_path_decision']
        host = source['host']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            ol_pagination = page_soup.find('ol', class_='pagination')
            assert ol_pagination
            for li in ol_pagination.find_all('li', class_='pagination-page'):
                page_link = li.find('a')
                if page_link is None:
                    continue
                page_href = page_link.get('href')
                page_link = host + page_href

                # If existing_pages contains the link already, don't add it again
                if pagination.has_link(page_link):
                    continue
                print("\nLINK ADDED TO PAGINATION OBJECT: " + host + page_href)
                pagination.add_item(page_link)
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
        added_docs += self.get_docs_Decisions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Opinions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)

        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Luxembourg Decision Documents =========================")
        added_docs = []
        # Starting url is set to page 1, instead of the generic url (which lacks page specifier but starts at page 1)
        pagination = self.update_pagination()

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nPage:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup
            search_results = results_soup.find('ol', class_='search-results')
            assert search_results
            # s1. Results
            for li in search_results.find_all('li', recursive=False):
                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1
                time.sleep(2)

                article_time = li.find('time', class_='article-published')
                assert article_time
                date_str = article_time.get('datetime')
                date_str = date_str.split()[0]

                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)


                # If document year is less than 2018, skip it
                if int(date_str[0:4]) < 2018:
                    print("\tSkipping outdated document: " + date.strftime('%d/%m/%Y'))
                    return added_docs

                print('\tDocument Date: ' + date.strftime('%d/%m/%Y'))

                '''
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tSkipping outdated document: " + date.strftime('%d/%m/%Y'))
                    continue
                '''

                article_title = li.find('h2', class_='article-title')
                assert article_title
                result_link = article_title.find('a')
                assert result_link

                document_title = result_link.get_text()
                print('\tDocument Title:\t' + document_title)
                print('\tdate:\t', date)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                host = "https://cnpd.public.lu"
                document_url = host + document_href
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup
                aside = document_soup.find('aside', class_='page-more')
                assert aside
                file_links = aside.find_all('a')
                file_url = None
                for file_link in file_links:
                    file_href = file_link.get('href')
                    if file_href.endswith('.pdf'):
                        if file_href.startswith('http') is False:
                            file_url = host + file_href
                        else:
                            file_url = file_href
                        break
                file_response = None
                try:
                    print('\tfile_url:', file_url)
                    file_response = requests.request('GET', file_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if file_response is None:
                    continue
                file_content = file_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(file_content)
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
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': file_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)

        return added_docs

    def get_docs_Opinions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Luxembourg Opinions =========================")
        added_docs = []
        # Starting url is set to page 1, instead of the generic url (which lacks page specifier but starts at page 1)
        pagination = self.update_pagination(start_path = "Opinions")

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nPage:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup
            search_results = results_soup.find('ol', class_='search-results')
            assert search_results
            # s1. Results
            for li in search_results.find_all('li', recursive=False):
                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                article_time = li.find('time', class_='article-published')
                assert article_time
                date_str = article_time.get('datetime')
                date_str = date_str.split()[0]

                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                # If document year is less than 2018, skip it
                if int(date_str[0:4]) < 2018:
                    print("\tSkipping outdated document: " + date.strftime('%d/%m/%Y'))
                    return added_docs

                print('\tDocument Date: ' + date.strftime('%d/%m/%Y'))

                '''
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print("\tSkipping outdated document: " + date.strftime('%d/%m/%Y'))
                    continue
                '''

                article_title = li.find('h2', class_='article-title')
                assert article_title
                result_link = article_title.find('a')
                assert result_link

                document_title = result_link.get_text()
                print('\tDocument Title:\t' + document_title)
                print('\tdate_str:\t', date_str)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                host = "https://cnpd.public.lu"
                document_url = host + document_href
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup
                aside = document_soup.find('aside', class_='page-more')
                assert aside
                file_links = aside.find_all('a')
                file_url = None
                for file_link in file_links:
                    file_href = file_link.get('href')
                    if file_href.endswith('.pdf'):
                        if file_href.startswith('http') is False:
                            file_url = host + file_href
                        else:
                            file_url = file_href
                        break
                file_response = None
                try:
                    print('\tfile_url:', file_url)
                    file_response = requests.request('GET', file_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if file_response is None:
                    continue
                file_content = file_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Opinions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(file_content)
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
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': file_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup, start_path="Opinions")

        return added_docs

    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Luxembourg Annual Reports =========================")
        added_docs = []

        iteration = 1

        page_url = 'https://cnpd.public.lu/fr/publications/rapports.html'
        if to_print:
            print('\nPage:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit("Couldn't connect to base url")

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        page_text = results_soup.find('div', class_='page-text')
        assert page_text

        ul = page_text.find('ul')
        assert ul

        for li in ul.find_all('li'):
            assert li

            print('\n------------ Document: ' + str(iteration) + '-------------')
            iteration += 1

            result_link = li.find('a')
            assert result_link

            document_title = result_link.get_text()
            print('\tDocument Title:\t' + document_title)

            # Check if document is outdated
            document_date = document_title[-4:]
            print('\tDocument Date:\t' + document_date)
            if int(document_date) < 2018:
                print('\tSkipping outdated document: ' + document_date)
                return added_docs

            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            document_href = result_link.get('href')
            assert document_href
            host = "https:"
            document_url = host + document_href
            if to_print:
                print("\tDocument:\t", document_hash)

            print("\tDocument URL: " + document_url)
            document_response = None
            try:
                document_response = requests.request('GET', document_url)
            except requests.exceptions.HTTPError as error:
                if to_print:
                    print(error)
                pass
            if document_response is None:
                continue

            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Annual Reports' + '/' + document_hash
            try:
                os.makedirs(document_folder)
                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_response.content)
                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                    try:
                        document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                    except:
                        print('\tFailed to convert pdf to text document')
                        pass
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