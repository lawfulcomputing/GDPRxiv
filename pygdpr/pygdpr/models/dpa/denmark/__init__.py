import os
import math
import time
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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.policies.webdriver_exec_policy import WebdriverExecPolicy
from selenium.common.exceptions import NoSuchElementException

class Denmark(DPA):
    def __init__(self, path=os.curdir):
        country_code='DK'
        super().__init__(country_code, path)

    def update_pagination(self, pagination=None, results_soup=None, driver=None, start_path="Decisions"):
        source = {
            'host': 'https://www.datatilsynet.dk',
            'start_path_Decisions': '/afgoerelser/afgoerelser?page=1',
            "start_path_Permissions": "/afgoerelser/tilladelser?page=1"
        }
        host = source['host']
        if start_path != "Decisions":
            start_path = source['start_path_Permissions']
        else:
            start_path = source['start_path_Decisions']
        page_url = ""
        if pagination is None:
            page_url = host + start_path
        else:
            pagination = driver.find_element_by_class_name('pagination')
            try:
                item = pagination.find_element_by_class_name("next")
                if item is not None:
                    page_url = item.get_attribute("href")
                    assert page_url

                    # there is a bug in Denmark websides: the next page button has a wrong href link
                    # so we replace it to the correct link
                    current_page = page_url
                    page_string = current_page.split('&PageNumber=')
                    if page_string[0][-2].isdigit():
                        page_url = page_string[0][:-2] + page_string[1]
                    else:
                        page_url = page_string[0][:-1]+page_string[1]
            except NoSuchElementException:
                pass

        if len(page_url) != 0:
            exec_path = WebdriverExecPolicy().get_system_path()
            options = webdriver.ChromeOptions()
            options.add_argument('headless')
            driver = webdriver.Chrome(options=options, executable_path=exec_path)
            driver.get(page_url)
            pagination = Pagination()
            pagination.add_item(driver)
        return pagination

    def get_source(self, page_url=None, driver=None):
        assert (driver is not None)
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located(
                (By.CLASS_NAME, 'archive-search-result')
            ))
            WebDriverWait(driver, 10).until(EC.presence_of_element_located(
                (By.CLASS_NAME, 'items')
            ))
        except:
            return None
        page_source = driver.page_source
        return page_source

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        # call all the get_docs_X() functions
        added_docs += self.get_docs_Decisions_1(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Decisions_2(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Permissions(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_AnnualReports(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    # add all the decision documents
    def get_docs_Decisions(self, existing_docs=[], overwrite=False, to_print=True):
        added_docs = []
        added_docs += self.get_docs_Decisions_1(existing_docs=[], overwrite=False, to_print=True)
        added_docs += self.get_docs_Decisions_2(existing_docs=[], overwrite=False, to_print=True)
        return added_docs

    def get_docs_Decisions_1(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        dict_hashcode = {}
        page_list = []
        print("\n========================= Denmark Decisions_1 Documents ===========================")
        # s0. Pagination
        try:
            pagination = self.update_pagination()
            while pagination.has_next():
                driver = pagination.get_next()
                page_number = ''
                if to_print:
                    current_url = driver.current_url
                    print('Page:\t', current_url)
                    for i in current_url:
                        if i.isdigit():
                            page_number += i

                if page_number in page_list:
                    continue
                #print('page_number: ', page_number)
                exec_path = WebdriverExecPolicy().get_system_path()
                options = webdriver.ChromeOptions()
                options.add_argument('headless')
                driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                driver_doc.get(current_url)
                ajaxhost = driver.find_element_by_class_name("ajaxhost")
                if "No results found" in ajaxhost.text:
                    return existed_docs
                items = ajaxhost.find_element_by_class_name("items")
                item_list = items.find_elements_by_class_name("item")
                for i in range(len(item_list)):
                    # date
                    date_str = item_list[i].find_element_by_class_name('date').text
                    assert date_str
                    date_str = date_str.strip().split(' ')[-1]
                    #print('date_str: ', date_str)
                    tmp = datetime.datetime.strptime(date_str, '%d-%m-%Y')
                    date = datetime.date(tmp.year, tmp.month, tmp.day)
                    print("\tdate: ", date)
                    if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                        print('\tNo satisfied by date\t', date)
                        continue
                    # document
                    i += 1
                    document = items.find_element_by_xpath('//*[@id="ContentPlaceHolderDefault_searchResult"]/div[2]/div/div/div['+str(i)+']/div/h2/a')
                    assert document
                    document_url = document.get_attribute("href")
                    assert document_url
                    print("document_url: ", document_url)
                    document_title = document.text
                    document_hash = hashlib.md5(document_title.encode()).hexdigest()

                    if document_hash in existing_docs and overwrite == False:
                        if to_print:
                            print('\tSkipping existing document:\t', document_hash)
                        continue
                    if document_hash in dict_hashcode.keys() and dict_hashcode[document_hash] == date:
                        if date_str == '17-05-2018':
                            print ('\t Last document')
                            return existed_docs
                        print('\tSkipping existing document:\t', document_hash)
                        continue
                    if document_hash in dict_hashcode:
                        # documents have the same hashcode, but different dates
                        document_hash = document_hash + '-' + date_str
                    dpa_folder = self.path
                    document_folder = dpa_folder + '/' + 'Decisions' + '/' + document_hash
                    try:
                        os.makedirs(document_folder)
                        print('\tdocument_title: ', document_title)
                        exec_path = WebdriverExecPolicy().get_system_path()
                        options = webdriver.ChromeOptions()
                        options.add_argument('headless')
                        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                        driver_doc.get(document_url)
                        document_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')
                        assert document_soup
                        WebDriverWait(driver_doc, 15).until(EC.presence_of_element_located(
                            (By.CLASS_NAME, 'news-page')
                        ))
                        #print("made it thus far to news_page")
                        news_page = document_soup.find('div', class_='news-page')
                        assert news_page
                        document_text = news_page.get_text()
                        document_text = document_text.lstrip()

                        #print("writing to the directory:", document_folder)
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
                        dict_hashcode[document_hash] = date
                        existed_docs.append(document_hash)

                    except FileExistsError:
                        print("Directory path already exists, continue.")
                page_list.append(page_number)
                pagination = self.update_pagination(pagination=pagination, driver=driver)
        except AttributeError:
            print('no more documents')
        return existed_docs

    def get_docs_Decisions_2(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        source = {
            "host": "https://www.datatilsynet.dk",
            "start_path": "/afgoerelser/boedesager"
        }
        host = source['host']
        start_path = source['start_path']
        source_url = host + start_path
        results_response = requests.request('GET', source_url)
        results_content = results_response.content
        results_soup = BeautifulSoup(results_content, 'html.parser')
        web_page = results_soup.find('div', class_='web-page')
        rich_text = web_page.find('div', class_='rich-text')
        print("\n========================= Denmark Decisions_2 Documents ===========================")

        for li in rich_text.find('ul').find_all('li'):
            time.sleep(2)
            document_href = li.find('a').get('href')
            # print("document_href: ", document_href)
            document_url = host + document_href
            assert document_url
            exec_path = WebdriverExecPolicy().get_system_path()
            options = webdriver.ChromeOptions()
            options.add_argument('headless')
            driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
            driver_doc.get(document_url)
            content = driver_doc.find_element_by_xpath('//*[@id="wrapper"]/div/div[3]/div/div/div[2]/div/div[1]/div')
            if content is None:
                print('\tno content')
                continue
            document_title = content.find_element_by_class_name('heading')
            document_title = document_title.text.strip()
            document_hash = hashlib.md5(document_title.encode()).hexdigest()
            if document_hash in existing_docs and overwrite == False:
                if to_print:
                    print('\tSkipping existing document:\t', document_hash)
                continue
            dpa_folder = self.path
            document_folder = dpa_folder + '/' + 'Decisions_2' + '/' + document_hash
            try:
                os.makedirs(document_folder)
                print("document_title: ", document_title)
                print("\tdocument_hash: ", document_hash)
                date_str = content.find_element_by_class_name('date').text
                date_str = date_str.strip().split(' ')[-1]
                tmp = datetime.datetime.strptime(date_str, '%d-%m-%Y')
                date = datetime.date(tmp.year, tmp.month, tmp.day)
                if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                    print('\tNo satisfied by date\t', date)
                    continue
                print("\tdocument_url: ", document_url)

                document_text = content.text
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
                existed_docs.append(document_hash)
            except FileExistsError:
                print('Directory path already exists, continue.')
        return existed_docs


    def get_docs_Permissions(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        dict_hashcode = {}
        page_list = []
        print("\n========================= Denmark Permissions Documents ===========================")
        # s0. Pagination
        pagination = self.update_pagination(start_path = "Permissions")
        try:
            while pagination.has_next():
                driver = pagination.get_next()
                page_number = ''
                if to_print:
                    current_url = driver.current_url
                    print('Page:\t', current_url)
                    for i in current_url:
                        if i.isdigit():
                            page_number += i
                if page_number in page_list:
                    continue
                #print('page_number: ', page_number)
                exec_path = WebdriverExecPolicy().get_system_path()
                options = webdriver.ChromeOptions()
                options.add_argument('headless')
                driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                driver_doc.get(current_url)
                ajaxhost = driver.find_element_by_class_name("ajaxhost")
                if "No results found" in ajaxhost.text:
                    return existed_docs
                items = ajaxhost.find_element_by_class_name("items")
                item_list = items.find_elements_by_class_name("item")
                # print('len of item: ', len(item_list))
                for i in range(len(item_list)):
                    # date
                    date_str = item_list[i].find_element_by_class_name('date').text
                    assert date_str
                    date_str = date_str.strip().split(' ')[-1]
                    # print('date_str: ', date_str)
                    tmp = datetime.datetime.strptime(date_str, '%d-%m-%Y')
                    date = datetime.date(tmp.year, tmp.month, tmp.day)
                    # print("\tdate: ", date)
                    if ShouldRetainDocumentSpecification().is_satisfied_by(date) is False:
                        print('\tNot satisfied by date:\t', date)
                        continue
                    # document
                    i += 1
                    document = items.find_element_by_xpath('//*[@id="ContentPlaceHolderDefault_searchResult"]/div[2]/div/div/div['+str(i)+']/div/h2/a')
                    assert document
                    document_url = document.get_attribute("href")
                    assert document_url
                    print("document_url: ", document_url)
                    document_title = document.text
                    document_hash = hashlib.md5(document_title.encode()).hexdigest()

                    if document_hash in existing_docs and overwrite == False:
                        if to_print:
                            print('\tSkipping existing document:\t', document_title)
                        continue
                    if document_hash in dict_hashcode and dict_hashcode[document_hash] == date:
                        print('\tSkipping existing document:\t', document_title)
                        continue
                    if document_hash in dict_hashcode:
                        # documents have the same hashcode, but different dates
                        document_hash = document_hash + '-' + date_str

                    dpa_folder = self.path
                    document_folder = dpa_folder + '/' + 'Permissions' + '/' + document_hash
                    try:
                        os.makedirs(document_folder)
                        print('\tdocument_title: ', document_title)
                        exec_path = WebdriverExecPolicy().get_system_path()
                        options = webdriver.ChromeOptions()
                        options.add_argument('headless')
                        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
                        driver_doc.get(document_url)
                        document_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')
                        assert document_soup
                        WebDriverWait(driver_doc, 15).until(EC.presence_of_element_located(
                            (By.CLASS_NAME, 'news-page')
                        ))
                        #print("made it thus far to news_page")
                        news_page = document_soup.find('div', class_='news-page')
                        assert news_page
                        document_text = news_page.get_text()
                        document_text = document_text.lstrip()

                        #print("writing to the directory:", document_folder)
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
                        existed_docs.append(document_hash)
                        dict_hashcode[document_hash] = date
                    except FileExistsError:
                        print("Directory path already exists, continue.")
                page_list.append(page_number)
                pagination = self.update_pagination(pagination=pagination, driver=driver, start_path="Permissions")
        except AttributeError:
            print('no more documents')
        return existed_docs

    # Method not complete, should implement later
    def get_docs_Guides(self, existing_docs=[], overwrite=False, to_print=True):
        existed_docs = []
        dict_hashcode = {}
        page_list = []
        source = {
            'host': 'https://www.datatilsynet.dk',
            'start_path': '/hvad-siger-reglerne/vejledning'
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        exec_path = WebdriverExecPolicy().get_system_path()
        options = webdriver.ChromeOptions()
        options.add_argument('headless')
        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
        driver_doc.get(page_url)
        document_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')
        assert document_soup
        WebDriverWait(driver_doc, 15).until(EC.presence_of_element_located(
            (By.CLASS_NAME, 'container')
        ))
        for div in document_soup.find_all('div', class_='span-4'):
            document = div.find('h2', class_='heading')
            document_href = document.find('a').get('href')
            document_url = host + document_href
            print('document_href: ', document_url)
            document_title = document.find('a').get_text()
            print('document_title: ', document_title)

            exec_path = WebdriverExecPolicy().get_system_path()
            options = webdriver.ChromeOptions()
            options.add_argument('headless')
            driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
            driver_doc.get(document_url)
            article_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')
            assert article_soup
            WebDriverWait(driver_doc, 15).until(EC.presence_of_element_located(
                (By.CLASS_NAME, 'container')
            ))

            for div in article_soup.find_all('div', class_='module multi-box bg-color-c card'):
                text = div.find('div', class_='text')
                article_href = text.find('a').get('href')
                article_url = host + article_href
                article_title = text.find('a').get_text()
                print('\tarticle_url\t ', article_url)
                print('\tarticle_title\t ', article_title)
                article_hash = hashlib.md5(article_title.encode()).hexdigest()
                # add date
                if article_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', article_title)
                    continue
                #if article_hash in dict_hashcode and dict_hashcode[article_hash] == date:
                #    print('\tSkipping existing document:\t', document_title)
                #    continue
        return existed_docs

    def get_docs_AnnualReports(self, existing_docs=[], overwrite=False, to_print=True):
        print("\n========================= Denmark Annual Reports ===========================")
        existed_docs = []
        source = {
            'host': 'https://www.datatilsynet.dk',
            'start_path': '/om-datatilsynet/aarsberetninger-og-aarsrapporter'
        }
        host = source['host']
        start_path = source['start_path']
        page_url = host + start_path
        exec_path = WebdriverExecPolicy().get_system_path()
        options = webdriver.ChromeOptions()
        options.add_argument('headless')
        driver_doc = webdriver.Chrome(options=options, executable_path=exec_path)
        driver_doc.get(page_url)
        document_soup = BeautifulSoup(driver_doc.page_source, 'html.parser')
        assert document_soup
        WebDriverWait(driver_doc, 15).until(EC.presence_of_element_located(
            (By.CLASS_NAME, 'container')
        ))
        for div in document_soup.find_all('div', class_='module link-list card drop-down'):
            for option in div.find_all('option'):
                text = option.get_text().strip('\n')
                year = option.get_text()
                if not text.isdigit():
                    continue
                elif int(year) < 2018:
                    continue
                #print('year: ', year)
                article_href = option.get('data-href')
                article_url = host + article_href
                print('article_url: ', article_url)
                article_title = article_href.split('/')[-1]
                print('article_title: ', article_title)
                article_hash = hashlib.md5(article_title.encode()).hexdigest()
                if article_hash in existing_docs and overwrite == False:
                    if to_print:
                        print('\tSkipping existing document:\t', document_title)
                try:
                    article_response = requests.request('GET', article_url)
                    article_response.raise_for_status()
                except requests.exceptions.HTTPError as error:
                    if to_print:
                        print(error)
                    pass
                dpa_folder = self.path
                document_folder = dpa_folder + '/' + 'Annual Reports' + '/' + article_hash
                # document_folder = dpa_folder + '/denmark' + '/' + 'Annual Reports' + '/' + article_hash
                try:
                    os.makedirs(document_folder)
                    if article_response is None:
                        continue
                    article_content = article_response.content
                    with open(document_folder + '/' + self.language_code + '.pdf', 'wb') as f:
                        f.write(article_content)
                    with open(document_folder + '/' + self.language_code + '.txt', 'w') as f:
                        document_text = PDFToTextService().text_from_pdf_path(
                            document_folder + '/' + self.language_code + '.pdf')
                        f.write(document_text)
                    with open(document_folder + '/' + 'metadata.json', 'w') as f:
                        metadata = {
                            'title': {
                                self.language_code: article_title
                            },
                            'md5': article_hash,
                            'releaseDate': year,
                            'url': article_url
                        }
                        json.dump(metadata, f, indent=4, sort_keys=True, ensure_ascii=False)
                    existed_docs.append(article_hash)
                except FileExistsError:
                    print("Directory path already exists, continue.")
        return existed_docs
