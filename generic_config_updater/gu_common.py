import json
import jsonpatch
from jsonpointer import JsonPointer
import sonic_yang
import subprocess
import yang as ly
import copy
import re
from enum import Enum

YANG_DIR = "/usr/local/yang-models"

class GenericConfigUpdaterError(Exception):
    pass

class JsonChange:
    """
    A class that describes a partial change to a JSON object.
    It is is similar to JsonPatch, but the order of updating the configs is unknown.
    Only the final outcome of the update can be retrieved.
    It provides a single function to apply the change to a given JSON object.
   """
    def __init__(self, patch):
        self.patch = patch

    def apply(self, config):
        return self.patch.apply(config)

    def __str__(self):
        return f'{self.patch}'

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, JsonChange):
            return self.patch == other.patch
        return False

class ConfigWrapper:
    def __init__(self, yang_dir = YANG_DIR):
        self.yang_dir = YANG_DIR

    def get_config_db_as_json(self):
        text = self._get_config_db_as_text()
        return json.loads(text)

    def _get_config_db_as_text(self):
        # TODO: Getting configs from CLI is very slow, need to get it from sonic-cffgen directly
        cmd = "show runningconfiguration all"
        result = subprocess.Popen(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        text, err = result.communicate()
        return_code = result.returncode
        if return_code: # non-zero means failure
            raise GenericConfigUpdaterError(f"Failed to get running config, Return code: {return_code}, Error: {err}")
        return text

    def get_sonic_yang_as_json(self):
        config_db_json = self.get_config_db_as_json()
        return self.convert_config_db_to_sonic_yang(config_db_json)

    def convert_config_db_to_sonic_yang(self, config_db_as_json):
        sy = sonic_yang.SonicYang(self.yang_dir)
        sy.loadYangModel()

        # Crop config_db tables that do not have sonic yang models
        cropped_config_db_as_json = self.crop_tables_without_yang(config_db_as_json)

        sonic_yang_as_json = dict()

        sy._xlateConfigDBtoYang(cropped_config_db_as_json, sonic_yang_as_json)

        return sonic_yang_as_json

    def convert_sonic_yang_to_config_db(self, sonic_yang_as_json):
        sy = sonic_yang.SonicYang(self.yang_dir)
        sy.loadYangModel()

        # replace container of the format 'module:table' with just 'table'
        new_sonic_yang_json = {}
        for module_top in sonic_yang_as_json:
            new_sonic_yang_json[module_top] = {}
            for container in sonic_yang_as_json[module_top]:
                tokens = container.split(':')
                if len(tokens) > 2:
                    raise ValueError(f"Expecting '<module>:<table>' or '<table>', found {container}")
                table = container if len(tokens) == 1 else tokens[1]
                new_sonic_yang_json[module_top][table] = sonic_yang_as_json[module_top][container]

        config_db_as_json = dict()
        sy.xlateJson = new_sonic_yang_json
        sy.revXlateJson = config_db_as_json
        sy._revXlateYangtoConfigDB(new_sonic_yang_json, config_db_as_json)

        return config_db_as_json

    def validate_sonic_yang_config(self, sonic_yang_as_json):
        config_db_as_json = self.convert_sonic_yang_to_config_db(sonic_yang_as_json)

        sy = sonic_yang.SonicYang(self.yang_dir)
        sy.loadYangModel()

        try:
            sy.loadData(config_db_as_json)

            sy.validate_data_tree()
            return True
        except sonic_yang.SonicYangException as ex:
            return False

    def validate_config_db_config(self, config_db_as_json):
        sy = sonic_yang.SonicYang(self.yang_dir)
        sy.loadYangModel()

        try:
            tmp_config_db_as_json = copy.deepcopy(config_db_as_json)

            sy.loadData(tmp_config_db_as_json)

            sy.validate_data_tree()
            return True
        except sonic_yang.SonicYangException as ex:
            return False

    def crop_tables_without_yang(self, config_db_as_json):
        sy = sonic_yang.SonicYang(self.yang_dir)
        sy.loadYangModel()

        sy.jIn = copy.deepcopy(config_db_as_json)

        sy.tablesWithOutYang = dict()

        sy._cropConfigDB()

        return sy.jIn

class DryRunConfigWrapper(ConfigWrapper):
    # TODO: implement DryRunConfigWrapper
    # This class will simulate all read/write operations to ConfigDB on a virtual storage unit.
    pass

class PatchWrapper:
    def __init__(self, config_wrapper=None):
        self.config_wrapper = config_wrapper if config_wrapper is not None else ConfigWrapper()
        self.path_addressing = PathAddressing()

    def validate_config_db_patch_has_yang_models(self, patch):
        config_db = {}
        for operation in patch:
            tokens = self.path_addressing.get_path_tokens(operation[OperationWrapper.PATH_KEYWORD])
            if len(tokens) == 0: # Modifying whole config_db
                tables_dict = {table_name: {} for table_name in operation['value']}
                config_db.update(tables_dict)
            elif not tokens[0]: # Not empty
                raise ValueError("Table name in patch cannot be empty")
            else:
                config_db[tokens[0]] = {}

        cropped_config_db = self.config_wrapper.crop_tables_without_yang(config_db)

        # valid if no tables dropped during cropping
        return len(cropped_config_db.keys()) == len(config_db.keys())

    def verify_same_json(self, expected, actual):
        # patch will be [] if no diff, [] evaluates to False
        return not jsonpatch.make_patch(expected, actual)

    def generate_patch(self, current, target):
        return jsonpatch.make_patch(current, target)

    def simulate_patch(self, patch, jsonconfig):
        return patch.apply(jsonconfig)

    def convert_config_db_patch_to_sonic_yang_patch(self, patch):
        if not(self.validate_config_db_patch_has_yang_models(patch)):
            raise ValueError(f"Given patch is not valid")

        current_config_db = self.config_wrapper.get_config_db_as_json()
        target_config_db = self.simulate_patch(patch, current_config_db)

        current_yang = self.config_wrapper.convert_config_db_to_sonic_yang(current_config_db)
        target_yang = self.config_wrapper.convert_config_db_to_sonic_yang(target_config_db)

        return self.generate_patch(current_yang, target_yang)

    def convert_sonic_yang_patch_to_config_db_patch(self, patch):
        current_yang = self.config_wrapper.get_sonic_yang_as_json()
        target_yang = self.simulate_patch(patch, current_yang)

        current_config_db = self.config_wrapper.convert_sonic_yang_to_config_db(current_yang)
        target_config_db = self.config_wrapper.convert_sonic_yang_to_config_db(target_yang)

        return self.generate_patch(current_config_db, target_config_db)

class OperationType(Enum):
    ADD = 1
    REMOVE = 2
    REPLACE = 3

class OperationWrapper:
    OP_KEYWORD = "op"
    PATH_KEYWORD = "path"
    VALUE_KEYWORD = "value"

    def create(self, operation_type, path, value=None):
        op_type = operation_type.name.lower()

        operation = {OperationWrapper.OP_KEYWORD: op_type, OperationWrapper.PATH_KEYWORD: path}

        if operation_type in [OperationType.ADD, OperationType.REPLACE]:
            operation[OperationWrapper.VALUE_KEYWORD] = value

        return operation

class PathAddressing:
    """
    Path refers to the 'path' in JsonPatch operations: https://tools.ietf.org/html/rfc6902
    The path corresponds to JsonPointer: https://tools.ietf.org/html/rfc6901

    All xpath operations in this class are only relevent to ConfigDb and the conversion to YANG xpath.
    It is not meant to support all the xpath functionalities, just the ones relevent to ConfigDb/YANG.
    """
    PATH_SEPARATOR = "/"
    XPATH_SEPARATOR = "/"
    def get_path_tokens(self, path):
        return JsonPointer(path).parts

    def create_path(self, tokens):
        return JsonPointer.from_parts(tokens).path

    def get_xpath_tokens(self, xpath):
        """
        Splits the given xpath into tokens by '/'.

        Example:
          xpath: /sonic-vlan:sonic-vlan/VLAN_MEMBER/VLAN_MEMBER_LIST[name='Vlan1000'][port='Ethernet8']/tagging_mode
          tokens: sonic-vlan:sonic-vlan, VLAN_MEMBER, VLAN_MEMBER_LIST[name='Vlan1000'][port='Ethernet8'], tagging_mode
        """
        if xpath == "":
            raise ValueError("xpath cannot be empty")

        if xpath == "/":
            return []

        idx = 0
        tokens = []
        while idx < len(xpath):
            end = self._get_xpath_token_end(idx+1, xpath)
            token = xpath[idx+1:end]
            tokens.append(token)
            idx = end

        return tokens

    def _get_xpath_token_end(self, start, xpath):
        idx = start
        while idx < len(xpath):
            if xpath[idx] == PathAddressing.XPATH_SEPARATOR:
                break
            elif xpath[idx] == "[":
                idx = self._get_xpath_predicate_end(idx, xpath)
            idx = idx+1

        return idx

    def _get_xpath_predicate_end(self, start, xpath):
        idx = start
        while idx < len(xpath):
            if xpath[idx] == "]":
                break
            elif xpath[idx] == "'":
                idx = self._get_xpath_single_quote_str_end(idx, xpath)
            elif xpath[idx] == '"':
                idx = self._get_xpath_double_quote_str_end(idx, xpath)

            idx = idx+1

        return idx

    def _get_xpath_single_quote_str_end(self, start, xpath):
        idx = start+1 # skip first single quote
        while idx < len(xpath):
            if xpath[idx] == "'":
                break
            # libyang implements XPATH 1.0 which does not escape single quotes
            # libyang src: https://netopeer.liberouter.org/doc/libyang/master/html/howtoxpath.html
            # XPATH 1.0 src: https://www.w3.org/TR/1999/REC-xpath-19991116/#NT-Literal
            idx = idx+1

        return idx

    def _get_xpath_double_quote_str_end(self, start, xpath):
        idx = start+1 # skip first single quote
        while idx < len(xpath):
            if xpath[idx] == '"':
                break
            # libyang implements XPATH 1.0 which does not escape double quotes
            # libyang src: https://netopeer.liberouter.org/doc/libyang/master/html/howtoxpath.html
            # XPATH 1.0 src: https://www.w3.org/TR/1999/REC-xpath-19991116/#NT-Literal
            idx = idx+1

        return idx

    def create_xpath(self, tokens):
        """
        Creates an xpath by combining the given tokens using '/'
        Example:
          tokens: module, container, list[key='value'], leaf
          xpath: /module/container/list[key='value']/leaf
        """
        if len(tokens) == 0:
            return "/"

        return f"{PathAddressing.XPATH_SEPARATOR}{PathAddressing.XPATH_SEPARATOR.join(str(t) for t in tokens)}"

    def find_ref_paths(self, path, config):
        """
        Finds the paths referencing any line under the given 'path' within the given 'config'.
        Example:
          path: /PORT
          config: 
            {
                "VLAN_MEMBER": {
                    "Vlan1000|Ethernet0": {},
                    "Vlan1000|Ethernet4": {}
                },
                "ACL_TABLE": {
                    "EVERFLOW": {
                        "ports": [
                            "Ethernet4"
                        ],
                    },
                    "EVERFLOWV6": {
                        "ports": [
                            "Ethernet4",
                            "Ethernet8"
                        ]
                    }
                },
                "PORT": {
                    "Ethernet0": {},
                    "Ethernet4": {},
                    "Ethernet8": {}
                }
            }
          return:
            /VLAN_MEMBER/Vlan1000|Ethernet0
            /VLAN_MEMBER/Vlan1000|Ethernet4
            /ACL_TABLE/EVERFLOW/ports/0
            /ACL_TABLE/EVERFLOW6/ports/0
            /ACL_TABLE/EVERFLOW6/ports/1
        """
        # TODO: Also fetch references by must statement (check similar statements)
        return self._find_leafref_paths(path, config)

    def _find_leafref_paths(self, path, config):
        sy = sonic_yang.SonicYang(YANG_DIR)
        sy.loadYangModel()

        sy.loadData(config)

        xpath = self.convert_path_to_xpath(path, config, sy)

        leaf_xpaths = self._get_inner_leaf_xpaths(xpath, sy)

        ref_xpaths = []
        for xpath in leaf_xpaths:
            ref_xpaths.extend(sy.find_data_dependencies(xpath))

        ref_paths = []
        for ref_xpath in ref_xpaths:
            ref_path = self.convert_xpath_to_path(ref_xpath, config, sy)
            ref_paths.append(ref_path)

        return set(ref_paths)

    def _get_inner_leaf_xpaths(self, xpath, sy):
        if xpath == "/": # Point to Root element which contains all xpaths
            nodes = sy.root.tree_for()
        else: # Otherwise get all nodes that match xpath
            nodes = sy.root.find_path(xpath).data()

        for node in nodes:
            for inner_node in node.tree_dfs():
                # TODO: leaflist also can be used as the 'path' argument in 'leafref' so add support to leaflist
                if self._is_leaf_node(inner_node):
                    yield inner_node.path()

    def _is_leaf_node(self, node):
        schema = node.schema()
        return ly.LYS_LEAF == schema.nodetype()

    def convert_path_to_xpath(self, path, config, sy):
        """
        Converts the given JsonPatch path (i.e. JsonPointer) to XPATH.
        Example:
          path: /VLAN_MEMBER/Vlan1000|Ethernet8/tagging_mode
          xpath: /sonic-vlan:sonic-vlan/VLAN_MEMBER/VLAN_MEMBER_LIST[name='Vlan1000'][port='Ethernet8']/tagging_mode
        """
        self.convert_xpath_to_path
        tokens = self.get_path_tokens(path)
        if len(tokens) == 0:
            return self.create_xpath(tokens)

        xpath_tokens = []
        table = tokens[0]

        cmap = sy.confDbYangMap[table]

        # getting the top level element <module>:<topLevelContainer>
        xpath_tokens.append(cmap['module']+":"+cmap['topLevelContainer'])

        xpath_tokens.extend(self._get_xpath_tokens_from_container(cmap['container'], 0, tokens, config))

        return self.create_xpath(xpath_tokens)

    def _get_xpath_tokens_from_container(self, model, token_index, path_tokens, config):
        token = path_tokens[token_index]
        xpath_tokens = [token]

        if len(path_tokens)-1 == token_index:
            return xpath_tokens

        # check if the configdb token is referring to a list
        list_model = self._get_list_model(model, token_index, path_tokens)
        if list_model:
            new_xpath_tokens = self._get_xpath_tokens_from_list(list_model, token_index+1, path_tokens, config[path_tokens[token_index]])
            xpath_tokens.extend(new_xpath_tokens)
            return xpath_tokens

        # check if it is targetting a child container
        child_container_model = self._get_model(model.get('container'), path_tokens[token_index+1])
        if child_container_model:
            new_xpath_tokens = self._get_xpath_tokens_from_container(child_container_model, token_index+1, path_tokens, config[path_tokens[token_index]])
            xpath_tokens.extend(new_xpath_tokens)
            return xpath_tokens

        new_xpath_tokens = self._get_xpath_tokens_from_leaf(model, token_index+1, path_tokens, config[path_tokens[token_index]])
        xpath_tokens.extend(new_xpath_tokens)

        return xpath_tokens

    def _get_xpath_tokens_from_list(self, model, token_index, path_tokens, config):
        list_name = model['@name']

        tableKey = path_tokens[token_index]
        listKeys = model['key']['@value']
        keyDict = self._extractKey(tableKey, listKeys)
        keyTokens = [f"[{key}='{keyDict[key]}']" for key in keyDict]
        item_token = f"{list_name}{''.join(keyTokens)}"

        xpath_tokens = [item_token]

        # if whole list-item is needed i.e. if in the path is not referencing child leaf items
        # Example:
        #   path: /VLAN/Vlan1000
        #   xpath: /sonic-vlan:sonic-vlan/VLAN/VLAN_LIST[name='Vlan1000']
        if len(path_tokens)-1 == token_index:
            return xpath_tokens

        new_xpath_tokens = self._get_xpath_tokens_from_leaf(model, token_index+1, path_tokens,config[path_tokens[token_index]])
        xpath_tokens.extend(new_xpath_tokens)
        return xpath_tokens

    def _get_xpath_tokens_from_leaf(self, model, token_index, path_tokens, config):
        token = path_tokens[token_index]

        # checking all leaves
        leaf_model = self._get_model(model.get('leaf'), token)
        if leaf_model:
            return [token]

        # checking choice
        choices = model.get('choice')
        if choices:
            for choice in choices:
                cases = choice['case']
                for case in cases:
                    leaf_model = self._get_model(case.get('leaf'), token)
                    if leaf_model:
                        return [token]

        # checking leaf-list (i.e. arrays of string, number or bool)
        leaf_list_model = self._get_model(model.get('leaf-list'), token)
        if leaf_list_model:
            # if whole-list is to be returned, just return the token without checking the list items
            # Example:
            #   path: /VLAN/Vlan1000/dhcp_servers
            #   xpath: /sonic-vlan:sonic-vlan/VLAN/VLAN_LIST[name='Vlan1000']/dhcp_servers
            if len(path_tokens)-1 == token_index:
                return [token]
            list_config = config[token]
            value = list_config[int(path_tokens[token_index+1])]
            # To get a leaf-list instance with the value 'val'
            #   /module-name:container/leaf-list[.='val']
            # Source: Check examples in https://netopeer.liberouter.org/doc/libyang/master/html/howto_x_path.html
            return [f"{token}[.='{value}']"]

        raise ValueError("Token not found")

    def _extractKey(self, tableKey, keys):
        keyList = keys.split()
        # get the value groups
        value = tableKey.split("|")
        # match lens
        if len(keyList) != len(value):
            raise ValueError("Value not found for {} in {}".format(keys, tableKey))
        # create the keyDict
        keyDict = dict()
        for i in range(len(keyList)):
            keyDict[keyList[i]] = value[i].strip()

        return keyDict

    def _get_list_model(self, model, token_index, path_tokens):
        parent_container_name = path_tokens[token_index]
        clist = model.get('list')
        # Container contains a single list, just return it 
        # TODO: check if matching also by name is necessary
        if isinstance(clist, dict):
            return clist

        if isinstance(clist, list):
            configdb_values_str = path_tokens[token_index+1]
            # Format: "value1|value2|value|..."
            configdb_values = configdb_values_str.split("|")
            for list_model in clist:
                yang_keys_str = list_model['key']['@value']
                # Format: "key1 key2 key3 ..."
                yang_keys = yang_keys_str.split()
                # if same number of values and keys, this is the intended list-model
                # TODO: Match also on types and not only the length of the keys/values
                if len(yang_keys) == len(configdb_values):
                    return list_model
            raise GenericConfigUpdaterError(f"Container {parent_container_name} has multiple lists, "
                                            f"but none of them match the config_db value {configdb_values_str}")

        return None

    def convert_xpath_to_path(self, xpath, config, sy):
        """
        Converts the given XPATH to JsonPatch path (i.e. JsonPointer).
        Example:
          xpath: /sonic-vlan:sonic-vlan/VLAN_MEMBER/VLAN_MEMBER_LIST[name='Vlan1000'][port='Ethernet8']/tagging_mode
          path: /VLAN_MEMBER/Vlan1000|Ethernet8/tagging_mode
        """
        tokens = self.get_xpath_tokens(xpath)
        if len(tokens) == 0:
            return self.create_path([])

        if len(tokens) == 1:
            raise GenericConfigUpdaterError("xpath cannot be just the module-name, there is no mapping to path")

        table = tokens[1]
        cmap = sy.confDbYangMap[table]

        path_tokens = self._get_path_tokens_from_container(cmap['container'], 1, tokens, config)
        return self.create_path(path_tokens)

    def _get_path_tokens_from_container(self, model, token_index, xpath_tokens, config):
        token = xpath_tokens[token_index]
        path_tokens = [token]

        if len(xpath_tokens)-1 == token_index:
            return path_tokens

        # check child list
        list_name = xpath_tokens[token_index+1].split("[")[0]
        list_model = self._get_model(model.get('list'), list_name)
        if list_model:
            new_path_tokens = self._get_path_tokens_from_list(list_model, token_index+1, xpath_tokens, config[token])
            path_tokens.extend(new_path_tokens)
            return path_tokens

        container_name = xpath_tokens[token_index+1]
        container_model = self._get_model(model.get('container'), container_name)
        if container_model:
            new_path_tokens = self._get_path_tokens_from_container(container_model, token_index+1, xpath_tokens, config[token])
            path_tokens.extend(new_path_tokens)
            return path_tokens

        new_path_tokens = self._get_path_tokens_from_leaf(model, token_index+1, xpath_tokens, config[token])
        path_tokens.extend(new_path_tokens)

        return path_tokens

    def _get_path_tokens_from_list(self, model, token_index, xpath_tokens, config):
        token = xpath_tokens[token_index]
        key_dict = self._extract_key_dict(token)

        # If no keys specified return empty tokens, as we are already inside the correct table.
        # Also note that the list name in SonicYang has no correspondence in ConfigDb and is ignored.
        # Example where VLAN_MEMBER_LIST has no specific key/value:
        #   xpath: /sonic-vlan:sonic-vlan/VLAN_MEMBER/VLAN_MEMBER_LIST
        #   path: /VLAN_MEMBER
        if not(key_dict):
            return []

        listKeys = model['key']['@value']
        key_list = listKeys.split()

        if len(key_list) != len(key_dict):
            raise GenericConfigUpdaterError(f"Keys in configDb not matching keys in SonicYang. ConfigDb keys: {key_dict.keys()}. SonicYang keys: {key_list}")

        values = [key_dict[k] for k in key_list]
        path_token = '|'.join(values)
        path_tokens = [path_token]

        if len(xpath_tokens)-1 == token_index:
            return path_tokens

        next_token = xpath_tokens[token_index+1]
        # if the target node is a key, then it does not have a correspondene to path.
        # Just return the current 'key1|key2|..' token as it already refers to the keys
        # Example where the target node is 'name' which is a key in VLAN_MEMBER_LIST:
        #   xpath: /sonic-vlan:sonic-vlan/VLAN_MEMBER/VLAN_MEMBER_LIST[name='Vlan1000'][port='Ethernet8']/name
        #   path: /VLAN_MEMBER/Vlan1000|Ethernet8
        if next_token in key_dict:
            return path_tokens

        new_path_tokens = self._get_path_tokens_from_leaf(model, token_index+1, xpath_tokens, config[path_token])
        path_tokens.extend(new_path_tokens)
        return path_tokens

    def _get_path_tokens_from_leaf(self, model, token_index, xpath_tokens, config):
        token = xpath_tokens[token_index]

        # checking all leaves
        leaf_model = self._get_model(model.get('leaf'), token)
        if leaf_model:
            return [token]

        # checking choices
        choices = model.get('choice')
        if choices:
            for choice in choices:
                cases = choice['case']
                for case in cases:
                    leaf_model = self._get_model(case.get('leaf'), token)
                    if leaf_model:
                        return [token]

        # checking leaf-list
        leaf_list_tokens = token.split("[", 1) # split once on the first '[', a regex is used later to fetch keys/values
        leaf_list_name = leaf_list_tokens[0]
        leaf_list_model = self._get_model(model.get('leaf-list'), leaf_list_name)
        if leaf_list_model:
            # if whole-list is to be returned, just return the list-name without checking the list items
            # Example:
            #   xpath: /sonic-vlan:sonic-vlan/VLAN/VLAN_LIST[name='Vlan1000']/dhcp_servers
            #   path: /VLAN/Vlan1000/dhcp_servers
            if len(leaf_list_tokens) == 1:
                return [leaf_list_name]
            leaf_list_pattern = "^[^\[]+(?:\[\.='([^']*)'\])?$"
            leaf_list_regex = re.compile(leaf_list_pattern)
            match = leaf_list_regex.match(token)
            # leaf_list_name = match.group(1)
            leaf_list_value = match.group(1)
            list_config = config[leaf_list_name]
            list_idx = list_config.index(leaf_list_value)
            return [leaf_list_name, list_idx]

        raise Exception("no leaf")

    def _extract_key_dict(self, list_token):
        # Example: VLAN_MEMBER_LIST[name='Vlan1000'][port='Ethernet8']
        # the groups would be ('VLAN_MEMBER'), ("[name='Vlan1000'][port='Ethernet8']")
        table_keys_pattern = "^([^\[]+)(.*)$"
        text = list_token
        table_keys_regex = re.compile(table_keys_pattern)
        match = table_keys_regex.match(text)
        # list_name = match.group(1)
        all_key_value = match.group(2)

        # Example: [name='Vlan1000'][port='Ethernet8']
        # the findall groups would be ('name', 'Vlan1000'), ('port', 'Ethernet8')
        key_value_pattern = "\[([^=]+)='([^']*)'\]"
        matches = re.findall(key_value_pattern, all_key_value)
        key_dict = {}
        for item in matches:
            key = item[0]
            value = item[1]
            key_dict[key] = value

        return key_dict

    def _get_model(self, model, name):
        if isinstance(model, dict) and model['@name'] == name:
            return model
        if isinstance(model, list):
            for submodel in model:
                if submodel['@name'] == name:
                    return submodel

        return None
