#!/usr/bin/env python3

import logging

import packer
from patch_category import IBasePatcher


class Rebuild(IBasePatcher):
    def __init__(self):
        self.logger = logging.getLogger(
            "{0}.{1}".format(__name__, self.__class__.__name__)
        )
        super().__init__()

    def patch(self, patch_info: packer.Packer):
        self.logger.info('Running "{0}" patcher'.format(self.__class__.__name__))

        try:
            patch_info.build_obfuscated_apk()
        except Exception as e:
            self.logger.error(
                'Error during execution of "{0}" patcher: {1}'.format(
                    self.__class__.__name__, e
                )
            )
            raise

