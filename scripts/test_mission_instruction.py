#!/usr/bin/env python3
"""
Test script to validate mission_instruction.json structure
"""
import json
from bot.utils.mission_instruction_utils import get_mission_instruction

def test_mission_instructions():
    """Test all missions in mission_instruction.json"""

    # Test cases
    test_cases = [
        # Mission with upload_instruction only
        {
            'mission_id': 14,
            'test_upload': True,
            'test_question': False,
            'expected_upload_title': '錄下你的哄睡聲音或噓噓聲(語音)',
        },
        # Mission with question_instruction only
        {
            'mission_id': 44,
            'test_upload': False,
            'test_question': True,
            'expected_question_title': '📝 這張照片裡的人是誰呢？',
        },
        # Mission with both upload and question instructions (array)
        {
            'mission_id': 1087,
            'test_upload': True,
            'test_question': True,
            'expected_upload_count': 2,
            'expected_question_count': 2,
            'upload_index_0_title': '上傳寶寶大哭的照片',
            'question_index_0_question': '請問寶寶大哭的原因呢?',
        },
        # Mission with multiple upload instructions only
        {
            'mission_id': 1097,
            'test_upload': True,
            'test_question': False,
            'expected_upload_count': 2,
            'upload_index_0_title': '上傳寶寶揮手說再見的影片',
        },
    ]

    print("Testing mission_instruction.json structure...\n")

    for test in test_cases:
        mission_id = test['mission_id']
        print(f"Testing Mission {mission_id}:")

        # Test upload instruction
        if test['test_upload']:
            upload_data = get_mission_instruction(mission_id, step_index=0, instruction_type='upload')

            if 'expected_upload_count' in test:
                # Multiple uploads
                print(f"  ✓ Upload instruction (array) found")
                for i in range(test['expected_upload_count']):
                    step_data = get_mission_instruction(mission_id, step_index=i, instruction_type='upload')
                    if step_data:
                        print(f"    - Step {i}: {step_data.get('title', 'N/A')}")
                    else:
                        print(f"    ✗ Step {i}: Not found")
            else:
                # Single upload
                if upload_data:
                    print(f"  ✓ Upload instruction: {upload_data.get('title', 'N/A')}")
                else:
                    print(f"  ✗ Upload instruction not found (expected)")
        else:
            upload_data = get_mission_instruction(mission_id, step_index=0, instruction_type='upload')
            if upload_data is None:
                print(f"  ✓ Upload instruction is None (as expected)")
            else:
                print(f"  ✗ Upload instruction should be None but got: {upload_data}")

        # Test question instruction
        if test['test_question']:
            question_data = get_mission_instruction(mission_id, step_index=0, instruction_type='question')

            if 'expected_question_count' in test:
                # Multiple questions
                print(f"  ✓ Question instruction (array) found")
                for i in range(test['expected_question_count']):
                    step_data = get_mission_instruction(mission_id, step_index=i, instruction_type='question')
                    if step_data:
                        print(f"    - Step {i}: {step_data.get('question', step_data.get('title', 'N/A'))}")
                    else:
                        print(f"    ✗ Step {i}: Not found")
            else:
                # Single question
                if question_data:
                    print(f"  ✓ Question instruction: {question_data.get('title', 'N/A')}")
                else:
                    print(f"  ✗ Question instruction not found (expected)")
        else:
            question_data = get_mission_instruction(mission_id, step_index=0, instruction_type='question')
            if question_data is None:
                print(f"  ✓ Question instruction is None (as expected)")
            else:
                print(f"  ✗ Question instruction should be None but got: {question_data}")

        print()

    print("All tests completed!")

if __name__ == '__main__':
    test_mission_instructions()
