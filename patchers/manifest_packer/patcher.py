import logging
import random

import packer
from patch_category import IBasePatcher
import xml.etree.cElementTree as Xml
from xml.etree.cElementTree import Element


class ManifestPatcher(IBasePatcher):
    def __init__(self):
        self.logger = logging.getLogger(
            "{0}.{1}".format(__name__, self.__class__.__name__)
        )
        super().__init__()

    def patch(self, patch_info: packer.Packer):

        # only considering to add permission
        add_permission = []

        for item in patch_info.features:
            item: packer.PatchFeature = item
            if item.type != packer.FeatureType.MANIFEST:
                continue
            if item.value > 0.5:
                add_permission.append(item)

        self.__add_permissions(add_permission, patch_info)

    def __add_permissions(self, perms: [packer.PatchFeature], patch_info: packer.Packer):
        if len(perms) == 0:
            return
        try:
            # Change default namespace.
            Xml.register_namespace(
                "obfuscation", "http://schemas.android.com/apk/res/android"
            )

            xml_parser = Xml.XMLParser(encoding="utf-8")
            manifest_tree = Xml.parse(
                patch_info.get_manifest_file(), parser=xml_parser
            )
            manifest_root = manifest_tree.getroot()
            self.insert_manifest(manifest_root, perms)
            self.remove_xml_duplicates(manifest_root)  # TODO remove duplicated
            self.scramble_xml_element(manifest_root)
            self.indent_xml(manifest_root)

            # Write the changes into the manifest file.
            manifest_tree.write(patch_info.get_manifest_file(), encoding="utf-8")

        except Exception as e:
            self.logger.error(
                'Error during execution of "{0}" obfuscator: {1}'.format(
                    self.__class__.__name__, e
                )
            )
            raise

    # http://effbot.org/zone/element-lib.htm#prettyprint
    def indent_xml(self, element: Element, level=0):
        indentation = "\n" + level * "    "
        if len(element):
            if not element.text or not element.text.strip():
                element.text = indentation + "    "
            if not element.tail or not element.tail.strip():
                element.tail = indentation
            for element in element:
                self.indent_xml(element, level + 1)
            if not element.tail or not element.tail.strip():
                element.tail = indentation
        else:
            if level and (not element.tail or not element.tail.strip()):
                element.tail = indentation

    # https://stackoverflow.com/a/27550126/5268548
    def xml_elements_equal(self, one: Element, other: Element) -> bool:
        if type(one) != type(other):
            return False
        if one.tag != other.tag:
            return False

        if one.text and other.text:
            if one.text.strip() != other.text.strip():
                return False
        elif one.text != other.text:
            return False

        if one.tail and other.tail:
            if one.tail.strip() != other.tail.strip():
                return False
        elif one.tail != other.tail:
            return False

        if one.attrib != other.attrib:
            return False
        if len(one) != len(other):
            return False

        return all(self.xml_elements_equal(e1, e2) for e1, e2 in zip(one, other))

    def remove_xml_duplicates(self, root: Element):

        # Recursively eliminate duplicates starting from children nodes.
        for element in root:
            self.remove_xml_duplicates(element)

        non_duplicates = []
        elements_to_remove = []

        # Find duplicate nodes which have the same parent node.
        for element in root:
            if any(self.xml_elements_equal(element, nd) for nd in non_duplicates):
                elements_to_remove.append(element)
            else:
                non_duplicates.append(element)

        # Remove existing duplicates at this level.
        for element_to_remove in elements_to_remove:
            root.remove(element_to_remove)

    def scramble_xml_element(self, element: Element):
        children = []

        # Get the children of the current element.
        for child in element:
            children.append(child)

        # Remove the children from the current element (they will be added later
        # in a different order).
        for child in children:
            element.remove(child)

        # Shuffle the order of the children of the element and add them again to
        # the element. Then repeat the scramble operation recursively.
        random.shuffle(children)
        for child in children:
            element.append(child)
            self.scramble_xml_element(child)

    def insert_manifest(self, element: Element, perms: [packer.PatchFeature]):
        def make_permission(_name, root: Element):
            ele = Xml.SubElement(root, 'uses-permission')
            ele.set('obfuscation:name', _name)
            return ele

        def make_feature(_name, root: Element):
            ele = Xml.SubElement(root, 'uses-feature')
            ele.set('obfuscation:name', _name)
            ele.set('obfuscation:required', 'true')
            return ele

        def make_provider(_name, root: Element):
            ele = Xml.SubElement(root, "receiver")
            ele.set('obfuscation:name', 'NonExistProvider' + str(random.randint(10, 100)))
            filter = Xml.SubElement(ele, 'intent-filter')
            action = Xml.SubElement(filter, 'action')
            action.set('obfuscation:name', 'android.appwidget.action.APPWIDGET_UPDATE')
            metadata = Xml.SubElement(ele, 'meta-data')
            metadata.set('obfuscation:name', _name)
            return ele

        def make_activity_main_launcher(_name, root: Element):
            ele = Xml.SubElement(root, 'activity')
            ele.set('obfuscation:name', _name)
            filter = Xml.SubElement(ele, 'intent-filter')
            action = Xml.SubElement(filter, 'action')
            action.set('obfuscation:name', 'android.intent.category.launcher')
            action = Xml.SubElement(filter, 'action')
            action.set('obfuscation:name', 'android.intent.action.main')
            return ele

        def make_activity(_name, root: Element):
            ele = Xml.SubElement(root, 'activity')
            ele.set('obfuscation:name', _name)
            return ele

        def make_service(_name, root: Element):
            ele = Xml.SubElement(root, 'service')
            ele.set('obfuscation:name', _name)
            return ele

        def make_receiver(_name, root: Element):
            ele = Xml.SubElement(root, 'receiver')
            ele.set('obfuscation:name', _name)
            return ele

        def make_intent(_name, root: Element):
            filter = Xml.SubElement(root, 'intent-filter')
            action = Xml.SubElement(filter, 'action')
            action.set('obfuscation:name', _name)
            return filter

        application = None
        for item in element.findall("application"):
            application = item
            break
        if application is not None:
            redundant_activity = make_activity("test_activity_sss", application)
            for item in perms:
                type = item.name.split("::")[0]
                name: str = item.name.split("::")[-1]
                name = name.replace('..', '.')
                if "permission" in type:
                    make_permission(name, element)
                elif "activity" in type:
                    make_activity(name, application)
                elif "service" in type:
                    make_service(name, application)
                elif "receiver" in type:
                    make_receiver(name, application)
                elif "provider" in type:
                    make_provider(name, application)
                elif "intent" in type:
                    make_intent('com.google.android.gms.measurement.upload', redundant_activity)
                elif "feature" in type:
                    make_feature(name, element)
