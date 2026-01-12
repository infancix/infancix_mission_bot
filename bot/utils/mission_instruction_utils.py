import json
import os
from typing import Optional, Dict, List


def get_mission_total_steps(mission_id) -> List[Dict]:
    """
    Load all steps for a mission from mission_questionnaire.json

    Args:
        mission_id: Mission ID (int or str)

    Returns:
        List of step dicts with 'type' and other fields, empty list if not found
    """
    mission_id_str = str(mission_id)
    questionnaire_path = os.path.join(
        os.path.dirname(__file__), '..', 'resource', 'mission_questionnaire.json'
    )

    try:
        with open(questionnaire_path, 'r', encoding='utf-8') as f:
            questionnaires = json.load(f)

        if mission_id_str in questionnaires:
            return questionnaires[mission_id_str]
    except Exception as e:
        print(f"Error loading mission_questionnaire.json: {e}")

    return []


def get_current_mission_step(mission_id, student_mission_info) -> Optional[Dict]:
    """
    Get current step data based on student_mission_info's current_step

    Args:
        mission_id: Mission ID (int or str)
        student_mission_info: Student mission info dict with 'current_step' field

    Returns:
        Dict: Current step data with 'type', 'title', 'description', etc.
        None: If mission not found or invalid step index
    """
    steps = get_mission_total_steps(mission_id)

    if not steps:
        return None

    # API uses 1-based step numbering, convert to 0-based array index
    current_step = student_mission_info.get('current_step', 1)
    step_index = current_step - 1

    if 0 <= step_index < len(steps):
        return steps[step_index]

    return None


def get_mission_instruction(mission_id, step_index=0) -> Optional[Dict[str, str]]:
    """
    Load mission instruction from mission_instruction.json

    Args:
        mission_id: Mission ID (int or str)
        step_index: Which step to retrieve (default 0 for first step)

    Returns:
        Dict with 'title' and 'description' if found, None otherwise
    """
    mission_id_str = str(mission_id)
    instruction_path = os.path.join(
        os.path.dirname(__file__), '..', 'resource', 'mission_instruction.json'
    )

    try:
        with open(instruction_path, 'r', encoding='utf-8') as f:
            mission_instructions = json.load(f)

        if mission_id_str in mission_instructions:
            steps = mission_instructions[mission_id_str]
            if 0 <= step_index < len(steps):
                return steps[step_index]
    except Exception as e:
        print(f"Error loading mission_instruction.json: {e}")

    return None
