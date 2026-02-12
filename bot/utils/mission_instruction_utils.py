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


def get_mission_instruction(mission_id, step_index=0, instruction_type='question') -> Optional[Dict[str, str]]:
    """
    Load mission instruction from mission_instruction.json

    Args:
        mission_id: Mission ID (int or str)
        step_index: Which step to retrieve (default 0 for first step)
        instruction_type: 'upload', 'question', or 'questionnaire' (default 'question')

    Returns:
        Dict with instruction data if found, None otherwise
        - For single instruction: Dict with 'question' and 'description'
        - For multiple instructions (array): Dict at the specified step_index
    """
    mission_id_str = str(mission_id)
    instruction_path = os.path.join(
        os.path.dirname(__file__), '..', 'resource', 'mission_instruction.json'
    )

    try:
        with open(instruction_path, 'r', encoding='utf-8') as f:
            mission_instructions = json.load(f)

        if mission_id_str not in mission_instructions:
            return None

        mission_data = mission_instructions[mission_id_str]

        # Determine which instruction to use based on type
        if instruction_type == 'upload':
            instruction = mission_data.get('upload_instruction')
        elif instruction_type == 'questionnaire':
            instruction = mission_data.get('questionnaire_instruction')
        else:  # 'question'
            instruction = mission_data.get('question_instruction')

        # If instruction is None, return None
        if instruction is None:
            return None

        # If instruction is a list, get the item at step_index
        if isinstance(instruction, list):
            if 0 <= step_index < len(instruction):
                return instruction[step_index]
            return None

        # If instruction is a dict (single instruction), return it
        # Note: step_index is ignored for single instructions
        return instruction

    except Exception as e:
        print(f"Error loading mission_instruction.json: {e}")

    return None
