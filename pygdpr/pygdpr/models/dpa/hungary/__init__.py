import os
import math
import requests
import json
import datetime
import hashlib
import dateparser
from pygdpr.models.dpa import DPA
from bs4 import BeautifulSoup
from pygdpr.services.filename_from_path_service import filename_from_path_service
from pygdpr.services.pdf_to_text_service import PDFToTextService
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy
import textract

class Hungary(DPA):
    def __init__(self, path=os.curdir):
        country_code='HU'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path="decisions"):
        source = {
            "host": "https://www.naih.hu",
            "start_path_decisions": "/hatarozatok-vegzesek?start=0",
            "start_path_recommendations": "/adatvedelmi-ajanlasok",
            "start_path_notices": "/dontesek-adatvedelem-tajekoztatok-koezlemenyek",
            "start_path_resolutions": "/adatvedelmi-allasfoglalasok?start=0",
            "start_path_annualReports": "/eves-beszamolok"
        }
        host = source['host']
        if start_path == "recommendations":
            start_path = source['start_path_recommendations']
        elif start_path == "notices":
            start_path = source['start_path_notices']
        elif start_path == "resolutions":
            start_path = source['start_path_resolutions']
        elif start_path == "annualReports":
            start_path = source['start_path_annualReports']
        else:
            start_path = source['start_path_decisions']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pagination = Pagination()
            sectiontablefooter = page_soup.find('div', class_='sectiontablefooter')
            if sectiontablefooter is None:
                return pagination
            pagination_next = sectiontablefooter.find('li', class_='pagination-next')
            if pagination_next is None:
                return pagination
            try_next_link = pagination_next.find('a', class_='hasTooltip pagenav')
            if try_next_link is None:
                return pagination
            next_link = try_next_link.get('href')
            print("next_link:", next_link)
            pagination.add_item(host + next_link)
            #print('added link to pagination: ', host + next_link)
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
        added_docs += self.get_docs_Recommendations(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Notices(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Resolutions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Hungary Decision Documents ===========================")
        iterator = 1
        existed_docs = []
        dict_hash = {}
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
            pd_category = results_soup.find('div', class_='pd-category')
            for pd_filebox in pd_category.find_all('div', class_='pd-filebox'):

                print("\n------------ Document " + str(iterator) + " ------------")
                iterator += 1

                pd_filenamebox = pd_filebox.find('div', class_='pd-filenamebox')
                pd_filename = pd_filenamebox.find('div', class_='pd-filename')
                pd_float = pd_filename.find('div', class_='pd-float')
                document_title = pd_float.find('a').get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                document_href = pd_float.find('a').get('href')
                pd_fl_m = pd_filebox.find('div', class_='pd-fl-m')
                date_str = pd_fl_m.get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                print('\tDocument Title:\t', document_title)
                print('\tdate:\t', date)
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                if document_hash in dict_hash and dict_hash[document_hash] == date:
                    if to_print:
                        print('\tDocument exist:\t', document_hash)
                    continue
                host = "https://www.naih.hu"
                document_url = host + '/' + document_href
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
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                # document_folder = dpa_folder + '/hungary' + '/' + 'Decisions' + '/' + document_hash
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
                    existed_docs.append(document_hash)
                    dict_hash[document_hash] = date
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs


    def get_docs_Recommendations(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Hungary Recommendations ===========================")
        iterator = 1
        existed_docs = []
        dict_hash = {}
        pagination = self.update_pagination(start_path="recommendations")
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
            pd_category = results_soup.find('div', class_='pd-category')
            for pd_filebox in pd_category.find_all('div', class_='pd-filebox'):
                print("\n------------ Document " + str(iterator) + " ------------")
                iterator += 1

                pd_filenamebox = pd_filebox.find('div', class_='pd-filenamebox')
                pd_filename = pd_filenamebox.find('div', class_='pd-filename')
                pd_float = pd_filename.find('div', class_='pd-float')
                document_title = pd_float.find('a').get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                document_href = pd_float.find('a').get('href')
                pd_fl_m = pd_filebox.find('div', class_='pd-fl-m')
                date_str = pd_fl_m.get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                print('\tDocument Title:\t', document_title)
                print('\tdate:\t', date)
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                if document_hash in dict_hash and dict_hash[document_hash] == date:
                    if to_print:
                        print('\tDocument exist:\t', document_hash)
                    continue
                host = "https://www.naih.hu"
                document_url = host + '/' + document_href
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
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Recommendations' + '/' + document_hash
                # document_folder = dpa_folder + '/hungary' + '/' + 'Recommendations' + '/' + document_hash
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
                    existed_docs.append(document_hash)
                    dict_hash[document_hash] = date
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs


    def get_docs_Notices(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Hungary Notices ===========================")
        iterator = 1
        existed_docs = []
        dict_hash = {}
        pagination = self.update_pagination(start_path="notices")
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
            pd_category = results_soup.find('div', class_='pd-category')
            for pd_filebox in pd_category.find_all('div', class_='pd-filebox'):

                print("\n------------ Document " + str(iterator) + " ------------")
                iterator += 1

                pd_filenamebox = pd_filebox.find('div', class_='pd-filenamebox')
                pd_filename = pd_filenamebox.find('div', class_='pd-filename')
                pd_float = pd_filename.find('div', class_='pd-float')
                document_title = pd_float.find('a').get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                document_href = pd_float.find('a').get('href')
                pd_fl_m = pd_filebox.find('div', class_='pd-fl-m')
                date_str = pd_fl_m.get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                print('\tDocument Title:\t', document_title)
                print('\tdate:\t', date)
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                if document_hash in dict_hash and dict_hash[document_hash] == date:
                    if to_print:
                        print('\tDocument exist:\t', document_hash)
                    continue
                host = "https://www.naih.hu"
                document_url = host + '/' + document_href
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
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Notices' + '/' + document_hash
                # document_folder = dpa_folder + '/hungary' + '/' + 'Notices' + '/' + document_hash
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
                    existed_docs.append(document_hash)
                    dict_hash[document_hash] = date
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs


    def get_docs_Resolutions(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Hungary Resolutions ===========================")
        iterator = 1
        existed_docs = []
        dict_hash = {}
        pagination = self.update_pagination(start_path="resolutions")
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
            pd_category = results_soup.find('div', class_='pd-category')
            for pd_filebox in pd_category.find_all('div', class_='pd-filebox'):
                print("\n------------ Document " + str(iterator) + " ------------")
                iterator += 1

                pd_filenamebox = pd_filebox.find('div', class_='pd-filenamebox')
                pd_filename = pd_filenamebox.find('div', class_='pd-filename')
                pd_float = pd_filename.find('div', class_='pd-float')
                document_title = pd_float.find('a').get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                document_href = pd_float.find('a').get('href')
                pd_fl_m = pd_filebox.find('div', class_='pd-fl-m')
                date_str = pd_fl_m.get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                print('\tDocument Title:\t', document_title)
                print('\tdate:\t', date)
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                if document_hash in dict_hash and dict_hash[document_hash] == date:
                    if to_print:
                        print('\tDocument exist:\t', document_hash)
                    continue
                host = "https://www.naih.hu"
                document_url = host + '/' + document_href
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
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Resolutions' + '/' + document_hash
                # document_folder = dpa_folder + '/hungary' + '/' + 'Resolutions' + '/' + document_hash
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
                    existed_docs.append(document_hash)
                    dict_hash[document_hash] = date
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs


    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Hungary Annual Reports ===========================")
        iterator = 1
        existed_docs = []
        dict_hash = {}
        pagination = self.update_pagination(start_path='annualReports')
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
            pd_category = results_soup.find('div', class_='pd-category')
            for pd_filebox in pd_category.find_all('div', class_='pd-filebox'):
                print("\n------------ Document " + str(iterator) + " ------------")
                iterator += 1

                pd_filenamebox = pd_filebox.find('div', class_='pd-filenamebox')
                pd_filename = pd_filenamebox.find('div', class_='pd-filename')
                pd_float = pd_filename.find('div', class_='pd-float')
                document_title = pd_float.find('a').get_text()
                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                document_href = pd_float.find('a').get('href')
                pd_fl_m = pd_filebox.find('div', class_='pd-fl-m')
                date_str = pd_fl_m.get_text()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                print('\tDocument Title:\t', document_title)
                print('\tdate:\t', date)
                if document_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_hash)
                    continue
                if document_hash in dict_hash and dict_hash[document_hash] == date:
                    if to_print:
                        print('\tDocument exist:\t', document_hash)
                    continue
                host = "https://www.naih.hu"
                document_url = host + '/' + document_href
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
                document_content = document_response.content
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Annual Reports' + '/' + document_hash
                # document_folder = dpa_folder + '/hungary' + '/' + 'Annual Reports' + '/' + document_hash
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
                    existed_docs.append(document_hash)
                    dict_hash[document_hash] = date
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs