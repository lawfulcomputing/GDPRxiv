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
import urllib3

class Portugal(DPA):
    def __init__(self, path=os.curdir):
        country_code='pt'
        super().__init__(country_code, path)

    # I add pgd=1 at end of default start_path string
    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://www.cnpd.pt",
            "start_path": "/decisoes/historico-de-decisoes/?year=2022"
        }
        host = source['host']
        start_path = source['start_path']

        # Just add initial page
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)

            # add previous year links
            previous_year = ['2021', '2020', '2019', '2018']
            for i in range(len(previous_year)):
                 start_path = start_path[:-4] + previous_year[i]
                 print('previous_year: ', host + start_path)
                 pagination.add_item(host + start_path)
        # Add next page
        else:
            c_pagination = page_soup.find('div', class_='c-pagination')
            if c_pagination is not None:
                for a in c_pagination.find_all('a'):
                    page_href = a.get('href')
                    # Only add link if not in objects link list
                    if pagination.has_link('href'):
                        continue
                    else:
                        pagination.add_item(page_href)
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
        added_docs += self.get_docs_Decisions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Reports(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Guidelines(existing_docs=[], overwrite=False, to_print=True)

        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Portugal Decision Documents =========================")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        added_docs = []
        pagination = self.update_pagination()
        iteration = 1
        while pagination.has_next():

            page_url = pagination.get_next()
            if to_print:
                print('\nPage: ', page_url)

            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                sys.exit('Page source is None')

            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            layout = results_soup.find('div', class_='layout')
            assert layout

            for c_card in layout.find_all('div', class_='c-card'):
                result_link = c_card.find('a')
                if result_link is None:
                    continue

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                document_title = result_link.find('div', 'c-card-header-medium')
                assert document_title

                document_title = document_title.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                print('\tDocument Title: ' + document_title)

                document_date = document_title[-4:]
                print('\tDocument Date: ' + document_date)

                if int(document_date) < 2018:
                    print("Skipping outdated document")
                    continue

                document_href = result_link.get('href')

                # ignore one page with "content not found" issue
                ignore_list = ['121657', '121658']
                if document_href[-6:] in ignore_list:
                    print("\tcontent not found")
                    continue

                host = "https://www.cnpd.pt"
                document_url = host + document_href
                if to_print:
                    print("\tDocument:\t", document_hash)
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

                print('\tDocument URL: ' + document_url)

                document_content = document_response.content
                dpa_folder = self.path

                document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        link_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(link_text)
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
            self.update_pagination(pagination=pagination, page_soup=results_soup)

        return added_docs

    def get_docs_Reports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Portugal Reports =========================")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        added_docs = []

        iteration = 1

        page_url = 'https://www.cnpd.pt/cnpd/relatorios-de-atividades/'
        if to_print:
            print('\nPage: ', page_url)

        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit('Page source is None')

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        layout = results_soup.find('div', class_='layout')
        assert layout

        c_content = layout.find('div', class_='c-content-text')
        assert c_content

        for p_tag in c_content.find_all('p'):
            assert p_tag

            result_link = p_tag.find('a')
            if result_link is None:
                continue

            print('\n------------ Document ' + str(iteration) + ' ------------')
            iteration += 1

            document_title = result_link.get_text()
            assert document_title

            print('\tDocument Title:\t' + document_title)

            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            document_date = document_title[-4:]
            print('\tDocument Date:\t' + document_date)

            if int(document_date) < 2018:
                print("\tSKIPPING OUTDATED DOCUMENT")
                continue

            document_href = result_link.get('href')
            host = "https://www.cnpd.pt"
            document_url = host + document_href

            if to_print:
                print("\tDocument:\t", document_hash)
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

            print('\tDocument URL:\t' + document_url)

            document_content = document_response.content
            dpa_folder = self.path

            document_folder = dpa_folder + '/' + 'Reports' + '/' + document_hash
            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_content)
                try:
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        link_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(link_text)
                except:
                    print('Can not convert pdf to txt')
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

    def get_docs_Guidelines(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Portugal Guidelines =========================")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        added_docs = []
        pagination = self.update_pagination()

        page_url = 'https://www.cnpd.pt/organizacoes/orientacoes-e-recomendacoes/'
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit('Page source is None')

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        layout = results_soup.find('div', class_='layout')
        assert layout

        side_nav = layout.find('ul', class_='sidenav-content')
        assert side_nav

        iteration = 1
        for li in side_nav.find_all('li'):
            assert li

            a_tag = li.find('a')
            assert a_tag

            href = a_tag.get('href')
            assert href

            if href.startswith('http') and 'download' in href:
                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1
                document_title = a_tag.get_text()
                print('\tdocument_title: ' + document_title)
                print('\tPDF Link: ' + href)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                print('\tdocument_hash: ' + document_hash)

                response = None
                try:
                    response = requests.request('GET', href, verify=False)
                    response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if response is None:
                    continue

                content = response.content

                dpa_folder = self.path
                document_folder = dpa_folder + '/' 'Guidelines' + '/' + document_hash

                try:
                    os.makedirs(document_folder)
                except FileExistsError:
                    pass
                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(content)
                try:
                    with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        document_text = PDFToTextService().text_from_pdf_path(document_folder + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                except:
                    print('\tFailed to convert PDF to text')

                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': None,
                        'url': href
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                added_docs.append(document_hash)
                continue

            url = "https://www.cnpd.pt" + href

            response = None
            try:
                response = requests.request('GET', url, verify=False)
                response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                if to_print:
                    print(error)
                pass
            if response is None:
                continue

            page_soup = BeautifulSoup(response.text, 'html.parser')
            assert page_soup

            page_layout = page_soup.find('div', class_='layout')
            assert page_layout

            c_content = page_layout.find('div', class_='c-content-text')
            assert c_content

            for p in c_content.find_all('p'):
                assert p

                a = p.find('a')
                assert a

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                document_title = a.get_text()
                print('\tDocument Title: ' + document_title)

                p_tag_all_text = p.get_text()
                assert p_tag_all_text

                document_date = p_tag_all_text[-4:]

                print('\tDocument Date: ' + document_date)

                if int(document_date) < 2018:
                    print('\tSkipping outdated document')
                    continue

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                pdf_href = a.get('href')
                assert pdf_href

                pdf_url = "https://www.cnpd.pt" + pdf_href

                print('\tPDF Link: ' + pdf_url)

                response = None
                try:
                    pdf_response = requests.request('GET', pdf_url, verify=False)
                    pdf_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if pdf_response is None:
                    continue

                pdf_content = pdf_response.content

                dpa_folder = self.path
                document_folder = dpa_folder + '/' 'Guidelines' + '/' + document_hash

                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(pdf_content)
                    try:
                        with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                            document_text = PDFToTextService().text_from_pdf_path(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                    except:
                        print('\tFailed to convert PDF to text')

                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': document_date,
                            'url': pdf_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
        return added_docs
