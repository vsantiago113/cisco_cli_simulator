#!/usr/bin/env python

import argparse
import atexit
import os
import re
import sys

try:
    import readline
except ImportError:
    readline = None


HISTORY_FILE = os.path.expanduser('~/.ios_show_file_history')
HISTORY_LENGTH = 1000
DEFAULT_CONFIG_ROOT = 'config'
DEFAULT_SWITCH_CONFIG_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'switch')
DEFAULT_ROUTER_CONFIG_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'router')
SHOW_VERSION_FILE = 'Show_Version.txt'
SHOW_RUNNING_CONFIG_FILE = 'Show_running-config.txt'
SHOW_RUNNING_CONFIG_ALL_FILE = 'Show_running-config_all.txt'
OPTIONAL_SHOW_OUTPUT_FILES = {
    'show ip interface brief': 'Show_ip_interface_brief.txt',
    'show interfaces': 'Show_interfaces.txt',
    'show interfaces status': 'Show_interfaces_status.txt',
    'show interfaces description': 'Show_interfaces_description.txt',
    'show controllers': 'Show_controllers.txt',
    'show ip route': 'Show_ip_route.txt',
    'show ip arp': 'Show_ip_arp.txt',
    'show ip cef': 'Show_ip_cef.txt',
    'show access-lists': 'Show_access-lists.txt',
    'show logging': 'Show_logging.txt',
    'show clock': 'Show_clock.txt',
    'show users': 'Show_users.txt',
    'show vrf': 'Show_vrf.txt',
    'show ip vrf': 'Show_ip_vrf.txt',
    'show mac address-table': 'Show_mac_address-table.txt',
    'show cdp neighbors': 'Show_cdp_neighbors.txt',
    'show cdp neighbors detail': 'Show_cdp_neighbors_detail.txt',
    'show lldp neighbors': 'Show_lldp_neighbors.txt',
    'show spanning-tree': 'Show_spanning-tree.txt',
    'show etherchannel summary': 'Show_etherchannel_summary.txt',
    'show power inline': 'Show_power_inline.txt',
    'show inventory': 'Show_inventory.txt',
    'show environment all': 'Show_environment_all.txt',
    'show license summary': 'Show_license_summary.txt',
    'show platform': 'Show_platform.txt',
    'show ip protocols': 'Show_ip_protocols.txt',
    'show ip bgp summary': 'Show_ip_bgp_summary.txt',
    'show ip ospf neighbor': 'Show_ip_ospf_neighbor.txt',
    'show ip eigrp neighbors': 'Show_ip_eigrp_neighbors.txt',
    'show ip nat translations': 'Show_ip_nat_translations.txt',
    'show ip nat statistics': 'Show_ip_nat_statistics.txt',
    'show crypto isakmp sa': 'Show_crypto_isakmp_sa.txt',
    'show crypto ipsec sa': 'Show_crypto_ipsec_sa.txt',
    'show standby brief': 'Show_standby_brief.txt',
}
SWITCH_ONLY_COMMANDS = set([
    'show interfaces status',
    'show mac address-table',
    'show spanning-tree',
    'show etherchannel summary',
    'show power inline',
])
ROUTER_ONLY_COMMANDS = set([
    'show controllers',
    'show ip nat translations',
    'show ip nat statistics',
    'show crypto isakmp sa',
    'show crypto ipsec sa',
    'show standby brief',
])
COMMON_COMMANDS = set(OPTIONAL_SHOW_OUTPUT_FILES.keys()) - SWITCH_ONLY_COMMANDS - ROUTER_ONLY_COMMANDS


def setup_history():
    if readline is None:
        return

    if os.path.exists(HISTORY_FILE):
        try:
            readline.read_history_file(HISTORY_FILE)
        except OSError:
            pass

    readline.set_history_length(HISTORY_LENGTH)
    atexit.register(save_history)


def save_history():
    if readline is None:
        return

    try:
        readline.write_history_file(HISTORY_FILE)
    except OSError:
        pass


def is_unique_prefix(token, word):
    return word.startswith(token)


def expand_command(user_input, valid_commands):
    tokens = user_input.strip().split()
    if not tokens:
        raise ValueError('Empty command')

    matches = []

    for command in valid_commands:
        command_tokens = command.split()

        if len(tokens) > len(command_tokens):
            continue

        ok = True
        for user_token, real_token in zip(tokens, command_tokens):
            if not is_unique_prefix(user_token, real_token):
                ok = False
                break

        if ok:
            matches.append(command)

    if not matches:
        raise ValueError('Invalid command: {0}'.format(user_input))

    if len(matches) > 1:
        raise ValueError(
            'Ambiguous command: {0}. Possible matches: {1}'.format(
                user_input,
                ', '.join(matches),
            )
        )

    return matches[0]


def split_command_and_pipe(command):
    if '|' in command:
        parts = [part.strip() for part in command.split('|', 1)]
        return parts[0], parts[1]

    return command, None


def apply_pipe_filter(output, pipe_part):
    if not pipe_part:
        return output

    valid_filters = ['include', 'exclude', 'begin', 'section']
    pipe_tokens = pipe_part.split(None, 1)

    if len(pipe_tokens) != 2:
        raise ValueError('% Invalid input detected at \'^\' marker.')

    filter_cmd_raw = pipe_tokens[0]
    filter_value = pipe_tokens[1]

    expanded_filter = expand_command(
        filter_cmd_raw,
        valid_filters,
    )

    filter_map = {
        'include': filter_include,
        'exclude': filter_exclude,
        'begin': filter_begin,
        'section': filter_section,
    }

    return filter_map[expanded_filter](output.splitlines(), filter_value)


def read_config_file(path):
    handle = open(path, 'r')
    try:
        return handle.read().splitlines()
    finally:
        handle.close()


def require_config_file(path):
    if not os.path.exists(path):
        raise ValueError('Missing required device file: {0}'.format(path))

    return read_config_file(path)


def load_optional_show_outputs(config_dir):
    show_outputs = {}

    for command, filename in OPTIONAL_SHOW_OUTPUT_FILES.items():
        path = os.path.join(config_dir, filename)
        if os.path.exists(path):
            show_outputs[command] = read_config_file(path)

    return show_outputs


def normalize_device_type(device_type):
    if device_type in ['switch', 'router']:
        return device_type

    return 'auto'


def default_config_path_for_device_type(device_type):
    if device_type == 'router':
        return DEFAULT_ROUTER_CONFIG_DIR

    return DEFAULT_SWITCH_CONFIG_DIR


def infer_device_type(running_config, show_version, show_outputs):
    combined_lines = running_config + show_version
    combined_text = '\n'.join(combined_lines).lower()

    switch_signals = [
        'switchport',
        'spanning-tree',
        'vlan ',
        'catalyst',
        'c9300',
        'c9200',
        'c9500',
    ]
    router_signals = [
        'ip nat inside',
        'ip nat outside',
        'crypto map',
        'tunnel',
        'router bgp',
        'isr',
        'asr',
        'c8300',
        'c8200',
    ]

    switch_score = len(SWITCH_ONLY_COMMANDS.intersection(show_outputs.keys()))
    router_score = len(ROUTER_ONLY_COMMANDS.intersection(show_outputs.keys()))

    for signal in switch_signals:
        if signal in combined_text:
            switch_score += 1

    for signal in router_signals:
        if signal in combined_text:
            router_score += 1

    if router_score > switch_score:
        return 'router'

    return 'switch'


def parse_hostname(running_config):
    for line in running_config:
        parts = line.split()
        if len(parts) == 2 and parts[0] == 'hostname':
            return parts[1]

    return 'Switch'


def build_device(show_version, running_config, running_config_all, show_outputs, device_type):
    normalized_type = normalize_device_type(device_type)
    if normalized_type == 'auto':
        normalized_type = infer_device_type(
            running_config,
            show_version,
            show_outputs,
        )

    return {
        'device_type': normalized_type,
        'hostname': parse_hostname(running_config),
        'show_version': show_version,
        'running_config': running_config,
        'running_config_all': running_config_all,
        'show_outputs': show_outputs,
    }


def guess_all_config_path(config_file):
    directory = os.path.dirname(config_file)
    filename = os.path.basename(config_file)
    root, extension = os.path.splitext(filename)

    if root.endswith('_all'):
        return config_file

    candidates = [
        os.path.join(directory, root + '_all' + extension),
        os.path.join(directory, 'show_run_all.txt'),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return None


def load_device_config(
    config_path=None,
    all_config_file=None,
    version_file=None,
    device_type='auto',
):
    if config_path is None:
        config_path = default_config_path_for_device_type(device_type)

    if os.path.isdir(config_path):
        running_config_file = os.path.join(config_path, SHOW_RUNNING_CONFIG_FILE)
        running_config_all_file = os.path.join(
            config_path,
            SHOW_RUNNING_CONFIG_ALL_FILE,
        )
        show_version_file = os.path.join(config_path, SHOW_VERSION_FILE)

        return build_device(
            require_config_file(show_version_file),
            require_config_file(running_config_file),
            require_config_file(running_config_all_file),
            load_optional_show_outputs(config_path),
            device_type,
        )

    running_config = read_config_file(config_path)

    if all_config_file is None:
        all_config_file = guess_all_config_path(config_path)

    if all_config_file and os.path.exists(all_config_file):
        running_config_all = read_config_file(all_config_file)
    else:
        running_config_all = running_config

    if version_file is None:
        candidate = os.path.join(
            default_config_path_for_device_type(device_type),
            SHOW_VERSION_FILE,
        )
        if os.path.exists(candidate):
            version_file = candidate

    if version_file and os.path.exists(version_file):
        show_version = read_config_file(version_file)
    else:
        show_version = []

    return build_device(
        show_version,
        running_config,
        running_config_all,
        {},
        device_type,
    )


def show_running_config(lines):
    return '\n'.join(lines)


def filter_include(lines, pattern):
    regex = re.compile(pattern)
    return '\n'.join([line for line in lines if regex.search(line)])


def filter_exclude(lines, pattern):
    regex = re.compile(pattern)
    return '\n'.join([line for line in lines if not regex.search(line)])


def filter_begin(lines, pattern):
    regex = re.compile(pattern)

    for index, line in enumerate(lines):
        if regex.search(line):
            return '\n'.join(lines[index:])

    return ''


def filter_section(lines, pattern):
    regex = re.compile(pattern)
    sections = []
    current_section = []

    for line in lines:
        if line and not line.startswith(' '):
            if current_section:
                sections.append(current_section)
            current_section = [line]
        else:
            current_section.append(line)

    if current_section:
        sections.append(current_section)

    matched_sections = []
    for section in sections:
        if section and regex.search(section[0]):
            matched_sections.append('\n'.join(section))

    return '\n'.join(matched_sections)


def parse_interfaces(lines):
    interfaces = []
    current = None

    for line in lines:
        stripped = line.strip()

        if line.startswith('interface '):
            if current:
                interfaces.append(current)

            name = line.split(None, 1)[1]
            current = {
                'name': name,
                'ip_address': 'unassigned',
                'admin_status': 'up',
                'protocol_status': 'up',
                'description': '',
            }
            continue

        if current is None:
            continue

        if not line.startswith(' '):
            interfaces.append(current)
            current = None
            continue

        if stripped == 'shutdown':
            current['admin_status'] = 'administratively down'
            current['protocol_status'] = 'down'
        elif stripped.startswith('ip address '):
            parts = stripped.split()
            if len(parts) >= 4 and parts[2].lower() != 'dhcp':
                current['ip_address'] = parts[2]
            elif len(parts) >= 3 and parts[2].lower() == 'dhcp':
                current['ip_address'] = 'dhcp'
        elif stripped == 'no ip address':
            current['ip_address'] = 'unassigned'
        elif stripped.startswith('description '):
            current['description'] = stripped[len('description '):]

    if current:
        interfaces.append(current)

    return interfaces


def normalize_interface_name(value):
    normalized = value.lower().replace(' ', '')

    aliases = [
        ('gigabitethernet', 'gigabitethernet'),
        ('gig', 'gigabitethernet'),
        ('gi', 'gigabitethernet'),
        ('tengigabitethernet', 'tengigabitethernet'),
        ('tengig', 'tengigabitethernet'),
        ('te', 'tengigabitethernet'),
        ('port-channel', 'port-channel'),
        ('portchannel', 'port-channel'),
        ('po', 'port-channel'),
        ('vlan', 'vlan'),
    ]

    for alias, real_name in aliases:
        if normalized.startswith(alias):
            return real_name + normalized[len(alias):]

    return normalized


def interface_matches(interface, selector):
    if not selector:
        return True

    interface_name = normalize_interface_name(interface['name'])
    selector_name = normalize_interface_name(selector)

    if re.search(r'\d', selector_name):
        return interface_name == selector_name

    return interface_name.startswith(selector_name)


def format_show_ip_interface_brief(interfaces):
    output = []
    output.append(
        '{0:<24} {1:<17} {2:<3} {3:<6} {4:<20} {5}'.format(
            'Interface',
            'IP-Address',
            'OK?',
            'Method',
            'Status',
            'Protocol',
        )
    )

    for interface in interfaces:
        if interface['ip_address'] == 'unassigned':
            method = 'unset'
        elif interface['ip_address'] == 'dhcp':
            method = 'DHCP'
        else:
            method = 'manual'

        output.append(
            '{0:<24} {1:<17} {2:<3} {3:<6} {4:<20} {5}'.format(
                interface['name'][:24],
                interface['ip_address'][:17],
                'YES',
                method[:6],
                interface['admin_status'][:20],
                interface['protocol_status'],
            )
        )

    return '\n'.join(output)


def format_show_ip_interface(interfaces, selector=None):
    output = []

    for interface in interfaces:
        if not interface_matches(interface, selector):
            continue

        output.append(
            '{0} is {1}, line protocol is {2}'.format(
                interface['name'],
                interface['admin_status'],
                interface['protocol_status'],
            )
        )

        if interface['description']:
            output.append('  Description: {0}'.format(interface['description']))

        if interface['ip_address'] == 'unassigned':
            output.append('  Internet protocol processing disabled')
        elif interface['ip_address'] == 'dhcp':
            output.append('  Internet address will be negotiated using DHCP')
        else:
            output.append('  Internet address is {0}'.format(interface['ip_address']))

        output.append('')

    if not output:
        raise ValueError('Invalid interface: {0}'.format(selector))

    return '\n'.join(output).rstrip()


def format_show_interfaces_description(interfaces):
    output = []
    output.append(
        '{0:<24} {1:<12} {2:<12} {3}'.format(
            'Interface',
            'Status',
            'Protocol',
            'Description',
        )
    )

    for interface in interfaces:
        if interface['admin_status'] == 'administratively down':
            status = 'admin down'
        else:
            status = interface['admin_status']

        output.append(
            '{0:<24} {1:<12} {2:<12} {3}'.format(
                interface['name'][:24],
                status[:12],
                interface['protocol_status'][:12],
                interface['description'],
            )
        )

    return '\n'.join(output)


def normalize_line_name(value):
    tokens = value.lower().split()

    if tokens and tokens[0].startswith('console'):
        tokens[0] = 'con'

    return ' '.join(tokens)


def parse_line_selector(value):
    if not value:
        return None

    tokens = normalize_line_name(value).split()
    if not tokens:
        return None

    kind = tokens[0]
    if 'vty'.startswith(kind):
        kind = 'vty'
    elif 'con'.startswith(kind):
        kind = 'con'

    numbers = []
    for token in tokens[1:]:
        if not token.isdigit():
            return {
                'kind': kind,
                'start': None,
                'end': None,
            }
        numbers.append(int(token))

    if not numbers:
        start = None
        end = None
    elif len(numbers) == 1:
        start = numbers[0]
        end = numbers[0]
    else:
        start = numbers[0]
        end = numbers[1]

    return {
        'kind': kind,
        'start': start,
        'end': end,
    }


def line_selector_is_specific(selector_info):
    return (
        selector_info is not None
        and selector_info['start'] is not None
        and selector_info['start'] == selector_info['end']
    )


def parse_line_configs(lines):
    line_configs = []
    current = None

    for line in lines:
        stripped = line.strip()

        if line.startswith('line '):
            if current:
                line_configs.append(current)

            current = {
                'name': line.split(None, 1)[1],
                'access_class': '-',
                'exec_timeout': 'default',
                'logging': '-',
                'transport_input': '-',
                'transport_output': '-',
            }
            continue

        if current is None:
            continue

        if not line.startswith(' '):
            line_configs.append(current)
            current = None
            continue

        if stripped.startswith('access-class '):
            current['access_class'] = stripped[len('access-class '):]
        elif stripped.startswith('exec-timeout '):
            current['exec_timeout'] = stripped[len('exec-timeout '):]
        elif stripped == 'logging synchronous':
            current['logging'] = 'synchronous'
        elif stripped.startswith('transport input '):
            current['transport_input'] = stripped[len('transport input '):]
        elif stripped.startswith('transport output '):
            current['transport_output'] = stripped[len('transport output '):]

    if current:
        line_configs.append(current)

    return line_configs


def line_matches(line_config, selector):
    if not selector:
        return True

    line_info = parse_line_selector(line_config['name'])
    selector_info = parse_line_selector(selector)

    if line_info is None or selector_info is None:
        return False

    if line_info['kind'] != selector_info['kind']:
        return False

    if selector_info['start'] is None:
        return True

    if line_info['start'] is None:
        return False

    return (
        selector_info['start'] <= line_info['end']
        and selector_info['end'] >= line_info['start']
    )


def format_exec_timeout(timeout_value):
    if timeout_value == 'default':
        return 'default'

    parts = timeout_value.split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return '{0} minutes, {1} seconds'.format(parts[0], parts[1])

    return timeout_value


def format_exec_timeout_clock(timeout_value):
    if timeout_value == 'default':
        return 'never'

    parts = timeout_value.split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return '00:{0:02d}:{1:02d}'.format(int(parts[0]), int(parts[1]))

    return timeout_value


def selected_line_number(line_config, selector_info):
    if line_selector_is_specific(selector_info):
        return selector_info['start']

    line_info = parse_line_selector(line_config['name'])
    if line_info and line_info['start'] is not None:
        return line_info['start']

    return 0


def line_access_classes(line_config):
    access_class = line_config['access_class']

    if access_class == '-':
        return '-', '-'

    parts = access_class.split()
    if len(parts) >= 2 and parts[-1] == 'in':
        return '-', ' '.join(parts[:-1])
    if len(parts) >= 2 and parts[-1] == 'out':
        return ' '.join(parts[:-1]), '-'

    return '-', access_class


def format_show_line_detail(line_config, selector_info):
    line_name = line_config['name']
    line_type = line_name.split()[0].upper()
    tty_number = selected_line_number(line_config, selector_info)
    access_class_out, access_class_in = line_access_classes(line_config)

    if line_selector_is_specific(selector_info):
        line_name = '{0} {1}'.format(
            selector_info['kind'],
            selector_info['start'],
        )
        line_type = selector_info['kind'].upper()

    output = []
    output.append(
        '   Tty Line Typ     Tx/Rx    A Modem  Roty AccO AccI  Uses  Noise Overruns  Int'
    )
    output.append(
        '{0:>6} {1:>4} {2:<7}          -    -      - {3:>4} {4:>4}{5:>6}{6:>7}    {7:<9} -'.format(
            tty_number,
            tty_number,
            line_type,
            access_class_out,
            access_class_in,
            0,
            0,
            '0/0',
        )
    )
    output.append('')
    output.append('Line {0}, Location: "", Type: ""'.format(tty_number))
    output.append('Length: 24 lines, Width: 80 columns')
    output.append('Baud rate (TX/RX) is 9600/9600')
    output.append('Status: No Exit Banner')
    output.append('Capabilities: none')
    output.append('Modem state: Idle')
    output.append('Special Chars: Escape  Hold  Stop  Start  Disconnect  Activation')
    output.append('                ^^x     none  -     -      none')
    output.append('Timeouts:      Idle EXEC    Idle Session   Modem Answer  Session   Dispatch')
    output.append(
        '               {0:<15}never                        none     not set'.format(
            format_exec_timeout_clock(line_config['exec_timeout'])
        )
    )
    output.append('                            Idle Session Disconnect Warning')
    output.append('                              never')
    output.append('                            Login-sequence User Response')
    output.append('                             00:00:30')
    output.append('                            Autoselect Initial Wait')
    output.append('                              not set')
    output.append('Modem type is unknown.')
    output.append('Session limit is not set.')
    output.append('Time since activation: never')
    output.append('Editing is enabled.')
    output.append('History is enabled, history size is 10.')
    output.append('DNS resolution in show commands is enabled')
    output.append('Full user help is disabled')

    input_transports = line_config['transport_input']
    output_transports = line_config['transport_output']
    if input_transports == '-':
        input_transports = 'none'
    if output_transports == '-':
        output_transports = 'none'

    output.append('Allowed input transports are {0}.'.format(input_transports))
    output.append('Allowed output transports are {0}.'.format(output_transports))
    output.append('Preferred transport is telnet.')
    output.append('No output characters are padded')
    output.append('No special data dispatching characters')

    return '\n'.join(output)


def format_show_line(line_configs, selector=None):
    selector_info = parse_line_selector(selector)

    if line_selector_is_specific(selector_info):
        for line_config in line_configs:
            if line_matches(line_config, selector):
                return format_show_line_detail(line_config, selector_info)

        raise ValueError('Invalid line: {0}'.format(selector))

    output = []
    output.append(
        '{0:<12} {1:<13} {2:<17} {3:<17} {4:<18} {5}'.format(
            'Line',
            'Exec Timeout',
            'Transport Input',
            'Transport Output',
            'Access Class',
            'Logging',
        )
    )

    matched = False
    for line_config in line_configs:
        if not line_matches(line_config, selector):
            continue

        matched = True
        output.append(
            '{0:<12} {1:<13} {2:<17} {3:<17} {4:<18} {5}'.format(
                line_config['name'][:12],
                line_config['exec_timeout'][:13],
                line_config['transport_input'][:17],
                line_config['transport_output'][:17],
                line_config['access_class'][:18],
                line_config['logging'],
            )
        )

    if not matched:
        raise ValueError('Invalid line: {0}'.format(selector))

    return '\n'.join(output)


def run_show_running_config(device, command_args=None):
    if command_args:
        raise ValueError('Invalid command: show running-config {0}'.format(command_args))

    return show_running_config(device['running_config'])


def run_show_running_config_all(device, command_args=None):
    if command_args:
        raise ValueError(
            'Invalid command: show running-config all {0}'.format(command_args)
        )

    return show_running_config(device['running_config_all'])


def run_show_version(device, command_args=None):
    if command_args:
        raise ValueError('Invalid command: show version {0}'.format(command_args))
    if not device['show_version']:
        raise ValueError('show version data is not loaded')

    return '\n'.join(device['show_version'])


def get_show_output(device, command):
    lines = device['show_outputs'].get(command)
    if lines is None:
        return None

    return '\n'.join(lines)


def run_file_backed_show(command):
    def handler(device, command_args=None):
        if command_args:
            raise ValueError('Invalid command: {0} {1}'.format(command, command_args))

        output = get_show_output(device, command)
        if output is None:
            raise ValueError('show output is not loaded: {0}'.format(command))

        return output

    return handler


def command_allowed_for_device(device, command):
    device_type = device.get('device_type', 'switch')

    if device_type == 'switch' and command in ROUTER_ONLY_COMMANDS:
        return False
    if device_type == 'router' and command in SWITCH_ONLY_COMMANDS:
        return False

    return True


def run_show_ip_interface(device, command_args=None):
    interfaces = parse_interfaces(device['running_config'])
    return format_show_ip_interface(interfaces, command_args)


def run_show_ip_interface_brief(device, command_args=None):
    if command_args:
        raise ValueError(
            'Invalid command: show ip interface brief {0}'.format(command_args)
        )

    output = get_show_output(device, 'show ip interface brief')
    if output is not None:
        return output

    interfaces = parse_interfaces(device['running_config'])
    return format_show_ip_interface_brief(interfaces)


def run_show_interfaces_description(device, command_args=None):
    if command_args:
        raise ValueError(
            'Invalid command: show interfaces description {0}'.format(command_args)
        )

    output = get_show_output(device, 'show interfaces description')
    if output is not None:
        return output

    interfaces = parse_interfaces(device['running_config'])
    return format_show_interfaces_description(interfaces)


def run_show_line(device, command_args=None):
    line_configs = parse_line_configs(device['running_config_all'])
    return format_show_line(line_configs, command_args)


COMMAND_HANDLERS = {
    'show version': run_show_version,
    'show running-config': run_show_running_config,
    'show running-config all': run_show_running_config_all,
    'show ip interface': run_show_ip_interface,
    'show ip interface brief': run_show_ip_interface_brief,
    'show interfaces': run_file_backed_show('show interfaces'),
    'show interfaces description': run_show_interfaces_description,
    'show interfaces status': run_file_backed_show('show interfaces status'),
    'show controllers': run_file_backed_show('show controllers'),
    'show ip route': run_file_backed_show('show ip route'),
    'show ip arp': run_file_backed_show('show ip arp'),
    'show ip cef': run_file_backed_show('show ip cef'),
    'show access-lists': run_file_backed_show('show access-lists'),
    'show logging': run_file_backed_show('show logging'),
    'show clock': run_file_backed_show('show clock'),
    'show users': run_file_backed_show('show users'),
    'show vrf': run_file_backed_show('show vrf'),
    'show ip vrf': run_file_backed_show('show ip vrf'),
    'show mac address-table': run_file_backed_show('show mac address-table'),
    'show cdp neighbors': run_file_backed_show('show cdp neighbors'),
    'show cdp neighbors detail': run_file_backed_show('show cdp neighbors detail'),
    'show lldp neighbors': run_file_backed_show('show lldp neighbors'),
    'show spanning-tree': run_file_backed_show('show spanning-tree'),
    'show etherchannel summary': run_file_backed_show('show etherchannel summary'),
    'show power inline': run_file_backed_show('show power inline'),
    'show inventory': run_file_backed_show('show inventory'),
    'show environment all': run_file_backed_show('show environment all'),
    'show license summary': run_file_backed_show('show license summary'),
    'show platform': run_file_backed_show('show platform'),
    'show ip protocols': run_file_backed_show('show ip protocols'),
    'show ip bgp summary': run_file_backed_show('show ip bgp summary'),
    'show ip ospf neighbor': run_file_backed_show('show ip ospf neighbor'),
    'show ip eigrp neighbors': run_file_backed_show('show ip eigrp neighbors'),
    'show ip nat translations': run_file_backed_show('show ip nat translations'),
    'show ip nat statistics': run_file_backed_show('show ip nat statistics'),
    'show crypto isakmp sa': run_file_backed_show('show crypto isakmp sa'),
    'show crypto ipsec sa': run_file_backed_show('show crypto ipsec sa'),
    'show standby brief': run_file_backed_show('show standby brief'),
    'show line': run_show_line,
}

COMMANDS_WITH_ARGS = set([
    'show ip interface',
    'show line',
])


def expand_show_command(user_input):
    tokens = user_input.strip().split()
    if not tokens:
        raise ValueError('Empty command')

    matches = []

    for command in COMMAND_HANDLERS:
        command_tokens = command.split()

        if len(tokens) < len(command_tokens):
            continue

        ok = True
        for user_token, real_token in zip(tokens, command_tokens):
            if not is_unique_prefix(user_token, real_token):
                ok = False
                break

        if not ok:
            continue

        command_args = ' '.join(tokens[len(command_tokens):])
        if command_args and command not in COMMANDS_WITH_ARGS:
            continue

        matches.append((command, command_args))

    if not matches:
        raise ValueError('Invalid command: {0}'.format(user_input))

    longest_match = max([len(match[0].split()) for match in matches])
    matches = [
        match for match in matches
        if len(match[0].split()) == longest_match
    ]

    if len(matches) > 1:
        raise ValueError(
            'Ambiguous command: {0}. Possible matches: {1}'.format(
                user_input,
                ', '.join([match[0] for match in matches]),
            )
        )

    return matches[0]


def run_show_command(device, command):
    command = command.strip()
    base_command, pipe_part = split_command_and_pipe(command)

    expanded_command, command_args = expand_show_command(base_command)
    if not command_allowed_for_device(device, expanded_command):
        raise ValueError('Invalid input detected at \'^\' marker.')

    handler = COMMAND_HANDLERS[expanded_command]
    output = handler(device, command_args)

    return apply_pipe_filter(output, pipe_part)


def run_shell(device):
    try:
        input_fn = raw_input
    except NameError:
        input_fn = input

    prompt = '{0}# '.format(device.get('hostname', 'Switch'))

    while True:
        try:
            command = input_fn(prompt)
        except EOFError:
            print('')
            break

        command = command.strip()

        if not command:
            continue

        if command in ['exit', 'quit']:
            break

        try:
            output = run_show_command(device, command)
            if output:
                print(output)
        except Exception as exc:
            print('% {0}'.format(exc))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'config_path',
        nargs='?',
        default=None,
        help='Path to the device config directory or a legacy running-config file',
    )
    parser.add_argument(
        '--all-config',
        help='Optional path to a legacy show running-config all file',
    )
    parser.add_argument(
        '--version-file',
        help='Optional path to a legacy show version file',
    )
    parser.add_argument(
        '--device-type',
        choices=['auto', 'switch', 'router'],
        default='auto',
        help='Device type marker used to handle platform-specific commands',
    )
    parser.add_argument(
        '--command',
        help='Optional single command to run instead of interactive shell',
    )
    args = parser.parse_args()

    device = load_device_config(
        args.config_path,
        args.all_config,
        args.version_file,
        args.device_type,
    )

    if args.command:
        try:
            output = run_show_command(device, args.command)
            if output:
                print(output)
        except Exception as exc:
            print('% {0}'.format(exc))
            sys.exit(1)
    else:
        setup_history()
        run_shell(device)


if __name__ == '__main__':
    main()
