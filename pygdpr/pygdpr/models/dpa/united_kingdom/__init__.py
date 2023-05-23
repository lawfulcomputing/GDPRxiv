import os
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
from pygdpr.specifications import pdf_file_extension_specification
from pygdpr.specifications.should_retain_document_specification import ShouldRetainDocumentSpecification
from pygdpr.models.common.pagination import Pagination
from pygdpr.policies.gdpr_policy import GDPRPolicy
from pygdpr.services.pdf_to_text_service import PDFToTextService
import docx2txt
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy
from selenium.webdriver.common.keys import Keys
import time


class UnitedKingdom(DPA):
    def __init__(self, path=os.curdir):
        country_code='GB'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, page_soup=None, driver=None, start_path="Reports"):
        source = {
            "host": "https://ico.org.uk",
            "start_path_Reports": "/action-weve-taken/audits-and-overview-reports/?facet_type=&facet_sector=&facet_date=custom&date_from=01%2F05%2F2018&date_to=",
            "start_path_Enforcements": "/action-weve-taken/enforcement/"
        }
        host = source['host']
        if start_path != "Reports":
            start_path = source['start_path_Enforcements']
        else:
            start_path = source['start_path_Reports']
        if pagination is None:
            pagination = Pagination()
            pagination.add_item(host + start_path)
        else:
            pagination = Pagination()

            button_next = page_soup.find('nav', class_='article-navigation')
            if button_next is None:
                return pagination
            page_link = button_next.find('a', class_='button button-top').get('href')
            if page_link is None:
                return pagination
            print("page_link:", page_link)
            pagination.add_item(host + page_link)
            print('added link to pagination: ', host + page_link)

        return pagination


    def get_source(self, page_url=None, driver=None):
        assert (page_url is not None)
        results_response = None
        try:
            results_response = requests.request('GET', page_url)
            results_response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            pass
        return results_response

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_Notices(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Enforcements(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Reports(existing_docs=[], overwrite=False, to_print=True)
        return added_docs


    def get_docs_Notices(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== United Kingdom Notices =========================")
        iteration = 1
        existed_docs = []
        existed_date = []
        source = {
            "host": "https://icosearch.ico.org.uk",
            "start_path": "/s/search.html?collection=ico-meta&profile=decisions&query&query=GDPR"
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        page_source = self.get_source(page_url=page_url)
        if page_source is None:
            print("This url is not exist.")
        results_soup = BeautifulSoup(page_source.text, 'html.parser')
        assert results_soup
        maincolumn = results_soup.find('div', class_='maincolumn')
        assert maincolumn
        resultlist = maincolumn.find('div', class_='resultlist')
        assert resultlist
        # s1. Results
        for itemlink in resultlist.find_all('div', class_='itemlink'):
            print('\n------------ Document ' + str(iteration) + ' ------------')
            iteration += 1
            time.sleep(2)
            result_link = itemlink.find('a')
            assert result_link
            text_small = itemlink.find('p', class_='text-small')
            assert text_small
            date_str = text_small.get_text().split(',')[0].strip()
            tmp = dateparser.parse(date_str, languages=[self.language_code]) # datetime.datetime.strptime(date_str, '%d %B %Y')
            date = datetime.date(tmp.year, tmp.month, tmp.day)
            print('\tdate:\t', str(date))

            uk_left_eu = datetime.date(2020, 1, 31)
            # check whether this article release after UK left EU
            #if date.year > uk_left_eu.year or (date.month > uk_left_eu.month and date.year == uk_left_eu.year):
            #    print("This article release after UK left EU.")
            #    continue

            if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                continue
            # s2. Documents
            h2 = result_link.find('h2', class_='h3')
            assert h2
            document_title = h2.get_text().strip()
            print('\tdocument_title:\t', document_title)
            document_hash = hashlib.md5(document_title.encode()).hexdigest()

            # check whether this articles already exist
            if document_hash in existed_docs and date in existed_date:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue

            document_href = result_link.get('title') # result_link.get('href')
            assert document_href
            if document_href.endswith('.pdf') is False:
                print("found a document which is not of mimeType PDF.")
                continue
            host = "https://icosearch.ico.org.uk" # "https://ico.org.uk"
            document_url = document_href# host + document_href
            print('\tdocument_url:\t', document_url)
            if to_print:
                print("\tDocument:\t", document_hash)
            document_response = None
            try:
                document_response = requests.request('GET', document_url)
                document_response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                pass
            if document_response is None:
                continue

            dpa_folder = self.path
            if document_hash in existed_docs:
                document_folder = dpa_folder + '/' + 'Notices' + '/' + document_hash + ' -02'
            else:
                document_folder = dpa_folder + '/' + 'Notices' + '/' + document_hash
            try:
                os.makedirs(document_folder)
                file_url = document_url

                try:
                    file_response = requests.request('GET', file_url)
                    file_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                if file_response is None:
                    continue
                file_content = file_response.content
                with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                    f.write(file_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        document_text = PDFToTextService().text_from_pdf_path(document_folder + '/' + self.language_code + '.pdf')
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
                    json.dump(metadata, f, indent=4, sort_keys=True)
                existed_docs.append(document_hash)
                existed_date.append(date)
                print('\n')
            except FileExistsError:
                print("\tDirectory path already exists, continue.")

        return existed_docs

    def get_docs_Reports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== United Kingdom Reports =========================")
        iteration = 1
        existed_docs = []
        hashcode_with_date = {}
        pagination = self.update_pagination()
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                print("None page source")
                continue
            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            resultlist = results_soup.find('div', class_='resultlist')
            assert resultlist
            # s1. Results
            for itemlink in resultlist.find_all('div', class_='itemlink'):

                print('\n------------ Document ' + str(iteration) + ' ------------')
                iteration += 1
                # time.sleep(2)
                result_link = itemlink.find('a')
                assert result_link
                text_small = itemlink.find('p', class_='text-small')
                assert text_small
                date_str = text_small.get_text().split(',')[0].strip()
                tmp = dateparser.parse(date_str, languages=[self.language_code]) # datetime.datetime.strptime(date_str, '%d %B %Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                # addition: we can check whether this article release after UK left EU
                # uk_left_eu = datetime.date(2020, 1, 31)
                # check whether this article release after UK left EU
                #if date.year > uk_left_eu.year or (date.month > uk_left_eu.month and date.year == uk_left_eu.year):
                #    print("This article release after UK left EU.")
                #    continue

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                # s2. Documents
                h2 = result_link.find('h2', class_='h3')
                assert h2
                document_title = h2.get_text().strip()

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                # check whether this articles already exist
                if document_hash in hashcode_with_date.keys() and hashcode_with_date[document_hash] == date:
                    if to_print:
                        print('\tAlready exist, skip:\t', document_hash)
                    continue

                print('\tdocument_title:\t', document_title)
                print('\tdate:\t', date)
                document_href = result_link.get('href')
                assert document_href

                host = "https://ico.org.uk"
                document_url = host + document_href
                print('\tdocument_url:\t', document_url)
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                if document_response is None:
                    continue

                dpa_folder = self.path
                if document_hash in existed_docs:
                    document_folder = dpa_folder + '/' + 'Reports' + '/' + document_hash + ' -02'
                else:
                    document_folder = dpa_folder + '/' + 'Reports' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    document_soup = BeautifulSoup(document_response.text, 'html.parser')
                    assert document_soup

                    article_content = document_soup.find_all('div', class_='article-content')
                    assert article_content
                    document_text = ''
                    for i in article_content:
                        document_text += i.get_text()
                    with open(document_folder + '/' + self.language_code + '-' + 'article_content' + '.txt', 'w') as f:
                        f.write(document_text)

                    aside_further = document_soup.find('aside', class_='aside-further')
                    if aside_further is not None:
                        count_articles = 0
                        for articles in aside_further.find_all('li'):
                            title = articles.find('h3').get_text()
                            print("\t\tfile_title: ", title)
                            article_url = articles.find('a').get('href')

                            if article_url is not None:
                                file_url = host + article_url
                                print("\t\tfile_url: ", file_url)
                                try:
                                    file_response = requests.request('GET', file_url)
                                    file_response.raise_for_status()
                                except requests.exceptions.HTTPError as error:
                                    if to_print:
                                        print(error)
                                    pass
                                if file_response is None:
                                    continue
                                count_articles += 1
                                file_content = file_response.content
                                if count_articles > 1:
                                    with open(document_folder + '/' + self.language_code + '-' + str(count_articles) + '.pdf', 'wb') as f:
                                        f.write(file_content)
                                    with open(document_folder + '/' + self.language_code + '_' + str(count_articles) + '.txt', 'w') as f:
                                        document_text = PDFToTextService().text_from_pdf_path(document_folder + '/' + self.language_code + '-' + str(count_articles) + '.pdf')
                                        f.write(document_text)
                                else:
                                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                                        f.write(file_content)
                                    with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                                        document_text = PDFToTextService().text_from_pdf_path(document_folder + '/' + self.language_code + '.pdf')
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
                        json.dump(metadata, f, indent=4, sort_keys=True)
                    existed_docs.append(document_hash)
                    hashcode_with_date[document_hash] = date
                    print('\n')
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs

    def get_docs_Enforcements(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n======================== United Kingdom Enforcements=========================")
        existed_docs = []
        existed_dates = []
        hashcode_with_type = ""
        hashcode_dict = {}
        pagination = self.update_pagination(start_path="Enforcements")
        # s0. Pagination
        while pagination.has_next():
            page_url = pagination.get_next()
            if to_print:
                print('Page:\t', page_url)
            page_source = self.get_source(page_url=page_url)
            if page_source is None:
                print("None page source")
                continue
            time.sleep(2)

            results_soup = BeautifulSoup(page_source.text, 'html.parser')
            assert results_soup

            exec_path = WebdriverExecPolicy().get_system_path()
            options = webdriver.ChromeOptions()
            options.add_argument('headless')
            driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
            driver_doc.get(page_url)
            resultlist = driver_doc.find_element_by_class_name('resultlist')

            # s1. Results
            for itemlink in resultlist.find_elements_by_class_name('itemlink'):
                time.sleep(2)
                result_link = itemlink.find_element_by_tag_name('a')
                assert result_link
                text_small = itemlink.find_element_by_class_name('text-small')
                assert text_small
                date_str = text_small.text.split(',')[0].strip()
                notice_type = text_small.text.split(',')[1].strip()
                tmp = dateparser.parse(date_str, languages=[self.language_code])
                date = datetime.date(tmp.year, tmp.month, tmp.day)

                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    continue
                # s2. Documents
                h2 = result_link.find_element_by_class_name('h3')
                assert h2
                document_title = h2.text.strip()

                document_hash = hashlib.md5(document_title.encode()).hexdigest()
                hashcode_with_type = document_hash + '-' + notice_type

                # check whether this articles already exist
                if hashcode_with_type in hashcode_dict.keys() and hashcode_dict[hashcode_with_type] == date:
                    if to_print:
                        print('\tAlready exist, skip:\t', document_hash)
                    continue

                print('document_title:\t', document_title)
                print('\tdate:\t', date)
                document_href = result_link.get_attribute('href')
                assert document_href
                host = "https://ico.org.uk"
                document_url = host + document_href
                print('\tdocument_url:\t', document_url)
                if to_print:
                    print("\tDocument:\t", document_hash)
                document_response = None
                try:
                    document_response = requests.request('GET', document_url)
                    document_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    pass
                except requests.exceptions.ConnectionError as error:
                    if to_print:
                        print("\tError:", error)
                    pass
                if document_response is None:
                    continue

                dpa_folder = self.path
                if document_hash in existed_docs:
                    document_folder = dpa_folder + '/' + 'Enforcements' + '/' + document_hash + ' -02'
                else:
                    document_folder = dpa_folder + '/' + 'Enforcements' + '/' + document_hash
                try:
                    os.makedirs(document_folder)

                    document_soup = BeautifulSoup(document_response.text, 'html.parser')
                    assert document_soup
                    article_content = document_soup.find_all('div', class_='article-content')
                    if article_content is not None:
                        document_text = ''
                        for i in article_content:
                            document_text += i.get_text()
                        with open(document_folder + '/' + self.language_code + '-' + 'article_content' + '.txt', 'w') as f:
                            f.write(document_text)
                    aside_further = document_soup.find('aside', class_='aside-further')
                    if aside_further is not None:
                        #count_articles = 0
                        count = 0
                        for articles in aside_further.find_all('li'):
                            title = articles.find('h3').get_text()
                            print("\t\tfile_title: ", title)
                            article_url = articles.find('a').get('href')
                            if article_url is not None:
                                file_url = host + article_url
                                print("\t\tfile_url: ", file_url)
                                file_response = None
                                try:
                                    file_response = requests.request('GET', file_url)
                                    file_response.raise_for_status()
                                except requests.exceptions.HTTPError as error:
                                    if to_print:
                                        print(error)
                                    pass
                                except requests.exceptions.ConnectionError as error:
                                    if to_print:
                                        print("\tError:",error)
                                    pass
                                if file_response is None:
                                    continue
                                # the current notice pdf page
                                if file_url.endswith('.pdf'):
                                    count += 1
                                    if count == 2:
                                        print("This is pdf file with another notice type")
                                        continue
                                    file_content = file_response.content
                                    with open(document_folder + '/' + self.language_code + '-' + notice_type + '.pdf',
                                            'wb') as f:
                                        f.write(file_content)
                                    with open(document_folder + '/' + self.language_code + '-' + notice_type + '.txt',
                                            'wb') as f:
                                        document_text = textract.process(
                                            document_folder + '/' + self.language_code + '-' + notice_type + '.pdf')
                                        f.write(document_text)
                                elif file_url.endswith('.docx'):
                                    # set a download path. Use selenium to download it
                                    exec_path = WebdriverExecPolicy().get_system_path()
                                    options = webdriver.ChromeOptions()
                                    prefs = {"download.default_directory": document_folder}
                                    options.add_argument('headless')
                                    options.add_experimental_option("prefs", prefs)
                                    driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                                    # open google search, and put the document_url into search box, and press enter

                                    driver_doc.get(document_url)
                                    button = driver_doc.find_element_by_xpath('//*[@id="startcontent"]/article/div[2]/div/aside/ul/li[1]/a')
                                    button.click()
                                    time.sleep(5)
                                    files = os.listdir(document_folder)
                                    for index, file in enumerate(files):
                                        if 'penalty' in os.path.basename(file):
                                            os.rename(os.path.join(document_folder, file), os.path.join(document_folder, self.language_code + '-' + 'final-penalty' + '.docx'))
                                        document_content = docx2txt.process(document_folder + '/' + self.language_code + '-' + 'final-penalty' + '.docx')
                                        with open(
                                                document_folder + '/' + self.language_code + '-' + 'final-penalty' + '.txt','w') as f:
                                            f.write(document_content)
                                else:
                                    file_soup = BeautifulSoup(file_response.text, 'html.parser')
                                    assert file_soup
                                    maincolumn = file_soup.find('div', class_='maincolumn column column-8')
                                    aside_further = maincolumn.find('aside', class_='aside-further')
                                    # only has the news
                                    if aside_further is None:
                                        file_content = maincolumn.find('div', class_='article-content')
                                        file_text = file_content.get_text()
                                        with open(
                                                document_folder + '/' + self.language_code + '-' + 'news' + '.txt',
                                                'w') as f:
                                            f.write(file_text)
                                    else:
                                        continue

                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: document_title
                            },
                            'md5': document_hash,
                            'releaseDate': date.strftime('%d/%m/%Y'),
                            'url': document_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True)
                    existed_docs.append(document_hash)
                    existed_dates.append(date)
                    hashcode_dict[hashcode_with_type] = date
                    print('\n')
                except FileExistsError:
                    print("\tDirectory path already exists, continue.")
            # s0. Pagination
            pagination = self.update_pagination(pagination=pagination, page_soup=results_soup)
        return existed_docs
