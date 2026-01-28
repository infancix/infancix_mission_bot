#!/usr/bin/env python3
"""
Test script for format_bilingual_sentence function
"""
import os
import sys
import json
import logging

# Add the bot directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from bot.utils.openai_utils import OpenAIUtils

def test_format_bilingual_sentence():
    """Test the format_bilingual_sentence function"""

    # Check for OpenAI API key
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Please set it with: export OPENAI_API_KEY='your-api-key'")
        return

    # Initialize simple logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test")

    # Initialize OpenAI Utils
    openai_utils = OpenAIUtils(api_key=api_key)

    print("=" * 80)
    print("Testing format_bilingual_sentence function")
    print("=" * 80)

    # Test Case 1: Simple answer (should use default template)
    print("\n[Test Case 1] Simple answer that fits default template")
    print("-" * 80)
    prompt1 = "你必須從使用者的回答中，取得寶寶大哭原因的答案，將答案填入句子「當{answer}，就會不開心的哭鬧。」(中文) 和 「Cries unhappily when {answer}.」(英文)。"
    answer1 = "肚子餓"

    print(f"Prompt: {prompt1[:100]}...")
    print(f"User answer: {answer1}")

    try:
        result1 = openai_utils.format_bilingual_sentence(prompt1, answer1)
        print(f"\nResult type: {type(result1)}")
        print(f"Result:\n{json.dumps(result1, ensure_ascii=False, indent=2)}")

        # Validate result structure
        if isinstance(result1, dict):
            assert 'answer' in result1, "Missing 'answer' key"
            assert 'answer_en' in result1, "Missing 'answer_en' key"
            assert 'use_default_template' in result1, "Missing 'use_default_template' key"
            assert 'sentence' in result1, "Missing 'sentence' key"
            assert 'sentence_en' in result1, "Missing 'sentence_en' key"

            print("\n✓ Test Case 1 PASSED - All required keys present")
            print(f"✓ use_default_template = {result1['use_default_template']} (expected: True)")
        else:
            print("\n✗ Test Case 1 FAILED - Result is not a dict")
    except Exception as e:
        print(f"\n✗ Test Case 1 FAILED with error: {e}")

    # Test Case 2: Another simple answer
    print("\n\n[Test Case 2] Another simple answer")
    print("-" * 80)
    prompt2 = "你必須從使用者的回答中，取得寶寶大笑原因的答案，將答案填入句子「當{answer}，就會開心的笑出來。」(中文) 和 「Laughs happily when {answer}.」(英文)。"
    answer2 = "看到爸爸"

    print(f"Prompt: {prompt2[:100]}...")
    print(f"User answer: {answer2}")

    try:
        result2 = openai_utils.format_bilingual_sentence(prompt2, answer2)
        print(f"\nResult type: {type(result2)}")
        print(f"Result:\n{json.dumps(result2, ensure_ascii=False, indent=2)}")

        if isinstance(result2, dict):
            print("\n✓ Test Case 2 PASSED")
            print(f"✓ use_default_template = {result2['use_default_template']}")
        else:
            print("\n✗ Test Case 2 FAILED - Result is not a dict")
    except Exception as e:
        print(f"\n✗ Test Case 2 FAILED with error: {e}")

    # Test Case 3: Old-style template (backward compatibility)
    print("\n\n[Test Case 3] Old-style template (backward compatibility)")
    print("-" * 80)
    old_style_template = "當{answer}，就會不開心的哭鬧。|Cries unhappily when {answer}."
    answer3 = "肚子餓"

    print(f"Template: {old_style_template}")
    print(f"User answer: {answer3}")

    try:
        result3 = openai_utils.format_bilingual_sentence(old_style_template, answer3)
        print(f"\nResult type: {type(result3)}")
        print(f"Result: {result3}")

        if isinstance(result3, str):
            print("\n✓ Test Case 3 PASSED - Old-style returns string")
        else:
            print("\n✗ Test Case 3 FAILED - Should return string for old-style")
    except Exception as e:
        print(f"\n✗ Test Case 3 FAILED with error: {e}")

    print("\n" + "=" * 80)
    print("Testing completed!")
    print("=" * 80)

if __name__ == "__main__":
    test_format_bilingual_sentence()
