import os
import json
from urllib.parse import urlparse
from pygdpr.models.common.reachability_node import *

path = os.path.abspath('pygdpr/assets/dpa-reachability-info.json')
f = open(path, 'r')
dpa_reachability_info = json.load(f)
f.close()

class BuildDPANodeService:
    def build_dpa_node(self, dpa):
        key = dpa.country_code
        return DPANode(key, dpa)

    def build_source_node(self, dpa):
        pagination = dpa.update_pagination()
        assert (pagination.has_next())
        item = pagination.get_next()
        page_url = None
        page_source = None
        if type(item) == str:
            page_url = item
            page_source = dpa.get_source(page_url=page_url)
            page_source = page_source.text
        else:
            driver = item
            page_url = driver.current_url
            page_source = dpa.get_source(driver=driver)
        if page_source is None:
            return None
        key = urlparse(page_url).path
        return SourceNode(key, page_source)

    def build_label_node(self, label):
        key = label
        return LabelNode(key, label)

    def build_xpath_node(self, xpath):
        key = '.../' + xpath.split('/')[-1]
        return XPathNode(key, xpath)

    def for_dpa(self, dpa):
        dpa_node = self.build_dpa_node(dpa)
        source_node = self.build_source_node(dpa)
        if source_node is None:
            return None
        reachability_info = dpa_reachability_info[dpa.country_code]
        if reachability_info is None:
            dpa_node.set_color(Color.BLACK)
            return dpa_node
        for label, xpaths in reachability_info.items():
            label_node = self.build_label_node(label)
            for xpath in xpaths:
                xpath_node = self.build_xpath_node(xpath)
                label_node.add_child(xpath_node)
            source_node.add_child(label_node)
        dpa_node.add_child(source_node)
        return dpa_node
