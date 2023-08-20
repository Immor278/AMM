import logging
import os
import re
import secrets
import string
import xml.etree.cElementTree as Xml
from binascii import hexlify
from typing import List, Set
from xml.etree.cElementTree import Element
import packer
import util
from patch_category import IBasePatcher
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util.Padding import pad


class StringPatcher(IBasePatcher):
    def __init__(self):
        self.logger = logging.getLogger(
            "{0}.{1}".format(__name__, self.__class__.__name__)
        )
        super().__init__()
        # self.encryption_secret = "APKPatcherAPKPatcherAPKPatcherAP"  # must be 32 chars
        self.encryption_secret = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(32)
        )  # must be 32 chars

    def patch(self, patch_info: packer.Packer):
        self.logger.info('Running "{0}" patcher'.format(self.__class__.__name__))
        add_strings = []
        remove_strings = []
        for item in patch_info.features:
            item: packer.PatchFeature = item
            if item.type != packer.FeatureType.STRING:
                continue
            url = item.name.split("::")[-1]
            if item.value < 0.5:
                remove_strings.append(url)
            else:
                add_strings.append(url)

        # first encrypt strings
        self.__remove_urls(remove_strings, patch_info)
        # then add urls
        self.__add_urls(add_strings, patch_info)

    def _find_main_activity(self, patch_info: packer.Packer):
        namespace = '{http://schemas.android.com/apk/res/android}'
        Xml.register_namespace(
            "android", namespace
        )

        xml_parser = Xml.XMLParser(encoding="utf-8")
        manifest_tree = Xml.parse(
            patch_info.get_manifest_file(), parser=xml_parser
        )
        manifest_root = manifest_tree.getroot()
        application: Element = manifest_root.find("application")
        for activity in application:
            if self.__is_main_activity__(activity):
                activity_name = activity.attrib[namespace + 'name']
                return activity_name
        return ""

    def __is_main_activity__(self, activity: Element):
        namespace = '{http://schemas.android.com/apk/res/android}'
        intent_filter = activity.find("intent-filter")
        if intent_filter is not None:
            action = intent_filter.find('action')
            category = intent_filter.find('category')
            if action is not None and category is not None \
                    and action.attrib[namespace + "name"] == 'android.intent.action.MAIN' \
                    and category.attrib[namespace + "name"] == 'android.intent.category.LAUNCHER':
                return True
        return False

    def __encrypt_string(self, string_to_encrypt: str) -> str:
        # This is needed to remove the escaping added by Python. For example, if we
        # find in smali the instruction const-string v0, "\"message\"" Android will
        # treat it as "message" while in Python it's \"message\", so we need to encrypt
        # "message" and not \"message\" (we have to remove the unnecessary escaping,
        # otherwise the backslashes would by encrypted as part of the string).
        string_to_encrypt = string_to_encrypt.encode(errors="replace").decode(
            "unicode_escape"
        )

        key = PBKDF2(
            password=self.encryption_secret,
            salt=self.encryption_secret.encode(),
            dkLen=32,
            count=128,
        )
        encrypted_string = hexlify(
            AES.new(key=key, mode=AES.MODE_ECB).encrypt(
                pad(string_to_encrypt.encode(errors="replace"), AES.block_size)
            )
        ).decode()
        return encrypted_string

    # add urls into main activity
    def __add_urls(self, urls, patch_info: packer.Packer):
        if len(urls) == 0:
            return

        activity_name = self._find_main_activity(patch_info)
        activity_smali_name = activity_name.replace('.', '/') + '.smali'
        try:
            for smali_file in util.show_list_progress(
                    patch_info.get_smali_files(),
                    interactive=patch_info.interactive,
                    description="Inserting arithmetic computations in smali files",
            ):
                self.logger.debug(
                    'Inserting arithmetic computations in file "{0}"'.format(smali_file)
                )

                if activity_smali_name != '' and activity_smali_name in smali_file:
                    self.__do_add_urls(smali_file, urls)

        except Exception as e:
            self.logger.error(
                'Error during execution of "{0}" obfuscator: {1}'.format(
                    self.__class__.__name__, e
                )
            )
            raise

    def __do_add_urls(self, smali_file, urls):
        try:
            with util.inplace_edit_file(smali_file) as (in_file, out_file):
                editing_method = False

                # adding dummy calls to every method
                for _ in range(0, 20):
                    for line in in_file:
                        if (
                                line.startswith(".method ")
                                and "onCreate" in line
                                and " abstract " not in line
                                and " native " not in line
                                and not editing_method
                        ):
                            # Entering method.
                            out_file.write(line)
                            editing_method = True

                        # elif line.startswith(".end method") and editing_method:
                        elif 'return-void' in line and editing_method:

                            # write logics at the end of the method
                            for url in urls:
                                out_file.write('\n\t sget-object v14, Ljava/lang/System;->out:Ljava/io/PrintStream; \n')
                                out_file.write('\n\t const-string v15, "' + url + '" \n')
                                out_file.write(
                                    '\n\t invoke-virtual {v14, v15}, Ljava/io/PrintStream;->println(Ljava/lang/String;)V \n')

                            out_file.write('\n')

                            # Exiting method.
                            out_file.write(line)
                            editing_method = False

                        else:
                            out_file.write(line)

        except Exception as e:
            self.logger.error(
                'Error during Adding main activity: execution of "{0}" obfuscator: {1}'.format(
                    self.__class__.__name__, e
                )
            )

    def __remove_urls(self, urls, patch_info: packer.Packer):
        if len(urls) == 0:
            return
        encrypted_strings: Set[str] = set()
        try:
            # .field <other_optional_stuff> <string_name>:Ljava/lang/String; =
            # "<string_value>"
            static_string_pattern = re.compile(
                r"\.field.+?static.+?(?P<string_name>\S+?):"
                r'Ljava/lang/String;\s=\s"(?P<string_value>.+)"',
                re.UNICODE,
            )

            for smali_file in util.show_list_progress(
                    patch_info.get_smali_files(),
                    interactive=patch_info.interactive,
                    description="Encrypting constant strings",
            ):
                self.logger.debug(
                    'Encrypting constant strings in file "{0}"'.format(smali_file)
                )

                with open(smali_file, "r", encoding="utf-8") as current_file:
                    lines = current_file.readlines()

                class_name = None

                # Line numbers where a static string is declared.
                static_string_index: List[int] = []

                # Names of the static strings.
                static_string_name: List[str] = []

                # Values of the static strings.
                static_string_value: List[str] = []

                direct_methods_line = -1
                static_constructor_line = -1

                # Line numbers where a constant string is declared.
                string_index: List[int] = []

                # Registers containing the constant strings.
                string_register: List[str] = []

                # Values of the constant strings.
                string_value: List[str] = []

                current_local_count = 0
                for line_number, line in enumerate(lines):

                    if not class_name:
                        class_match = util.class_pattern.match(line)
                        if class_match:
                            class_name = class_match.group("class_name")
                            continue

                    if line.startswith("# direct methods"):
                        direct_methods_line = line_number
                        continue

                    if line.startswith(".method static constructor <clinit>()V"):
                        static_constructor_line = line_number
                        continue

                    static_string_match = static_string_pattern.match(line)
                    if static_string_match and static_string_match.group(
                            "string_value"
                    ):
                        # A static non empty string initialization was found.
                        static_string_index.append(line_number)
                        static_string_name.append(
                            static_string_match.group("string_name")
                        )
                        static_string_value.append(
                            static_string_match.group("string_value")
                        )

                    # We are iterating the lines in order, so each time we enter a
                    # method we'll find the declaration with the number of local
                    # registers available. When we'll encounter a constant string later
                    # in the body of the method, we'll look at its register value and if
                    # it's greater than 15 we won't encrypt it (the invoke instruction
                    # that we need later won't take registers with values greater
                    # than 15).
                    match = util.locals_pattern.match(line)
                    if match:
                        current_local_count = int(match.group("local_count"))
                        continue

                    # If the constant string has a register v0-v15 we can proceed with
                    # the encryption, but if it uses a p<number> register, before
                    # encrypting we have to check if <number> + locals <= 15.
                    string_match = util.const_string_pattern.match(line)
                    if string_match and string_match.group("string"):
                        reg_type = string_match.group("register")[:1]
                        reg_number = int(string_match.group("register")[1:])
                        if (reg_type == "v" and reg_number <= 15) or (
                                reg_type == "p" and reg_number + current_local_count <= 15
                        ):
                            # A non empty string was found in a register <= 15.
                            string_index.append(line_number)
                            string_register.append(string_match.group("register"))
                            string_value.append(string_match.group("string"))

                # Const string encryption.

                for string_number, index in enumerate(string_index):
                    string_name = string_value[string_number]
                    if string_name not in urls:
                        continue
                    lines[index] = (
                        '\tconst-string/jumbo {register}, "{enc_string}"\n'
                        "\n\tinvoke-static {{{register}}}, "
                        "Lcom/decryptstringmanager/DecryptString"
                        ";->decryptString(Ljava/lang/String;)Ljava/lang/String;\n"
                        "\n\tmove-result-object {register}\n".format(
                            register=string_register[string_number],
                            enc_string=self.__encrypt_string(string_name),
                        )
                    )

                    encrypted_strings.add(string_value[string_number])

                # Static string encryption.

                static_string_encryption_code = ""
                for string_number, index in enumerate(static_string_index):
                    # Remove the original initialization.
                    lines[index] = "{0}\n".format(lines[index].split(" = ")[0])
                    string_name = static_string_name[string_number]
                    if string_name not in urls:
                        continue
                    # Initialize the static string from an encrypted string.
                    static_string_encryption_code += (
                        '\tconst-string/jumbo v0, "{enc_string}"\n'
                        "\n\tinvoke-static {{v0}}, "
                        "Lcom/decryptstringmanager/DecryptString"
                        ";->decryptString(Ljava/lang/String;)Ljava/lang/String;\n"
                        "\n\tmove-result-object v0\n"
                        "\n\tsput-object v0, {class_name}->"
                        "{string_name}:Ljava/lang/String;\n\n".format(
                            enc_string=self.__encrypt_string(string_name),
                            class_name=class_name,
                            string_name=string_name,
                        )
                    )

                    encrypted_strings.add(static_string_value[string_number])

                if static_constructor_line != -1:
                    # Add static string encryption to the existing static constructor.
                    local_match = util.locals_pattern.match(
                        lines[static_constructor_line + 1]
                    )
                    if local_match:
                        # At least one register is needed.
                        local_count = int(local_match.group("local_count"))
                        if local_count == 0:
                            lines[static_constructor_line + 1] = "\t.locals 1\n"
                        lines[static_constructor_line + 2] = "\n{0}".format(
                            static_string_encryption_code
                        )
                else:
                    # Add a new static constructor for the static string encryption.
                    if direct_methods_line != -1:
                        new_constructor_line = direct_methods_line
                    else:
                        new_constructor_line = len(lines) - 1

                    lines[new_constructor_line] = (
                        "{original}"
                        ".method static constructor <clinit>()V\n"
                        "\t.locals 1\n\n"
                        "{encryption_code}"
                        "\treturn-void\n"
                        ".end method\n\n".format(
                            original=lines[new_constructor_line],
                            encryption_code=static_string_encryption_code,
                        )
                    )

                with open(smali_file, "w", encoding="utf-8") as current_file:
                    current_file.writelines(lines)

            if (
                    not patch_info.decrypt_string_smali_file_added_flag
                    and encrypted_strings
            ):
                # Add to the app the code for decrypting the encrypted strings. The code
                # for decrypting can be put in any smali directory, since it will be
                # moved to the correct directory when rebuilding the application.
                destination_dir = os.path.dirname(patch_info.get_smali_files()[0])
                destination_file = os.path.join(destination_dir, "DecryptString.smali")
                with open(
                        destination_file, "w", encoding="utf-8"
                ) as decrypt_string_smali:
                    decrypt_string_smali.write(
                        util.get_decrypt_string_smali_code(self.encryption_secret)
                    )
                    patch_info.decrypt_string_smali_file_added_flag = True

        except Exception as e:
            self.logger.error(
                'Error during execution of "{0}" obfuscator: {1}'.format(
                    self.__class__.__name__, e
                )
            )
            raise
