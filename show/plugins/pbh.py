"""
This CLI plugin was auto-generated by using 'sonic-cli-gen' utility, BUT
it was manually modified to meet the PBH HLD requirements.

PBH HLD - https://github.com/Azure/SONiC/pull/773
CLI Auto-generation tool HLD - https://github.com/Azure/SONiC/pull/78
"""

import os
import click
import tabulate
import natsort
import json
import utilities_common.cli as clicommon
from swsscommon.swsscommon import SonicV2Connector

PBH_COUNTERS_LOCATION = '/tmp/.pbh_counters.txt'

COUNTER_PACKETS_ATTR = "SAI_ACL_COUNTER_ATTR_PACKETS"
COUNTER_BYTES_ATTR = "SAI_ACL_COUNTER_ATTR_BYTES"

COUNTERS = "COUNTERS"
ACL_COUNTER_RULE_MAP = "ACL_COUNTER_RULE_MAP"

pbh_hash_field_tbl_name = 'PBH_HASH_FIELD'
pbh_hash_tbl_name = 'PBH_HASH'
pbh_table_tbl_name = 'PBH_TABLE'
pbh_rule_tbl_name = 'PBH_RULE'


def format_attr_value(entry, attr):
    """ Helper that formats attribute to be presented in the table output.

        Args:
            entry (Dict[str, str]): CONFIG DB entry configuration.
            attr (Dict): Attribute metadata.

        Returns:
            str: fomatted attribute value.
    """

    if attr["is-leaf-list"]:
        return "\n".join(entry.get(attr["name"], []))

    return entry.get(attr["name"], "N/A")


def format_group_value(entry, attrs):
    """ Helper that formats grouped attribute to be presented in the table output.

        Args:
            entry (Dict[str, str]): CONFIG DB entry configuration.
            attrs (List[Dict]): Attributes metadata that belongs to the same group.

        Returns:
            str: fomatted group attributes.
    """

    data = []
    for attr in attrs:
        if entry.get(attr["name"]):
            data.append((attr["name"] + ":", format_attr_value(entry, attr)))

    return tabulate.tabulate(data, tablefmt="plain", numalign="left")


@click.group(
    name='pbh',
    cls=clicommon.AliasedGroup
)
def PBH():
    """ Show PBH (Policy based hashing) feature configuration """

    pass


@PBH.group(
    name="hash-field",
    cls=clicommon.AliasedGroup,
    invoke_without_command=True
)
@clicommon.pass_db
def PBH_HASH_FIELD(db):
    """  Show the PBH hash field configuration """

    header = [
        "NAME",
        "FIELD",
        "MASK",
        "SEQUENCE",
        "SYMMETRIC",
    ]

    body = []

    table = db.cfgdb.get_table(pbh_hash_field_tbl_name)
    for key in natsort.natsorted(table):

        entry = table[key]

        if not isinstance(key, tuple):
            key = (key,)

        row = [*key] + [
            format_attr_value(
                entry,
                {
                    'name': 'hash_field',
                    'description': 'Configures native hash field for this hash field',
                    'is-leaf-list': False,
                    'is-mandatory': True,
                    'group': ''
                }
            ),
            format_attr_value(
                entry,
                {
                    'name': 'ip_mask',
                    'description': 'Configures IPv4/IPv6 address mask for this hash field',
                    'is-leaf-list': False,
                    'is-mandatory': True,
                    'group': ''
                }
            ),
            format_attr_value(
                entry,
                {
                    'name': 'sequence_id',
                    'description': 'Configures in which order the fields are hashed and defines which fields should be associative',
                    'is-leaf-list': False,
                    'is-mandatory': True,
                    'group': ''
                }
            ),
        ]

        body.append(row)

    # sorted by 'sequence_id'
    body_sorted = sorted(body, key=lambda e: int(e[3]))
    inject_symmetric_field(body_sorted)
    click.echo(tabulate.tabulate(body_sorted, header, numalign="left"))


@PBH.group(
    name="hash",
    cls=clicommon.AliasedGroup,
    invoke_without_command=True
)
@clicommon.pass_db
def PBH_HASH(db):
    """  Show the PBH hash configuration """

    header = [
        "NAME",
        "HASH FIELD",
    ]

    body = []

    table = db.cfgdb.get_table(pbh_hash_tbl_name)
    for key in natsort.natsorted(table):
        entry = table[key]
        if not isinstance(key, tuple):
            key = (key,)

        row = [*key] + [
            format_attr_value(
                entry,
                {
                    'name': 'hash_field_list',
                    'description': 'The list of hash fields to apply with this hash',
                    'is-leaf-list': True,
                    'is-mandatory': False,
                    'group': ''
                }
            ),
        ]

        body.append(row)

    click.echo(tabulate.tabulate(body, header, numalign="left"))


@PBH.group(
    name="rule",
    cls=clicommon.AliasedGroup,
    invoke_without_command=True
)
@clicommon.pass_db
def PBH_RULE(db):
    """  Show the PBH rules configuration """

    header = [
        "TABLE",
        "RULE",
        "PRIORITY",
        "MATCH",
        "HASH",
        "ACTION",
        "COUNTER",
    ]

    body = []

    table = db.cfgdb.get_table(pbh_rule_tbl_name)
    for key in natsort.natsorted(table):
        entry = table[key]
        if not isinstance(key, tuple):
            key = (key,)

        row = [*key] + [
            format_attr_value(
                entry,
                {
                    'name': 'priority',
                    'description': 'Configures priority for this rule',
                    'is-leaf-list': False,
                    'is-mandatory': True,
                    'group': ''
                }
            ),
            format_group_value(
                entry,
                [
                    {
                        'name': 'gre_key',
                        'description': 'Configures packet match for this rule: GRE key (value/mask)',
                        'is-leaf-list':False,
                        'is-mandatory': False,
                        'group': 'Match'
                    },
                    {
                        'name': 'ether_type',
                        'description': 'Configures packet match for this rule: EtherType (IANA Ethertypes)',
                        'is-leaf-list': False,
                        'is-mandatory': False,
                        'group': 'Match'
                    },
                    {
                        'name': 'ip_protocol',
                        'description': 'Configures packet match for this rule: IP protocol (value/mask)',
                        'is-leaf-list': False,
                        'is-mandatory': False,
                        'group': 'Match'
                    },
                    {
                        'name': 'ipv6_next_header',
                        'description': 'Configures packet match for this rule: IPv6 Next header (value/mask)',
                        'is-leaf-list': False,
                        'is-mandatory': False,
                        'group': 'Match'
                    },
                    {
                        'name': 'l4_dst_port',
                        'description': 'Configures packet match for this rule: L4 destination port (value/mask)',
                        'is-leaf-list': False,
                        'is-mandatory': False,
                        'group': 'Match'
                    },
                    {
                        'name': 'inner_ether_type',
                        'description': 'Configures packet match for this rule: inner EtherType (value/mask)',
                        'is-leaf-list': False,
                        'is-mandatory': False,
                        'group': 'Match'
                    },
                ]
            ),
            format_attr_value(
                entry,
                {
                    'name': 'hash',
                    'description':'The hash to apply with this rule',
                    'is-leaf-list': False,
                    'is-mandatory': True,
                    'group': ''}
            ),
            format_attr_value(
                entry,
                {
                    'name': 'packet_action',
                    'description': 'Configures packet action for this rule',
                    'is-leaf-list': False,
                    'is-mandatory': False,
                    'group': ''
                }
            ),
            format_attr_value(
                entry,
                {
                    'name': 'flow_counter',
                    'description': 'Configures packet action for this rule',
                    'is-leaf-list': False,
                    'is-mandatory': False,
                    'group': ''
                }
            ),
        ]

        body.append(row)

    # sorted by 'Priority'
    body_sorted = sorted(body, key=lambda e: int(e[2]), reverse=True)
    click.echo(tabulate.tabulate(body_sorted, header, numalign="left"))


@PBH.group(
    name="table",
    cls=clicommon.AliasedGroup,
    invoke_without_command=True
)
@clicommon.pass_db
def PBH_TABLE(db):
    """  Show the PBH table configuration """

    header = [
        "NAME",
        "INTERFACE",
        "DESCRIPTION",
    ]

    body = []

    table = db.cfgdb.get_table(pbh_table_tbl_name)
    for key in natsort.natsorted(table):
        entry = table[key]
        if not isinstance(key, tuple):
            key = (key,)

        row = [*key] + [
            format_attr_value(
                entry,
                {
                    'name': 'interface_list',
                    'description': 'Interfaces to which this table is applied',
                    'is-leaf-list': True,
                    'is-mandatory': False,
                    'group': ''
                }
            ),
            format_attr_value(
                entry,
                {
                    'name': 'description',
                    'description': 'The description of this table',
                    'is-leaf-list': False,
                    'is-mandatory': True,
                    'group': ''
                }
            ),
        ]

        body.append(row)

    click.echo(tabulate.tabulate(body, header, numalign="left"))


@PBH.group(
    name="statistics",
    cls=clicommon.AliasedGroup,
    invoke_without_command=True
)
@clicommon.pass_db
def PBH_STATISTICS(db):
    """  Show the PBH counters """

    header = [
        "TABLE",
        "RULE",
        "RX PACKETS COUNT",
        "RX BYTES COUNT",
    ]

    body = []

    pbh_rules = db.cfgdb.get_table(pbh_rule_tbl_name)
    pbh_counters = read_pbh_counters(pbh_rules)
    saved_pbh_counters = read_saved_pbh_counters()

    for key in pbh_rules:
        if pbh_rules[key]['flow_counter'] == 'ENABLED':
            row = [
                key[0],
                key[1],
                get_counter_value(pbh_counters, saved_pbh_counters, key, COUNTER_PACKETS_ATTR),
                get_counter_value(pbh_counters, saved_pbh_counters, key, COUNTER_BYTES_ATTR),
            ]
            body.append(row)

    click.echo(tabulate.tabulate(body, header, numalign="left"))


def get_counter_value(pbh_counters, saved_pbh_counters, key, type):
    if not pbh_counters[key]:
        return '0'

    if key in saved_pbh_counters:
        new_value = int(pbh_counters[key][type]) - int(saved_pbh_counters[key][type])
        if new_value >= 0:
            return str(new_value)

    return str(pbh_counters[key][type])


def remap_keys(obj_list):
    res = {}
    for e in obj_list:
        res[e['key'][0], e['key'][1]] = e['value']
    return res


def read_saved_pbh_counters():
    if os.path.isfile(PBH_COUNTERS_LOCATION):
        try:
            with open(PBH_COUNTERS_LOCATION) as fp:
                return remap_keys(json.load(fp))
        except Exception:
            return {}

    return {}


def read_pbh_counters(pbh_rules) -> dict:
    pbh_counters = {}

    db_connector = SonicV2Connector(use_unix_socket_path=False)
    db_connector.connect(db_connector.COUNTERS_DB)
    counters_db_separator = db_connector.get_db_separator(db_connector.COUNTERS_DB)
    rule_to_counter_map = db_connector.get_all(db_connector.COUNTERS_DB, ACL_COUNTER_RULE_MAP)

    for table, rule in natsort.natsorted(pbh_rules):
        pbh_counters[table, rule] = {}
        rule_identifier = table + counters_db_separator + rule
        if not rule_to_counter_map:
            continue
        counter_oid = rule_to_counter_map.get(rule_identifier)
        if not counter_oid:
            continue
        counters_db_key = COUNTERS + counters_db_separator + counter_oid
        counter_props = db_connector.get_all(db_connector.COUNTERS_DB, counters_db_key)
        if counter_props:
            pbh_counters[table, rule] = counter_props

    return pbh_counters


def inject_symmetric_field(obj_list):
    """ The 'Symmetric' parameter will have 'Yes' value
        if there are 2 'pbh hash fields' with identical 'sequence_id' value

        Args:
            obj_list: a row of pbh hash fields that will be
                displayed to the user
    """

    sequence_id = 3
    counter = 0

    for i in range(0, len(obj_list)):
        for j in range(0, len(obj_list)):
            if i == j:
                continue

            if obj_list[i][sequence_id] == obj_list[j][sequence_id]:
                counter += 1

        if counter >= 1:
            obj_list[i].append('Yes')
        else:
            obj_list[i].append('No')

        counter = 0


def register(cli):
    cli_node = PBH
    if cli_node.name in cli.commands:
        raise Exception(f"{cli_node.name} already exists in CLI")
    cli.add_command(PBH)

