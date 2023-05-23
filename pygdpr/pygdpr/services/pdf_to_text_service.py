import os
import io
import shutil
#import pytesseract
from pdfminer.converter import TextConverter
from pdfminer.converter import PDFPageAggregator

from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfinterp import PDFResourceManager

from pdfminer.pdfpage import PDFPage
from pdfminer.layout import LTImage, LTFigure

from pdf2image import convert_from_path
from PIL import Image # brew install pillow
from pytesseract import image_to_string # brew install tesseract

from ..specifications.pdf_file_extension_specification import PDFFileExtensionSpecification
from .filename_from_path_service import filename_from_path_service

TMP_PATH = '/tmp'

#pytesseract.pytesseract.tesseract_cmd = r'/usr/local/Cellar/tesseract/4.1.1/bin/tesseract'
class PDFToTextService:
    # subroutine
    def text_from_pdf_images_path(self, path):
        if PDFFileExtensionSpecification().is_satisfied_by(path) is False:
            raise ValueError("path is not of type pdf")

        #pages = convert_from_path(path, 500, poppler_path=r'/usr/local/Cellar/poppler/21.09.0/bin')
        pages = convert_from_path(path, 500)

        if len(pages) == 0:
            return None

        filename = filename_from_path_service(path)
        dirpath = TMP_PATH + '/' + filename

        try:
            os.makedirs(dirpath)
            #os.mkdir(dirpath)
        except FileExistsError:
            print("directory already exists.")

        text = ''
        for i in range(len(pages)):
            im_path = '{path}/{no}.jpg'.format(path=dirpath, no=i)

            page = pages[i]
            page.save(im_path, 'JPEG')

            im = Image.open(im_path)
            text += image_to_string(im, lang='eng')

            if i != len(pages) - 1:
                text += '\n'

        shutil.rmtree(dirpath, ignore_errors=True)

        text = text.strip()
        return text

    def text_from_pdf_path(self, path):
        if PDFFileExtensionSpecification().is_satisfied_by(path) is False:
            raise ValueError("path is not of type pdf")

        resource_manager = PDFResourceManager()
        fake_file_handle = io.StringIO()
        converter = TextConverter(resource_manager, fake_file_handle)
        page_interpreter = PDFPageInterpreter(resource_manager, converter)

        with open(path, 'rb') as fh:
            for page in PDFPage.get_pages(fh,
                                          caching=True,
                                          check_extractable=True):
                page_interpreter.process_page(page)
            text = fake_file_handle.getvalue()

        # close open handles
        converter.close()
        fake_file_handle.close()

        text = text.strip()

        if len(text) == 0:
            text = self.text_from_pdf_images_path(path)

        return text
