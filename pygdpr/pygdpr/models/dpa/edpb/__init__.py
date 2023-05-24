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
from datetime import datetime

class EDPB(DPA):
    def __init__(self, path=os.curdir):
        country_code = 'edpb'
        super().__init__(country_code, path)

    # Must include start_path argument on initial call, and new_page_path an subsequent calls
    # start_path should be in the same format as usual
    # new_page_path is 'https://edpb.europa.eu' + start_path + 'unique new page sub-url' + 'new page href'
    # new_page_path is needed because in cases, the 'host' + 'start_path' + 'new page href' doesn't contain
    # the unique new page sub-url
    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path=None, new_page_path=None):
        host = "https://edpb.europa.eu"
        start_path = start_path

        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)

        elif pagination is not None:
            pagination_heading = page_soup.find('ul', class_='pagination')
            assert pagination_heading

            next_page_tag = pagination_heading.find('li', class_='pager__item--next')
            if next_page_tag is None:
                print("\nupdate_pagination: Couldn't find next page button. Stop")
            else:
                assert next_page_tag
                page_a = next_page_tag.find('a')
                assert page_a

                page_href = page_a.get('href')
                assert page_href

                page_link = new_page_path + page_href

                # If existing_pages contains the link already, don't add it again
                if pagination.has_link(page_link):
                    pass
                else:
                    print('\nupdate_pagination: adding link: ' + page_link)
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
        added_docs += self.get_docs_Recommendations(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Guidelines(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Opinions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Decisions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Letters(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)

        return added_docs



    def get_docs_Recommendations(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= EDPB Recommendations ===========================")
        added_docs = []
        dict_hashcode = {}
        iteration = 1

        page_url = 'https://edpb.europa.eu/our-work-tools/general-guidance/guidelines-recommendations-best-practices_en?f%5B0%5D=opinions_publication_type%3A98'
        if to_print:
            print('\nPage:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit("page_source is None")

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        view_content = results_soup.find('div', class_='view-content')
        assert view_content

        view_row_content = view_content.find('div', class_='view-row-content')
        assert view_row_content

        for views_row in view_row_content.find_all('div', class_='views-row'):
            assert views_row

            print('\n------------ Document: ' + str(iteration) + '-------------')
            iteration += 1

            # Get document date
            span = views_row.find('span', class_='news-date')
            assert span

            document_date = span.get_text()
            date_str = datetime.strptime(document_date, '%d %B %Y')
            date_str = date_str.strftime('%d/%m/%Y')
            print('\tDocument Date: ' + date_str)

            # If document year is less than 2018, skip it
            if int(document_date[-4:]) < 2018:
                print("\tSkipping outdated document: " + document_date)
                continue

            # Get document page link
            node_title = views_row.find('h4', class_='node__title')
            assert node_title

            a_tag = node_title.find('a')
            assert a_tag

            document_href = a_tag.get('href')
            assert document_href

            if document_href.startswith('http'):
                document_url = document_href
            else:
                document_url = 'https://edpb.europa.eu' + document_href

            print("\tDocument Page URL: " + document_url)

            # Get document title
            node_span = node_title.find('span')
            assert node_span

            document_title = node_span.get_text()
            print('\tDocument Title: ' + document_title)

            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            # documents have the same hashcode, but different dates
            date_part = date_str.replace('/', '_')
            if document_hash in dict_hashcode:
                document_hash = document_hash + '-' + date_part

            if to_print:
                print("\tDocument:", document_hash)

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

            article = document_soup.find('article', role='article')
            assert article

            # Check if there is 'final document version' notice that has a link -> if so, use this link
            alert_document = article.find('div', class_='alert')
            if alert_document is not None:
                print('\tGetting final version after public consultation')
                alert_a = alert_document.find('a')
                assert alert_a

                alert_href = alert_a.get('href')
                assert alert_href

                if alert_href.startswith('http'):
                    alert_url = alert_href
                else:
                    alert_url = 'https://edpb.europa.eu' + alert_href

                print('alert_url:' + alert_url)
                # Visit the page that contains the download link for the pdf
                alert_response = None
                try:
                    alert_response = requests.request('GET', alert_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if alert_response is None:
                    continue

                # Now get the pdf download link
                alert_soup = BeautifulSoup(alert_response.text, 'html.parser')
                assert alert_soup

                alert_article = alert_soup.find('article', role='article')
                assert alert_article

                col_sm_2 = alert_article.find('div', class_='col-sm-2')
                assert col_sm_2

                document_a = col_sm_2.find('a')
                assert document_a

                pdf_href = document_a.get('href')
                assert pdf_href

                if pdf_href.startswith('http'):
                    pdf_url = pdf_href
                else:
                    pdf_url = 'https://edpb.europa.eu' + pdf_href

                print('\tPDF URL: ' + pdf_url)

                # Download the pdf
                pdf_response = None
                try:
                    pdf_response = requests.request('GET', pdf_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if pdf_response is None:
                    continue

            else:
                col_sm_2 = article.find('div', class_='col-sm-2')
                assert col_sm_2

                document_a = col_sm_2.find('a')
                assert document_a

                pdf_href = document_a.get('href')
                assert pdf_href

                if pdf_href.startswith('http'):
                    pdf_url = pdf_href
                else:
                    pdf_url = 'https://edpb.europa.eu' + pdf_href

                print('\tPDF URL: ' + pdf_url)

                pdf_response = None
                try:
                    pdf_response = requests.request('GET', pdf_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if pdf_response is None:
                    continue

            dpa_folder = self.path

            dpa_folder = self.path
            # document_folder = dpa_folder + '/edpb' + '/' + 'Recommendations' + '/' + document_hash
            document_folder = dpa_folder + '/' + 'Recommendations' + '/' + document_hash

            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(pdf_response.content)
                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                    try:
                        pdf_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(pdf_text)
                    except:
                        pass
                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': date_str,
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True)
                added_docs.append(document_hash)
                dict_hashcode[document_hash] = date_part
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        return added_docs

    def get_docs_Guidelines(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= EDPB Guidelines ===========================")
        added_docs = []
        dict_hashcode = {}
        # Starting url is set to page 1, instead of the generic url (which lacks page specifier but starts at page 1)
        pagination = self.update_pagination(start_path='/our-work-tools/general-guidance/guidelines-recommendations-best-practices_en?f%5B0%5D=opinions_publication_type%3A64')

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nPage:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                print("page_source is None")
                continue

            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            view_content = results_soup.find('div', class_='view-content')
            assert view_content

            view_row_content = view_content.find('div', class_='view-row-content')
            assert view_row_content

            for views_row in view_row_content.find_all('div', class_='views-row'):
                assert views_row

                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                # Get document date
                span = views_row.find('span', class_='news-date')
                assert span

                document_date = span.get_text()
                date_str = datetime.strptime(document_date, '%d %B %Y')
                date_str = date_str.strftime('%d/%m/%Y')
                print('\tDocument date: ' + date_str)

                # If document year is less than 2018, skip it
                if int(document_date[-4:]) < 2018:
                    print("\tSkipping outdated document: " + document_date)
                    continue

                # Get document page link
                node_title = views_row.find('h4', class_='node__title')
                assert node_title

                a_tag = node_title.find('a')
                assert a_tag

                document_href = a_tag.get('href')
                assert document_href

                if document_href.startswith('http'):
                    document_url = document_href
                else:
                    document_url = 'https://edpb.europa.eu' + document_href

                print("\tDocument Page URL: " + document_url)

                # Get document title
                node_span = node_title.find('span')
                assert node_span

                document_title = node_span.get_text()
                print('\tDocument Title: ' + document_title)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                # documents have the same hashcode, but different dates
                date_part = date_str.replace('/', '_')
                if document_hash in dict_hashcode:
                    document_hash = document_hash + '-' + date_part
                print('\tDocument hash: ' + document_hash)

                dpa_folder = self.path

                # document_folder = dpa_folder + '/edpb' + '/' + 'Guidelines' + '/' + document_hash
                document_folder = dpa_folder + '/' + 'Guidelines' + '/' + document_hash

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

                article = document_soup.find('article', role='article')
                assert article

                # If the standard download button is missing
                if article.find('div', class_='col-sm-2') is None:
                    print('Standard download button is missing')

                    # avoid broken links
                    broken_links = ['bcce02dab0081e0017b2d4709b0d7df3', '1725b5ab1d3cf73aac4c82cb0246d717']
                    if document_hash in broken_links:
                        print('links is not working, continue')
                        continue

                    field_item = article.find('div', class_='field-item')

                    if field_item is None:
                        field_item = article.find('div', class_='text-formatted')
                        # print('doc 5 should be here')

                    field_a = field_item.find('a')
                    assert field_a

                    field_href = field_a.get('href')
                    assert field_href

                    field_response = None
                    try:
                        field_response = requests.request('GET', field_href)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if field_response is None:
                        continue

                    # Now get the pdf download links
                    field_soup = BeautifulSoup(field_response.text, 'html.parser')
                    assert field_soup

                    cnect = field_soup.find('div', class_='cnect-main-body')
                    assert cnect

                    try:
                        os.makedirs(document_folder)

                        pdf_iterator = 1
                        cnect_list = cnect.find_all('div', class_='ecl-u-mt-m')
                        # type 1 document
                        if len(cnect_list) == 0:
                            a = cnect.find('a')
                            href = a.get('href')
                            pdf_response = None
                            try:
                                pdf_response = requests.request('GET', href)
                            except requests.exceptions.HTTPError as error:
                                if to_print:
                                    print(error)
                                pass
                            if pdf_response is None:
                                continue

                            with open(document_folder + '/' + self.language_code + '.pdf',
                                      'wb') as f:
                                f.write(pdf_response.content)
                            with open(document_folder + '/' + self.language_code + '.txt',
                                      'wb') as f:
                                try:
                                    pdf_text = textract.process(
                                        document_folder + '/' + self.language_code + '.pdf')
                                    f.write(pdf_text)
                                except:
                                    pass
                        # type 2 document
                        else:
                            for div in cnect_list:

                                assert div
                                a = div.find('a')
                                assert a

                                href = a.get('href')
                                assert href

                                pdf_response = None
                                try:
                                    pdf_response = requests.request('GET', href)
                                except requests.exceptions.HTTPError as error:
                                    if to_print:
                                        print(error)
                                    pass
                                if pdf_response is None:
                                    continue

                                with open(document_folder + '/' + self.language_code + str(pdf_iterator) + '.pdf', 'wb') as f:
                                    f.write(pdf_response.content)
                                with open(document_folder + '/' + self.language_code + str(pdf_iterator) + '.txt', 'wb') as f:
                                    try:
                                        pdf_text = textract.process(document_folder + '/' + self.language_code + str(pdf_iterator) + '.pdf')
                                        f.write(pdf_text)
                                    except:
                                        pass
                                pdf_iterator += 1
                        with open(document_folder + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': {
                                    self.language_code: document_title
                                },
                                'md5': document_hash,
                                'releaseDate': date_str,
                                'url': document_url
                            }
                            json.dump(metadata, f, indent=4, sort_keys=True)
                        added_docs.append(document_hash)
                        dict_hashcode[document_hash] = date_part

                    except FileExistsError:
                        print("\tDirectory path already exists, continue.")

                    # Move to next outer for loop iteration (move to next overall document page on e)
                    continue

                # Check if there is 'final document version' notice that has a link -> if so, use this link
                alert_document = article.find('div', class_='alert')
                if alert_document is not None:
                    print('\tGetting final version after public consultation')
                    alert_a = alert_document.find('a')
                    assert alert_a

                    alert_href = alert_a.get('href')
                    assert alert_href

                    if alert_href.startswith('http'):
                        alert_url = alert_href
                    else:
                        alert_url = 'https://edpb.europa.eu' + alert_href

                    # Visit the page that contains the download link for the pdf
                    alert_response = None
                    try:
                        alert_response = requests.request('GET', alert_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if alert_response is None:
                        continue

                    # Now get the pdf download link
                    alert_soup = BeautifulSoup(alert_response.text, 'html.parser')
                    assert alert_soup

                    alert_article = alert_soup.find('article', role='article')
                    assert alert_article

                    col_sm_2 = alert_article.find('div', class_='col-sm-2')
                    assert col_sm_2

                    document_a = col_sm_2.find('a')
                    assert document_a

                    pdf_href = document_a.get('href')
                    assert pdf_href

                    if pdf_href.startswith('http'):
                        pdf_url = pdf_href
                    else:
                        pdf_url = 'https://edpb.europa.eu' + pdf_href

                    # Download the pdf
                    pdf_response = None
                    try:
                        pdf_response = requests.request('GET', pdf_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if pdf_response is None:
                        continue

                # There is no 'updated document after public consultation' link
                else:
                    col_sm_2 = article.find('div', class_='col-sm-2')
                    assert col_sm_2

                    document_a = col_sm_2.find('a')
                    assert document_a

                    pdf_href = document_a.get('href')
                    assert pdf_href

                    if pdf_href.startswith('http'):
                        pdf_url = pdf_href
                    else:
                        pdf_url = 'https://edpb.europa.eu' + pdf_href

                    pdf_response = None
                    try:
                        pdf_response = requests.request('GET', pdf_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if pdf_response is None:
                        continue

                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(pdf_response.content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        try:
                            pdf_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(pdf_text)
                        except:
                            pass
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': date_str,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True)
                    added_docs.append(document_hash)
                    dict_hashcode[document_hash] = date_part
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup, new_page_path='https://edpb.europa.eu/our-work-tools/general-guidance/guidelines-recommendations-best-practices_en')
        return added_docs

    def get_docs_Opinions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= EDPB Opinions ===========================")
        added_docs = []
        # Starting url is set to page 1, instead of the generic url (which lacks page specifier but starts at page 1)
        pagination = self.update_pagination(start_path='/our-work-tools/consistency-findings/opinions_en')

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nPage:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                print("page_source is None")
                continue

            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            view_content = results_soup.find('div', class_='view-content')
            assert view_content

            view_row_content = view_content.find('div', class_='view-row-content')
            assert view_row_content

            for views_row in view_row_content.find_all('div', class_='views-row'):
                assert views_row

                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                # Get document date
                span = views_row.find('span', class_='news-date')
                assert span

                document_date = span.get_text()
                date_str = datetime.strptime(document_date, '%d %B %Y')
                date_str = date_str.strftime('%d/%m/%Y')
                print('\tDocument date: ' + date_str)

                # If document year is less than 2018, skip it
                if int(document_date[-4:]) < 2018:
                    print("\tSkipping outdated document: " + document_date)
                    continue

                # Get document page link
                node_title = views_row.find('h4', class_='node__title')
                assert node_title

                a_tag = node_title.find('a')
                assert a_tag

                document_href = a_tag.get('href')
                assert document_href

                if document_href.startswith('http'):
                    document_url = document_href
                else:
                    document_url = 'https://edpb.europa.eu' + document_href

                print("\tDocument Page URL: " + document_url)

                # Get document title
                node_span = node_title.find('span')
                assert node_span

                document_title = node_span.get_text()
                print('\tDocument Title: ' + document_title)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

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

                article = document_soup.find('article', role='article')
                assert article

                # Check if there is 'final document version' notice that has a link -> if so, use this link
                alert_document = article.find('div', class_='alert')
                if alert_document is not None:
                    print('\tGetting final version after public consultation')
                    alert_a = alert_document.find('a')
                    assert alert_a

                    alert_href = alert_a.get('href')
                    assert alert_href

                    if alert_href.startswith('http'):
                        alert_url = alert_href
                    else:
                        alert_url = 'https://edpb.europa.eu' + alert_href

                    # Visit the page that contains the download link for the pdf
                    alert_response = None
                    try:
                        alert_response = requests.request('GET', alert_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if alert_response is None:
                        continue

                    # Now get the pdf download link
                    alert_soup = BeautifulSoup(alert_response.text, 'html.parser')
                    assert alert_soup

                    alert_article = alert_soup.find('article', role='article')
                    assert alert_article

                    col_sm_2 = alert_article.find('div', class_='col-sm-2')
                    assert col_sm_2

                    document_a = col_sm_2.find('a')
                    assert document_a

                    pdf_href = document_a.get('href')
                    assert pdf_href

                    if pdf_href.startswith('http'):
                        pdf_url = pdf_href
                    else:
                        pdf_url = 'https://edpb.europa.eu' + pdf_href

                    # Download the pdf
                    pdf_response = None
                    try:
                        pdf_response = requests.request('GET', pdf_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if pdf_response is None:
                        continue

                # There is no 'updated document after public consultation' link
                else:
                    col_sm_2 = article.find('div', class_='col-sm-2')
                    assert col_sm_2

                    document_a = col_sm_2.find('a')
                    assert document_a

                    pdf_href = document_a.get('href')
                    assert pdf_href

                    if pdf_href.startswith('http'):
                        pdf_url = pdf_href
                    else:
                        pdf_url = 'https://edpb.europa.eu' + pdf_href

                    pdf_response = None
                    try:
                        pdf_response = requests.request('GET', pdf_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    except requests.exceptions.ConnectionError as error:
                        if to_print:
                            print(error)
                    if pdf_response is None:
                        continue

                dpa_folder = self.path
                # document_folder = dpa_folder + '/edpb' + '/' + 'Opinions' + '/' + document_hash
                document_folder = dpa_folder + '/' + 'Opinions' + '/' + document_hash

                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(pdf_response.content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        try:
                            pdf_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(pdf_text)
                        except:
                            pass
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': date_str,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True)
                    added_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup, new_page_path='https://edpb.europa.eu/our-work-tools/consistency-findings/opinions_en')
        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= EDPB Decision Documents ===========================")
        added_docs = []

        iteration = 1

        page_url = 'https://edpb.europa.eu/our-work-tools/consistency-findings/binding-decisions_en'
        if to_print:
            print('\nPage:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit("page_source is None")

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        view_content = results_soup.find('div', class_='view-content')
        assert view_content

        view_row_content = view_content.find('div', class_='view-row-content')
        assert view_row_content

        for views_row in view_row_content.find_all('div', class_='views-row'):
            assert views_row

            print('\n------------ Document: ' + str(iteration) + '-------------')
            iteration += 1

            # Get document date
            span = views_row.find('span', class_='news-date')
            assert span

            document_date = span.get_text()
            date_str = datetime.strptime(document_date, '%d %B %Y')
            date_str = date_str.strftime('%d/%m/%Y')
            print('\tDocument Date: ' + date_str)

            # If document year is less than 2018, skip it
            if int(document_date[-4:]) < 2018:
                print("\tSkipping outdated document: " + document_date)
                continue

            # Get document page link
            node_title = views_row.find('h4', class_='node__title')
            assert node_title

            a_tag = node_title.find('a')
            assert a_tag

            document_href = a_tag.get('href')
            assert document_href

            if document_href.startswith('http'):
                document_url = document_href
            else:
                document_url = 'https://edpb.europa.eu' + document_href

            print("\tDocument Page URL: " + document_url)

            # Get document title
            node_span = node_title.find('span')
            assert node_span

            document_title = node_span.get_text()
            print('\tDocument Title: ' + document_title)

            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

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

            article = document_soup.find('article', role='article')
            assert article

            # Check if there is 'final document version' notice that has a link -> if so, use this link
            alert_document = article.find('div', class_='alert')
            if alert_document is not None:
                print('\tGetting final version after public consultation')
                alert_a = alert_document.find('a')
                assert alert_a

                alert_href = alert_a.get('href')
                assert alert_href

                if alert_href.startswith('http'):
                    alert_url = alert_href
                else:
                    alert_url = 'https://edpb.europa.eu' + alert_href

                print('alert_url:' + alert_url)
                # Visit the page that contains the download link for the pdf
                alert_response = None
                try:
                    alert_response = requests.request('GET', alert_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if alert_response is None:
                    continue

                # Now get the pdf download link
                alert_soup = BeautifulSoup(alert_response.text, 'html.parser')
                assert alert_soup

                alert_article = alert_soup.find('article', role='article')
                assert alert_article

                col_sm_2 = alert_article.find('div', class_='col-sm-2')
                assert col_sm_2

                document_a = col_sm_2.find('a')
                assert document_a

                pdf_href = document_a.get('href')
                assert pdf_href

                if pdf_href.startswith('http'):
                    pdf_url = pdf_href
                else:
                    pdf_url = 'https://edpb.europa.eu' + pdf_href

                print('\tPDF URL: ' + pdf_url)

                # Download the pdf
                pdf_response = None
                try:
                    pdf_response = requests.request('GET', pdf_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if pdf_response is None:
                    continue

            else:
                col_sm_2 = article.find('div', class_='col-sm-2')
                assert col_sm_2

                document_a = col_sm_2.find('a')
                assert document_a

                pdf_href = document_a.get('href')
                assert pdf_href

                if pdf_href.startswith('http'):
                    pdf_url = pdf_href
                else:
                    pdf_url = 'https://edpb.europa.eu' + pdf_href

                print('\tPDF URL: ' + pdf_url)

                pdf_response = None
                try:
                    pdf_response = requests.request('GET', pdf_url)
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if pdf_response is None:
                    continue

            dpa_folder = self.path
            # document_folder = dpa_folder + '/edpb' + '/' + 'Decisions' + '/' + document_hash
            document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash

            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(pdf_response.content)
                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                    try:
                        pdf_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(pdf_text)
                    except:
                        pass
                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': date_str,
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True)
                added_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        return added_docs

    # Some old document pages are blank -> skip them
    def get_docs_Letters(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= EDPB Letters ===========================")
        added_docs = []

        pagination = self.update_pagination(start_path='/our-work-tools/documents/letters_en')

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\nPage:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                print("page_source is None")
                continue

            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            view_content = results_soup.find('div', class_='view-content')
            assert view_content

            view_row_content = view_content.find('div', class_='view-row-content')
            assert view_row_content

            for views_row in view_row_content.find_all('div', class_='views-row'):
                assert views_row

                print('\n------------ Document: ' + str(iteration) + '-------------')
                iteration += 1

                # Get document date
                span = views_row.find('span', class_='news-date')
                assert span

                document_date = span.get_text()
                date_str = datetime.strptime(document_date, '%d %B %Y')
                date_str = date_str.strftime('%d/%m/%Y')
                print('\tDocument Date: ' + date_str)

                # If document year is less than 2018, skip it
                if int(document_date[-4:]) < 2018:
                    print("\tSkipping outdated document: " + document_date)
                    continue

                # Get document page link
                node_title = views_row.find('h4', class_='node__title')
                assert node_title

                a_tag = node_title.find('a')
                assert a_tag

                document_href = a_tag.get('href')
                assert document_href

                if document_href.startswith('http'):
                    document_url = document_href
                else:
                    document_url = 'https://edpb.europa.eu' + document_href

                print("\tDocument Page URL: " + document_url)

                # Get document title
                node_span = node_title.find('span')
                assert node_span

                document_title = node_span.get_text()
                print('\tDocument Title: ' + document_title)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

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

                article = document_soup.find('article', role='article')
                assert article

                # Check if there is 'final document version' notice that has a link -> if so, use this link
                alert_document = article.find('div', class_='alert')
                if alert_document is not None:
                    print('\tGetting final version after public consultation')
                    alert_a = alert_document.find('a')
                    assert alert_a

                    alert_href = alert_a.get('href')
                    assert alert_href

                    if alert_href.startswith('http'):
                        alert_url = alert_href
                    else:
                        alert_url = 'https://edpb.europa.eu' + alert_href

                    # Visit the page that contains the download link for the pdf
                    alert_response = None
                    try:
                        alert_response = requests.request('GET', alert_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if alert_response is None:
                        continue

                    # Now get the pdf download link
                    alert_soup = BeautifulSoup(alert_response.text, 'html.parser')
                    assert alert_soup

                    alert_article = alert_soup.find('article', role='article')
                    assert alert_article

                    col_sm_2 = alert_article.find('div', class_='col-sm-2')
                    assert col_sm_2

                    document_a = col_sm_2.find('a')
                    assert document_a

                    pdf_href = document_a.get('href')
                    assert pdf_href

                    if pdf_href.startswith('http'):
                        pdf_url = pdf_href
                    else:
                        pdf_url = 'https://edpb.europa.eu' + pdf_href

                    # Download the pdf
                    pdf_response = None
                    try:
                        pdf_response = requests.request('GET', pdf_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if pdf_response is None:
                        continue

                # There is no 'updated document after public consultation' link
                else:
                    col_sm_2 = article.find('div', class_='col-sm-2')

                    # This usually means the document page is blank
                    if col_sm_2 is None:
                        print("\tUnable to parse data on document page")
                        continue

                    document_a = col_sm_2.find('a')
                    assert document_a

                    pdf_href = document_a.get('href')
                    assert pdf_href

                    if pdf_href.startswith('http'):
                        pdf_url = pdf_href
                    else:
                        pdf_url = 'https://edpb.europa.eu' + pdf_href

                    pdf_response = None
                    try:
                        pdf_response = requests.request('GET', pdf_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if pdf_response is None:
                        continue

                dpa_folder = self.path
                # document_folder = dpa_folder + '/edpb' + '/' + 'Letters' + '/' + document_hash
                document_folder = dpa_folder + '/' + 'Letters' + '/' + document_hash

                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(pdf_response.content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        try:
                            pdf_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(pdf_text)
                        except:
                            pass
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': date_str,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True)
                    added_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup, new_page_path='https://edpb.europa.eu/our-work-tools/documents/letters_en')
        return added_docs

    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):

        print("\n========================= EDPB Annual Reports ===========================")
        added_docs = []

        iteration = 1

        page_url = 'https://edpb.europa.eu/about-edpb/about-edpb/annual-reports_en'
        if to_print:
            print('\nPage:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit("page_source is None")

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        view_content = results_soup.find('div', class_='view-content')
        assert view_content

        view_row_content = view_content.find('div', class_='view-row-content')
        assert view_row_content

        for views_row in view_row_content.find_all('div', class_='views-row'):
            assert views_row

            print('\n------------ Document: ' + str(iteration) + '-------------')
            iteration += 1

            # Get document date
            span = views_row.find('span', class_='news-date')
            assert span

            document_date = span.get_text()
            date_str = datetime.strptime(document_date, '%d %B %Y')
            date_str = date_str.strftime('%d/%m/%Y')
            print('\tDocument Date: ' + date_str)

            # If document year is less than 2018, skip it
            if int(document_date[-4:]) < 2018:
                print("\tSkipping outdated document: " + document_date)
                continue

            # Get document page link
            node_title = views_row.find('h4', class_='node__title')
            assert node_title

            a_tag = node_title.find('a')
            assert a_tag

            document_href = a_tag.get('href')
            assert document_href

            if document_href.startswith('http'):
                document_url = document_href
            else:
                document_url = 'https://edpb.europa.eu' + document_href

            print("\tDocument Page URL: " + document_url)

            # Get document title
            node_span = node_title.find('span')
            assert node_span

            document_title = node_span.get_text()
            print('\tDocument Title: ' + document_title)

            document_hash = hashlib.md5(document_title.encode()).hexdigest()

            if (document_hash in existing_docs) and (overwrite is False):
                if to_print:
                    print('\tSkipping existing document (It exists in visitedDocs.txt):\t', document_hash)
                continue

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

            article = document_soup.find('article', role='article')
            assert article

            col_sm_2 = article.find_all('div', class_='col-sm-2')
            assert col_sm_2

            dpa_folder = self.path
            # Put documents in folder for the dpa automatically
            # document_folder = dpa_folder + '/edpb' + '/' + 'Annual Reports' + '/' + document_hash
            document_folder = dpa_folder + '/' + 'Annual Reports' + '/' + document_hash

            try:
                os.makedirs(document_folder)

                # There are usually two pdf's -> the actual report, and an executive summary
                pdf_iteration = 1
                for col in col_sm_2:
                    document_a = col.find('a')
                    assert document_a

                    pdf_href = document_a.get('href')
                    assert pdf_href

                    if pdf_href.startswith('http'):
                        pdf_url = pdf_href
                    else:
                        pdf_url = 'https://edpb.europa.eu' + pdf_href

                    print('\tPDF URL: ' + pdf_url)

                    pdf_response = None
                    try:
                        pdf_response = requests.request('GET', pdf_url)
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if pdf_response is None:
                        continue

                    with open(document_folder + '/' + self.language_code + str(pdf_iteration) + '.pdf', 'wb') as f:
                        f.write(pdf_response.content)
                    with open(document_folder + '/' + self.language_code + str(pdf_iteration) + '.txt', 'wb') as f:
                        try:
                            pdf_text = textract.process(document_folder + '/' + self.language_code + str(pdf_iteration) + '.pdf')
                            f.write(pdf_text)
                        except:
                            pass
                    pdf_iteration += 1

                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': date_str,
                        'releaseDate': document_date,
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True)
                added_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        # Contains unique hashes not in master file...
        return added_docs
