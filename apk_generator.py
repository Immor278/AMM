import argparse
import json
import logging
import multiprocessing
import os
import random
import shutil
import time
from itertools import repeat
from typing import List

import packer
import util
from patcher_manager import PatcherManager
from patchers.api_patcher import ApiPatcher
from patchers.manifest_packer import ManifestPatcher
from patchers.string_packer import StringPatcher
from patchers.rebuild import Rebuild
from tool import Apktool, Jarsigner, Zipalign

if "LOG_LEVEL" in os.environ:
    log_level = os.environ["LOG_LEVEL"]
else:
    # By default log only the error messages.
    log_level = logging.INFO

# For the plugin system log only the error messages and ignore the log level set by
# the user.
logging.getLogger("yapsy").level = log_level

# Logging configuration.
logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s> [%(levelname)s][%(name)s][%(funcName)s()] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    level=log_level,
)


def check_external_tool_dependencies():
    """
    Make sure all the external needed tools are available and ready to be used.
    """
    # APKTOOL_PATH, JARSIGNER_PATH and ZIPALIGN_PATH environment variables can be
    # used to specify the location of the external tools (make sure they have the
    # execute permission). If there is a problem with any of the executables below,
    # an exception will be thrown by the corresponding constructor.
    logger.debug("Checking external tool dependencies")
    Apktool()
    Jarsigner()
    Zipalign()


def perform_patching(
        input_apk_path: str,
        feature_patch_path: str,
        working_dir_path: str = None,
        obfuscated_apk_path: str = None,
        ignore_libs: bool = False,
        interactive: bool = False,
        keystore_file: str = None,
        keystore_password: str = None,
        key_alias: str = None,
        key_password: str = None,
        ignore_packages_file: str = None,
):
    """
    Apply the obfuscation techniques to an input application and generate an obfuscated
    apk file.

    :param input_apk_path: The path to the input application file to obfuscate.
    :param feature_patch_path: The path to the feature patch file
    :param working_dir_path: The working directory where to store the intermediate
                             files. By default a directory will be created in the same
                             directory as the input application. If the specified
                             directory doesn't exist, it will be created.
    :param obfuscated_apk_path: The path where to save the obfuscated apk file. By
                                default the file will be saved in the working directory.
    :param ignore_libs: If True, exclude known third party libraries from the
                        obfuscation operations.
    :param interactive: If True, show a progress bar with the obfuscation progress.
    :param keystore_file: The path to a custom keystore file to be used for signing the
                          resulting obfuscated application. If not provided, a default
                          keystore bundled with this tool will be used instead.
    :param keystore_password: The password of the custom keystore used for signing the
                              resulting obfuscated application (needed only when
                              specifying a custom keystore file).
    :param key_alias: The key alias for signing the resulting obfuscated application
                      (needed only when specifying a custom keystore file).
    :param key_password: The key password for signing the resulting obfuscated
                         application (needed only when specifying a custom keystore
                         file).
    :param ignore_packages_file: The file containing the package names to be ignored
                                 during the obfuscation (one package name per line).
    """

    check_external_tool_dependencies()

    if not os.path.isfile(input_apk_path):
        logger.critical('Unable to find application file "{0}"'.format(input_apk_path))
        raise FileNotFoundError(
            'Unable to find application file "{0}"'.format(input_apk_path)
        )

    if os.path.isdir(obfuscated_apk_path):
        obfuscated_apk_path = os.path.join(obfuscated_apk_path, os.path.split(input_apk_path)[-1] + '_pack.apk')

    # skip existed apk
    if os.path.exists(obfuscated_apk_path):
        return

    feature_patches = []

    # # test
    # for index in range(10):
    #     strPtch = packer.PatchFeature()
    #     strPtch.name = "activity::testurl" + str(index)
    #     strPtch.value = 1
    #     strPtch.type = packer.FeatureType.MANIFEST
    #     feature_patches.append(strPtch)

    with open(feature_patch_path, 'r') as file:
        jsonObj = json.load(file)
        for key in jsonObj:
            value = jsonObj[key]
            feature = packer.PatchFeature()
            feature.name = key
            feature.value = value
            if "api_call::" in key or "call::" in key or 'real_permission::' in key:
                feature.type = packer.FeatureType.API
            elif "url::" in key or "su_call::" in key:
                feature.type = packer.FeatureType.STRING
            else:
                feature.type = packer.FeatureType.MANIFEST


    pack = packer.Packer(
        input_apk_path,
        feature_patches,
        working_dir_path,
        obfuscated_apk_path,
        ignore_libs,
        interactive,
        keystore_file,
        keystore_password,
        key_alias,
        key_password,
        ignore_packages_file,
    )

    try:
        pack.decode_apk()
        ApiPatcher().patch(pack)
        ManifestPatcher().patch(pack)
        StringPatcher().patch(pack)
        Rebuild().patch(pack)
    except:
        print('failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Multi-thread Obfuscating generation tool. Only support in non-Windows system. "
                    "This tools should be placed and run in src directory of obfuscapk")
    parser.add_argument('path', metavar='APK_path', type=str,
                        help='Directory containing APK files')
    parser.add_argument('-f', metavar='feature_patch_file', type=str,
                        help='Feature Patch json file')
    parser.add_argument('-o', metavar='output_dir', type=str,
                        help='Output Directory. Default "outdir"', default='outdir')
    parser.add_argument('-n', metavar='parallel_number', type=int,
                        help='The number of parallel works, default is the number of CPU cores', default=8)

    args = parser.parse_args()
    number = args.n
    path: str = args.path
    output: str = args.o
    feature_file = args.f

    file_list = []
    if os.path.isfile(path):
        file_list.append(path)
    elif os.path.isdir(path):
        for subdir, dirs, files in os.walk(path):
            for filename in files:
                filename = os.path.split(filename)[-1]
                file_list.append(subdir + os.sep + filename)

    work_path = '/tmp/obf_working/' + str(time.time())
    with multiprocessing.Pool(processes=number) as pool:
        pool.starmap(perform_patching, zip(file_list, repeat(feature_file), repeat(work_path), repeat(output)))
