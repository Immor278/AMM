import os

from yapsy.PluginManager import PluginManager

import patch_category


class PatcherManager:
    def __init__(self):
        self.manager = PluginManager(
            directories_list=[
                os.path.join(os.path.dirname(os.path.realpath(__file__)), "patchers")
            ],
            plugin_info_ext="patchers",
            categories_filter={
                "Patcher": patch_category.IBasePatcher,
            },
        )
        self.manager.collectPlugins()

    def get_all_patchers(self):
        return self.manager.getAllPlugins()

    def get_patchers_names(self):
        return [
            ob.name
            for ob in sorted(
                self.get_all_patchers(), key=lambda x: (x.category, x.name)
            )
        ]