#!/usr/bin/env python3

import argparse
import getpass
import os
import re
import sys
import time

from main import (
    DEFAULT_ROUTER_CONFIG_DIR,
    DEFAULT_SWITCH_CONFIG_DIR,
    OPTIONAL_SHOW_OUTPUT_FILES,
    ROUTER_ONLY_COMMANDS,
    SHOW_RUNNING_CONFIG_ALL_FILE,
    SHOW_RUNNING_CONFIG_FILE,
    SHOW_VERSION_FILE,
    SWITCH_ONLY_COMMANDS,
)


REQUIRED_COMMANDS = {
    'show version': SHOW_VERSION_FILE,
    'show running-config': SHOW_RUNNING_CONFIG_FILE,
    'show running-config all': SHOW_RUNNING_CONFIG_ALL_FILE,
}

PROMPT_RE = re.compile(r'(?m)(?:^|\n)([A-Za-z0-9_.:/() -]+[>#])\s*$')
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
BACKSPACE_RE = re.compile(r'.\x08')


def build_command_map(device_type):
    command_map = dict(REQUIRED_COMMANDS)

    for command, filename in OPTIONAL_SHOW_OUTPUT_FILES.items():
        if device_type == 'switch' and command in ROUTER_ONLY_COMMANDS:
            continue
        if device_type == 'router' and command in SWITCH_ONLY_COMMANDS:
            continue

        command_map[command] = filename

    return command_map


def default_output_dir(device_type):
    if device_type == 'router':
        return DEFAULT_ROUTER_CONFIG_DIR

    return DEFAULT_SWITCH_CONFIG_DIR


def import_paramiko():
    try:
        import paramiko
    except ImportError:
        print(
            'Paramiko is required for collection. Install it with: '
            'python3 -m pip install paramiko',
            file=sys.stderr,
        )
        sys.exit(1)

    return paramiko


def normalize_newlines(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def strip_ansi(text):
    return ANSI_RE.sub('', text)


def strip_backspaces(text):
    previous = None
    while previous != text:
        previous = text
        text = BACKSPACE_RE.sub('', text)

    return text


def clean_command_output(raw_output, command, prompt):
    output = normalize_newlines(strip_backspaces(strip_ansi(raw_output)))
    lines = output.split('\n')

    while lines and not lines[0].strip():
        lines.pop(0)

    if lines and lines[0].strip() == command:
        lines.pop(0)

    while lines and not lines[-1].strip():
        lines.pop()

    if lines and lines[-1].strip() == prompt.strip():
        lines.pop()

    return '\n'.join(lines).rstrip() + '\n'


def read_available(channel, timeout):
    deadline = time.time() + timeout
    output = ''

    while time.time() < deadline:
        if channel.recv_ready():
            output += channel.recv(65535).decode('utf-8', errors='replace')
            deadline = time.time() + 0.3
            continue

        time.sleep(0.05)

    return output


def read_until_prompt(channel, timeout):
    deadline = time.time() + timeout
    output = ''
    prompt = None

    while time.time() < deadline:
        if channel.recv_ready():
            output += channel.recv(65535).decode('utf-8', errors='replace')
            normalized = normalize_newlines(strip_ansi(output))
            match = PROMPT_RE.search(normalized)
            if match:
                prompt = match.group(1)
                quiet_until = time.time() + 0.25
                while time.time() < quiet_until:
                    if channel.recv_ready():
                        output += channel.recv(65535).decode(
                            'utf-8',
                            errors='replace',
                        )
                        quiet_until = time.time() + 0.25
                    else:
                        time.sleep(0.05)
                return output, prompt

        time.sleep(0.05)

    raise TimeoutError('Timed out waiting for device prompt')


def run_command(channel, command, timeout):
    channel.send(command + '\n')
    return read_until_prompt(channel, timeout)


def enter_enable_mode(channel, enable_password, timeout):
    channel.send('enable\n')
    output = ''
    deadline = time.time() + timeout

    while time.time() < deadline:
        if channel.recv_ready():
            output += channel.recv(65535).decode('utf-8', errors='replace')
            normalized = normalize_newlines(output)

            if 'Password:' in normalized:
                channel.send(enable_password + '\n')
                return read_until_prompt(channel, timeout)

            match = PROMPT_RE.search(normalized)
            if match:
                return output, match.group(1)

        time.sleep(0.05)

    raise TimeoutError('Timed out entering enable mode')


def connect(args):
    paramiko = import_paramiko()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    password = args.password
    if password is None and args.ask_password:
        password = getpass.getpass('SSH password: ')

    client.connect(
        args.host,
        port=args.port,
        username=args.username,
        password=password,
        key_filename=args.key_file,
        look_for_keys=args.look_for_keys,
        allow_agent=args.allow_agent,
        timeout=args.timeout,
        banner_timeout=args.timeout,
        auth_timeout=args.timeout,
    )

    channel = client.invoke_shell(width=512, height=1000)
    time.sleep(0.5)
    read_available(channel, 1)

    return client, channel


def ensure_privileged_prompt(channel, args):
    channel.send('\n')
    _, prompt = read_until_prompt(channel, args.timeout)

    if prompt.endswith('#'):
        return prompt

    enable_password = args.enable_password
    if enable_password is None and args.ask_enable_password:
        enable_password = getpass.getpass('Enable password: ')

    if enable_password is None:
        raise RuntimeError(
            'Device prompt is not privileged. Use --enable-password or '
            '--ask-enable-password.',
        )

    _, prompt = enter_enable_mode(channel, enable_password, args.timeout)
    if not prompt.endswith('#'):
        raise RuntimeError('Failed to enter privileged exec mode')

    return prompt


def prepare_terminal(channel, args):
    setup_commands = [
        'terminal length 0',
        'terminal width 512',
    ]

    for command in setup_commands:
        run_command(channel, command, args.timeout)


def collect_outputs(args):
    command_map = build_command_map(args.device_type)
    output_dir = args.output_dir or default_output_dir(args.device_type)

    os.makedirs(output_dir, exist_ok=True)

    client = None
    try:
        client, channel = connect(args)
        prompt = ensure_privileged_prompt(channel, args)
        print('Connected to {0}; prompt is {1}'.format(args.host, prompt))

        prepare_terminal(channel, args)
        print('Paging disabled with terminal length 0')

        for command, filename in command_map.items():
            path = os.path.join(output_dir, filename)
            print('Collecting {0} -> {1}'.format(command, path))
            raw_output, prompt = run_command(channel, command, args.command_timeout)
            cleaned_output = clean_command_output(raw_output, command, prompt)

            with open(path, 'w') as handle:
                handle.write(cleaned_output)

    finally:
        if client is not None:
            client.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description='Collect Cisco show command output files over SSH.',
    )
    parser.add_argument('--host', help='Device hostname or IP')
    parser.add_argument('--username', help='SSH username')
    parser.add_argument('--password', help='SSH password')
    parser.add_argument(
        '--ask-password',
        action='store_true',
        help='Prompt securely for the SSH password',
    )
    parser.add_argument(
        '--key-file',
        help='SSH private key file for key-based authentication',
    )
    parser.add_argument(
        '--look-for-keys',
        action='store_true',
        help='Allow Paramiko to search for private keys',
    )
    parser.add_argument(
        '--allow-agent',
        action='store_true',
        help='Allow Paramiko to use an SSH agent',
    )
    parser.add_argument('--port', type=int, default=22, help='SSH port')
    parser.add_argument(
        '--device-type',
        choices=['switch', 'router'],
        required=True,
        help='Collect switch or router command set',
    )
    parser.add_argument(
        '--list-commands',
        action='store_true',
        help='Print the commands and output filenames, then exit',
    )
    parser.add_argument(
        '--output-dir',
        help='Directory for captured files; defaults to config/switch or config/router',
    )
    parser.add_argument('--enable-password', help='Enable password if needed')
    parser.add_argument(
        '--ask-enable-password',
        action='store_true',
        help='Prompt securely for the enable password',
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=15,
        help='SSH and prompt timeout in seconds',
    )
    parser.add_argument(
        '--command-timeout',
        type=float,
        default=90,
        help='Per-command timeout in seconds',
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.list_commands:
        for command, filename in build_command_map(args.device_type).items():
            print('{0} -> {1}'.format(command, filename))
        return

    if not args.host or not args.username:
        print(
            'error: --host and --username are required unless --list-commands is used',
            file=sys.stderr,
        )
        sys.exit(2)

    collect_outputs(args)


if __name__ == '__main__':
    main()
