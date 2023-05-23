import os
import shutil
import math
import requests
import json
import datetime
import hashlib
from pygdpr.models.dpa import DPA
from bs4 import BeautifulSoup
import textract
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.specifications.root_document_specification import RootDocumentSpecification
from pygdpr.policies.gdpr_policy import GDPRPolicy
import re
import sys

class Austria(DPA):
    def __init__(self, path=os.curdir):
        country_code='AT'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        from_date = GDPRPolicy().implementation_date().strftime('%d.%m.%Y')
        to_date = datetime.datetime.now().strftime('%d.%m.%Y')
        source = {
            "host": "https://www.ris.bka.gv.at",
            "start_path": f"/Ergebnis.wxe?Abfrage=Dsk&Entscheidungsart=Undefined&Organ=Undefined&SucheNachRechtssatz=True&SucheNachText=True&GZ=&VonDatum=25.05.2018&BisDatum=25.05.2021&Norm=&ImRisSeitVonDatum=&ImRisSeitBisDatum=&ImRisSeit=Undefined&ResultPageSize=100&Suchworte=&Position=1",
        }
        host = source['host']
        start_path = source['start_path']
        if pagination is None or page_soup is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
            return pagination
        pages = page_soup.find('ul', class_='Pages')

        # Removed loop -> place li's into a list and abstract the middle li to get the href
        href_index = 1
        if pages is not None:
            li_list = pages.find_all('li')
            assert li_list
            page_link = li_list[href_index].find('a')
            assert page_link
            page_href = page_link.get('href')
            assert page_href
            pagination.add_item(host + page_href)

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
        added_docs += self.get_docs_Decisions(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        pagination = self.update_pagination()
        iteration = 1
        print("\n========================= Austria Decisions Documents ===========================")
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
            table = page_soup.find('table', class_='bocListTable')
            assert table
            tbody = table.find('tbody', class_='bocListTableBody')
            assert tbody
            # s1. Results
            for tr in tbody.find_all('tr', class_='bocListDataRow'):
                result_index, date_index, document_links_index = 2, 4, 8
                td_list = tr.find_all('td', class_='bocListDataCell')
                assert len(td_list) >= document_links_index + 1
                date_str = td_list[date_index].get_text()
                tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                result_link = td_list[result_index].find('a')
                assert result_link
                # s2. Documents
                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1
                document_title = result_link.get('title')
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                document_links = td_list[document_links_index]
                document_href = None
                for document_link in document_links.find_all('a'):
                    cand_href = document_link.get('href')
                    if cand_href.endswith('.pdf'):
                        document_href = cand_href
                        break
                assert document_href
                host = "https://www.ris.bka.gv.at"
                document_url = host + document_href
                if to_print:
                    print('\tdocument_title:\t', document_title)
                    print("\tDocument:\t", document_hash)
                    print('\tdate:\t', str(date))
                    print('\tdocument_url:\t', document_url)
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
                        document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
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

            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=page_soup)
        return added_docs

    # Using an iterator counter to keep track of documents for now
    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        print('------------ GETTING ANNUAL REPORTS ------------')
        added_docs = []

        page_url = "https://www.dsb.gv.at/download-links/dokumente.html"
        if to_print:
            print('Page:\t', page_url)
        page_source = self.get_source(page_url)
        if page_source is None:
            sys.exit("Couldn't obtain page_source from page_url")
        page_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert page_soup

        body = page_soup.find('body', class_='template-article')
        assert body
        main = body.find('main', class_='col-12 content col-xl-9')
        assert main
        span_soup = main.find('span', class_='richtext_output')
        assert span_soup
        ul_list = span_soup.find_all('ul')
        assert ul_list

        iteration = 1
        for ul in ul_list[5:8]:
            for li in ul.find_all('li'):
                assert li

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1;

                # date_str = td_list[date_index].get_text()
                # tmp = datetime.datetime.strptime(date_str, '%d.%m.%Y')
                # date = datetime.date(tmp.year, tmp.month, tmp.day)
                # if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                # continue

                result_link = li.find('a')
                assert result_link

                document_href = result_link.get('href')
                assert document_href

                if ".pdf" in document_href:
                    print("PDF DOC:")
                    document_url = "https://www.dsb.gv.at" + document_href
                    # Check date of pdf link by getting the pdf title
                    pdf_title = result_link.text
                    assert pdf_title
                    document_title = pdf_title

                    # Use re library to look for pdf date in the title string
                    pdf_date_search = re.search(' (.+?) ', pdf_title)
                    if pdf_date_search:
                        found_date = pdf_date_search.group(1)

                    print("PDF year: " + found_date)

                    pdf_end_date = found_date[-4:]
                    print("PDF end date: " + pdf_end_date)

                    if len(pdf_end_date) == 4:
                        if int(pdf_end_date) < 2018:
                            print("\nPDF IS OUTDATED -> SKIPPING\n")
                            continue

                else:
                    print("TEXT DOC:")
                    document_url = document_href
                    document_title = str(iteration)
                print("      Document url:" + document_url)

                # If doc is a pdf, title and date should be correct, if then title is just the iteration number for now
                assert document_title
                print("DOCUMENT TITLE: " + document_title)

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue

                if to_print:
                    print("Document:\t", document_hash)
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
                document_folder = dpa_folder + '/' 'AnnualReports' + '/' + document_hash
                try:
                    os.makedirs(document_folder)
                    if '.pdf' in document_url:
                        document_content = document_response.content

                        with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                            f.write(document_content)
                        with open(document_folder + '/' + self.language_code + '.txt', 'wb') as f:
                            document_text = textract.process(document_folder + '/' + self.language_code + '.pdf')
                            f.write(document_text)

                        added_docs.append(document_hash)
                        iteration += 1
                        continue

                    document_soup = BeautifulSoup(document_response.text, 'html.parser')
                    assert document_soup

                    # Get document_text according to the link scraper is visiting
                    if '.html' in document_url:
                        document_paper = document_soup.find('div', class_='paperw')
                        assert document_paper
                        document_text = document_paper.get_text()
                    elif 'eur-lex.europa.eu' in document_url:
                        document_clear = document_soup.find('div', class_='Wrapper clearfix')
                        assert document_clear
                        document_area = document_clear.find('div', class_='col-md-9')
                        assert document_area
                        document_page = document_area.find('div', class_='tabContent')
                        assert document_page
                        document_text = document_page.get_text()
                    else:
                        document_div = document_soup.find('div', class_='aspNetHidden')
                        assert document_div
                        field_name_body = document_soup.find('div', class_='document', recursive=True)
                        assert field_name_body
                        document_text = field_name_body.get_text()

                    with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        f.write(document_text)
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title,
                            },
                            'md5': document_hash,
                            'releaseDate': "(Put date here)",  # date.strftime('%d/%m/%Y'),
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True)
                    added_docs.append(document_hash)  # put doc hash in here

                except FileExistsError:
                    print("Directory path already exists, continue.")
        return added_docs

