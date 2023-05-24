import os
import sys
import time
import shutil
import math
import requests
import json
import datetime
import hashlib
import textract
from pygdpr.models.dpa import DPA
from bs4 import BeautifulSoup
import dateparser
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy

from zipfile import ZipFile


class Belgium(DPA):
    def __init__(self, path=os.curdir):
        country_code='BE'
        super().__init__(country_code, path)

    # Modified method to take the host and start path as inputs
    def update_pagination(self, pagination=None, page_soup=None, host_link_input=None, start_path_input=None):
        #if pagination is None:
        pagination = Pagination()
        pager = page_soup.find('ul', class_='pagination')
        page_repeat = False
        if pager is not None:
            for li in pager.find_all('li', class_='page-item'):
                page_link = li.find('a')
                if page_link is None:
                    continue
                host = "https://www.autoriteprotectiondonnees.be"
                page_href = page_link.get('href')
                # avoid duplicate page contents
                if page_repeat and '&l=50&p=1' in page_href:
                    return pagination
                if '&l=50&p=1' in page_href:
                    page_repeat = True
                page_url = host + page_href
                # print(page_url)
                pagination.add_item(page_url)
        else:
            page_url = host_link_input + start_path_input
            pagination.add_item(page_url)
        return pagination

    def get_source(self, page_url=None, driver=None):
        assert (page_url is not None)
        results_response = None
        try:
            results_response = requests.request('GET', page_url, timeout=1000)
            results_response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            pass
        return results_response

    # Calls all scraper methods at once
    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_Decisions_v1(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Decisions_v2(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Opinions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Guides(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)

        return added_docs

    # Calls both decisions scrapers and returns all document hashes collected
    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        added_docs += self.get_docs_Decisions_v1()
        added_docs += self.get_docs_Decisions_v2()

        return added_docs

    # Gets all documents located at first Decisions link
    # Date checking correct
    def get_docs_Decisions_v1(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []

        host_link_input = "https://www.autoriteprotectiondonnees.be"
        start_path_input = "/citoyen/chercher?q=&search_category%5B%5D=taxonomy%3Apublications&search_type%5B%5D=decision&search_subtype%5B%5D=taxonomy%3Adispute_chamber_substance_decisions&s=recent&l=50"
        iteration_number = 1
        page_url = host_link_input + start_path_input
        page_source = self.get_source(page_url)
        page_soup = BeautifulSoup(page_source.text, 'html.parser')
        pagination = self.update_pagination(page_soup=page_soup)
        print("\n========================= Belgium Decisions_v1 Documents ===========================")

        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url)
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            search_result = page_soup.find('div', id='search-result')
            assert search_result
            # s1. Results
            for media in search_result.find_all('div', class_='media'):
                time.sleep(1)
                media_title = media.find('h3', class_='media-title')
                print("------------ Document " + str(iteration_number) + " ------------")
                iteration_number += 1
                assert media_title
                result_link = media_title.find('a')
                # s2. Documents
                document_title = result_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                host = "https://www.autoriteprotectiondonnees.be"
                document_url = host + document_href
                print('document_url:', document_url)
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url, timeout=1000)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    if document_url.endswith('.pdf') is False:
                        document_soup = BeautifulSoup(document_response.text, 'html.parser')
                        assert document_soup
                        date_text = document_soup.find('div', class_='date').get_text()
                        date_str = date_text[-4:] # date_text[:-4] + ' ' + date_text[-4:]
                        tmp = dateparser.parse(date_str, languages=[self.language_code])
                        date = datetime.date(tmp.year, tmp.month, tmp.day)
                        if date.year < 2018:
                            print("Skipping outdated document")
                            continue
                        page_body = document_soup.find('div', class_='page-body')
                        assert page_body
                        document_text = page_body.get_text()
                    else:
                        date_str = document_title.split(' du ')[-1]
                        #print("date_str:", date_str)
                        tmp = dateparser.parse(date_str, languages=[self.language_code])
                        if tmp is None:
                            media_date = media.find('span', class_="media-date")
                            assert media_date
                            year = int(media_date.get_text())
                            if year < 2018:
                                continue
                        else:
                            # Use a fixed date (GDRP release date) rather than a moving window
                            date = datetime.date(tmp.year, tmp.month, tmp.day)
                            #if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                                #continue
                            if date.year < 2018:
                                print("Skipping outdated document")
                                continue

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_response.content)
                    if document_url.endswith('.pdf'):
                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                    else:
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
                    added_docs.append(document_hash)

                except FileExistsError:
                    print("Directory path already exists, continue.")
        return added_docs

    # Gets all documents located at second Decisions link
    # Date checking is correct
    def get_docs_Decisions_v2(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        print("\n========================= Belgium Decisions_v2 Documents ===========================")

        host_link_input = "https://www.autoriteprotectiondonnees.be"
        start_path_input = "/citoyen/chercher?q=&search_category%5B%5D=taxonomy%3Apublications&search_type%5B%5D=decision&search_subtype%5B%5D=taxonomy%3Ageneral_secretary_international_decisions&search_subtype%5B%5D=taxonomy%3Ageneral_secretary_general_decisions&s=recent&l=25"
        iteration_number = 1
        page_url = host_link_input + start_path_input
        page_source = self.get_source(page_url)
        page_soup = BeautifulSoup(page_source.text, 'html.parser')
        pagination = self.update_pagination(page_soup=page_soup, host_link_input=host_link_input, start_path_input=start_path_input)

        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url)
            if page_source is None:
                continue
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert page_soup
            search_result = page_soup.find('div', id='search-result')
            assert search_result
            # s1. Results
            for media in search_result.find_all('div', class_='media'):
                time.sleep(1)
                media_title = media.find('h3', class_='media-title')
                print("------------ Document " + str(iteration_number) + " ------------")
                iteration_number += 1
                # print('title:', media_title)
                assert media_title
                result_link = media_title.find('a')
                # s2. Documents
                document_title = result_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                # if document_href.endswith('.pdf') is False:
                #    continue
                host = "https://www.autoriteprotectiondonnees.be"
                document_url = host + document_href
                print('document_url:', document_url)
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url, timeout=1000)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decisions 2' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    if document_url.endswith('.pdf') is False:
                        document_soup = BeautifulSoup(document_response.text, 'html.parser')
                        assert document_soup
                        date_text = document_soup.find('div', class_='date').get_text()
                        date_str = date_text[-4:]  # date_text[:-4] + ' ' + date_text[-4:]
                        tmp = dateparser.parse(date_str, languages=[self.language_code])
                        date = datetime.date(tmp.year, tmp.month, tmp.day)

                        if date.year < 2018:
                            print("Skipping outdated document")
                            continue
                        page_body = document_soup.find('div', class_='page-body')
                        assert page_body
                        document_text = page_body.get_text()
                    else:
                        date_str = document_title.split(' du ')[-1]
                        print("date_str:", date_str)
                        tmp = dateparser.parse(date_str, languages=[self.language_code])

                        # Conditional checks for document date
                        if tmp is None:
                            media_date = media.find('span', class_="media-date")
                            assert media_date
                            year = int(media_date.get_text())
                            if year < 2018:
                                print("Skipping outdated document")
                                continue
                        else:
                            date = datetime.date(tmp.year, tmp.month, tmp.day)
                            #if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                                #continue
                            if date.year < 2018:
                                print("Skipping outdated document")
                                continue

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_response.content)
                    if document_url.endswith('.pdf'):
                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                    else:
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
                    added_docs.append(document_hash)
                except FileExistsError:
                    print('Directory path already exists, continue.')
        return added_docs

    # Gets all documents located at opinions link
    # Date checking correct
    # Only visits first page, since rest of pages are all outdated (only call update pagination once)
    def get_docs_Opinions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Belgium Opinion Documents ===========================")
        added_docs = []

        host_link_input = "https://www.autoriteprotectiondonnees.be"
        start_path_input = "/citoyen/chercher?q=GDPR&search_category%5B%5D=taxonomy%3Apublications&search_type%5B%5D=advice&s=recent&l=50"
        iteration_number = 1
        page_url = host_link_input + start_path_input
        page_source = self.get_source(page_url)
        page_soup = BeautifulSoup(page_source.text, 'html.parser')
        pagination = self.update_pagination(page_soup=page_soup)
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url)
            if page_source is None:
                continue
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert page_soup
            search_result = page_soup.find('div', id='search-result')
            assert search_result
            # s1. Results
            for media in search_result.find_all('div', class_='media'):
                time.sleep(1)
                media_title = media.find('h3', class_='media-title')
                print("------------ Document " + str(iteration_number) + " ------------")
                iteration_number += 1
                # print('title:', media_title)
                assert media_title
                result_link = media_title.find('a')
                # s2. Documents
                document_title = result_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                # if document_href.endswith('.pdf') is False:
                #    continue
                host = "https://www.autoriteprotectiondonnees.be"
                document_url = host + document_href
                print('document_url:', document_url)
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url, timeout=1000)
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
                    if document_url.endswith('.pdf') is False:
                        document_soup = BeautifulSoup(document_response.text, 'html.parser')
                        assert document_soup
                        date_text = document_soup.find('div', class_='date').get_text()
                        date_str = date_text[-4:]  # date_text[:-4] + ' ' + date_text[-4:]
                        tmp = dateparser.parse(date_str, languages=[self.language_code])
                        date = datetime.date(tmp.year, tmp.month, tmp.day)
                        if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                            return added_docs
                        if date.year < 2018:
                            print("Skipping outdated document")
                            return added_docs

                        page_body = document_soup.find('div', class_='page-body')
                        assert page_body
                        document_text = page_body.get_text()
                    else:
                        date_str = document_title.split(' du ')[-1]
                        print("\ndate:", date_str)
                        tmp = dateparser.parse(date_str, languages=[self.language_code])
                        if tmp is None:
                            media_date = media.find('span', class_="media-date")
                            assert media_date
                            year = int(media_date.get_text())
                            if year < 2018:
                                return added_docs
                        else:
                            date = datetime.date(tmp.year, tmp.month, tmp.day)
                            if date.year < 2018:
                                print("Skipping outdated document")
                                return added_docs

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_response.content)
                    if document_url.endswith('.pdf'):
                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                    else:
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
                    added_docs.append(document_hash)
                except FileExistsError:
                    print('Directory path already exists, continue.')
        return added_docs

    # Gets all documents located at guides link
    def get_docs_Guides(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Belgium Guides ===========================")
        added_docs = []

        host_link_input = "https://www.autoriteprotectiondonnees.be"
        start_path_input = "/citoyen/chercher?q=&search_category%5B%5D=taxonomy%3Apublications&search_type%5B%5D=recommendation&s=recent&l=25"
        page_url = host_link_input + start_path_input
        page_source = self.get_source(page_url)
        page_soup = BeautifulSoup(page_source.text, 'html.parser')
        pagination = self.update_pagination(page_soup=page_soup)

        iteration_number = 1
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url)
            if page_source is None:
                continue
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert page_soup
            search_result = page_soup.find('div', id='search-result')
            assert search_result
            # s1. Results
            for media in search_result.find_all('div', class_='media'):
                time.sleep(5)
                media_title = media.find('h3', class_='media-title')
                print("------------ Document " + str(iteration_number) + " ------------")
                iteration_number += 1
                # print('title:', media_title)
                assert media_title
                result_link = media_title.find('a')
                # s2. Documents
                document_title = result_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                host = "https://www.autoriteprotectiondonnees.be"
                document_url = host + document_href
                print('document_url:', document_url)
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url, timeout=1000)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Guides' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    if document_url.endswith('.pdf') is False:
                        document_soup = BeautifulSoup(document_response.text, 'html.parser')
                        assert document_soup
                        date_text = document_soup.find('div', class_='date').get_text()
                        date_str = date_text[-4:]  # date_text[:-4] + ' ' + date_text[-4:]
                        tmp = dateparser.parse(date_str, languages=[self.language_code])
                        date = datetime.date(tmp.year, tmp.month, tmp.day)
                        if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                            print("Skipping outdated document")
                            return added_docs
                        if date.year < 2018:
                            print("Skipping outdated document")
                            return added_docs
                        page_body = document_soup.find('div', class_='page-body')
                        assert page_body
                        document_text = page_body.get_text()
                    else:
                        date_str = document_title.split(' du ')[-1]
                        tmp = dateparser.parse(date_str, languages=[self.language_code])
                        if tmp is None:
                            media_date = media.find('span', class_="media-date")
                            assert media_date
                            year = int(media_date.get_text())
                            if year < 2018:
                                print("---> SKIPPING DOCUMENT BECAUSE OF DATE <---")
                                return added_docs
                        else:
                            date = datetime.date(tmp.year, tmp.month, tmp.day)
                            if date.year < 2018:
                                print("Skipping outdated document")
                                return added_docs

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_response.content)
                    if document_url.endswith('.pdf'):
                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                    else:
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
                    added_docs.append(document_hash)
                except FileExistsError:
                    print('Directory path already exists, continue.')

        return added_docs

    # Gets all documents located at annual report link
    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Belgium Annual Reports ===========================")
        added_docs = []

        page_url = "https://www.autoriteprotectiondonnees.be/citoyen/l-autorite/rapport-annuel"
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url)
        if page_source is None:
            sys.exit("Couldn't obtain page_source from page_url")
        page_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert page_soup
        page_content = page_soup.find('section', id='page-content')
        assert page_content
        page_body = page_content.find('div', class_='page-body')
        assert page_body

        iteration_number = 1
        for expanded in page_body.find_all('div', class_='collapse'):
            time.sleep(5)
            assert expanded
            result_link = expanded.find_all('a')
            assert result_link

            for link in result_link:
                document_href = link.get('href')
                assert document_href

                # If the document_href is not a pdf or zip file, its not relevant to our objective
                if not (document_href.endswith('.pdf') or document_href.endswith('.zip')):
                    continue

                # Get the year of the document by slicing document_href
                href_get_year = document_href[slice(-8, -4)]
                href_year_int = int(href_get_year)

                # If the document is older than 2018, skip it
                if href_year_int < 2018:
                    continue

                # Get document title by slicing it out of the href
                document_title = document_href[slice(-23, -4)]

                print('\n------------ Document ' + str(iteration_number) + '-------------')
                iteration_number += 1
                print('Document Title: ' + document_title)

                # If we don't want to overwrite documents and we already have this document_has in existing_docs,
                # skip the document
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                host = "https://www.autoriteprotectiondonnees.be"
                document_url = host + document_href

                print('document_url:', document_url)
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url, timeout=1000)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass

                if document_response is None:
                    continue

                dpa_folder = self.path

                document_folder = dpa_folder + '/' + 'AnnualReports' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    # If the link downloads a .zip file -> extract it, then iterate through the html files within it
                    # and store their text in one big text file. Store .txt file in document_folder
                    if document_url.endswith('.zip'):
                        with open(document_folder + '/' + self.language_code + '.zip', 'wb') as f:
                            f.write(document_response.content)
                        # Extract zip file
                        file_name = document_folder + '/' + self.language_code + '.zip'
                        with ZipFile(file_name, 'r') as zip:
                            print('\n--- ZIP FILE CONTENT ---')
                            os.chdir(document_folder)
                            zip.printdir()
                            zip.extractall()

                            print('\n--- CONVERTING .HTML TO .TXT ---')

                            # Iterate through the extracted zip folder -> concatenate the text within html files to one big
                            # text file
                            all_text_concatenated = ''
                            html_iteration = 1
                            for file in os.listdir(document_folder):
                                filename = os.fsdecode(file)
                                if 'Rapport annuel' in filename:
                                    for html_file in os.listdir(filename):
                                        os.chdir(filename)
                                        # print(html_file)
                                        with open(html_file, 'r') as f:
                                            contents = f.read()
                                            html_soup = BeautifulSoup(contents, 'html.parser')
                                            assert html_soup
                                            html_body = html_soup.find('body')
                                            assert html_body

                                            all_text_concatenated = html_body.get_text() + all_text_concatenated

                                        os.chdir(document_folder)

                                    # Store the text file in the document folder for the link
                                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                                        f.write(str.encode(all_text_concatenated))
                                        html_iteration += 1

                    # document_url ends with '.pdf'
                    else:
                        with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                            f.write(document_response.content)

                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)

                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': href_year_int,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)
                    iteration_number += 1
                except FileExistsError:
                    print('Directory path already exists, continue.')

        return added_docs
