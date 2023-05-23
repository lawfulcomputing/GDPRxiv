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

class Romania(DPA):
    def __init__(self, path=os.curdir):
        country_code='ro'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None):
        source = {
            "host": "https://www.dataprotection.ro",
            "start_path": "/?page=allnews&lang=ro"
        }
        host = source['host']
        start_path = source['start_path']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        return pagination

    def get_source(self, page_url=None, driver=None):
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
        print("\n===================== Romania Decisions & Reports ====================")
        iteration = 1
        added_docs = []
        dict_hashcode = {}
        pagination = self.update_pagination()
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup
            rectangle_scroll = results_soup.find('div', id='rectangle_scroll')
            assert rectangle_scroll
            date_index, title_index, link_index = 0, 2, 3
            p_all = rectangle_scroll.find_all('p')
            assert len(p_all) > 0
            # s1. Results
            for i in range(1, len(p_all)):
                p_date = p_all[i]
                date_str = p_date.get_text()
                tmp = None
                try:
                    tmp = datetime.datetime.strptime(date_str, '%d/%m/%Y')
                except ValueError:
                    pass
                if tmp is None:
                    continue
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                # s2. Documents
                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1

                title = p_all[i + 1]
                document_title = title.get_text().strip()
                print('\tdocument_title:\t', document_title)
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                result_link = None
                j, j_threshold = 0, 4
                while result_link is None:
                    cand_link = p_all[i + j]
                    result_link = cand_link.find('a')
                    if j == j_threshold:
                        break
                    j += 1
                assert result_link
                document_href = result_link.get('href')
                host = "https://www.dataprotection.ro"
                document_url = host + document_href
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
                document_target_area = document_soup.find('div', id='rectangle_scroll')
                assert document_target_area
                document_text = document_target_area.get_text()
                document_text = document_text.strip()
                dpa_folder = self.path

                # solve documents with same title and same date issue
                if document_hash not in dict_hashcode:
                    dict_hashcode[document_hash] = 1
                else:
                    dict_hashcode[document_hash] = dict_hashcode[document_hash] + 1

                document_hash = document_hash + '-' + str(dict_hashcode[document_hash])
                if to_print:
                    print("\tDocument:\t", document_hash)
                    print("\tdate_str: ", date_str)
                    print("\tdocument_url: ", document_url)
                document_folder = dpa_folder + '/' + "Decisions & Reports" + '/' + document_hash

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
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    added_docs.append(document_hash)
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
        return added_docs

