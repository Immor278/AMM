import json
import logging
import os
import re
from typing import Set, List

import packer
import util
from patch_category import IBasePatcher
from patchers.api_patcher import api_util


class ApiPatcher(IBasePatcher):
    def __init__(self):
        self.logger = logging.getLogger(
            "{0}.{1}".format(__name__, self.__class__.__name__)
        )
        super().__init__()

        self.methods_with_reflection: int = 0

        # Keep track of the length of the added instructions for advanced reflection
        # obfuscator, since there is a limit for the number of maximum instructions in
        # a try catch block. Not all the instructions have the same length.
        self.obfuscator_instructions_length: int = 0
        self.obfuscator_instructions_limit: int = 60000

        with open('resources/PScoutPermApiDict.json', 'r') as FH:  # 'rb'
            # Use SmallCase json file to prevent run time case conversion in GetPermFromApi
            perm_api_dict_from_json_temp = json.load(FH)
            self.perm_api_dict_from_json = {}
            self.perm_first_api = {}
            for perms in perm_api_dict_from_json_temp:

                # store first api of each permission
                first_api = perm_api_dict_from_json_temp[perms][0]
                method_params = first_api[3]
                method_param_str = ''
                if len(method_params) > 0:
                    for __item in method_params:
                        _item = api_util.change_plain_name(__item)
                        method_param_str = method_param_str + _item + ' '
                    method_param_str = method_param_str[:-1]
                method_name = api_util.change_plain_name(first_api[0]) + ';->' + first_api[
                    1] + '(' + method_param_str + ')' + api_util.change_plain_name(first_api[2])
                self.perm_first_api[perms] = method_name

            del perm_api_dict_from_json_temp

    def patch(self, patch_info: packer.Packer):
        add_apis = []
        remove_apis = []
        for item in patch_info.features:
            item: packer.PatchFeature = item
            if item.type != packer.FeatureType.API:
                continue
            type_name = item.name.split('::')[0]
            api_name = item.name.split('::')[-1]
            if type_name == 'real_permission':
                api_name = self.perm_first_api[api_name]

            if item.value > 0.5:
                add_apis.append(api_name)
            else:
                remove_apis.append(api_name)

        self._remove_apis(remove_apis, patch_info)
        self._add_apis(add_apis, patch_info)

    def _add_apis(self, apis, patch_info: packer.Packer):
        if len(apis) == 0:
            return
        activity_name = api_util.find_main_activity(patch_info)
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
                                    output_apis = self.__get_add_apis_inst(apis, patch_info)

                                    # add if and try
                                    out_file.write('\n\t nop \n')
                                    out_file.write('\n\t :try_start_a \n')
                                    out_file.write('\n\t invoke-static {}, Ljava/lang/System;->currentTimeMillis()J \n')
                                    out_file.write('\n\t move-result-wide v2 \n')
                                    out_file.write('\n\t .local v2, "timestamp":J \n')
                                    out_file.write('\n\t const-wide/16 v4, 0x0 \n')
                                    out_file.write('\n\t cmp-long v1, v2, v4 \n')
                                    out_file.write('\n\t if-gez v1, :cond_19 \n')

                                    for api in output_apis:
                                        out_file.write('\n\t ' + api + ' \n')

                                    # add catch
                                    out_file.write('\n\t :try_end_19 \n')
                                    out_file.write(
                                        '\n\t .catch Ljava/lang/Exception; {:try_start_a .. :try_end_19} :catch_1a \n')
                                    out_file.write('\n\t .end local v2    # "timestamp":J \n')
                                    out_file.write('\n\t :cond_19 \n')
                                    out_file.write('\n\t :goto_19 \n')
                                    out_file.write('\n\t return-void \n')
                                    out_file.write('\n\t :catch_1a \n')
                                    out_file.write('\n\t move-exception v0 \n')
                                    out_file.write('\n\t .local v0, "e":Ljava/lang/Exception; \n')
                                    out_file.write(
                                        '\n\t invoke-virtual {v0}, Ljava/lang/Exception;->printStackTrace()V \n')
                                    out_file.write('\n\t goto :goto_19 \n')

                                    out_file.write('\n')

                                    # Exiting method.
                                    out_file.write(line)
                                    editing_method = False

                                else:
                                    out_file.write(line)

        except Exception as e:
            self.logger.error(
                'Error during execution of "{0}" obfuscator: {1}'.format(
                    self.__class__.__name__, e
                )
            )
            raise

    def __get_add_apis_inst(self, apis, patch_info: packer.Packer):
        the_apis: Set[str] = set(apis)
        output: [str] = []
        for api in the_apis:
            #     new-instance v1, Landroidx/core/view/accessibility/AccessibilityNodeProviderCompat;
            #
            #     invoke-direct {v1}, Landroidx/core/view/accessibility/AccessibilityNodeProviderCompat;-><init>()V
            #
            #     const/4 v4, 0x0
            #
            #     const/4 v5, 0x0
            #
            #     const/4 v6, 0x0
            #
            #     invoke-virtual {v1, v4, v5, v6}, Landroidx/core/view/accessibility/AccessibilityNodeProviderCompat;->performAction(IILandroid/os/Bundle;)Z

            invoke_match = util.invoke_pattern.match(api)
            invoke_object = invoke_match.group("invoke_object")
            invoke_method = invoke_match.group("invoke_method")
            invoke_param = invoke_match.group("invoke_param")
            invoke_return = invoke_match.group("invoke_return")
            split_params = api_util.split_method_params(invoke_param)

            output.append('new-instance v1, ' + invoke_object)
            output.append('invoke-direct {v1}, ' + invoke_object + '-><init>()V')

            # create n null/0 params
            param_names = []
            param_len = len(split_params)
            if param_len > 0:
                for index in range(param_len):
                    param_type = split_params[index]
                    param_name = 'v' + str(15 - param_len + index)
                    output.append('const/4 ' + param_name + ', 0x0')
                    if param_type.startswith('L'):
                        output.append('check-cast ' + param_name + ', ' + param_type)
                    param_names.append(param_name)

            sub_param_v = ', '.join(param_names)
            if len(sub_param_v) > 0:
                sub_param_v = ', ' + sub_param_v

            output.append('invoke-virtual {v1' + sub_param_v + '}, ' + api)

        return output

    def _remove_apis(self, apis, patch_info: packer.Packer):
        if len(apis) == 0:
            return
        try:
            dangerous_api: Set[str] = set(apis)  # set(util.get_dangerous_api()) # TODO

            obfuscator_smali_code: str = ""

            move_result_pattern = re.compile(
                r"\s+move-result.*?\s(?P<register>[vp0-9]+)"
            )

            for smali_file in util.show_list_progress(
                    patch_info.get_smali_files(),
                    interactive=patch_info.interactive,
                    description="Obfuscating dangerous APIs using reflection",
            ):
                self.logger.debug(
                    'Obfuscating dangerous APIs using reflection in file "{0}"'.format(
                        smali_file
                    )
                )

                # There is no space for further reflection instructions.
                if (
                        self.obfuscator_instructions_length
                        >= self.obfuscator_instructions_limit
                ):
                    break

                with open(smali_file, "r", encoding="utf-8") as current_file:
                    lines = current_file.readlines()

                # Line numbers where a method is declared.
                method_index: List[int] = []

                # For each method in method_index, True if there are enough registers
                # to perform some operations by using reflection, False otherwise.
                method_is_reflectable: List[bool] = []

                # The number of local registers of each method in method_index.
                method_local_count: List[int] = []

                # Find the method declarations in this smali file.
                for line_number, line in enumerate(lines):
                    method_match = util.method_pattern.match(line)
                    if method_match:
                        method_index.append(line_number)

                        param_count = api_util.count_needed_registers(
                            api_util.split_method_params(method_match.group("method_param"))
                        )

                        # Save the number of local registers of this method.
                        local_count = 16
                        local_match = util.locals_pattern.match(lines[line_number + 1])
                        if local_match:
                            local_count = int(local_match.group("local_count"))
                            method_local_count.append(local_count)
                        else:
                            # For some reason the locals declaration was not found where
                            # it should be, so assume the local registers are all used.
                            method_local_count.append(local_count)

                        # If there are enough registers available we can perform some
                        # reflection operations.
                        if param_count + local_count <= 11:
                            method_is_reflectable.append(True)
                        else:
                            method_is_reflectable.append(False)

                # Look for method invocations of dangerous APIs inside the methods
                # declared in this smali file and change normal invocations with
                # invocations through reflection.
                for method_number, index in enumerate(method_index):

                    # If there are enough registers for reflection operations, look for
                    # method invocations inside each method's body.
                    if method_is_reflectable[method_number]:
                        current_line_number = index
                        while not lines[current_line_number].startswith(".end method"):

                            # There is no space for further reflection instructions.
                            if (
                                    self.obfuscator_instructions_length
                                    >= self.obfuscator_instructions_limit
                            ):
                                break

                            current_line_number += 1

                            invoke_match = util.invoke_pattern.match(
                                lines[current_line_number]
                            )
                            if invoke_match:
                                method = (
                                    "{class_name}->{method_name}"
                                    "({method_param}){method_return}".format(
                                        class_name=invoke_match.group("invoke_object"),
                                        method_name=invoke_match.group("invoke_method"),
                                        method_param=invoke_match.group("invoke_param"),
                                        method_return=invoke_match.group(
                                            "invoke_return"
                                        ),
                                    )
                                )

                                # Use reflection only if this method belongs to
                                # dangerous APIs.
                                if method not in dangerous_api:
                                    continue

                                if (
                                        invoke_match.group("invoke_type")
                                        == "invoke-virtual"
                                ):
                                    tmp_is_virtual = True
                                elif (
                                        invoke_match.group("invoke_type") == "invoke-static"
                                ):
                                    tmp_is_virtual = False
                                else:
                                    continue

                                tmp_register = invoke_match.group("invoke_pass")
                                tmp_class_name = invoke_match.group("invoke_object")
                                tmp_method = invoke_match.group("invoke_method")
                                tmp_param = invoke_match.group("invoke_param")
                                tmp_return_type = invoke_match.group("invoke_return")

                                # Check if the method invocation result is used in the
                                # following lines.
                                for move_result_index in range(
                                        current_line_number + 1,
                                        min(current_line_number + 10, len(lines) - 1),
                                ):
                                    if "invoke-" in lines[move_result_index]:
                                        # New method invocation, the previous method
                                        # result is not used.
                                        break

                                    move_result_match = move_result_pattern.match(
                                        lines[move_result_index]
                                    )
                                    if move_result_match:
                                        tmp_result_register = move_result_match.group(
                                            "register"
                                        )

                                        # Fix the move-result instruction after the
                                        # method invocation.
                                        new_move_result = ""
                                        if tmp_return_type in api_util.primitive_types:
                                            new_move_result += (
                                                "\tmove-result-object "
                                                "{result_register}\n\n"
                                                "\tcheck-cast {result_register}, "
                                                "{result_class}\n\n".format(
                                                    result_register=tmp_result_register,
                                                    result_class=api_util.type_dict[
                                                        tmp_return_type
                                                    ],
                                                )
                                            )

                                            new_move_result += "\tinvoke-virtual " "{{{result_register}}}, {cast}\n\n".format(
                                                result_register=tmp_result_register,
                                                cast=api_util.reverse_cast_dict[
                                                    tmp_return_type
                                                ],
                                            )

                                            if (
                                                    tmp_return_type == "J"
                                                    or tmp_return_type == "D"
                                            ):
                                                new_move_result += (
                                                    "\tmove-result-wide "
                                                    "{result_register}\n".format(
                                                        result_register=tmp_result_register
                                                    )
                                                )
                                            else:
                                                new_move_result += (
                                                    "\tmove-result "
                                                    "{result_register}\n".format(
                                                        result_register=tmp_result_register
                                                    )
                                                )

                                        else:
                                            new_move_result += (
                                                "\tmove-result-object "
                                                "{result_register}\n\n"
                                                "\tcheck-cast {result_register}, "
                                                "{return_type}\n".format(
                                                    result_register=tmp_result_register,
                                                    return_type=tmp_return_type,
                                                )
                                            )

                                        lines[move_result_index] = new_move_result

                                # Add the original method to the list of methods using
                                # reflection.
                                obfuscator_smali_code += self.add_smali_reflection_code(
                                    tmp_class_name, tmp_method, tmp_param
                                )

                                # Change the original code with code using reflection.
                                lines[
                                    current_line_number
                                ] = api_util.create_reflection_method(
                                    self.methods_with_reflection,
                                    method_local_count[method_number],
                                    tmp_is_virtual,
                                    tmp_register,
                                    tmp_param,
                                )

                                self.methods_with_reflection += 1

                                # Add the registers needed for performing reflection.
                                lines[index + 1] = "\t.locals {0}\n".format(
                                    method_local_count[method_number] + 4
                                )

                with open(smali_file, "w", encoding="utf-8") as current_file:
                    current_file.writelines(lines)

            # Add to the app the code needed for the reflection obfuscator. The code
            # can be put in any smali directory, since it will be moved to the correct
            # directory when rebuilding the application.
            destination_dir = os.path.dirname(patch_info.get_smali_files()[0])
            destination_file = os.path.join(
                destination_dir, "AdvancedApiReflection.smali"
            )
            with open(destination_file, "w", encoding="utf-8") as api_reflection_smali:
                reflection_code = util.get_advanced_api_reflection_smali_code().replace(
                    "#!code_to_replace!#", obfuscator_smali_code
                )
                api_reflection_smali.write(reflection_code)

        except Exception as e:
            self.logger.error(
                'Error during execution of "{0}" obfuscator: {1}'.format(
                    self.__class__.__name__, e
                )
            )
            raise

    def add_smali_reflection_code(
            self, class_name: str, method_name: str, param_string: str
    ) -> str:
        params = api_util.split_method_params(param_string)

        smali_code = "\n\tconst/4 v1, {param_num:#x}\n\n".format(param_num=len(params))
        self.obfuscator_instructions_length += 1

        if len(params) > 0:
            smali_code += "\tnew-array v1, v1, [Ljava/lang/Class;\n\n"
            self.obfuscator_instructions_length += 2

        for param_index, param in enumerate(params):
            smali_code += "\tconst/4 v2, {param_num:#x}\n\n".format(
                param_num=param_index
            )
            self.obfuscator_instructions_length += 1

            class_param = api_util.sget_dict.get(param, None)
            if class_param:
                smali_code += "\tsget-object v3, {param}\n\n".format(param=class_param)
                self.obfuscator_instructions_length += 2
            else:
                smali_code += "\tconst-class v3, {param}\n\n".format(param=param)
                self.obfuscator_instructions_length += 2

            smali_code += "\taput-object v3, v1, v2\n\n"
            self.obfuscator_instructions_length += 2

        smali_code += (
            "\tconst-class v2, {class_name}\n\n"
            '\tconst-string v3, "{method_name}"\n\n'.format(
                class_name=class_name, method_name=method_name
            )
        )
        self.obfuscator_instructions_length += 4

        smali_code += (
            "\tinvoke-virtual {v2, v3, v1}, Ljava/lang/Class;->getDeclaredMethod("
            "Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;\n\n"
        )
        self.obfuscator_instructions_length += 3

        smali_code += (
            "\tmove-result-object v1\n\n"
            "\tsget-object v2, Lcom/apireflectionmanager/AdvancedApiReflection;->"
            "obfuscatedMethods:Ljava/util/List;\n\n"
        )
        self.obfuscator_instructions_length += 3

        smali_code += (
            "\tinvoke-interface {v2, v1}, Ljava/util/List;->add(Ljava/lang/Object;)Z\n"
        )
        self.obfuscator_instructions_length += 3

        return smali_code
