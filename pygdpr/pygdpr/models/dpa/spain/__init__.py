import os
import time
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


class Spain(DPA):
    def __init__(self, path=os.curdir):
        country_code='es'
        super().__init__(country_code, path)

    # Added two new arguments: new_page_type and start_path
    # new_page_type: indicates the type of document we are scraping. This is needed to index the correct link
    # sub-string in source{} when adding additional pages to the pagination object
    # start_path: this is the usual start_path parameter normally contained in source{}. It's just passed as an
    # argument now
    def update_pagination(self, pagination=None, page_soup=None, driver=None, new_page_type=None, start_path=None):
        source = {
            "host": "https://www.aepd.es",
            "new_page_decisions": "/es/informes-y-resoluciones/resoluciones",
            "new_page_reports": "/es/informes-y-resoluciones/informes-juridicos",
            "new_page_guides": "/es/guias-y-herramientas/guias",
            "new_page_infographics": "/es/guias-y-herramientas/infografias",
            "new_page_blogs": "/es/prensa-y-comunicacion/blog"
        }
        host = source['host']
        start_path_new_page = source[new_page_type]

        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            assert page_soup is not None
            pager = page_soup.find('nav', class_='pager')
            assert pager
            pager_items = pager.find('ul', class_='pager__items')
            assert pager_items

            li = pager_items.find('li', class_='pager__item--next')
            if li is not None:
                page_link = li.find('a')
                page_href = page_link.get('href')
                page_link = host + start_path_new_page + page_href
                if not pagination.has_link(page_link):
                    print('\n')
                    # print('Adding page: ' + page_link + ' to pagination object')
                    pagination.add_item(page_link)

        return pagination

    def get_source(self, page_url=None, driver=None):
        assert (page_url is not None)
        page_source = None
        try:
            page_source = requests.request('GET', page_url)
            page_source.raise_for_status()
        except requests.exceptions.HTTPError as error:
            pass
        return page_source

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_Decisions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Reports(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Guides(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Infographics(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Blogs(existing_docs=[], overwrite=False, to_print=True)

        return added_docs


    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Spain Decision Documents =========================")

        added_docs = []
        pagination = self.update_pagination(new_page_type='new_page_decisions', start_path='/es/informes-y-resoluciones/resoluciones?f%5B0%5D=ley_tipificacion_de_la_gravedad%3AReglamento%20General%20de%20Protecci%C3%B3n%20de%20Datos')

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nNEW PAGE: ' + page_url)

            page_source = self.get_source(page_url=page_url)
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert page_soup

            view_content = page_soup.find('div', class_='view-content')
            assert view_content

            for views_row in view_content.find_all('div', class_='views-row'):
                time.sleep(2)
                views_field_title = views_row.find('div', class_='views-field-title')
                assert views_field_title
                result_link = views_field_title.find('a')
                if result_link is None:
                    continue

                document_title = result_link.get_text()

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                print('\tDocument Title: ' + document_title)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                if document_href.endswith('.pdf') is False:
                    continue
                host = "https://www.aepd.es"
                document_url = host + document_href

                print('\tDocument URL: ' + document_url)
                views_field_field_advertise_on = views_row.find('div', class_='views-field-field-advertise-on')
                assert views_field_field_advertise_on
                time_ = views_field_field_advertise_on.find('time')
                assert time_
                date_part = time_.get('datetime')
                date_str = date_part.split('T')[0]
                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                print('\tDocument Date: ' + str(date))

                document_year = str(date)[0:4]

                # By the time we reach document from 2017 and below, it is unlikely to encounter any relevant ones
                if int(document_year) < 2018:
                    # sys.exit('Remaining documents outdated')
                    print('Remaining documents outdated')
                    return added_docs

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print('Before GDPR adopted')
                    continue

                if to_print:
                    print("\tDocument:", document_hash)

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

                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        try:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                        except:
                            print('Failed to convert PDF to text')
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
                    print("\tDirectory path already exists, continue.")
            pagination = self.update_pagination(pagination=pagination, page_soup=page_soup, new_page_type='new_page_decisions', start_path='/es/informes-y-resoluciones/resoluciones?f%5B0%5D=ley_tipificacion_de_la_gravedad%3AReglamento%20General%20de%20Protecci%C3%B3n%20de%20Datos')
        return added_docs

    def get_docs_Reports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Spain Reports =========================")

        added_docs = []
        pagination = self.update_pagination(new_page_type="new_page_reports", start_path='/informes-y-resoluciones/informes-juridicos?f%5B0%5D=informes_disposiciones_estudiadas%3AReglamento%20General%20de%20Protecci%C3%B3n%20de%20Datos%20UE%202016/679')

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nNEW PAGE: ' + page_url)

            page_source = self.get_source(page_url=page_url)
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert page_soup

            view_content = page_soup.find('div', class_='view-content')
            assert view_content

            for views_row in view_content.find_all('div', class_='views-row'):
                time.sleep(2)
                views_field_title = views_row.find('div', class_='views-field-title')
                assert views_field_title
                result_link = views_field_title.find('a')
                if result_link is None:
                    continue

                document_title = result_link.get_text()

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                print('\tDocument Title: ' + document_title)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                if document_href.endswith('.pdf') is False:
                    continue
                host = "https://www.aepd.es"
                document_url = host + document_href

                print('\tDocument URL: ' + document_url)
                views_field_field_advertise_on = views_row.find('div', class_='views-field-field-advertise-on')
                assert views_field_field_advertise_on
                time_ = views_field_field_advertise_on.find('time')
                assert time_
                date_str = time_.get('datetime')
                date_str = date_str.split('T')[0]
                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                print('\tDocument Date: ' + str(date))

                document_year = str(date)[0:4]
                # By the time we reach document from 2017 and below, it is unlikely to encounter any relevant ones
                if int(document_year) < 2018:
                    # sys.exit('Remaining documents outdated')
                    print('Remaining documents outdated')
                    return added_docs

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print('Before GDPR adopted')
                    continue

                if to_print:
                    print("\tDocument:", document_hash)

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
                        try:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                        except:
                            print('Failed to convert PDF to text')
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
                    print("\tDirectory path already exists, continue.")
            pagination = self.update_pagination(pagination=pagination, page_soup=page_soup, new_page_type="new_page_reports", start_path='/informes-y-resoluciones/informes-juridicos?f%5B0%5D=informes_disposiciones_estudiadas%3AReglamento%20General%20de%20Protecci%C3%B3n%20de%20Datos%20UE%202016/679')
        return added_docs

    def get_docs_Guides(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Spain Guides =========================")

        added_docs = []
        pagination = self.update_pagination(new_page_type="new_page_guides", start_path='/es/guias-y-herramientas/guias')

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nNEW PAGE: ' + page_url)

            page_source = self.get_source(page_url=page_url)
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert page_soup

            view_content = page_soup.find('div', class_='view-content')
            assert view_content

            for views_row in view_content.find_all('div', class_='views-row'):
                time.sleep(2)
                views_field_title = views_row.find('div', class_='views-field-title')
                assert views_field_title
                document_title = views_field_title.get_text()

                views_field_advertise = views_row.find('div', class_='views-field-field-advertise-on')
                assert views_field_advertise

                views_time = views_field_advertise.find('time')
                assert views_time
                document_date = views_time.get('datetime')
                date_str = document_date.split('T')[0]
                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                result_link = views_row.find('a')
                if result_link is None:
                    continue

                # document_title = result_link.get_text()

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                print('\tDocument Title: ' + document_title)

                print('\tDocument Date: ' + date_str)

                document_year = str(date)[0:4]
                # By the time we reach document from 2017 and below, it is unlikely to encounter any relevant ones
                if int(document_year) < 2018:
                    # sys.exit('Remaining documents outdated')
                    print('Remaining documents outdated')
                    return added_docs

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print('Before GDPR adopted')
                    continue

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href

                host = "https://www.aepd.es"

                if document_href.startswith('http'):
                    document_url = document_href
                else:
                    document_url = host + document_href

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

                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Guides' + '/' + document_hash

                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        try:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)
                        except:
                            print('\tFailed to convert PDF to text')
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
                    print("\tDirectory path already exists, continue.")
            pagination = self.update_pagination(pagination=pagination, page_soup=page_soup, new_page_type="new_page_guides", start_path='/es/guias-y-herramientas/guias')
        return added_docs

    def get_docs_Infographics(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Spain Infographics =========================")

        added_docs = []
        pagination = self.update_pagination(new_page_type="new_page_infographics", start_path='/es/guias-y-herramientas/infografias')

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nNEW PAGE: ' + page_url)

            page_source = self.get_source(page_url=page_url)
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert page_soup

            view_content = page_soup.find('div', class_='view-content')
            assert view_content

            for views_row in view_content.find_all('div', class_='views-row'):
                time.sleep(2)
                views_field_title = views_row.find('div', class_='views-field-title')
                assert views_field_title

                # Find the document date
                views_field_advertise = views_row.find('div', class_='views-field-field-advertise-on')
                assert views_field_advertise

                views_time = views_field_advertise.find('time')
                assert views_time
                document_date = views_time.get('datetime')
                date_str = document_date.split('T')[0]
                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                # Get the document result link
                result_link = views_field_title.find('a')
                if result_link is None:
                    continue

                document_title = result_link.get_text()

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                print('\tDocument Title: ' + document_title)

                print('\tDocument Date: ' + date_str)

                document_year = str(date)[0:4]
                # By the time we reach document from 2017 and below, it is unlikely to encounter any relevant ones
                if int(document_year) < 2018:
                    # sys.exit('Remaining documents outdated')
                    print('Remaining documents outdated')
                    return added_docs

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print('Before GDPR adopted')
                    continue

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href

                host = "https://www.aepd.es"

                if document_href.startswith('http'):
                    document_url = document_href
                else:
                    document_url = host + document_href

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

                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Infographics' + '/' + document_hash

                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        try:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
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
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            pagination = self.update_pagination(pagination=pagination, page_soup=page_soup, new_page_type="new_page_infographics", start_path='/es/guias-y-herramientas/infografias')
        return added_docs

    def get_docs_Blogs(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== Spain Blogs =========================")

        added_docs = []
        pagination = self.update_pagination(new_page_type="new_page_blogs", start_path='/es/prensa-y-comunicacion/blog')

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nNEW PAGE: ' + page_url)

            page_source = self.get_source(page_url=page_url)
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert page_soup

            view_content = page_soup.find('div', class_='view-content')
            assert view_content

            for li in view_content.find_all('li'):
                time.sleep(2)

                views_field_title = li.find('div', class_='views-field-title')
                assert views_field_title

                # Find the document date
                views_field_advertise = li.find('div', class_='views-field-field-advertise-on')
                assert views_field_advertise

                views_time = views_field_advertise.find('time')
                assert views_time
                document_date = views_time.get('datetime')
                date_str = document_date.split('T')[0]
                tmp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                # Get the document result link
                result_link = views_field_title.find('a')
                if result_link is None:
                    continue

                document_title = result_link.get_text()

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                print('\tDocument Title: ' + document_title)

                print('\tDocument Date: ' + date_str)

                document_year = str(date)[0:4]
                # By the time we reach document from 2017 and below, it is unlikely to encounter any relevant ones
                if int(document_year) < 2018:
                    # sys.exit('Remaining documents outdated')
                    print('Remaining documents outdated')
                    return added_docs

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print('Before GDPR adopted')
                    continue

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href

                host = "https://www.aepd.es"

                if document_href.startswith('http'):
                    document_url = document_href
                else:
                    document_url = host + document_href

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

                # Get the document text
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                main_content = document_soup.find('main')
                assert main_content

                layout_wrapper = main_content.find('div', class_='layout-wrapper')
                assert layout_wrapper

                document_text = layout_wrapper.get_text()

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Blogs' + '/' + document_hash

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
                            'releaseDate': document_date,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            pagination = self.update_pagination(pagination=pagination, page_soup=page_soup, new_page_type="new_page_blogs", start_path='/es/prensa-y-comunicacion/blog')
        return added_docs
