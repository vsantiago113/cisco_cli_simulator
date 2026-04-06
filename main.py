#!/usr/bin/env python

import argparse
import atexit
import os
import re

try:
    import readline
except ImportError:
    readline = None


HISTORY_FILE = os.path.expanduser('~/.ios_show_file_history')
HISTORY_LENGTH = 1000


def setup_history():
    if readline is None:
        return

    if os.path.exists(HISTORY_FILE):
        readline.read_history_file(HISTORY_FILE)

    readline.set_history_length(HISTORY_LENGTH)
    atexit.register(save_history)


def save_history():
    if readline is None:
        return

    readline.write_history_file(HISTORY_FILE)


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


def read_config_file(path):
    handle = open(path, 'r')
    try:
        return handle.read().splitlines()
    finally:
        handle.close()


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


def run_show_running_config(lines, pipe_part=None):
    if not pipe_part:
        return show_running_config(lines)

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

    return filter_map[expanded_filter](lines, filter_value)


def run_show_ip_interface_brief(lines, pipe_part=None):
    if pipe_part:
        raise ValueError('Piping is not supported for this simulated command')

    interfaces = parse_interfaces(lines)
    return format_show_ip_interface_brief(interfaces)


def run_show_interfaces_description(lines, pipe_part=None):
    if pipe_part:
        raise ValueError('Piping is not supported for this simulated command')

    interfaces = parse_interfaces(lines)
    return format_show_interfaces_description(interfaces)


COMMAND_HANDLERS = {
    'show running-config': run_show_running_config,
    'show ip interface brief': run_show_ip_interface_brief,
    'show interfaces description': run_show_interfaces_description,
}

VALID_COMMANDS = list(COMMAND_HANDLERS.keys())


def run_show_command(lines, command):
    command = command.strip()

    if '|' in command:
        parts = [part.strip() for part in command.split('|', 1)]
        base_command = parts[0]
        pipe_part = parts[1]
    else:
        base_command = command
        pipe_part = None

    expanded_command = expand_command(base_command, VALID_COMMANDS)
    handler = COMMAND_HANDLERS[expanded_command]

    return handler(lines, pipe_part)


def run_shell(lines):
    while True:
        try:
            command = raw_input('Switch# ')
        except NameError:
            command = input('Switch# ')
        except EOFError:
            print('')
            break

        command = command.strip()

        if not command:
            continue

        if command in ['exit', 'quit']:
            break

        try:
            output = run_show_command(lines, command)
            if output:
                print(output)
        except Exception as exc:
            print('% {0}'.format(exc))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file', help='Path to the saved running-config file')
    parser.add_argument(
        '--command',
        help='Optional single command to run instead of interactive shell',
    )
    args = parser.parse_args()

    lines = read_config_file(args.config_file)
    setup_history()

    if args.command:
        output = run_show_command(lines, args.command)
        print(output)
    else:
        run_shell(lines)


if __name__ == '__main__':
    main()