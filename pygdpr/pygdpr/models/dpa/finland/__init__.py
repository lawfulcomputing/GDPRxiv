import os
import math
import requests
import json
import datetime
import hashlib

import textract

from pygdpr.models.dpa import DPA
from bs4 import BeautifulSoup
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy

class Finland(DPA):
    def __init__(self, path=os.curdir):
        country_code='FI'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path=None):
        page_url = 'https://tietosuoja.fi/en/current-issues'
        pagination = Pagination()
        pages = page_soup.find('ul', class_='nav-pills')
        # print('pages: ', pages)
        for li in pages.find_all('li', class_='nav-item'):
            a = li.find('a')
            page_url = a.get('href')
            pagination.add_item(page_url)
        return pagination


    def get_source(self, page_url=None, driver=None):
        assert (page_url is not None)
        results_response = None
        try:

            results_response = requests.request('GET', page_url, timeout=2)
            results_response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            pass
        return results_response

    # some docs are written is english, and some are in Finnish
    # for the english version docs, change the language.code as 'en'
    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):

        page_url = 'https://tietosuoja.fi/en/current-issues'
        page_source = self.get_source(page_url)
        page_soup = BeautifulSoup(page_source.text, 'html.parser')
        pagination = self.update_pagination(page_soup=page_soup)

        print("\n========================= Finland Documents ===========================")
        added_docs = []


        if to_print:
            print('\nPAGE:\t', page_url)

        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)

            iterator = 1
            page_source = self.get_source(page_url)
            page_soup = BeautifulSoup(page_source.text, 'html.parser')
            ul = page_soup.find('ul', class_='results')
            for li in ul.find_all('li', class_='list__item'):
                span_date = li.find('span', class_='date')
                assert span_date
                date_str = span_date.get_text()
                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if date.year < 2018:
                    print("Skipping outdated document")
                    return added_docs

                ul_year = date.year
                result_link = li.find('a')
                assert result_link
                # s2. Documents
                document_title = result_link.get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                print('\n------------ Document: ' + str(iterator) + ' ------------')
                print('\tDocument Title: ' + document_title)
                print("\tdate: ", date)
                iterator += 1

                document_href = result_link.get('href')
                assert document_href
                host = "https://tietosuoja.fi"
                document_url = host + document_href

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

                # Document parse object
                document_soup = BeautifulSoup(document_response.text, 'html.parser')
                assert document_soup

                # Obtain document text
                news_page = document_soup.find('div', class_='news-page')
                if news_page is None:
                    continue
                document_text = news_page.get_text()
                document_text = document_text.lstrip()

                # Look at all links contained in the document
                document_tags = news_page.find_all(['p', 'ul'])
                assert document_tags

                dpa_folder = self.path
                document_folder = dpa_folder + '/' + str(ul_year) + ' Finland Documents' + '/' + document_hash
                # document_folder = dpa_folder + '/finland' + '/' + str(ul_year) + ' Finland Documents' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    # Use this when naming the files for pdf links we download. Only increment if use it in a name.
                    link_iterator = 1
                    # This second iterator is for if we have finlex links on the page too
                    # -> don't want to confuse with pdf stuff
                    link_iterator_finlex_links = 1
                    for tags in document_tags:
                        if tags.find('a') is not None:
                            a_tag = tags.find_all('a')
                            for i in range(len(a_tag)):
                                href = a_tag[i].get('href')
                                assert href

                                if href.startswith('http'):
                                    url = href
                                else:
                                    url = "https://tietosuoja.fi" + href

                                if '.pdf' in url:
                                    pdf_response = None
                                    try:
                                        pdf_response = requests.request('GET', url)
                                        pdf_response.raise_for_status()
                                    except requests.exceptions.HTTPError as error:
                                        if to_print:
                                            print(error)
                                        pass
                                    if pdf_response is None:
                                        continue

                                    print("\tDownloading PDF: " + url)
                                    # Write pdf and its text to files

                                    with open(document_folder + '/' + 'en' + str(link_iterator) + '.pdf', 'wb') as f:
                                        f.write(pdf_response.content)
                                    with open(document_folder + '/' + 'en' + str(link_iterator) + '.txt', 'wb') as f:
                                        link_text = textract.process(document_folder + '/' + 'en' + str(link_iterator) + '.pdf')
                                        f.write(link_text)

                                    link_iterator += 1

                                elif url.startswith('https://finlex') or url.startswith('https://www.finlex'):
                                    text_response = None
                                    try:
                                        text_response = requests.request('GET', url)
                                        text_response.raise_for_status()
                                    except requests.exceptions.HTTPError as error:
                                        if to_print:
                                            print(error)
                                        pass
                                    if text_response is None:
                                        continue

                                    print("\tDownloading Finlex text: " + url)
                                    text_soup = BeautifulSoup(text_response.text, 'html.parser')
                                    assert text_soup

                                    body = text_soup.find('div', id='main-content')
                                    # print(body)
                                    assert body
                                    body_text = body.get_text()
                                    body_text = body_text.lstrip()
                                    assert body_text

                                    with open(document_folder + '/' + self.language_code + 'Finlex' + str(link_iterator_finlex_links) + '.txt', 'wb') as f:
                                        f.write(body_text.encode())
                                    link_iterator_finlex_links += 1

                                # Link is not useful
                                else:
                                    continue

                        # The <p tag doesn't provide a link
                        else:
                            continue

                    with open(document_folder + '/' + 'en' + 'Summary' + '.txt', 'w') as f:
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
                    print("\tDirectory path already exists, continue.")
        return added_docs
