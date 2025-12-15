#!/usr/bin/env python3
"""Shared YAML loader for Home Assistant configuration files.

Handles HA-specific YAML tags like !include, !secret, !input, etc.
This module provides a single source of truth for YAML loading across
all validation tools.
"""

import yaml
from pathlib import Path
from typing import Any


class HAYamlLoader(yaml.SafeLoader):
    """Custom YAML loader that handles Home Assistant specific tags.

    Supports all standard HA YAML tags:
    - !include - Include another YAML file
    - !include_dir_named - Include directory as named dict
    - !include_dir_merge_named - Include and merge directory as named dict
    - !include_dir_merge_list - Include and merge directory as list
    - !include_dir_list - Include directory as list
    - !input - Blueprint input reference
    - !secret - Secret value reference
    """

    pass


def _make_tag_constructor(tag_name: str):
    """Factory to create tag constructors that preserve tag info.

    Args:
        tag_name: The HA tag name without the leading '!'

    Returns:
        A constructor function for the YAML loader
    """

    def constructor(loader: yaml.Loader, node: yaml.Node) -> str:
        value = loader.construct_scalar(node)
        return f"!{tag_name} {value}"

    return constructor


# All supported Home Assistant YAML tags
_HA_TAGS = [
    "include",
    "include_dir_named",
    "include_dir_merge_named",
    "include_dir_merge_list",
    "include_dir_list",
    "input",
    "secret",
]

# Register all HA-specific tag constructors
for _tag in _HA_TAGS:
    HAYamlLoader.add_constructor(f"!{_tag}", _make_tag_constructor(_tag))


def load_yaml(file_path: Path) -> Any:
    """Load a YAML file using the HA-aware loader.

    Args:
        file_path: Path to the YAML file to load

    Returns:
        The parsed YAML content

    Raises:
        yaml.YAMLError: If the file contains invalid YAML
        FileNotFoundError: If the file doesn't exist
        UnicodeDecodeError: If the file isn't valid UTF-8
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.load(f, Loader=HAYamlLoader)


def load_yaml_string(content: str) -> Any:
    """Load YAML content from a string using the HA-aware loader.

    Args:
        content: YAML content as a string

    Returns:
        The parsed YAML content

    Raises:
        yaml.YAMLError: If the content is invalid YAML
    """
    return yaml.load(content, Loader=HAYamlLoader)
