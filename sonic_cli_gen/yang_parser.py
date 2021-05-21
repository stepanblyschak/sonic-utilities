#!/usr/bin/env python

from collections import OrderedDict
from config.config_mgmt import ConfigMgmt

yang_guidelines_link = 'https://github.com/Azure/SONiC/blob/master/doc/mgmt/SONiC_YANG_Model_Guidelines.md'

class YangParser:
    """ YANG model parser

        Attributes:
        yang_model_name: Name of the YANG model file
        conf_mgmt: Instance of Config Mgmt class to help parse YANG models
        y_module: Reference to 'module' entity from YANG model file
        y_top_level_container: Reference to top level 'container' entity from YANG model file
        y_table_containers: Reference to 'container' entities from YANG model file
                            that represent Config DB tables
        yang_2_dict: dictionary created from YANG model file that represent Config DB schema.
                     In case if YANG model has a 'list' entity:
        {
            'tables': [{
                'name': 'value',
                'description': 'value',
                'dynamic-objects': [
                    'name': 'value',
                    'description': 'value,
                    'attrs': [
                        {
                            'name': 'value',
                            'description': 'value',
                            'is-leaf-list': False,
                            'is-mandatory': False
                        }
                        ...
                    ],
                    'keys': [
                        {
                            'name': 'ACL_TABLE_NAME',
                            'description': 'value'
                        }
                        ...
                    ]
                ],
            }]
        }
        In case if YANG model does NOT have a 'list' entity, it has the same structure as above, but 'dynamic-objects' changed to 'static-objects' and have no 'keys'
    """

    def __init__(self,
                 yang_model_name,
                 config_db_path,
                 allow_tbl_without_yang,
                 debug):
        self.yang_model_name = yang_model_name
        self.conf_mgmt = None
        self.y_module = None
        self.y_top_level_container = None
        self.y_table_containers = None
        self.yang_2_dict = dict()

        try:
            self.conf_mgmt = ConfigMgmt(source=config_db_path,
                                        debug=debug,
                                        allowTablesWithoutYang=allow_tbl_without_yang)
        except Exception as e:
            raise Exception("Failed to load the {} class".format(str(e)))
    
    def _init_yang_module_and_containers(self):
        """ Initialize inner class variables:
            self.y_module
            self.y_top_level_container
            self.y_table_containers

            Raises:
                Exception: if YANG model is invalid or NOT exist
        """

        self.y_module = self._find_yang_model_in_yjson_obj()

        if self.y_module is None:
            raise Exception('The YANG model {} is NOT exist'.format(self.yang_model_name))

        if self.y_module.get('container') is None:
            raise Exception('The YANG model {} does NOT have "top level container" element\
                            Please follow the SONiC YANG model guidelines:\n{}'.format(self.yang_model_name, yang_guidelines_link))
        self.y_top_level_container = self.y_module.get('container')

        if self.y_top_level_container.get('container') is None:
            raise Exception('The YANG model {} does NOT have "container" element after "top level container"\
                            Please follow the SONiC YANG model guidelines:\n{}'.format(self.yang_model_name, yang_guidelines_link))
        self.y_table_containers = self.y_top_level_container.get('container')

    def _find_yang_model_in_yjson_obj(self) -> OrderedDict:
        """ Find provided YANG model inside yJson object,
            yJson object contain all yang-models parsed from directory - /usr/local/yang-models

            Returns:
                reference to yang_model_name
        """

        # TODO: consider to check yJson type
        for yang_model in self.conf_mgmt.sy.yJson:
            if yang_model.get('module').get('@name') == self.yang_model_name:
                return yang_model.get('module')

    def parse_yang_model(self) -> dict:
        """ Parse proviced YANG model
            and save output to self.yang_2_dict object 

            Returns:
                dictionary - parsed YANG model in dictionary format
        """

        self._init_yang_module_and_containers()
        self.yang_2_dict['tables'] = list()

        # determine how many (1 or couple) containers a YANG model have after 'top level' container
        # 'table' container it is a container that goes after 'top level' container
        if isinstance(self.y_table_containers, list):
            for tbl_container in self.y_table_containers:
                y2d_elem = on_table_container(self.y_module, tbl_container, self.conf_mgmt)
                self.yang_2_dict['tables'].append(y2d_elem)
        else:
            y2d_elem = on_table_container(self.y_module, self.y_table_containers, self.conf_mgmt)
            self.yang_2_dict['tables'].append(y2d_elem)

        return self.yang_2_dict

#------------------------------HANDLERS--------------------------------#

def on_table_container(y_module: OrderedDict, tbl_container: OrderedDict, conf_mgmt: ConfigMgmt) -> dict:
    """ Parse 'table' container,
        'table' container goes after 'top level' container

        Args:
            y_module: reference to 'module'
            tbl_container: reference to 'table' container
            conf_mgmt: reference to ConfigMgmt class instance,
                       it have yJson object which contain all parsed YANG models
        Returns:
            dictionary: element for self.yang_2_dict['tables'] 
    """

    y2d_elem = {
        'name': tbl_container.get('@name'),
        'description': get_description(tbl_container)
    }

    # determine if 'table container' have a 'list' entity
    if tbl_container.get('list') is None:
        y2d_elem['static-objects'] = list()

        # 'object' container goes after 'table' container
        # 'object' container have 2 types - list (like sonic-flex_counter.yang) and NOT list (like sonic-device_metadata.yang)
        obj_container = tbl_container.get('container')
        if isinstance(obj_container, list):
            for y_container in obj_container:
                static_obj_elem = on_object_container(y_module, y_container, conf_mgmt, is_list=False)
                y2d_elem['static-objects'].append(static_obj_elem)
        else:
            static_obj_elem = on_object_container(y_module, obj_container, conf_mgmt, is_list=False)
            y2d_elem['static-objects'].append(static_obj_elem)
    else:
        y2d_elem['dynamic-objects'] = list()
        tbl_container_lists = tbl_container.get('list')
        # 'container' can have more than 1 'list' entity
        if isinstance(tbl_container_lists, list):
            for _list in tbl_container_lists:
                dynamic_obj_elem = on_object_container(y_module, _list, conf_mgmt, is_list=True)
                y2d_elem['dynamic-objects'].append(dynamic_obj_elem)
        else:
            dynamic_obj_elem = on_object_container(y_module, tbl_container_lists, conf_mgmt, is_list=True)
            y2d_elem['dynamic-objects'].append(dynamic_obj_elem)

        # move 'keys' elements from 'attrs' to 'keys'
        change_dyn_obj_struct(y2d_elem['dynamic-objects'])

    return y2d_elem

def on_object_container(y_module: OrderedDict, y_container: OrderedDict, conf_mgmt, is_list: bool) -> dict:
    """ Parse a 'object container'.
        'Object container' represent OBJECT inside Config DB schema:
        {
            "TABLE": {
                "OBJECT": {
                    "attr": "value"
                }
            }
        }

        Args:
            y_module: reference to 'module'
            y_container: reference to 'object container'
            conf_mgmt: reference to ConfigMgmt class instance,
                       it have yJson object which contain all parsed YANG models
            is_list: boolean flag to determine if container has 'list'
        Returns:
            dictionary: element for y2d_elem['static-objects'] OR y2d_elem['dynamic-objects']
    """

    if y_container is None:
        return {}

    obj_elem = {
        'name': y_container.get('@name'),
        'description': get_description(y_container),
        'attrs': list()
    }

    if is_list:
        obj_elem['keys'] = get_list_keys(y_container)

    attrs_list = list()
    # grouping_name is empty because 'grouping' is not used so far
    attrs_list.extend(get_leafs(y_container, grouping_name = ''))
    attrs_list.extend(get_leaf_lists(y_container, grouping_name = ''))
    attrs_list.extend(get_choices(y_module, y_container, conf_mgmt, grouping_name = ''))
    attrs_list.extend(get_uses(y_module, y_container, conf_mgmt))

    obj_elem['attrs'] = attrs_list

    return obj_elem

def on_uses(y_module: OrderedDict, y_uses, conf_mgmt: ConfigMgmt) -> list:
    """ Parse a YANG 'uses' entities
        'uses' refearing to 'grouping' YANG entity

        Args:
            y_module: reference to 'module'
            y_uses: reference to 'uses'
            conf_mgmt: reference to ConfigMgmt class instance,
                       it have yJson object which contain all parsed YANG model
        Returns:
            list: element for obj_elem['attrs'], 'attrs' contain a parsed 'leafs'
    """

    ret_attrs = list()
    y_grouping = get_all_grouping(y_module, y_uses, conf_mgmt)
    # trim prefixes in order to the next checks
    trim_uses_prefixes(y_uses)

    # not sure if it can happend
    if y_grouping == []:
        raise Exception('Grouping NOT found')

    # TODO: 'refine' support
    for group in y_grouping:
        if isinstance(y_uses, list):
            for use in y_uses:
                if group.get('@name') == use.get('@name'):
                    ret_attrs.extend(get_leafs(group, group.get('@name')))
                    ret_attrs.extend(get_leaf_lists(group, group.get('@name')))
                    ret_attrs.extend(get_choices(y_module, group, conf_mgmt, group.get('@name')))
        else:
            if group.get('@name') == y_uses.get('@name'):
                ret_attrs.extend(get_leafs(group, group.get('@name')))
                ret_attrs.extend(get_leaf_lists(group, group.get('@name')))
                ret_attrs.extend(get_choices(y_module, group, conf_mgmt, group.get('@name')))

    return ret_attrs

def on_choices(y_module: OrderedDict, y_choices, conf_mgmt: ConfigMgmt, grouping_name: str) -> list:
    """ Parse a YANG 'choice' entities

        Args:
            y_module: reference to 'module'
            y_choices: reference to 'choice' element
            conf_mgmt: reference to ConfigMgmt class instance,
                       it have yJson object which contain all parsed YANG model
            grouping_name: if YANG entity contain 'uses', this arg represent 'grouping' name
        Returns:
            list: element for obj_elem['attrs'], 'attrs' contain a parsed 'leafs'
    """

    ret_attrs = list()

    # the YANG model can have multiple 'choice' entities inside a 'container' or 'list'
    if isinstance(y_choices, list):
        for choice in y_choices:
            attrs = on_choice_cases(y_module, choice.get('case'), conf_mgmt, grouping_name)
            ret_attrs.extend(attrs)
    else:
        ret_attrs = on_choice_cases(y_module, y_choices.get('case'), conf_mgmt, grouping_name)

    return ret_attrs

def on_choice_cases(y_module: OrderedDict, y_cases: list, conf_mgmt: ConfigMgmt, grouping_name: str) -> list:
    """ Parse a single YANG 'case' entity from 'choice' entity
        'case' element can have inside - 'leaf', 'leaf-list', 'uses'

        Args:
            y_module: reference to 'module'
            y_cases: reference to 'case'
            conf_mgmt: reference to ConfigMgmt class instance,
                       it have yJson object which contain all parsed YANG model
            grouping_name: if YANG entity contain 'uses', this arg represent 'grouping' name
        Returns:
            list: element for obj_elem['attrs'], 'attrs' contain a parsed 'leafs'
    """

    ret_attrs = list()

    if isinstance(y_cases, list):
        for case in y_cases:
            ret_attrs.extend(get_leafs(case, grouping_name))
            ret_attrs.extend(get_leaf_lists(case, grouping_name))
            # TODO: need to deeply test it
            ret_attrs.extend(get_uses(y_module, case, conf_mgmt))
    else:
        raise Exception('It has no sense to using a single "case" element inside "choice" element')
    
    return ret_attrs

def on_leafs(y_leafs, grouping_name, is_leaf_list: bool) -> list:
    """ Parse all the 'leaf' or 'leaf-list' elements

        Args:
            y_leafs: reference to all 'leaf' elements
            grouping_name: if YANG entity contain 'uses', this arg represent 'grouping' name
            is_leaf_list: boolean to determine if 'leaf-list' was passed in 'y_leafs' arg
        Returns:
            list: list of parsed 'leaf' elements 
    """

    ret_attrs = list()
    # The YANG 'container' entity may have only 1 'leaf' element OR a list of 'leaf' elements
    if isinstance(y_leafs, list): 
        for leaf in y_leafs:
            attr = on_leaf(leaf, is_leaf_list, grouping_name)
            ret_attrs.append(attr)
    else:
        attr = on_leaf(y_leafs, is_leaf_list, grouping_name)
        ret_attrs.append(attr)

    return ret_attrs

def on_leaf(leaf: OrderedDict, is_leaf_list: bool, grouping_name: str) -> dict:
    """ Parse a single 'leaf' element

        Args:
            leaf: reference to a 'leaf' entity
            grouping_name: if YANG entity contain 'uses', this arg represent 'grouping' name
            is_leaf_list: boolean to determine if 'leaf-list' was passed in 'y_leafs' arg
        Returns:
            dictionary: parsed 'leaf' element
    """

    attr = { 'name': leaf.get('@name'),
             'description': get_description(leaf),
             'is-leaf-list': is_leaf_list,
             'is-mandatory': get_mandatory(leaf),
             'group': grouping_name}

    return attr

#----------------------GETERS-------------------------#

def get_mandatory(y_leaf: OrderedDict) -> bool:
    """ Parse 'mandatory' statement for 'leaf'

        Args:
            y_leaf: reference to a 'leaf' entity
        Returns:
            bool: 'leaf' 'mandatory' value
    """

    if y_leaf.get('mandatory') is not None:
        return True

    return False

def get_description(y_entity: OrderedDict) -> str:
    """ Parse 'description' entity from any YANG element

        Args:
            y_entity: reference to YANG 'container' OR 'list' OR 'leaf' ...
        Returns:
            str - text of the 'description'
    """

    if y_entity.get('description') is not None:
        return y_entity.get('description').get('text')
    else:
        return ''

def get_leafs(y_entity: OrderedDict, grouping_name: str) -> list:
    """ Check if YANG entity have 'leafs', if so call handler

        Args:
            y_entity: reference YANG 'container' or 'list' or 'choice' or 'uses'
            grouping_name: if YANG entity contain 'uses', this arg represent 'grouping' name
        Returns:
            list: list of parsed 'leaf' elements 
    """

    if y_entity.get('leaf') is not None:
        return on_leafs(y_entity.get('leaf'), grouping_name, is_leaf_list=False)

    return []

def get_leaf_lists(y_entity: OrderedDict, grouping_name: str) -> list:
    """ Check if YANG entity have 'leaf-list', if so call handler

        Args:
            y_entity: reference YANG 'container' or 'list' or 'choice' or 'uses'
            grouping_name: if YANG entity contain 'uses', this arg represent 'grouping' name
        Returns:
            list: list of parsed 'leaf-list' elements 
    """

    if y_entity.get('leaf-list') is not None:
        return on_leafs(y_entity.get('leaf-list'), grouping_name, is_leaf_list=True)

    return []

def get_choices(y_module: OrderedDict, y_entity: OrderedDict, conf_mgmt: ConfigMgmt, grouping_name: str) -> list:
    """ Check if YANG entity have 'choice', if so call handler

        Args:
            y_module: reference to 'module'
            y_entity: reference YANG 'container' or 'list' or 'choice' or 'uses'
            conf_mgmt: reference to ConfigMgmt class instance,
                       it have yJson object which contain all parsed YANG model
            grouping_name: if YANG entity contain 'uses', this arg represent 'grouping' name
        Returns:
            list: list of parsed elements inside 'choice'
    """

    if y_entity.get('choice') is not None:
        return on_choices(y_module, y_entity.get('choice'), conf_mgmt, grouping_name)

    return []

def get_uses(y_module: OrderedDict, y_entity: OrderedDict, conf_mgmt: ConfigMgmt) -> list:
    """ Check if YANG entity have 'uses', if so call handler

        Args:
            y_module: reference to 'module'
            y_entity: reference YANG 'container' or 'list' or 'choice' or 'uses'
            conf_mgmt: reference to ConfigMgmt class instance,
                       it have yJson object which contain all parsed YANG model
        Returns:
            list: list of parsed elements inside 'grouping' that referenced by 'uses'
    """

    if y_entity.get('uses') is not None:
        return on_uses(y_module, y_entity.get('uses'), conf_mgmt)

    return []

def get_all_grouping(y_module: OrderedDict, y_uses: OrderedDict, conf_mgmt: ConfigMgmt) -> list:
    """ Get all 'grouping' entities that is referenced by 'uses' in current YANG model

        Args:
            y_module: reference to 'module'
            y_entity: reference to 'uses'
            conf_mgmt: reference to ConfigMgmt class instance,
                       it have yJson object which contain all parsed YANG model
        Returns:
            list: list of 'grouping' elements
    """

    # TODO add to the design statement that grouping should be defined under the 'module' and NOT in nested containers
    ret_grouping = list()
    prefix_list = get_import_prefixes(y_uses)

    # in case if 'grouping' located in the same YANG model
    local_grouping = y_module.get('grouping')
    if local_grouping is not None:
        if isinstance(local_grouping, list):
            for group in local_grouping:
                ret_grouping.append(group)
        else:
            ret_grouping.append(local_grouping)

    # if prefix_list is NOT empty it means that 'grouping' was imported from another YANG model
    if prefix_list != []:
        for prefix in prefix_list:
            y_import = y_module.get('import')
            if isinstance(y_import, list):
                for _import in y_import:
                    if _import.get('prefix').get('@value') == prefix:
                        ret_grouping.extend(get_grouping_from_another_yang_model(_import.get('@module'), conf_mgmt))
            else:
                if y_import.get('prefix').get('@value') == prefix:
                    ret_grouping.extend(get_grouping_from_another_yang_model(y_import.get('@module'), conf_mgmt))

    return ret_grouping

def get_grouping_from_another_yang_model(yang_model_name: str, conf_mgmt) -> list:
    """ Get the YANG 'grouping' entity

        Args:
            yang_model_name - YANG model to search
            conf_mgmt - reference to ConfigMgmt class instance,
                        it have yJson object which contain all parsed YANG models

        Returns:
            list - list 'grouping' entities
    """
    ret_grouping = list()

    for i in range(len(conf_mgmt.sy.yJson)):
        if (conf_mgmt.sy.yJson[i].get('module').get('@name') == yang_model_name):
            grouping = conf_mgmt.sy.yJson[i].get('module').get('grouping')
            if isinstance(grouping, list):
                for group in grouping:
                    ret_grouping.append(group)
            else:
                ret_grouping.append(grouping)

    return ret_grouping

def get_import_prefixes(y_uses: OrderedDict) -> list:
    """ Parse 'import prefix' of YANG 'uses' entity
        Example:
        {
			    uses stypes:endpoint;
        }
        'stypes' - prefix of imported YANG module.
        'endpoint' - YANG 'grouping' entity name

        Args:
            y_uses: refrence to YANG 'uses'
        Returns:
            list - of parsed prefixes
    """
    ret_prefixes = list()

    if isinstance(y_uses, list):
        for use in y_uses:
            prefix = use.get('@name').split(':')[0]
            if prefix != use.get('@name'):
                ret_prefixes.append(prefix)
    else:
        prefix = y_uses.get('@name').split(':')[0]
        if prefix != y_uses.get('@name'):
            ret_prefixes.append(prefix)

    return ret_prefixes

def trim_uses_prefixes(y_uses) -> list:
    """ Trim prefixes from 'uses' YANG entities.
        If YANG 'grouping' was imported from another YANG file, it use 'prefix' before 'grouping' name:
        {
            uses sgrop:endpoint;
        }
        Where 'sgrop' = 'prefix'; 'endpoint' = 'grouping' name.

        Args:
            y_uses - reference to 'uses'
    """

    prefixes = get_import_prefixes(y_uses)

    for prefix in prefixes:
        if isinstance(y_uses, list):
            for use in y_uses:
                if prefix in use.get('@name'):
                    use['@name'] = use.get('@name').split(':')[1]
        else:
            if prefix in y_uses.get('@name'):
                y_uses['@name'] = y_uses.get('@name').split(':')[1]

def get_list_keys(y_list: OrderedDict) -> list:
    """ Parse YANG 'keys'
        If YANG have 'list', inside the list exist 'keys'

        Args:
            y_list: reference to 'list'
        Returns:
            list: parsed keys
    """

    ret_list = list()
    keys = y_list.get('key').get('@value').split()
    for k in keys:
        key = { 'name': k }
        ret_list.append(key)

    return ret_list

def change_dyn_obj_struct(dynamic_objects: OrderedDict):
    """ Rearrange self.yang_2_dict['dynamic_objects'] structure.
        If YANG model have a 'list' entity - inside the 'list' it has 'key' entity.
        'key' entity it is whitespace-separeted list of 'leafs', those 'leafs' was
        parsed by 'on_leaf()' function and placed under 'attrs' in self.yang_2_dict['dynamic_objects']
        need to move 'leafs' from 'attrs' and put them to 'keys' section of elf.yang_2_dict['dynamic_objects']

        Args:
            dynamic_objects: reference to self.yang_2_dict['dynamic_objects']
    """

    for obj in dynamic_objects:
        for key in obj.get('keys'):
            for attr in obj.get('attrs'):
                if key.get('name') == attr.get('name'):
                    key['description'] = attr.get('description')
                    obj['attrs'].remove(attr)
                    break

