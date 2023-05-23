from lxml import html, etree
from lxml.etree import XPathEvalError
from pygdpr.models.common.reachability_node import Color
from pygdpr.specifications.reachable_node_specification import ReachableNodeSpecification
import os

class ReachabilityAnalysisService:
    def propagate_color(self, node):
        reachable_node = ReachableNodeSpecification()
        is_reachable = reachable_node.is_satisfied_by(node)
        if is_reachable:
            node.set_color(Color.BLACK)
        else:
            node.set_color(Color.WHITE)
        return node

    def analyze_gdpr_node(self, gdpr_node):
        gdpr_node.set_color(Color.GREY)
        for dpa_node in gdpr_node.get_children():
            self.analyze_dpa_node(dpa_node)
        gdpr_node = self.propagate_color(gdpr_node)
        return gdpr_node

    def analyze_dpa_node(self, dpa_node):
        dpa_node.set_color(Color.GREY)
        for source_node in dpa_node.get_children():
            self.analyze_source_node(source_node)
        dpa_node = self.propagate_color(dpa_node)
        return dpa_node

    def analyze_source_node(self, source_node):
        source_node.set_color(Color.GREY)
        page_source = source_node.source
        source_html = html.fromstring(page_source.encode())
        for label_node in source_node.get_children():
            self.analyze_label_node(source_html, label_node)
        source_node = self.propagate_color(source_node)
        return source_node

    def analyze_label_node(self, source_html, label_node):
        label_node.set_color(Color.GREY)
        for xpath_node in label_node.get_children():
            self.analyze_xpath_node(source_html, xpath_node)
        label_node = self.propagate_color(label_node)
        return label_node

    def analyze_xpath_node(self, source_html, xpath_node):
        xpath_node.set_color(Color.GREY)
        xpath = xpath_node.xpath
        try:
            elements = source_html.xpath(xpath)
            color = Color.BLACK if len(elements) > 0 else Color.WHITE
            xpath_node.set_color(color)
        except XPathEvalError:
            xpath_node.set_color(Color.WHITE)
        return xpath_node

    def perform_analysis(self, node):
        if node.get_color() == Color.BLACK:
            return node

        classname = node.__class__.__name__
        if classname == 'GDPRNode':
            return self.analyze_gdpr_node(node)
        elif classname == 'DPANode':
            return self.analyze_dpa_node(node)
        else:
            raise ValueError(f"The subclass {classname} is not supported, only GDPRNode and DPANode")
        return None
