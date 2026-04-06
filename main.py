#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Callable


def is_unique_prefix(token: str, word: str) -> bool:
    return word.startswith(token)


def expand_command(user_input: str, valid_commands: list[str]) -> str:
    tokens = user_input.strip().split()
    if not tokens:
        raise ValueError('Empty command')

    matches: list[str] = []

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
        raise ValueError(f'Invalid command: {user_input}')

    if len(matches) > 1:
        raise ValueError(
            f'Ambiguous command: {user_input}. Possible matches: {", ".join(matches)}'
        )

    return matches[0]


def read_config_file(path: str) -> list[str]:
    return Path(path).read_text(encoding='utf-8').splitlines()


def show_running_config(lines: list[str]) -> str:
    return '\n'.join(lines)


def filter_include(lines: list[str], pattern: str) -> str:
    regex = re.compile(pattern)
    return '\n'.join(line for line in lines if regex.search(line))


def filter_exclude(lines: list[str], pattern: str) -> str:
    regex = re.compile(pattern)
    return '\n'.join(line for line in lines if not regex.search(line))


def filter_begin(lines: list[str], pattern: str) -> str:
    regex = re.compile(pattern)

    for index, line in enumerate(lines):
        if regex.search(line):
            return '\n'.join(lines[index:])

    return ''


def filter_section(lines: list[str], pattern: str) -> str:
    regex = re.compile(pattern)
    sections: list[list[str]] = []
    current_section: list[str] = []

    for line in lines:
        if line and not line.startswith(' '):
            if current_section:
                sections.append(current_section)
            current_section = [line]
        else:
            current_section.append(line)

    if current_section:
        sections.append(current_section)

    matched_sections = [
        section
        for section in sections
        if section and regex.search(section[0])
    ]

    return '\n'.join('\n'.join(section) for section in matched_sections)


def run_show_command(lines: list[str], command: str) -> str:
    command = command.strip()

    if '|' not in command:
        expanded = expand_command(command, ['show running-config'])
        if expanded == 'show running-config':
            return show_running_config(lines)
        raise ValueError(f'Unsupported command: {command}')

    base_command, pipe_part = [part.strip() for part in command.split('|', 1)]
    expanded_base = expand_command(base_command, ['show running-config'])

    if expanded_base != 'show running-config':
        raise ValueError(f'Unsupported command: {command}')

    pipe_tokens = pipe_part.split(maxsplit=1)
    if len(pipe_tokens) != 2:
        raise ValueError('Filter requires an argument')

    filter_cmd_raw, filter_value = pipe_tokens
    expanded_filter = expand_command(
        filter_cmd_raw,
        ['include', 'exclude', 'begin', 'section'],
    )

    filter_map: dict[str, Callable[[list[str], str], str]] = {
        'include': filter_include,
        'exclude': filter_exclude,
        'begin': filter_begin,
        'section': filter_section,
    }

    return filter_map[expanded_filter](lines, filter_value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file', help='Path to the saved running-config file')
    parser.add_argument('command', help='Show command to run against the file')
    args = parser.parse_args()

    lines = read_config_file(args.config_file)
    output = run_show_command(lines, args.command)
    print(output)


if __name__ == '__main__':
    main()
