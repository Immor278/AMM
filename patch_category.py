from yapsy.IPlugin import IPlugin

import packer


class IBasePatcher(IPlugin):
    def __init__(self):
        super().__init__()

    def patch(self, patch_info: packer.Packer):
        raise "not implemented"
