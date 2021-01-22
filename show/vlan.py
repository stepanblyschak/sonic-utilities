import click
from natsort import natsorted
from tabulate import tabulate

import utilities_common.cli as clicommon


@click.group(cls=clicommon.AliasedGroup)
def vlan():
    """Show VLAN information"""
    pass


def get_vlan_id(ctx, vlan):
    vlan_prefix, vid = vlan.split('Vlan')
    return vid


def get_vlan_ip_address(ctx, vlan):
    cfg, _ = ctx
    _, vlan_ip_data, _ = cfg
    ip_address = ""
    for key in vlan_ip_data:
        if not clicommon.is_ip_prefix_in_key(key):
            continue
        ifname, address = key
        if vlan == ifname:
            ip_address += "\n{}".format(address)

    return ip_address


def get_vlan_ports(ctx, vlan):
    cfg, db = ctx
    _, _, vlan_ports_data = cfg
    vlan_ports = []
    iface_alias_converter = clicommon.InterfaceAliasConverter(db)
    # Here natsorting is important in relation to another
    # column which prints port tagging mode.
    # If we sort both in the same way using same keys
    # we will result in right order in both columns.
    # This should be fixed by cli code autogeneration tool
    # and we won't need this specific approach with
    # VlanBrief.COLUMNS anymore.
    for key in natsorted(list(vlan_ports_data.keys())):
        ports_key, ports_value = key
        if vlan != ports_key:
            continue

        if clicommon.get_interface_naming_mode() == "alias":
            ports_value = iface_alias_converter.name_to_alias(ports_value)

        vlan_ports.append(ports_value)

    return '\n'.join(vlan_ports)


def get_vlan_ports_tagging(ctx, vlan):
    cfg, db = ctx
    _, _, vlan_ports_data = cfg
    vlan_ports_tagging = []
    # Here natsorting is important in relation to another
    # column which prints port tagging mode.
    # If we sort both in the same way using same keys
    # we will result in right order in both columns.
    # This should be fixed by cli code autogeneration tool
    # and we won't need this specific approach with
    # VlanBrief.COLUMNS anymore.
    for key in natsorted(list(vlan_ports_data.keys())):
        ports_key, ports_value = key
        if vlan != ports_key:
            continue

        tagging_value = vlan_ports_data[key]["tagging_mode"]
        vlan_ports_tagging.append(tagging_value)

    return '\n'.join(vlan_ports_tagging)


def get_proxy_arp(ctx, vlan):
    cfg, _ = ctx
    _, vlan_ip_data, _ = cfg
    proxy_arp = "disabled"
    for key in vlan_ip_data:
        if clicommon.is_ip_prefix_in_key(key):
            continue
        if vlan == key:
            proxy_arp = vlan_ip_data[key].get("proxy_arp", "disabled")

    return proxy_arp


class VlanBrief:
    """ This class is used as a namespace to
    define columns for "show vlan brief" command.
    The usage of this class is for external plugin
    (in this case dhcp-relay) to append new columns
    to this list.
    """

    COLUMNS = [
        ("VLAN ID", get_vlan_id),
        ("IP Address", get_vlan_ip_address),
        ("Ports", get_vlan_ports),
        ("Port Tagging", get_vlan_ports_tagging),
        ("Proxy ARP", get_proxy_arp)
    ]


@vlan.command()
@click.option('--verbose', is_flag=True, help="Enable verbose output")
@clicommon.pass_db
def brief(db, verbose):
    """Show all bridge information"""
    header = [colname for colname, getter in VlanBrief.COLUMNS]
    body = []

    # Fetching data from config db for VLAN, VLAN_INTERFACE and VLAN_MEMBER
    vlan_data = db.cfgdb.get_table('VLAN')
    vlan_ip_data = db.cfgdb.get_table('VLAN_INTERFACE')
    vlan_ports_data = db.cfgdb.get_table('VLAN_MEMBER')
    vlan_cfg = (vlan_data, vlan_ip_data, vlan_ports_data)

    for vlan in natsorted(vlan_data):
        row = []
        for column in VlanBrief.COLUMNS:
            column_name, getter = column
            row.append(getter((vlan_cfg, db), vlan))
        body.append(row)

    click.echo(tabulate(body, header, tablefmt="grid"))


@vlan.command()
@clicommon.pass_db
def config(db):
    data = db.cfgdb.get_table('VLAN')
    keys = list(data.keys())
    member_data = db.cfgdb.get_table('VLAN_MEMBER')

    def tablelize(keys, data):
        table = []

        for k in natsorted(keys):
            members = set(data[k].get('members', []))
            for (vlan, interface_name) in member_data:
                if vlan == k:
                    members.add(interface_name)

            for m in natsorted(list(members)):
                r = []
                r.append(k)
                r.append(data[k]['vlanid'])
                if clicommon.get_interface_naming_mode() == "alias":
                    alias = clicommon.InterfaceAliasConverter(db).name_to_alias(m)
                    r.append(alias)
                else:
                    r.append(m)

                entry = db.cfgdb.get_entry('VLAN_MEMBER', (k, m))
                mode = entry.get('tagging_mode')
                if mode is None:
                    r.append('?')
                else:
                    r.append(mode)

                table.append(r)

        return table

    header = ['Name', 'VID', 'Member', 'Mode']
    click.echo(tabulate(tablelize(keys, data), header))

