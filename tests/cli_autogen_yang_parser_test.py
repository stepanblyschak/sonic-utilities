import os
import logging
import pprint

from sonic_cli_gen.yang_parser import YangParser
from .cli_autogen_input import assert_dictionaries

logger = logging.getLogger(__name__)

test_path = os.path.dirname(os.path.abspath(__file__))
yang_models_path = '/usr/local/yang-models'
test_yang_models = [
    'sonic-1-table-container',
    'sonic-2-table-containers',
    'sonic-1-object-container',
    'sonic-2-object-containers',
    'sonic-1-list',
    'sonic-2-lists',
    'sonic-static-object-complex-1',
    'sonic-static-object-complex-2',
    'sonic-dynamic-object-complex-1',
    'sonic-dynamic-object-complex-2',
    'sonic-choice-complex',
    'sonic-grouping-complex',
    'sonic-grouping-1',
    'sonic-grouping-2',
]


class TestYangParser:
    @classmethod
    def setup_class(cls):
        logger.info("SETUP")
        os.environ['UTILITIES_UNIT_TESTING'] = "1"
        move_yang_models()

    @classmethod
    def teardown_class(cls):
        logger.info("TEARDOWN")
        os.environ['UTILITIES_UNIT_TESTING'] = "0"
        remove_yang_models()

    def test_1_table_container(self):
        """ Test for 1 'table' container
            'table' container represent TABLE in Config DB schema:
            {
                "TABLE": {
                    "OBJECT": {
                        "attr": "value"
                        ...
                    }
                }
            }
        """

        base_test('sonic-1-table-container',
                 assert_dictionaries.one_table_container)

    def test_2_table_containers(self):
        """ Test for 2 'table' containers """

        base_test('sonic-2-table-containers',
                 assert_dictionaries.two_table_containers)

    def test_1_object_container(self):
        """ Test for 1 'object' container
            'object' container represent OBJECT in Config DB schema:
            {
                "TABLE": {
                    "OBJECT": {
                        "attr": "value"
                        ...
                    }
                }
            }
        """

        base_test('sonic-1-object-container',
                 assert_dictionaries.one_object_container)

    def test_2_object_containers(self):
        """ Test for 2 'object' containers """

        base_test('sonic-2-object-containers',
                 assert_dictionaries.two_object_containers)

    def test_1_list(self):
        """ Test for 1 container that has inside
            the YANG 'list' entity
        """

        base_test('sonic-1-list', assert_dictionaries.one_list)

    def test_2_lists(self):
        """ Test for 2 containers that have inside
            the YANG 'list' entity
        """

        base_test('sonic-2-lists', assert_dictionaries.two_lists)

    def test_static_object_complex_1(self):
        """ Test for the object container with:
            1 leaf, 1 leaf-list, 1 choice.
        """

        base_test('sonic-static-object-complex-1',
                 assert_dictionaries.static_object_complex_1)

    def test_static_object_complex_2(self):
        """ Test for object container with:
            2 leafs, 2 leaf-lists, 2 choices.
        """

        base_test('sonic-static-object-complex-2',
                 assert_dictionaries.static_object_complex_2)

    def test_dynamic_object_complex_1(self):
        """ Test for object container with:
            1 key, 1 leaf, 1 leaf-list, 1 choice.
        """

        base_test('sonic-dynamic-object-complex-1',
                 assert_dictionaries.dynamic_object_complex_1)

    def test_dynamic_object_complex_2(self):
        """ Test for object container with:
            2 keys, 2 leafs, 2 leaf-list, 2 choice.
        """

        base_test('sonic-dynamic-object-complex-2',
                 assert_dictionaries.dynamic_object_complex_2)

    def test_choice_complex(self):
        """ Test for object container with the 'choice'
            that have complex strucutre:
            leafs, leaf-lists, multiple 'uses' from different files
        """

        base_test('sonic-choice-complex',
                 assert_dictionaries.choice_complex)

    def test_grouping_complex(self):
        """ Test for object container with multitple 'uses' that using 'grouping'
            from different files. The used 'grouping' have a complex structure:
            leafs, leaf-lists, choices
        """

        base_test('sonic-grouping-complex',
                 assert_dictionaries.grouping_complex)


def base_test(yang_model_name, correct_dict):
    """ General logic for each test case """

    config_db_path = os.path.join(test_path,
                                  'mock_tables/config_db.json')
    parser = YangParser(yang_model_name=yang_model_name,
                        config_db_path=config_db_path,
                        allow_tbl_without_yang=True,
                        debug=False)
    yang_dict = parser.parse_yang_model()
    pretty_log_debug(yang_dict)
    assert yang_dict == correct_dict


def move_yang_models():
    """ Move a test YANG models to known location
        in order to be parsed by YangParser class
    """

    for yang_model in test_yang_models:
        src_path = os.path.join(test_path,
                                'cli_autogen_input',
                                yang_model + '.yang')
        cmd = 'sudo cp {} {}'.format(src_path, yang_models_path)
        os.system(cmd)


def remove_yang_models():
    """ Remove a test YANG models to known location
        in order to be parsed by YangParser class
    """

    for yang_model in test_yang_models:
        yang_model_path = os.path.join(yang_models_path,
                                       yang_model + '.yang')
        cmd = 'sudo rm {}'.format(yang_model_path)
        os.system(cmd)


def pretty_log_debug(dictionary):
    """ Pretty print of parsed dictionary """

    for line in pprint.pformat(dictionary).split('\n'):
        logging.debug(line)

