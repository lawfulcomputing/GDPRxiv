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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pygdpr.models.dpa.germany.dpa.federal_DPA import FederalDPA
from pygdpr.models.dpa.germany.dpa.baden_wurttemberg import BadenWurttemberg
from pygdpr.models.dpa.germany.dpa.bavaria_privatesector import Bavaria_PrivateSector
from pygdpr.models.dpa.germany.dpa.bavaria_publicsector import Bavaria_PublicSector
from pygdpr.models.dpa.germany.dpa.berlin import Berlin
from pygdpr.models.dpa.germany.dpa.brandenburg import Brandenburg
from pygdpr.models.dpa.germany.dpa.bremen import Bremen
from pygdpr.models.dpa.germany.dpa.hamburg import Hamburg
from pygdpr.models.dpa.germany.dpa.hessen import Hessen
from pygdpr.models.dpa.germany.dpa.mecklenburg_vorpommern import MecklenburgVorpommern
from pygdpr.models.dpa.germany.dpa.lower_saxony import LowerSaxony
from pygdpr.models.dpa.germany.dpa.rhineland_palatinate import RhinelandPalatinate
from pygdpr.models.dpa.germany.dpa.saarland import Saarland
from pygdpr.models.dpa.germany.dpa.saxony import Saxony
from pygdpr.models.dpa.germany.dpa.saxony_anhalt import SaxonyAnhalt
from pygdpr.models.dpa.germany.dpa.schleswig_holstein import SchleswigHolstein
from pygdpr.models.dpa.germany.dpa.thuringia import Thuringia


class Germany(DPA):
    def __init__(self, path=os.curdir):
        country_code='de'
        super().__init__(country_code, path)

    def get_docs(self, existing_docs=[], overwrite=False, to_print=True):
        print('docs - dpa germany')
        added_docs = []
        added_docs += FederalDPA().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += BadenWurttemberg().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Bavaria_PrivateSector().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Bavaria_PublicSector().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Berlin().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Brandenburg().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Bremen().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Hamburg().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Hessen().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += MecklenburgVorpommern().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += LowerSaxony().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += RhinelandPalatinate().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Saarland().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Saxony().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += SaxonyAnhalt().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += SchleswigHolstein().get_docs(overwrite=False, to_print=True, path=self.path)
        added_docs += Thuringia().get_docs(overwrite=False, to_print=True, path=self.path)
        return added_docs
