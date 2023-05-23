import os
import math
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
import time
import sys
import re

class Italy(DPA):
    def __init__(self, path=os.curdir):
        country_code='IT'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path=None):
        source = {
            "host": "https://www.garanteprivacy.it",
            "start_path": "/web/guest/home/stampa-comunicazione/interviste"
        }
        host = source['host']
        start_path = start_path

        if page_soup is not None:
            pagination = Pagination()

            # Page soup should be the page results_soup object
            pages = page_soup.find('ul', class_='pagination justify-content-center mt-3')
            assert pages

            li_page_list = pages.find_all('li', class_='page-item')
            assert li_page_list

            last_page_a = li_page_list[-2].find('a')
            assert last_page_a

            num_pages = int(last_page_a.get_text())

            # Add all the pages (including the first here)
            for num in range(1, num_pages + 1):
                page_link = host + start_path + str(num)
                # print(page_link)
                pagination.add_item(page_link)
        else:
            print("Please give update_pagination() a page_source argument")
            pass

        return pagination

    # Returns pagination list but the reverse of update_pagination
    def update_pagination_backwards(self, pagination=None, page_soup=None, driver=None, start_path=None):
        source = {
            "host": "https://www.garanteprivacy.it",
            "start_path": "/web/guest/home/stampa-comunicazione/interviste"
        }
        host = source['host']
        start_path = start_path

        if page_soup is not None:
            pagination = Pagination()

            # Page soup should be the page results_soup object
            pages = page_soup.find('ul', class_='pagination justify-content-center mt-3')
            assert pages

            li_page_list = pages.find_all('li', class_='page-item')
            assert li_page_list

            last_page_a = li_page_list[-2].find('a')
            assert last_page_a

            num_pages = int(last_page_a.get_text())

            # Add all the pages (including the first here)
            for num in range(num_pages, 0, -1):
                page_link = host + start_path + str(num)
                # print(page_link)
                pagination.add_item(page_link)
        else:
            print("Please give update_pagination() a page_source argument")
            pass

        return pagination

    def get_source(self, page_url=None, driver=None, to_print=True):
        assert (page_url is not None)
        results_response = None
        try:
            results_response = requests.request('GET', page_url, timeout=5)
            results_response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            if to_print:
                print(error)
            pass
        return results_response

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_Interviews(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Publications(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Newsletters(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Injunctions(existing_docs=[], overwrite=False, to_print=True)
        # added_docs += self.get_docs_InjunctionsFromLastPage(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Hearings(existing_docs=[], overwrite=False, to_print=True)

        return added_docs

    def get_docs_Interviews(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Italy Decision Documents ===========================")
        added_docs = []

        page_url = 'https://www.garanteprivacy.it/home/stampa-comunicazione/interviste'
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit('page_source is None')
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        testo = results_soup.find('div', class_='testo')
        assert testo
        ul_all = testo.find_all('ul', recursive=False)

        # Use iterator to keep track of document number
        iterator = 1
        for ul in ul_all:
            for li in ul.find_all('li'):
                time.sleep(2)
                result_link = li.find('a')
                assert result_link

                print('\n------------ Document ' + str(iterator) + ' ------------')
                iterator += 1

                document_title = result_link.get_text()
                print('Document Title: ' + document_title)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print("\tdocument_hash: ", document_hash)
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                if document_href.startswith('http') and document_href.startswith("https://www.garanteprivacy.it") is False:
                    print('\tSkipping document that leads to page outside of dpa site')
                    continue
                document_url = document_href
                if document_href.startswith('http') is False:
                    host = "https://www.garanteprivacy.it"
                    document_url = host + document_url

                print('\tDocument URL: ' + document_url)

                document_response = None
                try:
                    document_response = requests.request('GET', document_url, timeout=10)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue

                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                # Get the document date:
                section = document_soup.find('section', id='content')
                assert section

                page_property = section.find('span', property='dc:date')

                # If a page is entirely blank, the first things the scraper notices is a failed assertion for property
                try:
                    assert page_property
                except AssertionError:
                    continue
                    print("Unable to obtain date from document page. It is likely blank")

                date = page_property.get_text()
                date_str = str(date)

                print('\tDocument Date: ' + date_str)

                # Weird bug where string length is much longer than it appear in html
                index = len(date_str)-11
                year_digits = date_str[index:]
                # print('\tDocument Year: ' + year_digits)
                date_str = date_str.strip()

                if int(year_digits) < 17:
                    print("Terminating program as only old document remain on page")
                    return added_docs

                if int(year_digits) < 18:
                    print("Skipping outdated document")
                    return added_docs

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Interviews' + '/' + document_hash
                # document_folder = dpa_folder + '/italy' + '/' + 'Interviews' + '/' + document_hash

                # Try to get document text directly from web page first
                try:
                    document_text = document_soup.find('div', id='div-to-print', class_='journal-content-article')
                    assert document_text

                    try:
                        os.makedirs(document_folder)

                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            f.write(document_text.get_text().encode())

                        with open(document_folder + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': {
                                    self.language_code: document_title
                                },
                                'md5': document_hash,
                                'releaseDate': date_str,
                                'url': document_url
                            }
                            json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    except FileExistsError:
                        print("\tDirectory path already exists, continue.")

                # Try to download pdf instead
                except:
                    print("\tFailed to get text directly from page -> attempting to download pdf")
                    pdf_section = document_soup.find('section', id='content')
                    assert pdf_section

                    link_area = pdf_section.find('div', id='internal-content-wrapper')
                    assert link_area

                    pdf_a = link_area.find('a')
                    assert pdf_a

                    pdf_href = pdf_a.get('href')

                    if pdf_href.startswith('http') and pdf_href.startswith(host) is False:
                        continue
                    pdf_url = pdf_href
                    if pdf_href.startswith('http') is False:
                        host = "https://www.garanteprivacy.it"
                        pdf_url = host + pdf_url

                    print('\tPDF URL: ' + pdf_url)

                    if '.mp4' or '.mp3' in pdf_url:
                        print('\tLink leads to a video or audio file: Skipping')
                        continue

                    pdf_response = None
                    try:
                        pdf_response = requests.request('GET', pdf_url, timeout=5)
                        pdf_response.raise_for_status()
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if pdf_response is None:
                        print("\tPDF response is None")
                        continue

                    if to_print:
                        print("\tDocument:\t", document_hash)

                    try:
                        os.makedirs(document_folder)

                        with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                            f.write(pdf_response.content)
                        try:
                            with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                                pdf_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                                f.write(pdf_text)
                        except:
                            print("Failed to convert pdf to text document")

                        with open(document_folder + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': {
                                    self.language_code: document_title
                                },
                                'md5': document_hash,
                                'releaseDate': date_str,
                                'url': document_url
                            }
                            json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                        added_docs.append(document_hash)
                    except FileExistsError:
                        print("\tDirectory path already exists, continue.")

        return added_docs
    

    def get_docs_Hearings(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Italy Hearings ===========================")
        added_docs = []

        page_url = 'https://www.garanteprivacy.it/home/attivita-e-documenti/documenti/audizioni'
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit('page_source is None')

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        testo = results_soup.find('div', class_='testo')
        assert testo

        # Get p tags starting at third one in html layout
        p_all = testo.find_all('p', recursive=False)[3:]

        iteration = 1
        for p in p_all:

            print('\n------------- Document ' + str(iteration) + ' ------------')
            iteration +=1

            result_link = p.find('a')
            # Some p tag contain html for additional header separating the document links.
            # So if no <a tag is available, it's most likely one of these
            try:
                assert result_link
            except:
                continue

            title_date = p.find('em').get_text()
            assert title_date
            print(title_date)

            # Some of the titles are identical in the html since the date is separate by another tag.
            # So concatenate this date back on to get a unique document title.
            document_title = result_link.get_text() + title_date
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            print('\tDocument Hash: ' + document_hash)

            document_href = result_link.get('href')
            if document_href.startswith('http') and document_href.startswith(host) is False:
                continue
            document_url = document_href

            if document_href.startswith('http') is False:
                host = "https://www.garanteprivacy.it"
                document_url = host + document_url

            print('\tdocument url: ' + document_url)

            document_response = None
            try:
                document_response = requests.request('GET', document_url, timeout=5)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                if to_print:
                    print(error)
                pass
            if document_response is None:
                continue

            document_soup = BeautifulSoup(document_response.text, 'html.parser')
            assert document_soup

            # Get the document date:
            section = document_soup.find('section', id='content')
            assert section

            property = section.find('span', property='dc:date')
            assert property

            date = property.get_text()
            date_str = str(date)

            print('\tDocument Date: ' + date_str)

            # Weird bug where string length is much longer than it appear in html
            index = len(date_str)-11
            year_digits = date_str[index:]
            #print('Year: ' + year_digits)

            if int(year_digits) < 17:
                print("Terminating program as only old document remain on page")
                return added_docs

            if int(year_digits) < 18:
                print("Skipping outdate document")
                return added_docs
            date_str = date_str.strip()
            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Hearings' + '/' + document_hash
            # document_folder = dpa_folder + '/italy' + '/' + 'Hearings' + '/' + document_hash

            try:
                os.makedirs(document_folder)
                try:
                    document_text = document_soup.find('div', id='div-to-print')
                    assert document_text

                    # Should just find the very next div, which will get the scraper to the pure text
                    document_text_deeper = document_text.find('div')
                    assert document_text_deeper

                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        f.write(document_text_deeper.get_text().encode())

                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': date_str,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                        print("\tDownloaded text")

                except:
                    pdf_section = document_soup.find('section', id='content')
                    assert pdf_section

                    link_area = pdf_section.find('div', id='internal-content-wrapper')
                    assert link_area

                    pdf_a = link_area.find('a')
                    assert pdf_a

                    pdf_href = pdf_a.get('href')

                    if pdf_href.startswith('http') and pdf_href.startswith(host) is False:
                        continue
                    pdf_url = pdf_href
                    if pdf_href.startswith('http') is False:
                        host = "https://www.garanteprivacy.it"
                        pdf_url = host + pdf_url

                    print('\tPDF URL: ' + pdf_url)

                    pdf_response = None
                    try:
                        pdf_response = requests.request('GET', pdf_url, timeout=5)
                        pdf_response.raise_for_status()
                    except requests.exceptions.HTTPError as error:
                        if to_print:
                            print(error)
                        pass
                    if pdf_response is None:
                        continue

                    if to_print:
                        print("\tDocument:", document_hash)

                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(pdf_response.content)
                    try:
                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            pdf_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(pdf_text)
                    except:
                        print("Failed to convert pdf to text document")

                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': date_str,
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                        print("\tDownloaded pdf")
                added_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        return added_docs

    # Utilizes the link starting at page 1, rather than the generic link
    def get_docs_Injunctions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Italy Injunctions ===========================")
        added_docs = []

        # Create pagination object and add all pages at once
        init_page_url = 'https://www.garanteprivacy.it/home/ricerca?p_p_id=g_gpdp5_search_GGpdp5SearchPortlet&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_g_gpdp5_search_GGpdp5SearchPortlet_mvcRenderCommandName=%2FrenderSearch&_g_gpdp5_search_GGpdp5SearchPortlet_text=&_g_gpdp5_search_GGpdp5SearchPortlet_dataInizio=&_g_gpdp5_search_GGpdp5SearchPortlet_dataFine=&_g_gpdp5_search_GGpdp5SearchPortlet_idsTipologia=10526&_g_gpdp5_search_GGpdp5SearchPortlet_idsArgomenti=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParole=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_nonParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_paginaWeb=false&_g_gpdp5_search_GGpdp5SearchPortlet_allegato=false&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoPer=DESC&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoTipo=data&_g_gpdp5_search_GGpdp5SearchPortlet_cur=1'
        init_page_source = self.get_source(page_url=init_page_url)
        init_results_soup = BeautifulSoup(init_page_source.text, 'html.parser')
        assert init_results_soup
        # The start_path doesn't contain the very last character, which is the unique page number
        pagination = self.update_pagination(start_path='/home/ricerca?p_p_id=g_gpdp5_search_GGpdp5SearchPortlet&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_g_gpdp5_search_GGpdp5SearchPortlet_mvcRenderCommandName=%2FrenderSearch&_g_gpdp5_search_GGpdp5SearchPortlet_text=&_g_gpdp5_search_GGpdp5SearchPortlet_dataInizio=&_g_gpdp5_search_GGpdp5SearchPortlet_dataFine=&_g_gpdp5_search_GGpdp5SearchPortlet_idsTipologia=10526&_g_gpdp5_search_GGpdp5SearchPortlet_idsArgomenti=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParole=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_nonParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_paginaWeb=false&_g_gpdp5_search_GGpdp5SearchPortlet_allegato=false&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoPer=DESC&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoTipo=data&_g_gpdp5_search_GGpdp5SearchPortlet_cur=', page_soup=init_results_soup)

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\n New Page:\t', page_url)

            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            section = results_soup.find('section', id='content')
            assert section

            blocco = section.find('div', class_='blocco-risultati')
            assert blocco

            for div in blocco.find_all('div', class_='card-risultato'):
                assert div
                time.sleep(2)

                # Obtain the document date
                date_div = div.find('div', class_='data-risultato')
                assert date_div
                p_tag = date_div.find('p')
                assert p_tag
                document_date = p_tag.get_text()

                # If we reach documents of year 2016 or below, stop scraping
                # We keep searching year 2017 just in case there are any remaining docs...
                document_year = document_date[-4:]
                if int(document_year) <= 2017:
                    print("Terminating because remaining documents are outdated")
                    # sys.exit("Remaining documents are outdated")
                    return added_docs

                # Check if the document is outdated
                if int(document_year) < 2018:
                    print("Skipping outdated document")
                    return added_docs

                result_link = div.find('a', class_='titolo-risultato')
                assert result_link

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                document_title = result_link.get_text()
                print('Document Title: ' + document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                print('\tDocument Date: ' + document_date)
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                document_href = result_link.get('href')
                if document_href.startswith('http') and document_href.startswith(host) is False:
                    continue
                document_url = document_href
                if document_href.startswith('http') is False:
                    host = "https://www.garanteprivacy.it"
                    document_url = host + document_url
                document_response = None

                try:
                    document_response = requests.request('GET', document_url, timeout=10)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue
                print('\tdocument_url:\t', document_url)
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                body = document_soup.find('body')
                assert body

                body_text = body.find('div', class_='col-md-8 pl-4 px-md-5')
                assert body_text

                text_print_format = body_text.find('div', id='div-to-print')
                assert text_print_format

                second_text_print = text_print_format.find('div', class_='journal-content-article')

                if second_text_print is None:
                    second_text_print = text_print_format

                if to_print:
                    print("\tDocument:\t", document_hash)

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Injunctions' + '/' + document_hash
                # document_folder = dpa_folder + '/italy' + '/' + 'Injunctions' + '/' + document_hash

                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        f.write(second_text_print.get_text().encode())
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

    # This is an additional method to help scrape Injunctions Documents placed on the last pages of the website
    # Start at the last page of the injuctions link -> scrape backwards until reach outdated documents
    # This method keeps track of how many outdated documnets it encounters -> after hitting 15, stop scraping
    def get_docs_InjunctionsFromLastPage(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n============ Italy Injunctions  (STARTING FROM LAST PAGE)===================")
        added_docs = []

        # Create pagination object and add all pages at once
        init_page_url = 'https://www.garanteprivacy.it/home/ricerca?p_p_id=g_gpdp5_search_GGpdp5SearchPortlet&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_g_gpdp5_search_GGpdp5SearchPortlet_mvcRenderCommandName=%2FrenderSearch&_g_gpdp5_search_GGpdp5SearchPortlet_text=&_g_gpdp5_search_GGpdp5SearchPortlet_dataInizio=&_g_gpdp5_search_GGpdp5SearchPortlet_dataFine=&_g_gpdp5_search_GGpdp5SearchPortlet_idsTipologia=10526&_g_gpdp5_search_GGpdp5SearchPortlet_idsArgomenti=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParole=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_nonParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_paginaWeb=false&_g_gpdp5_search_GGpdp5SearchPortlet_allegato=false&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoPer=DESC&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoTipo=data&_g_gpdp5_search_GGpdp5SearchPortlet_cur=1'
        init_page_source = self.get_source(page_url=init_page_url)
        init_results_soup = BeautifulSoup(init_page_source.text, 'html.parser')
        assert init_results_soup
        # The start_path doesn't contain the very last character, which is the unique page number
        pagination = self.update_pagination_backwards(start_path='/home/ricerca?p_p_id=g_gpdp5_search_GGpdp5SearchPortlet&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_g_gpdp5_search_GGpdp5SearchPortlet_mvcRenderCommandName=%2FrenderSearch&_g_gpdp5_search_GGpdp5SearchPortlet_text=&_g_gpdp5_search_GGpdp5SearchPortlet_dataInizio=&_g_gpdp5_search_GGpdp5SearchPortlet_dataFine=&_g_gpdp5_search_GGpdp5SearchPortlet_idsTipologia=10526&_g_gpdp5_search_GGpdp5SearchPortlet_idsArgomenti=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParole=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_nonParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_paginaWeb=false&_g_gpdp5_search_GGpdp5SearchPortlet_allegato=false&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoPer=DESC&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoTipo=data&_g_gpdp5_search_GGpdp5SearchPortlet_cur=', page_soup=init_results_soup)

        # outdate_count keeps track of how many outdated documents have been encountered so ar
        outdated_count = 0
        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\n New Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            section = results_soup.find('section', id='content')
            assert section

            blocco = section.find('div', class_='blocco-risultati')
            assert blocco

            for div in blocco.find_all('div', class_='card-risultato'):
                assert div
                time.sleep(2)

                # Obtain the document date
                date_div = div.find('div', class_='data-risultato')
                assert date_div
                p_tag = date_div.find('p')
                assert p_tag
                document_date = p_tag.get_text()

                result_link = div.find('a', class_='titolo-risultato')
                assert result_link

                # Try to get date from date tag, but if not, get the doc year from the title
                try:
                    # If failure occurs, will fail here
                    document_year = document_date[-4:]

                    # If we reach documents of year 2016 or below, stop scraping
                    # We keep searching year 2017 just in case there are any remaining docs...
                    if int(document_year) < 2018:
                        outdated_count += 1

                        if outdated_count >= 15:
                            print("Terminating because remaining documents are outdated")
                            # sys.exit("Remaining documents are outdated")
                            return added_docs
                        else:
                            print("Skipping outdated document")
                            continue

                # No date tag next to document title
                except:
                    title = result_link.get_text()
                    document_year = title[-14:-10]
                    document_date = document_year

                    # If we reach documents of year 2016 or below, stop scraping
                    # We keep searching year 2017 just in case there are any remaining docs...
                    if int(document_year) < 2018:
                        outdated_count += 1

                        if outdated_count >= 15:
                            print("Terminating because remaining documents are outdated")
                            # sys.exit("Remaining documents are outdated")
                            return added_docs

                        else:
                            print("Skipping outdated document")
                            continue

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1
                print('\tDocument Date: ' + document_date)
                document_title = result_link.get_text()
                print('\tDocument Title: ' + document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                document_href = result_link.get('href')
                if document_href.startswith('http') and document_href.startswith(host) is False:
                    continue
                document_url = document_href
                if document_href.startswith('http') is False:
                    host = "https://www.garanteprivacy.it"
                    document_url = host + document_url
                document_response = None

                try:
                    document_response = requests.request('GET', document_url, timeout=5)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue

                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                body = document_soup.find('body')
                assert body

                body_text = body.find('div', class_='col-md-8 pl-4 px-md-5')
                assert body_text

                text_print_format = body_text.find('div', id='div-to-print')
                assert text_print_format

                second_text_print = text_print_format.find('div', class_='journal-content-article')
                assert second_text_print

                if to_print:
                    print("\tDocument:\t", document_hash)

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Injunctions Backwards' + '/' + document_hash
                # document_folder = dpa_folder + '/italy' + '/' + 'Injunctions Backwards' + '/' + document_hash

                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        f.write(second_text_print.get_text().encode())
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

    # Utilizes the link starting at page 1, rather than the generic link
    def get_docs_Newsletters(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================== Italy Newsletters=============================")

        added_docs = []

        # Create pagination object and add all pages at once
        init_page_url = 'https://www.garanteprivacy.it/home/ricerca?p_p_id=g_gpdp5_search_GGpdp5SearchPortlet&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_g_gpdp5_search_GGpdp5SearchPortlet_mvcRenderCommandName=%2FrenderSearch&_g_gpdp5_search_GGpdp5SearchPortlet_text=&_g_gpdp5_search_GGpdp5SearchPortlet_dataInizio=&_g_gpdp5_search_GGpdp5SearchPortlet_dataFine=&_g_gpdp5_search_GGpdp5SearchPortlet_idsTipologia=10524&_g_gpdp5_search_GGpdp5SearchPortlet_idsArgomenti=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParole=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_nonParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_paginaWeb=false&_g_gpdp5_search_GGpdp5SearchPortlet_allegato=false&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoPer=DESC&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoTipo=data&_g_gpdp5_search_GGpdp5SearchPortlet_cur=1'
        init_page_source = self.get_source(page_url=init_page_url)
        init_results_soup = BeautifulSoup(init_page_source.text, 'html.parser')
        assert init_results_soup
        # The start_path doesn't contain the very last character, which is the unique page number
        pagination = self.update_pagination(start_path='/home/ricerca?p_p_id=g_gpdp5_search_GGpdp5SearchPortlet&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_g_gpdp5_search_GGpdp5SearchPortlet_mvcRenderCommandName=%2FrenderSearch&_g_gpdp5_search_GGpdp5SearchPortlet_text=&_g_gpdp5_search_GGpdp5SearchPortlet_dataInizio=&_g_gpdp5_search_GGpdp5SearchPortlet_dataFine=&_g_gpdp5_search_GGpdp5SearchPortlet_idsTipologia=10524&_g_gpdp5_search_GGpdp5SearchPortlet_idsArgomenti=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParole=&_g_gpdp5_search_GGpdp5SearchPortlet_quanteParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_nonParoleStr=&_g_gpdp5_search_GGpdp5SearchPortlet_paginaWeb=false&_g_gpdp5_search_GGpdp5SearchPortlet_allegato=false&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoPer=DESC&_g_gpdp5_search_GGpdp5SearchPortlet_ordinamentoTipo=data&_g_gpdp5_search_GGpdp5SearchPortlet_cur=', page_soup=init_results_soup)

        iteration = 1
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('\n New Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            section = results_soup.find('section', id='content')
            assert section

            blocco = section.find('div', class_='blocco-risultati')
            assert blocco

            for div in blocco.find_all('div', class_='card-risultato'):
                assert div
                time.sleep(2)

                # Obtain the document date
                date_div = div.find('div', class_='data-risultato')
                assert date_div
                p_tag = date_div.find('p')
                assert p_tag
                document_date = p_tag.get_text()

                # Check if the document is outdated or if we have reached a point where
                # won't encounter new documents
                document_year = document_date[-4:]

                if int(document_year) < 2017:
                    # sys.exit("Remaining documents are outdated")
                    # continue
                    return added_docs

                # Check if the document is outdated
                if int(document_year) < 2018:
                    print("Skipping outdated document")
                    return added_docs

                result_link = div.find('a', class_='titolo-risultato')
                assert result_link

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1
                print('\tDocument Date: ' + document_date)
                document_title = result_link.get_text()
                print('\tDocument Title: ' + document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite is False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                document_href = result_link.get('href')
                if document_href.startswith('http') and document_href.startswith(host) is False:
                    continue
                document_url = document_href
                if document_href.startswith('http') is False:
                    host = "https://www.garanteprivacy.it"
                    document_url = host + document_url
                document_response = None

                try:
                    document_response = requests.request('GET', document_url, timeout=5)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if document_response is None:
                    continue

                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                body = document_soup.find('body')
                assert body

                body_text = body.find('div', class_='col-md-8 pl-4 px-md-5')
                assert body_text

                text_print_format = body_text.find('div', id='div-to-print')
                assert text_print_format

                # Try to go deep in order to get text without excess html baggage
                obtained_text = None
                try:
                    second_text_print = text_print_format.find('div', class_='journal-content-article')
                    assert second_text_print
                    obtained_text = second_text_print
                except:
                    obtained_text = text_print_format

                assert obtained_text

                if to_print:
                    print("\tDocument:\t", document_hash)

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Newsletters' + '/' + document_hash
                # document_folder = dpa_folder + '/italy' + '/' + 'Newsletters' + '/' + document_hash

                try:
                    os.makedirs(document_folder)

                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        f.write(obtained_text.get_text().encode())
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


    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================== Italy Annual Reports==========================")
        added_docs = []

        iteration = 1

        page_url = 'https://www.garanteprivacy.it/home/attivita-e-documenti/documenti/relazioni-annuali'

        if to_print:
            print('\n New Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit("page_soure is None")
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        section = results_soup.find('section', id='content')
        assert section

        interna = section.find('div', class_='interna-webcontent')
        assert interna

        for tr in interna.find_all('tr')[1:]:
            assert tr

            # Obtain the document date
            td = tr.find_all('td')[0]
            assert td

            year = td.find('strong')

            assert year
            document_year = year.get_text()

            # Can use this to improve rutime since documents are already in chronological order
            if int(document_year) < 2017:
                break

            # Check if the document is outdated
            if int(document_year) < 2018:
                print("Skipping outdated document: " + document_year)
                continue

            result_link = tr.find('a')
            assert result_link

            print('\n------------ Document ' + str(iteration) + ' ------------')
            iteration += 1
            print('\tDocument Date: ' + document_year)
            document_title = "Annual Report " + document_year
            print('\tDocument Title: ' + document_title)
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            document_href = result_link.get('href')
            if document_href.startswith('http') and document_href.startswith(host) is False:
                continue
            document_url = document_href
            if document_href.startswith('http') is False:
                host = "https://www.garanteprivacy.it"
                document_url = host + document_url
            document_response = None

            try:
                document_response = requests.request('GET', document_url, timeout=5)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                if to_print:
                    print(error)
                pass
            if document_response is None:
                continue

            document_soup = BeautifulSoup(document_response.text, 'html.parser')
            assert document_soup

            pdf_section = document_soup.find('section', id='content')
            assert pdf_section

            link_area = pdf_section.find('div', id='internal-content-wrapper')
            assert link_area

            pdf_a = link_area.find('a')
            assert pdf_a

            pdf_href = pdf_a.get('href')

            if pdf_href.startswith('http') and pdf_href.startswith(host) is False:
                continue
            pdf_url = pdf_href
            if pdf_href.startswith('http') is False:
                host = "https://www.garanteprivacy.it"
                pdf_url = host + pdf_url

            print('\tPDF URL: ' +pdf_url)

            pdf_response = None
            try:
                pdf_response = requests.request('GET', pdf_url, timeout=5)
                pdf_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                if to_print:
                    print(error)
                pass
            if pdf_response is None:
                continue

            if to_print:
                print("\tDocument:\t", document_hash)

            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Annual Reports' + '/' + document_hash
            # document_folder = dpa_folder + '/italy' + '/' + 'Annual Reports' + '/' + document_hash

            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(pdf_response.content)
                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                    pdf_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                    f.write(pdf_text)
                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': document_year,
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                added_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")
        return added_docs

    # Utilizes the link starting at page 1, rather than the generic link
    def get_docs_Publications(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================== Italy Publications==========================")
        added_docs = []

        iteration = 1

        page_url = 'https://www.garanteprivacy.it/home/attivita-e-documenti/documenti/collana-contributi'
        if to_print:
            print('\n New Page:\t', page_url)
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            sys.exit('page_source is None')

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup

        section = results_soup.find('section', id='content')
        assert section

        testo = section.find('div', id='interna-webcontent')
        assert testo

        # Just get the very first <tr>
        tr = testo.find('tr')
        assert tr

        for p in tr.find_all('p'):
            assert p

            if p.find('br') is None:
                continue

            print('\n------------ Document ' + str(iteration) + ' ------------')
            iteration += 1

            document_title = p.get_text()
            print('\tDocument Title: ' + document_title)

            document_year = document_title[-4:]
            #print('\tDocument Year: ' + document_year)

            try:
                if int(document_year) < 2018:
                    print('Remaining documents are outdated')
                    break
            except ValueError:
                print("\tCouldn't parse document_year to integer")

            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            a_tag = p.find('a')
            assert a_tag

            href = a_tag.get('href')
            assert href

            document_url = 'https://www.garanteprivacy.it' + href
            print('\tDocument URL: ' + document_url)

            document_response = None
            try:
                document_response = requests.request('GET', document_url, timeout=5)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                if to_print:
                    print(error)
                pass
            if document_response is None:
                continue

            document_soup = BeautifulSoup(document_response.text, 'html.parser')
            assert document_soup

            document_section = document_soup.find('section', id='content')
            assert document_section

            portlet_body = document_section.find('div', class_='portlet-body')
            assert portlet_body

            content_wrapper = portlet_body.find('div', id='internal-content-wrapper')
            assert content_wrapper

            document_a = content_wrapper.find('a')
            assert document_a

            pdf_href = document_a.get('href')
            assert pdf_href

            pdf_url = 'https://www.garanteprivacy.it' + pdf_href
            print('\tPDF URL: ' + pdf_url)

            pdf_response = None
            try:
                pdf_response = requests.request('GET', pdf_url, timeout=5)
                pdf_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                if to_print:
                    print(error)
                pass
            if pdf_response is None:
                print('\tpdf_response is None')
                continue

            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Publications' + '/' + document_hash
            # document_folder = dpa_folder + '/italy' + '/' + 'Publications' + '/' + document_hash

            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(pdf_response.content)
                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                    pdf_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                    f.write(pdf_text)
                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': document_year,
                        'url': pdf_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                added_docs.append(document_hash)
            except FileExistsError:
                print("\tDirectory path already exists, continue.")
        return added_docs
