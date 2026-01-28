"""
Mission validation utilities for checking mission completion status.
"""
from typing import Dict, Any, Optional


def check_mission_ready(mission_id: int, mission_result: Dict[str, Any], requirements: Optional[Dict[str, int]] = None) -> bool:
    """
    Check if mission is ready to finalize based on requirements.

    This function validates that all required content types (photo, video, audio, aside_text)
    meet the minimum counts specified in mission_requirements.

    Args:
        mission_id: Mission ID (int or str)
        mission_result: Dictionary containing mission content:
            - 'attachment'/'attachments': Photo attachments (single dict or list)
            - 'video'/'videos': Video attachments (single dict or list)
            - 'audio'/'audios': Audio attachments (single dict or list)
            - 'aside_text'/'aside_texts': Text content (single string or list)
            - 'content': Text content (for legacy support)
        requirements: Optional dict specifying required counts for each type
            Example: {"photo": 1, "aside_text": 1, "video": 2}
            If None, will fetch from config

    Returns:
        bool: True if mission has all required content, False otherwise

    Examples:
        >>> check_mission_ready(1008, {"attachment": {...}, "aside_text": "text"}, {"photo": 1, "aside_text": 1})
        True

        >>> check_mission_ready(1087, {"attachments": [{...}, {...}], "aside_texts": ["a", "b"]}, {"photo": 2, "aside_text": 2})
        True

        >>> check_mission_ready(14, {"audios": [...]}, {"audio": 1})
        True
    """
    # If requirements not provided, fetch from config
    if requirements is None:
        from bot.config import config
        mission_id_str = str(mission_id)
        requirements = config.mission_requirements.get(mission_id_str, {})

    # Check each required content type
    for content_type, required_count in requirements.items():
        if required_count <= 0:
            continue

        current_count = _count_content(mission_result, content_type)

        if current_count < required_count:
            return False

    return True


def _count_content(mission_result: Dict[str, Any], content_type: str) -> int:
    """
    Count the number of valid content items of a specific type.

    Args:
        mission_result: Dictionary containing mission content
        content_type: Type of content to count ('photo', 'video', 'audio', 'aside_text')

    Returns:
        int: Number of valid content items
    """
    if content_type == 'photo':
        return _count_attachments(mission_result, ['attachment', 'attachments'])

    elif content_type == 'video':
        return _count_attachments(mission_result, ['video', 'videos'])

    elif content_type == 'audio':
        return _count_attachments(mission_result, ['audio', 'audios'])

    elif content_type == 'aside_text':
        return _count_text(mission_result, ['aside_text', 'aside_texts', 'content'])

    else:
        return 0


def _count_attachments(mission_result: Dict[str, Any], keys: list) -> int:
    """
    Count valid attachment items (photo/video/audio).

    An attachment is considered valid if it has a 'url' field.

    Args:
        mission_result: Dictionary containing mission content
        keys: List of possible keys to check

    Returns:
        int: Number of valid attachments
    """
    for key in keys:
        value = mission_result.get(key)

        if not value:
            continue

        # Check if it's a list of attachments
        if isinstance(value, list):
            count = len([item for item in value if item and isinstance(item, dict) and item.get('url')])
            if count > 0:
                return count

        # Check if it's a single attachment
        elif isinstance(value, dict) and value.get('url'):
            return 1

    return 0


def _count_text(mission_result: Dict[str, Any], keys: list) -> int:
    """
    Count valid text items (aside_text).

    Text is considered valid if it's not empty, not "跳過", and not a placeholder.

    Args:
        mission_result: Dictionary containing mission content
        keys: List of possible keys to check

    Returns:
        int: Number of valid text items
    """
    invalid_values = ['', '跳過', '[使用者選擇跳過]', 'null', None]

    for key in keys:
        value = mission_result.get(key)

        if not value:
            continue

        # Check if it's a list of text items
        if isinstance(value, list):
            count = len([item for item in value if item not in invalid_values])
            if count > 0:
                return count

        # Check if it's a single text item
        elif value not in invalid_values:
            return 1

    return 0
