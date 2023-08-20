from typing import List, Set
from xml.etree.cElementTree import Element
import xml.etree.cElementTree as Xml

import packer

primitive_types: Set[str] = {"I", "Z", "B", "S", "J", "F", "D", "C"}
type_dict = {
    "I": "Ljava/lang/Integer;",
    "Z": "Ljava/lang/Boolean;",
    "B": "Ljava/lang/Byte;",
    "S": "Ljava/lang/Short;",
    "J": "Ljava/lang/Long;",
    "F": "Ljava/lang/Float;",
    "D": "Ljava/lang/Double;",
    "C": "Ljava/lang/Character;",
}
sget_dict = {
    "I": "Ljava/lang/Integer;->TYPE:Ljava/lang/Class;",
    "Z": "Ljava/lang/Boolean;->TYPE:Ljava/lang/Class;",
    "B": "Ljava/lang/Byte;->TYPE:Ljava/lang/Class;",
    "S": "Ljava/lang/Short;->TYPE:Ljava/lang/Class;",
    "J": "Ljava/lang/Long;->TYPE:Ljava/lang/Class;",
    "F": "Ljava/lang/Float;->TYPE:Ljava/lang/Class;",
    "D": "Ljava/lang/Double;->TYPE:Ljava/lang/Class;",
    "C": "Ljava/lang/Character;->TYPE:Ljava/lang/Class;",
}
cast_dict = {
    "I": "Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;",
    "Z": "Ljava/lang/Boolean;->valueOf(Z)Ljava/lang/Boolean;",
    "B": "Ljava/lang/Byte;->valueOf(B)Ljava/lang/Byte;",
    "S": "Ljava/lang/Short;->valueOf(S)Ljava/lang/Short;",
    "J": "Ljava/lang/Long;->valueOf(J)Ljava/lang/Long;",
    "F": "Ljava/lang/Float;->valueOf(F)Ljava/lang/Float;",
    "D": "Ljava/lang/Double;->valueOf(D)Ljava/lang/Double;",
    "C": "Ljava/lang/Character;->valueOf(C)Ljava/lang/Character;",
}
reverse_cast_dict = {
    "I": "Ljava/lang/Integer;->intValue()I",
    "Z": "Ljava/lang/Boolean;->booleanValue()Z",
    "B": "Ljava/lang/Byte;->byteValue()B",
    "S": "Ljava/lang/Short;->shortValue()S",
    "J": "Ljava/lang/Long;->longValue()J",
    "F": "Ljava/lang/Float;->floatValue()F",
    "D": "Ljava/lang/Double;->doubleValue()D",
    "C": "Ljava/lang/Character;->charValue()C",
}


def find_main_activity(patch_info: packer.Packer):
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
        if __is_main_activity__(activity):
            activity_name = activity.attrib[namespace + 'name']
            return activity_name
    return ""


def __is_main_activity__(activity: Element):
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


def split_method_params(param_string: str) -> List[str]:
    params: List[str] = []

    possible_classes = param_string.split(";")
    for possible_class in possible_classes:
        # Make sure the parameter list is not empty.
        if possible_class:
            if possible_class.startswith("L"):
                # Class.
                params.append("{0};".format(possible_class))
            elif possible_class.startswith("["):
                # Array + other optional parameters (e.g. [ILjava/lang/Object).
                for string_position in range(1, len(possible_class)):
                    if possible_class[string_position] == "[":
                        # Multi-dimensional array, proceed with the next char.
                        continue
                    elif possible_class[string_position] == "L":
                        # Class array, no need to proceed with the next char.
                        params.append("{0};".format(possible_class))
                        break
                    else:
                        # Primitive type array, add it to the list and proceed with
                        # the rest of the string
                        params.append(possible_class[: string_position + 1])
                        params.extend(
                            split_method_params(
                                possible_class[string_position + 1:]
                            )
                        )
                        break
            elif possible_class[0] in primitive_types:
                # Primitive type + other optional parameters
                # (e.g. ILjava/lang/Object).
                params.append(possible_class[0])
                params.extend(split_method_params(possible_class[1:]))

    return params


def count_needed_registers(params: List[str]) -> int:
    needed_registers: int = 0

    for param in params:
        # Long and double variables need 2 registers.
        if param == "J" or param == "D":
            needed_registers += 2
        else:
            needed_registers += 1

    return needed_registers


def create_reflection_method(
        num_of_methods: int,
        local_count: int,
        is_virtual_method: bool,
        invoke_registers: str,
        invoke_parameters: str,
):
    # Split method passed registers (if the method has no registers there is
    # an empty line that has to be removed, that's why strip() is used).
    invoke_registers = [
        register.strip()
        for register in invoke_registers.split(", ")
        if register.strip()
    ]

    params = split_method_params(invoke_parameters)

    param_to_register: List[
        List[str]
    ] = []  # list[i][0] = i-th param, list[i][1] = [i-th param register(s)]

    if is_virtual_method:
        # If this is a virtual method, the first register is the object instance
        # and not a parameter.
        register_index = 1
        for param in params:
            # Long and double variables need 2 registers.
            if param == "J" or param == "D":
                param_to_register.append(
                    [param, invoke_registers[register_index: register_index + 2]]
                )
                register_index += 2
            else:
                param_to_register.append(
                    [param, [invoke_registers[register_index]]]
                )
                register_index += 1
    else:
        # This is a static method, so we don't need a reference to the object
        # instance. If this is a virtual method, the first register is the object
        # instance and not a parameter.
        register_index = 0
        for param in params:
            # Long and double variables need 2 registers.
            if param == "J" or param == "D":
                param_to_register.append(
                    [param, invoke_registers[register_index: register_index + 2]]
                )
                register_index += 2
            else:
                param_to_register.append(
                    [param, [invoke_registers[register_index]]]
                )
                register_index += 1

    smali_code = "\tconst/4 #reg1#, {register_num:#x}\n\n".format(
        register_num=len(params)
    )

    if len(params) > 0:
        smali_code += "\tnew-array #reg1#, #reg1#, [Ljava/lang/Object;\n\n"
        for param_index, param_and_register in enumerate(param_to_register):
            # param_and_register[0] = parameter type
            # param_and_register[1] = [register(s) holding the passed parameter(s)]
            cast_primitive_to_class = cast_dict.get(
                param_and_register[0], None
            )

            if cast_primitive_to_class:
                if len(param_and_register[1]) > 1:
                    # 2 register parameter.
                    smali_code += (
                        "\tinvoke-static {{{register_pair}}}, {cast}\n\n"
                        "\tmove-result-object #reg2#\n\n".format(
                            register_pair=", ".join(param_and_register[1]),
                            cast=cast_primitive_to_class,
                        )
                    )
                else:
                    smali_code += (
                        "\tinvoke-static {{{register}}}, {cast}\n\n"
                        "\tmove-result-object #reg2#\n\n".format(
                            register=param_and_register[1][0],
                            cast=cast_primitive_to_class,
                        )
                    )

                smali_code += (
                    "\tconst/4 #reg4#, {param_index:#x}\n\n"
                    "\taput-object #reg2#, #reg1#, #reg4#\n\n".format(
                        param_index=param_index
                    )
                )

            else:
                smali_code += (
                    "\tconst/4 #reg3#, {param_index:#x}\n\n"
                    "\taput-object {register}, #reg1#, #reg3#\n\n".format(
                        param_index=param_index, register=param_and_register[1][0]
                    )
                )

    smali_code += "\tconst/16 #reg3#, {method_num:#x}\n\n".format(
        method_num=num_of_methods
    )

    if is_virtual_method:
        smali_code += (
            "\tinvoke-static {{#reg3#, {obj_instance}, #reg1#}}, "
            "Lcom/apireflectionmanager/AdvancedApiReflection;->obfuscate("
            "ILjava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;\n".format(
                obj_instance=invoke_registers[0]
            )
        )
    else:
        smali_code += "\tconst/4 #reg4#, 0x0\n\n"
        smali_code += (
            "\tinvoke-static {#reg3#, #reg4#, #reg1#}, "
            "Lcom/apireflectionmanager/AdvancedApiReflection;->"
            "obfuscate(ILjava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;\n"
        )

    for index in range(0, 4):
        smali_code = smali_code.replace(
            "#reg{0}#".format(index + 1), "v{0}".format(local_count + index)
        )

    return smali_code


# change plain name to instruction name
def change_plain_name(plain_name):
    if plain_name == 'int' or plain_name == 'int[]':
        return plain_name.replace('int', 'I')
    elif plain_name == 'boolean' or plain_name == 'boolean[]':
        return plain_name.replace('boolean', 'Z')
    elif plain_name == 'float' or plain_name == 'float[]':
        return plain_name.replace('float', 'F')
    elif plain_name == 'byte' or plain_name == 'byte[]':
        return plain_name.replace('byte', 'B')
    elif plain_name == 'long' or plain_name == 'long[]':
        return plain_name.replace('long', 'J')
    elif plain_name == 'short' or plain_name == 'short[]':
        return plain_name.replace('short', 'S')
    elif plain_name == 'double' or plain_name == 'double[]':
        return plain_name.replace('double', 'D')
    elif plain_name == 'char' or plain_name == 'char[]':
        return plain_name.replace('char', 'C')
    return 'L' + plain_name.replace('.', '/') + ';'
