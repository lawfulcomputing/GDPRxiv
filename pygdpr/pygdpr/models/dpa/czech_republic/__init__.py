import os
import math
import requests
import json
import datetime
import hashlib
import textract
import urllib3
from pygdpr.models.dpa import DPA
from bs4 import BeautifulSoup
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy
import sys
import time
import re

class CzechRepublic(DPA):
    def __init__(self, path=os.curdir):
        country_code='CZ'
        super().__init__(country_code, path)

    # Added start_path as input parameter so different scraper methods can use update_pagination()
    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path=None):
        source = {
            "host": "https://www.uoou.cz",
            # "start_path": "/vismo/zobraz_dok.asp?id_ktg=901"
            "start_path": "/tiskove%2Dzpravy/ds-1017/p1=1017&tzv=1&pocet=25&stranka=1"
            # "start_path": "/na%2Daktualni%2Dtema/ds-1018/archiv=0&p1=1099&tzv=1&pocet=25&stranka=1"
        }
        host = source['host']
        start_path = start_path
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            strlistovani = page_soup.find('div', class_='strlistovani')
            if strlistovani is not None:
                for a in strlistovani.find_all('a'):
                    page_href = a.get('href')
                    pagination.add_item(host + page_href)
        return pagination

    def get_source(self, page_url=None, driver=None):
        assert (page_url is not None)
        results_response = None
        try:
            # Set timeout param to low value
            # If IPv6 takes too long, the request will then switch to IPv4 quickly and use that protocol
            # This seems to be an issue for links with weaker infrastructure
            results_response = requests.request('GET', page_url, timeout=2)

            results_response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            pass
        return results_response

    # Calls all scraper methods at once
    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_PressReleases(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Opinions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_CourtRulings(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_DecisionOfPresident(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_DecisionMakingActivites(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_CompletedInspections(existing_docs=[], overwrite=False, to_print=True)

        return added_docs

    # Always gets text from a document page
    # If there is a pdf link on the document page, downloads the pdf (and its text) as well
    # Does check dates
    def get_docs_PressReleases(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Czech Republic Press Releases ===========================")
        iteration = 1
        added_docs = []

        # We want to create the pagination object, then add the rest of the pages to visit to the
        # pagination object all at once, because calling update_pagination will insert all pages into the
        # pagination list each time.
        # We have to parse the first page before the while loop to do this
        pagination = self.update_pagination(start_path='/tiskove%2Dzpravy/ds-1017/p1=1017&tzv=1&pocet=25&stranka=1')
        initial_page_source = self.get_source(page_url='https://www.uoou.cz/tiskove%2Dzpravy/ds-1017/p1=1017&tzv=1&pocet=25&stranka=1')
        initial_results_soup = BeautifulSoup(initial_page_source.text, 'html.parser')
        pagination = self.update_pagination(pagination=pagination, page_soup=initial_results_soup)

        while pagination.has_next():
            page_url = pagination.get_next()
            print('\n------------ NEW PAGE ------------')
            if to_print:
                print('Page:\t', page_url)

            page_source = self.get_source(page_url=page_url)

            if page_source is None:
                print("Skipping page because page_source is None")
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            dok = results_soup.find('div', class_='obsah')
            assert dok
            ui = dok.find('ul', class_='ui')
            assert ui

            # Get the page number we are on -> if it greater than 3, skip
            # Only the first three pages contain documents made 2018 and after
            page_number = page_url[-1:]
            if int(page_number) > 3:
                print("\tSkipping page: " + page_number)
                continue

            for li in ui.find_all('li'):
                result_link = li.find('a')
                # s2. Documents
                document_title = result_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                if document_href.startswith('http') is not True:
                    host = "https://www.uoou.cz"
                    document_url = host + document_href
                else:
                    document_url = document_href

                # One of the document_urls leads to a pdf link -> skip it for now
                if document_url == 'https://www.uoou.cz/assets/File.ashx?id_org=200144&id_dokumenty=31695':
                    continue

                document_response = None
                try:
                    document_response = requests.request('GET', document_url, timeout=2)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if document_response is None:
                    print("\tSkipping existing document: document_response is None")
                    continue

                # Created soup for the document link
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                # Obtain document date -> implemented simpler method that just checks the years
                div = li.find('div')
                if div is None:
                    print("\tSkipping existing document: div is None")
                    continue
                created_index = 0

                # Use this to get the date out
                div_text = div.get_text()

                m = re.search('(.+?) - ', div_text)
                if m:
                    found_date = m.group(1)
                else:
                    m = re.search('(.+?) – ', div_text)
                    if m:
                        found_date = m.group(1)

                found_date_year = found_date[-5:]

                if int(found_date_year):
                    found_date_year_int = int(found_date_year)
                    if found_date_year_int < 2018:
                        print("\tSkipping existing document: Document year is: " + found_date_year)
                        return added_docs
                    # Document year is 2018 or greater
                    else:
                        document_year = found_date_year
                # Can't convert the year string to an int for whatever reason -> just keep the doc anyways
                else:
                    document_year = "Date not available"

                # If significant pdf links exists, go to them and download
                obalcelek_tag = document_soup.find('div', id='obalcelek')
                if not obalcelek_tag is None:
                    a_tag = obalcelek_tag.find_all('a')
                    dpa_folder = self.path
                    document_folder = dpa_folder + '/' + 'PressReleases' + '/' + document_hash
                    try:
                        os.makedirs(document_folder)
                        if a_tag:
                            for element in a_tag:
                                assert element
                                # Check if we can get a href and if that href contains the string 'File.ashx', which indicates
                                # the link is intended to be downloaded
                                if element.get('href') is not None and ('File.ashx' in element.get('href')):
                                    link_href = element.get('href')
                                    assert link_href
                                    link_url = 'https://www.uoou.cz' + link_href
                                    print("Link URL: " + link_url)

                                    link_response = None
                                    try:
                                        link_response = requests.request('GET', link_url, timeout=2)
                                        link_response.raise_for_status()
                                    except requests.exceptions.HTTPError as error:
                                        pass
                                    if link_response is None:
                                        continue

                                    # If get a link response, then write the contents of the file as a pdf and text
                                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                                        f.write(link_response.content)
                                    try:
                                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                                            link_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                                            f.write(link_text)
                                    # If the link leads to a word document or a file format other than a pdf
                                    # -> skip text conversion
                                    except:
                                        pass

                                else:
                                    continue

                        # When we print document stuff, that means the document is not going to be thrown out
                        print('\n\t------------ Document: ' + str(iteration) + ' ------------')
                        iteration += 1
                        if to_print:
                            print("\tDocument:\t", document_hash)
                        obsah = document_soup.find('div', class_='obsah')
                        assert obsah
                        document_text = obsah.get_text()
                        document_text = document_text.lstrip()


                        with open(document_folder + '/' + self.language_code + 'Summary' + '.txt', 'w') as f:
                            f.write(document_text)
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
                # Don't need to call update_pagination -> it already has all the pages
        return added_docs

    # Always gets text from a document page
    # If there is a pdf link on the document page, downloads the pdf (and its text) as well
    # Doesn't get dates -> html is to inconsistent -> just scrape first page of link instead (other pages
    # contains links that are too old)
    def get_docs_Opinions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Czech Republic Opinions ===========================")
        iteration = 1
        added_docs = []

        # We want to create the pagination object, then add the rest of the pages to visit to the
        # pagination object all at once, because calling update_pagination will insert all pages into the
        # pagination list each time.
        # We have to parse the first page before the while loop to do this
        pagination = self.update_pagination(start_path='/na%2Daktualni%2Dtema/ds-1018/archiv=0&p1=1099&tzv=1&pocet=25&stranka=1')
        initial_page_source = self.get_source(page_url='https://www.uoou.cz/na%2Daktualni%2Dtema/ds-1018/archiv=0&p1=1099&tzv=1&pocet=25&stranka=1')
        initial_results_soup = BeautifulSoup(initial_page_source.text, 'html.parser')
        pagination = self.update_pagination(pagination=pagination, page_soup=initial_results_soup)

        while pagination.has_next():
            page_url = pagination.get_next()
            print('\n------------ NEW PAGE ------------')
            if to_print:
                print('\tPage:\t', page_url)

            page_source = self.get_source(page_url=page_url)

            if page_source is None:
                print("Skipping page because page_source is None")
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            dok = results_soup.find('div', class_='obsah')
            assert dok
            ui = dok.find('ul', class_='ui')
            assert ui

            # Get the page number we are on -> if it greater than 1, skip
            # Only the first page contains documents made 2018 and after
            page_number = page_url[-1:]
            if int(page_number) > 1:
                print("\tSkipping page: " + page_number)
                continue

            for li in ui.find_all('li'):
                result_link = li.find('a')
                # s2. Documents
                document_title = result_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                if document_href.startswith('http') is not True:
                    host = "https://www.uoou.cz"
                    document_url = host + document_href
                else:
                    document_url = document_href

                # One of the document_urls leads to a pdf link -> skip it for now
                if document_url == 'https://www.uoou.cz/assets/File.ashx?id_org=200144&id_dokumenty=31695':
                    continue

                document_response = None
                try:
                    document_response = requests.request('GET', document_url, timeout=2)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if document_response is None:
                    print("\tSkipping existing document: document_response is None")
                    continue

                # Created soup for the document link
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                # If significant pdf links exists, go to them and download
                obalcelek_tag = document_soup.find('div', id='obalcelek')
                if not obalcelek_tag is None:
                    a_tag = obalcelek_tag.find_all('a')
                    dpa_folder = self.path
                    document_folder = dpa_folder + '/' + 'Opinions' + '/' + document_hash
                    try:
                        os.makedirs(document_folder)
                        if a_tag:
                            for element in a_tag:
                                assert element
                                # Check if we can get a href and if that href contains the string 'File.ashx', which indicates
                                # the link is intended to be downloaded
                                if element.get('href') is not None and ('File.ashx' in element.get('href')) :
                                    link_href = element.get('href')
                                    assert link_href
                                    link_url = 'https://www.uoou.cz' + link_href
                                    print("Link URL: " + link_url)

                                    link_response = None
                                    try:
                                        link_response = requests.request('GET', link_url, timeout=2)
                                        link_response.raise_for_status()
                                    except requests.exceptions.HTTPError as error:
                                        pass
                                    if link_response is None:
                                        continue

                                    # If get a link reponse, then write the contents of the file as a pdf and text
                                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                                        f.write(link_response.content)
                                    try:
                                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                                            link_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                                            f.write(link_text)
                                    # If the link leads to a word document or a file format other than a pdf
                                    # -> skip text conversion
                                    except:
                                        pass
                                else:
                                    continue

                        # Don't try to find the document date -> website html is too inconsistent
                        # When we print document stuff, that means the document is not going to be thrown out
                        print('\n\t------------ Document: ' + str(iteration) + ' ------------')
                        iteration += 1
                        if to_print:
                            print("\tDocument:\t", document_hash)
                        obsah = document_soup.find('div', class_='obsah')
                        assert obsah
                        document_text = obsah.get_text()
                        document_text = document_text.lstrip()
                        with open(document_folder + '/' + self.language_code + 'Summary' + '.txt', 'w') as f:
                            f.write(document_text)
                        with open(document_folder + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': {
                                    self.language_code: document_title
                                },
                                'md5': document_hash,
                                'releaseDate': "Date not available",
                                'url': document_url
                            }
                            json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                        added_docs.append(document_hash)
                    except FileExistsError:
                        print("\tDirectory path already exists, continue.")
                # Don't need to call update_pagination -> it already has all the pages
        return added_docs

    # Does date checking
    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Czech Republic Annual Reports ===========================")
        added_docs = []

        page_url = 'https://www.uoou.cz/vyrocni-zprava/ds-2089/archiv=0&p1=2087'
        if to_print:
            print('\tPage:\t', page_url)

        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("Skipping page because page_source is None")
            sys.exit()

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        dok = results_soup.find('div', id='obalcelek')
        assert dok
        ui = dok.find('ul', class_='ui')
        assert ui

        iteration = 1
        for li in ui.find_all('li'):
            result_link = li.find('a')

            document_title = result_link.get_text()
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite == False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            document_href = result_link.get('href')

            assert document_href

            if document_href.startswith('http') is not True:
                host = "https://www.uoou.cz"
                document_url = host + document_href
            else:
                document_url = document_href
            document_response = None
            try:
                document_response = requests.request('GET', document_url, timeout=2)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                pass
            if document_response is None:
                print("\tSkipping existing document: document_response is None")
                continue
            # If document year is earlier than 2018, skip it
            document_year = result_link.get_text()[-4:]
            if int(document_year) < 2018:
                print("\tSkipping existing document: Document year is: " + document_year)
                return added_docs

            # When we print document stuff, that means the document is not going to be thrown out
            print('\n\t------------ Document: ' + str(iteration) + ' ------------')
            iteration += 1
            if to_print:
                print("\tDocument:\t", document_hash)

            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'AnnualReports' + '/' + document_hash
            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(document_response.content)

                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                    link_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                    f.write(link_text)

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

                print('------------------------')
            except FileExistsError:
                print("\tDirectory path already exists, continue.")
        return added_docs

    # Does date checking to an extent -> if date is obtainable check it, if not, then include doc anyways
    def get_docs_CourtRulings(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Czech Republic Court Rulings ===========================")
        added_docs = []
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        page_url = 'https://www.uoou.cz/ceska-republika/ds-2850/archiv=0&p1=1271'
        if to_print:
            print('\tPage:\t', page_url)

        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("Skipping page because page_source is None")
            sys.exit()

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        kategorie_tag = results_soup.find('div', id='kategorie')
        assert kategorie_tag
        ui_tag = kategorie_tag.find('ul', class_='ui')
        assert ui_tag

        iteration = 1
        for li in ui_tag.find_all('li'):
            result_link = li.find('a')

            document_href = result_link.get('href')
            assert document_href

            if document_href.startswith('http') is not True:
                host = "https://www.uoou.cz"
                document_url = host + document_href
            else:
                document_url = document_href

            print("---VISITING LINK: " + document_url + ' ---')

            document_response = None
            try:
                document_response = requests.request('GET', document_url, timeout=4, verify=False)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                pass
            if document_response is None:
                print("\tSkipping existing link: document_response is None")
                continue

            # Created soup for the document link
            document_soup = BeautifulSoup(document_response.text, 'html.parser')
            assert document_soup

            link_kategorie_tag = document_soup.find('div', id='kategorie')
            assert link_kategorie_tag
            link_ui_tag = link_kategorie_tag.find('ul', class_='ui')
            assert link_ui_tag

            for link_li in link_ui_tag.find_all('li'):
                doc_tag = link_li.find('a')
                assert doc_tag

                # Get title and make hash for document
                document_title = doc_tag.get_text()

                # Try to obtain the document year from the last 4 characters of document_title
                # Not all titles contain the date here, but a lot do, so its worth the check
                document_year = document_title[-4:]

                if document_year.isnumeric():
                    if int(document_year) < 2018:
                        print("\tSkipping document because it is out of date")
                        continue
                    else:
                        pass
                else:
                    document_year = "Document year not available"

                # Ensure the document year is a string
                document_year = str(document_year)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                link_href = doc_tag.get('href')
                assert link_href

                if link_href.startswith('http') is not True:
                    link_host = "https://www.uoou.cz"
                    link_url = link_host + link_href
                else:
                    link_url = link_href

                link_response = None
                try:
                    link_response = requests.request('GET', link_url, timeout=10, verify=False)
                    link_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if link_response is None:
                    print("\tSkipping existing document: link_response is None")
                    continue
                # link_response now contains the pdf contents

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'CourtRulings' + '/' + document_hash

                # The conditionals check if the link is either a pdf or a text doc. This is done by identifying
                # strings within the url to indicate the document type. Note that the conditional checks may excluded
                # extremely dated docs. Very old links use different identifiers for pdf and text links than newer ones.

                # Document isn't a pdf
                if 'GetText.aspx' in link_url:

                    # When we print document stuff, that means the document is not going to be thrown out
                    print('\n\t------------ (TEXT) Document: ' + str(iteration) + ' ------------')
                    print("\tLink URL: " + link_url)
                    iteration += 1
                    if to_print:
                        print("\tDocument:\t", document_hash)

                    # Create soup for the link
                    link_soup = BeautifulSoup(link_response.text, 'html.parser')
                    assert link_soup
                    body = link_soup.find('form', id='WordForm')
                    assert body

                    body_text = body.get_text()
                    assert body_text

                    try:
                        os.makedirs(document_folder)

                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            f.write(body_text.encode())

                        with open(document_folder + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': {
                                    self.language_code: document_title
                                },
                                'md5': document_hash,
                                'releaseDate': "Date not implemented yet",
                                'url': link_url
                            }
                            json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    except FileExistsError:
                        print("\tDirectory path already exists, continue.")

                # Document is a pdf
                # Some of the links end with a space character at the end
                elif link_url.endswith('.pdf') or link_url.endswith('.pdf ') or 'File.ashx' in link_url:
                    # When we print document stuff, that means the document is not going to be thrown out
                    print('\n\t------------ (PDF) Document: ' + str(iteration) + ' ------------')
                    link_url = link_url.strip()
                    print("\tLink URL: " + link_url)
                    iteration += 1
                    if to_print:
                        print("\tDocument:\t", document_hash)

                    try:
                        os.makedirs(document_folder)
                        with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                            f.write(link_response.content)
                        time.sleep(5)

                        # Fix bug where converting pdf to text fails occasionally (could be request header issue)
                        try:
                            with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                                link_text = PDFToTextService().text_from_pdf_path(document_folder + '/' + self.language_code + '.pdf')
                                f.write(link_text)
                        except:
                            print("\tFailed to convert pdf to text")
                            pass

                        with open(document_folder + '/' + 'metadata.json', 'w') as f:
                            metadata = {
                                'title': {
                                    self.language_code: document_title
                                },
                                'md5': document_hash,
                                'releaseDate': "Date not implemented yet",
                                'url': link_url
                            }
                            json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    except FileExistsError:
                        print("\tDirectory path already exists, continue.")
                # If link doesn't lead to a pdf or text page, scrap it
                else:
                    print('\tSkipping document link because it does not appear to lead to a text page/pdf.'
                          '\n\t Or document link may be so outdated that text/pdf check fails')
                    continue

                added_docs.append(document_hash)
                print('\t------------------------')

        return added_docs

    # Always gets text from a document page
    # If there is a pdf link on the document page, downloads the pdf (and its text) as well
    # Checks document year, only visits first page for now since rest of pages only contain
    # outdated documents
    def get_docs_DecisionMakingActivites(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Czech Republic Decision Making Activites ===========================")
        iteration = 1
        added_docs = []

        # We want to create the pagination object, then add the rest of the pages to visit to the
        # pagination object all at once, because calling update_pagination will insert all pages into the
        # pagination list each time.
        # We have to parse the first page before the while loop to do this
        pagination = self.update_pagination(
            start_path='/z-rozhodovaci-cinnosti-uradu/ds-1022/p1=1277&tzv=1&pocet=25&stranka=1')
        initial_page_source = self.get_source(
            page_url='https://www.uoou.cz/z-rozhodovaci-cinnosti-uradu/ds-1022/p1=1277&tzv=1&pocet=25&stranka=1')
        initial_results_soup = BeautifulSoup(initial_page_source.text, 'html.parser')
        pagination = self.update_pagination(pagination=pagination, page_soup=initial_results_soup)

        while pagination.has_next():
            page_url = pagination.get_next()
            print('\n------------ NEW PAGE ------------')
            if to_print:
                print('\tPage:\t', page_url)

            page_source = self.get_source(page_url=page_url)

            if page_source is None:
                print("Skipping page because page_source is None")
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            dok = results_soup.find('div', class_='obsah')
            assert dok
            ui = dok.find('ul', class_='ui')
            assert ui

            # Get the page number we are on -> if it greater than 1, skip
            # Only the first page contains documents made 2018 and after
            page_number = page_url[-1:]
            if int(page_number) > 1:
                print("\tSkipping page: " + page_number)
                continue

            for li in ui.find_all('li'):
                result_link = li.find('a')
                # s2. Documents
                document_title = result_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_href = result_link.get('href')
                assert document_href
                if document_href.startswith('http') is not True:
                    host = "https://www.uoou.cz"
                    document_url = host + document_href
                else:
                    document_url = document_href

                document_response = None
                try:
                    document_response = requests.request('GET', document_url, timeout=2)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if document_response is None:
                    print("\tSkipping existing document: document_response is None")
                    continue

                # Created soup for the document link
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                # Check document date
                popis = document_soup.find('div', class_='popis dpopis')
                assert popis
                date_string = popis.get_text()
                document_year = date_string[-4:]
                # Document was made before 2018, skip it
                if int(document_year) < 2018:
                    print("\tSkipping outdated document existing document:\t", document_hash)
                    continue

                # If significant pdf links exists, go to them and download
                obalcelek_tag = document_soup.find('div', id='obalcelek')
                if obalcelek_tag is not None:
                    a_tag = obalcelek_tag.find_all('a')
                    dpa_folder = self.path
                    document_folder = dpa_folder + '/' + 'Decision-Making Activities' + '/' + document_hash
                    try:
                        os.makedirs(document_folder)
                        if a_tag:
                            for element in a_tag:
                                assert element
                                # Check if we can get a href and if that href contains the string 'File.ashx', which indicates
                                # the link is intended to be downloaded
                                if element.get('href') is not None and ('File.ashx' in element.get('href')):
                                    link_href = element.get('href')
                                    assert link_href
                                    link_url = 'https://www.uoou.cz' + link_href
                                    print("Link URL: " + link_url)

                                    link_response = None
                                    try:
                                        link_response = requests.request('GET', link_url, timeout=2)
                                        link_response.raise_for_status()
                                    except requests.exceptions.HTTPError as error:
                                        pass
                                    if link_response is None:
                                        continue

                                    # If get a link reponse, then write the contents of the file as a pdf and text
                                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                                        f.write(link_response.content)
                                    try:
                                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                                            link_text = textract.process(
                                                document_folder + '/' + self.language_code + '.pdf')
                                            f.write(link_text)
                                    # If the link leads to a word document or a file format other than a pdf
                                    # -> skip text conversion
                                    except:
                                        pass
                                else:
                                    continue

                        # Don't try to find the document date -> website html is too inconsistent
                        # When we print document stuff, that means the document is not going to be thrown out
                        print('\n\t------------ Document: ' + str(iteration) + ' ------------')
                        iteration += 1
                        if to_print:
                            print("\tDocument:\t", document_hash)
                        print('\t------------------------')
                        obsah = document_soup.find('div', class_='obsah')
                        assert obsah
                        document_text = obsah.get_text()
                        document_text = document_text.lstrip()
                        with open(document_folder + '/' + self.language_code + 'Summary' + '.txt', 'w') as f:
                            f.write(document_text)
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
                # Don't need to call update_pagination -> it already has all the pages
        return added_docs

    # No date checking
    def get_docs_DecisionOfPresident(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Czech Republic Decision Of President ===========================")
        added_docs = []

        page_url = 'https://www.uoou.cz/rozhodnuti-predsedy-uradu/ds-3815/archiv=0&p1=1277'
        if to_print:
            print('\tPage:\t', page_url)

        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("Skipping page because page_source is None")
            sys.exit()

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        dok = results_soup.find('div', id='obalcelek')
        assert dok
        obsah = dok.find('div', class_='obsah')
        assert obsah

        iteration = 1
        for ul in obsah.find_all('ul'):
            assert ul
            for li in ul.find_all('li'):
                assert li

                result_link = li.find('a')

                document_title = result_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                document_href = result_link.get('href')
                assert document_href

                if document_href.startswith('http') is not True:
                    host = "https://www.uoou.cz"
                    document_url = host + document_href
                else:
                    document_url = document_href

                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if document_response is None:
                    print("\tSkipping existing document: document_response is None")
                    continue

                # When we print document stuff, that means the document is not going to be thrown out
                print('\n\t------------ Document: ' + str(iteration) + ' ------------')
                iteration += 1
                if to_print:
                    print("\tDocument:\t", document_hash)

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decision of President' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(document_response.content)

                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        link_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                        f.write(link_text)

                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title.strip()
                            },
                            'md5': document_hash,
                            'releaseDate': 'date not available',
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)

                    print('\t------------------------')
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

        return added_docs

    # THE REMAINDER OF THIS FILE IS DEALING WITH THE COMPLETED INSPECTIONS LINK

    # This method is designed to be called by parent method get_docs_CompletedInspections() that
    # scrapes completed inspections.
    # Doesn't get date of specific text documents
    # argument: page_url -> the page we want to scrape. This needs to be a link to a yearly control activities page,
    # where we can see the headings for Finances, Marketing, Education, etc...
    # argument: folder_title -> this is the name of the folder we will store everything in
    def get_docs_DecisionChecksControlActivites(self, existing_docs=[], overwrite=False, to_print=True, page_url=None,
                                                folder_title=None):
        added_docs = []

        if to_print:
            print('\tPage:\t', page_url)

        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("Skipping page because page_source is None")
            sys.exit()

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        dok = results_soup.find('div', id='obalcelek')
        assert dok
        ui = dok.find('ul', class_='ui')
        assert ui

        iteration = 1
        for li in ui.find_all('li'):
            assert li
            result_link = li.find('a')
            assert result_link

            document_href = result_link.get('href')
            assert document_href

            if document_href.startswith('http') is not True:
                host = "https://www.uoou.cz"
                document_url = host + document_href
            else:
                document_url = document_href

            document_response = None
            try:
                document_response = requests.request('GET', document_url, timeout=2)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                pass
            if document_response is None:
                print("\tSkipping outer link: document_response is None")
                continue

            document_soup = BeautifulSoup(document_response.text, 'html.parser')
            assert document_soup

            # Now get the text from each of the links on this second page
            obalcelek = document_soup.find('div', id='obalcelek')
            assert obalcelek
            document_ui = obalcelek.find('ul', class_='ui')
            assert document_ui

            for document_li in document_ui.find_all('li'):
                assert document_li
                text_link = document_li.find('a')
                assert text_link

                document_title = text_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document - hash already exists:\t', document_hash)
                    continue

                text_href = text_link.get('href')
                assert text_href

                if text_href.startswith('http') is not True:
                    host = "https://www.uoou.cz"
                    text_url = host + text_href
                else:
                    text_url = text_href

                text_response = None
                try:
                    text_response = requests.request('GET', text_url, timeout=2)
                    text_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if text_response is None:
                    print("\tSkipping existing document: document_response is None")
                    continue

                text_soup = BeautifulSoup(text_response.text, 'html.parser')
                assert text_soup

                text_obalcelek = text_soup.find('div', id='obalcelek')
                assert text_obalcelek
                text_body = text_obalcelek.find('div', id='stred')
                assert text_body

                # When we print document info, that means the document is not going to be thrown out
                print('\n\t------------ Document: ' + str(iteration) + ' ------------')
                print('\tDocument title: ' + document_title)
                iteration += 1
                if to_print:
                    print("\tDocument:\t", document_hash)

                # Now store the text in the appropriate folder
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Inspections' + '/' + folder_title + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                        f.write(text_body.get_text().encode())

                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': 'date not available',
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)

                    print('\t------------------------')
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")

        return added_docs

    # Same method as get_docs_DecisionChecksControlActivities, except this handles older link version where
    # scraper only needs to go 1 layer deep to access text documents
    def get_docs_DecisionChecksControlActivites2018Below(self, existing_docs=[], overwrite=False, to_print=True, page_url=None,
                                                folder_title=None):

        added_docs = []

        if to_print:
            print('\tPage:\t', page_url)

        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("Skipping page because page_source is None")
            sys.exit()

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        dok = results_soup.find('div', id='obalcelek')
        assert dok
        ui = dok.find('ul', class_='ui')
        assert ui

        iteration = 1
        for li in ui.find_all('li'):
            assert li
            result_link = li.find('a')
            assert result_link

            document_title = result_link.get_text()
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document - hash already exists:\t', document_hash)
                continue

            document_href = result_link.get('href')
            assert document_href

            if document_href.startswith('http') is not True:
                host = "https://www.uoou.cz"
                document_url = host + document_href
            else:
                document_url = document_href

            document_response = None
            try:
                document_response = requests.request('GET', document_url, timeout=2)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                pass
            if document_response is None:
                print("\tSkipping outer link: document_response is None")
                continue

            document_soup = BeautifulSoup(document_response.text, 'html.parser')
            assert document_soup

            text_obalcelek = document_soup.find('div', id='obalcelek')
            assert text_obalcelek
            text_body = text_obalcelek.find('div', id='stred')
            assert text_body

            # When we print document info, that means the document is not going to be thrown out
            print('\n\t------------ Document: ' + str(iteration) + ' ------------')
            print('\tDocument title: ' + document_title)
            iteration += 1
            if to_print:
                print("\tDocument:\t", document_hash)

            # Now store the text in the appropriate folder
            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Inspections' + '/' + folder_title + '/' + document_hash
            try:
                os.makedirs(document_folder)

                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                    f.write(text_body.get_text().encode())

                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': 'date not available',
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                added_docs.append(document_hash)
                print('\t------------------------')
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        return added_docs

    # This method is designed to be called by parent method get_docs_CompletedInspections() that
    # scrapes completed inspections.
    # Doesn't get date of specific text documents
    # argument: page_url -> the page we want to scrape. This needs to be a link to a yearly unsolicited commercial
    # communications page, where we can see the headings for company inspections
    # argument: folder_title -> this is the name of the folder we will store everything in
    def get_docs_DecisionChecksUnsolicitedCommerical(self, existing_docs=[], overwrite=False, to_print=True, page_url=None,
                                                folder_title=None):
        added_docs = []

        if to_print:
            print('\tPage:\t', page_url)

        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("Skipping page because page_source is None")
            sys.exit()

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        dok = results_soup.find('div', id='obalcelek')
        assert dok
        ui = dok.find('ul', class_='ui')
        assert ui

        iteration = 1
        hash_iteration = 1
        for li in ui.find_all('li'):
            assert li
            result_link = li.find('a')
            assert result_link

            # The titles the page gives are often the same, we add iteration number to title to distinguish
            document_title = result_link.get_text() + ' ' + str(hash_iteration)
            hash_iteration += 1
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite is False:
                if to_print:
                    print('\tSkipping existing document - hash already exists:\t', document_hash)
                continue

            document_href = result_link.get('href')
            assert document_href

            if document_href.startswith('http') is not True:
                host = "https://www.uoou.cz"
                document_url = host + document_href
            else:
                document_url = document_href

            document_response = None
            try:
                document_response = requests.request('GET', document_url, timeout=2)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                pass
            if document_response is None:
                print("\tSkipping outer link: document_response is None")
                continue

            document_soup = BeautifulSoup(document_response.text, 'html.parser')
            assert document_soup

            text_obalcelek = document_soup.find('div', id='obalcelek')
            assert text_obalcelek
            text_body = text_obalcelek.find('div', id='stred')
            assert text_body

            # When we print document info, that means the document is not going to be thrown out
            print('\n\t------------ Document: ' + str(iteration) + ' ------------')
            print('\tDocument title: ' + document_title)
            iteration += 1
            if to_print:
                print("\tDocument:\t", document_hash)

            # Now store the text in the appropriate folder
            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Inspections' + '/' + folder_title + '/' + document_hash
            try:
                os.makedirs(document_folder)
                with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                    f.write(text_body.get_text().encode())

                with open(document_folder + '/' + 'metadata.json', 'w') as f:
                    metadata = {
                        'title': {
                            self.language_code: document_title
                        },
                        'md5': document_hash,
                        'releaseDate': 'date not available',
                        'url': document_url
                    }
                    json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                added_docs.append(document_hash)
                print('\t------------------------')
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        return added_docs

    # This is the method to be called when scraping Completed Inspections documents (part of Decisions).
    # This method starts at the main Completed Inspections page and visits each "Checks for XXXX" link.
    # If year for the link is less than 2018, it is not scraped.
    # Once inside "Check for XXXX" link, the method examines the links on the new page and determines the
    # appropriate scraper methods to call, depending on if links lead to Control Activities or Commercial
    # Communications type documents.
    def get_docs_CompletedInspections(self, existing_docs=[], overwrite=False, to_print=True):

        print("\n========================= Czech Republic Completed Inspections ===========================")
        added_docs = []

        page_url = 'https://www.uoou.cz/ukoncene-kontroly/ds-5649/archiv=0&p1=1277'
        if to_print:
            print('\tPage:\t', page_url)

        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("Skipping page because page_source is None")
            sys.exit()

        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        dok = results_soup.find('div', id='obalcelek')
        assert dok
        ui = dok.find('ul', class_='ui')
        assert ui

        for li in ui.find_all('li'):
            assert li
            result_link = li.find('a')
            assert result_link

            # The titles the page gives are often the same, we add iteration number to title to distinguish
            document_title = result_link.get_text()
            inspection_date = document_title[-4:]
            if int(inspection_date) < 2018:
                print('\tSkipping inspections for year: ' + inspection_date)
                continue

            document_href = result_link.get('href')
            assert document_href

            if document_href.startswith('http') is not True:
                host = "https://www.uoou.cz"
                document_url = host + document_href
            else:
                document_url = document_href

            print('URL for Checks: ' + inspection_date + ' is ' + document_url)

            document_response = None
            try:
                document_response = requests.request('GET', document_url, timeout=2)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                pass
            if document_response is None:
                print("\tSkipping inspection link: document_response is None")
                continue

            soup = BeautifulSoup(document_response.text, 'html.parser')
            assert soup

            # Now look at control actives and unsolicited commercial communications
            obalcelek = soup.find('div', id='obalcelek')
            assert obalcelek
            page_ui = obalcelek.find('ul', class_='ui')
            assert page_ui

            for page_li in page_ui.find_all('li'):
                assert page_li

                next_link = page_li.find('a')
                assert next_link

                link_title = next_link.get_text()
                assert link_title

                link_href = next_link.get('href')
                assert link_href

                if link_href.startswith('http') is not True:
                    host = "https://www.uoou.cz"
                    link_url = host + link_href
                else:
                    link_url = link_href

                # If links leads to a control actives pages and the year is 2018 or lower
                if 'kontrolni' in link_url and int(inspection_date) <= 2018:
                    # If this is control activities for second half of the year
                    if '2.' in link_title:
                        added_docs += self.get_docs_DecisionChecksControlActivites2018Below(page_url=link_url,
                                        folder_title=(inspection_date + ' Control Activities - 2nd half of the year'))

                    elif '1.' in link_title:
                        added_docs += self.get_docs_DecisionChecksControlActivites2018Below(page_url=link_url,
                                        folder_title=(inspection_date + ' Control Activities - 1st half of the year'))

                    else:
                        print('Failed to scrape Control Activities link')

                # If links leads to a regular control actives pages
                elif 'kontrolni' in link_url:
                    # If this is control activities for second half of the year
                    if '2.' in link_title:
                        added_docs += self.get_docs_DecisionChecksControlActivites(page_url=link_url,
                                        folder_title=(inspection_date + ' Control Activities - 2nd half of the year'))

                    elif '1.' in link_title:
                        added_docs += self.get_docs_DecisionChecksControlActivites(page_url=link_url,
                                        folder_title=(inspection_date + ' Control Activities - 1st half of the year'))

                    else:
                        print('Failed to scrape Control Activities link')

                # Link leads to unsolicited commercial communications page
                elif 'nevyzadana' in link_url:
                    # If this is unsolicited commercial communications for second half of the year
                    if '2.' in link_title:
                        added_docs += self.get_docs_DecisionChecksUnsolicitedCommerical(page_url=link_url,
                                        folder_title=(inspection_date
                                                    + ' Unsolicited Commercial Communications - 2nd half of the year'))

                    elif '1.' in link_title:
                        added_docs += self.get_docs_DecisionChecksUnsolicitedCommerical(page_url=link_url,
                                        folder_title=(inspection_date
                                                    + ' Unsolicited Commercial Communications - 1st half of the year'))
                    else:
                        print('Failed to scrape Unsolicited Commercial Communications link')

                else:
                    print("Couldn't determine type for link: " + link_url)

        return added_docs
