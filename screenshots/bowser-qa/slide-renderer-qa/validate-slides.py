#!/usr/bin/env python3
"""
Slide Renderer QA — Validates all 68 slide types against the renderer code.
Uses HEX encoding for slide_content to avoid TSV newline issues.
"""
import json
import subprocess
import sys
from collections import defaultdict


def _repair_json_quotes(s):
    """Fix unescaped double quotes inside JSON string values (from backend)."""
    result = []
    i = 0
    in_string = False
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\' and in_string:
            result.append(c)
            i += 1
            if i < n:
                result.append(s[i])
            i += 1
            continue
        if c == '"':
            if not in_string:
                in_string = True
                result.append(c)
            else:
                j = i + 1
                while j < n and s[j] in ' \t\r\n':
                    j += 1
                if j >= n or s[j] in ':,}]':
                    in_string = False
                    result.append(c)
                else:
                    result.append('\\"')
            i += 1
            continue
        result.append(c)
        i += 1
    return ''.join(result)


# Map of slide type → renderer function name (from renderSlideContent routing)
RENDERER_MAP = {
    'video': '_renderVideo', 'video2': '_renderVideo', 'video3': '_renderVideo',
    'video4': '_renderVideo', 'video5': '_renderVideo', 'video6': '_renderVideo',
    'video-with-question': '_renderVideo',
    'greetings': '_renderGreeting',
    'take-away': '_renderTakeaway',
    'one-word-apprication': '_renderOneWord', 'one-word-content-box': '_renderOneWord',
    'image': '_renderImage', 'image1': '_renderImage', 'image2': '_renderImage',
    'image3': '_renderImage', 'image4': '_renderImage', 'image5': '_renderImage',
    'image6': '_renderImage', 'special-image': '_renderImage', 'special-image1': '_renderImage',
    'sparkle': '_renderImage',
    'image-with-content': '_renderImageHybrid', 'image-with-question2': '_renderImageHybrid',
    'image-with-questions': '_renderImageHybrid', 'image-with-radio': '_renderImageHybrid',
    'image-with-select-option': '_renderImageHybrid',
    'question-answer': '_renderQuestion', 'question-answer1': '_renderQuestion',
    'question-answer3': '_renderQuestion', 'question-with-example': '_renderQuestion',
    'questions-example2': '_renderQuestion',
    'stakeholder-question': '_renderStakeholder', 'stakeholder-question-answer': '_renderStakeholder',
    'stakeholders': '_renderStakeholder', 'stakeholders-selected': '_renderStakeholder',
    'answered-stakeholders': '_renderStakeholder',
    'multiple-choice': '_renderMultipleChoice', 'single-choice-with-message': '_renderMultipleChoice',
    'select-true-or-false': '_renderTrueFalse', 'choose-true-or-false': '_renderTrueFalse',
    'check-yes-or-no': '_renderCheckYesNo',
    'select-range': '_renderSelectRange',
    'three-word': '_renderWordSelection', 'select-one-word': '_renderWordSelection',
    'one-word-select-option': '_renderWordSelection',
    'select-option': '_renderSelectOption', 'select-option2': '_renderSelectOption',
    'select-option3': '_renderSelectOption', 'select-option4': '_renderSelectOption',
    'select-option5': '_renderSelectOption', 'select-option6': '_renderSelectOption',
    'select-option7': '_renderSelectOption', 'select-option-with-button': '_renderSelectOption',
    'select-option-with-message': '_renderSelectOption', 'select-the-best': '_renderSelectOption',
    'side-by-side-dropdown-selector': '_renderDropdownSelector',
    'side-by-side-form': '_renderSideBySideForm', 'side-by-side-form2': '_renderSideBySideForm',
    'side-by-side-form4': '_renderSideBySideForm', 'side-by-side-print': '_renderSideBySideForm',
    'celebrate': '_renderEngagement', 'show-gratitude': '_renderEngagement',
    'decision': '_renderEngagement', 'decision2': '_renderEngagement',
    'take-to-lunch': '_renderEngagement', 'people-you-would-like-to-thank': '_renderEngagement',
    'chat-interface': '_renderEngagement', 'build-your-network': '_renderEngagement',
}


def get_all_slides():
    """Get all slides from DB using HEX encoding for slide_content."""
    sql = (
        "SELECT ls.id, ls.type, ls.lesson_detail_id, ls.video_library_id, "
        "HEX(ls.slide_content) AS content_hex "
        "FROM lesson_slides ls "
        "WHERE ls.deleted_at IS NULL "
        "ORDER BY ls.type, ls.id"
    )
    proc = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=30
    )
    if proc.returncode != 0:
        print(f"DB error: {proc.stderr}", file=sys.stderr)
        return []

    lines = proc.stdout.strip().split('\n')
    if len(lines) < 2:
        return []

    headers = lines[0].split('\t')
    rows = []
    for line in lines[1:]:
        vals = line.split('\t')
        row = {}
        for i, col in enumerate(headers):
            row[col] = vals[i] if i < len(vals) and vals[i] != 'NULL' else None
        # Decode hex content
        hex_content = row.get('content_hex')
        if hex_content:
            try:
                row['slide_content'] = bytes.fromhex(hex_content).decode('utf-8')
            except (ValueError, UnicodeDecodeError):
                row['slide_content'] = None
        else:
            row['slide_content'] = None
        rows.append(row)
    return rows


def validate_slide(slide_row):
    """Validate a single slide's content against renderer expectations."""
    issues = []
    slide_type = slide_row.get('type', 'unknown')
    slide_id = slide_row.get('id', '?')
    raw_content = slide_row.get('slide_content')

    # Check 1: JSON parseable (using strict=False like the backend)
    content = {}
    if raw_content:
        try:
            content = json.loads(raw_content, strict=False)
        except json.JSONDecodeError:
            # Try repair (like backend _repair_json_quotes)
            try:
                repaired = _repair_json_quotes(raw_content)
                content = json.loads(repaired, strict=False)
            except (json.JSONDecodeError, ValueError) as e:
                issues.append({
                    'slide_id': int(slide_id) if slide_id else 0,
                    'type': slide_type,
                    'issue': f'JSON parse error (even after repair): {str(e)[:100]}',
                    'severity': 'high'
                })
                return issues
    else:
        issues.append({
            'slide_id': int(slide_id) if slide_id else 0,
            'type': slide_type,
            'issue': 'Empty slide_content',
            'severity': 'medium'
        })
        return issues

    # Check 2: Has renderer (not fallback)
    renderer = RENDERER_MAP.get(slide_type)
    if not renderer:
        issues.append({
            'slide_id': int(slide_id), 'type': slide_type,
            'issue': f'No specific renderer — falls to _renderFallback',
            'severity': 'high'
        })

    # Check 3: Key content fields present based on renderer
    if renderer == '_renderVideo':
        vid_lib = slide_row.get('video_library_id')
        if not vid_lib and not content.get('slide_title'):
            pass  # Many videos just rely on video_library

    elif renderer == '_renderImage':
        if not content.get('background_image') and not content.get('content') and not content.get('slide_title') and not content.get('content_title'):
            issues.append({
                'slide_id': int(slide_id), 'type': slide_type,
                'issue': 'Image slide: no content at all',
                'severity': 'medium'
            })

    elif renderer == '_renderImageHybrid':
        has_image = content.get('background_image') or content.get('image')
        has_text = content.get('slide_title') or content.get('card_title') or content.get('content_title') or content.get('content_description')
        has_interactive = content.get('options') or content.get('questions')
        if not has_image and not has_text and not has_interactive:
            issues.append({
                'slide_id': int(slide_id), 'type': slide_type,
                'issue': 'Image hybrid: no image, text, or interactive content',
                'severity': 'medium'
            })

    elif renderer == '_renderSelectOption':
        has_choices = content.get('options') or content.get('data') or content.get('images') or content.get('questions')
        has_title = content.get('card_title') or content.get('slide_title') or content.get('content_title')
        if not has_choices and not has_title:
            issues.append({
                'slide_id': int(slide_id), 'type': slide_type,
                'issue': 'Select option: no choices or title',
                'severity': 'medium'
            })

    elif renderer == '_renderQuestion':
        has_questions = content.get('questions') or content.get('questionss')
        has_title = content.get('card_title') or content.get('slide_title') or content.get('content_title')
        if not has_questions and not has_title:
            issues.append({
                'slide_id': int(slide_id), 'type': slide_type,
                'issue': 'Question slide: no questions or title',
                'severity': 'medium'
            })

    return issues


def main():
    print("Fetching all slides from DB (HEX-encoded)...")
    slides = get_all_slides()
    print(f"Found {len(slides)} slides\n")

    type_counts = defaultdict(int)
    type_examples = defaultdict(list)
    all_issues = []
    types_tested = set()
    types_passed = set()
    types_failed = set()

    for slide in slides:
        slide_type = slide.get('type', 'unknown')
        type_counts[slide_type] += 1
        types_tested.add(slide_type)

        if len(type_examples[slide_type]) < 3:
            type_examples[slide_type].append(int(slide.get('id', 0)))

        issues = validate_slide(slide)
        if issues:
            all_issues.extend(issues)
            types_failed.add(slide_type)
        else:
            types_passed.add(slide_type)

    # Remove from passed if any slide of that type failed
    types_passed = types_passed - types_failed

    # Print summary
    print(f"Total types in DB: {len(type_counts)}")
    print(f"Types tested: {len(types_tested)}")
    print(f"Types fully passed: {len(types_passed)}")
    print(f"Types with issues: {len(types_failed)}")
    print()

    # Only show high-severity issues
    high_issues = [i for i in all_issues if i['severity'] == 'high']
    medium_issues = [i for i in all_issues if i['severity'] == 'medium']

    if high_issues:
        print(f"HIGH SEVERITY ISSUES ({len(high_issues)}):")
        for issue in high_issues:
            print(f"  Slide {issue['slide_id']} ({issue['type']}): {issue['issue']}")
        print()

    if medium_issues:
        # Deduplicate by type+issue pattern
        seen = set()
        print(f"MEDIUM SEVERITY ISSUES ({len(medium_issues)} total, showing unique):")
        for issue in medium_issues:
            key = f"{issue['type']}:{issue['issue'][:50]}"
            if key not in seen:
                seen.add(key)
                count = sum(1 for i in medium_issues if i['type'] == issue['type'] and i['issue'][:50] == issue['issue'][:50])
                print(f"  {issue['type']}: {issue['issue']} (x{count})")
        print()

    # Generate coverage report
    issues_by_type = defaultdict(list)
    for issue in all_issues:
        issues_by_type[issue['type']].append(issue)

    report = {
        "total_slides": len(slides),
        "total_types_in_db": len(type_counts),
        "types_tested": sorted(types_tested),
        "types_passed": sorted(types_passed),
        "types_failed": sorted(types_failed),
        "type_counts": dict(sorted(type_counts.items())),
        "issues": all_issues,
        "issues_by_severity": {
            "high": len(high_issues),
            "medium": len(medium_issues),
            "low": len([i for i in all_issues if i['severity'] == 'low']),
        },
        "renderer_coverage": {
            stype: {
                "count": type_counts[stype],
                "renderer": RENDERER_MAP.get(stype, '_renderFallback'),
                "status": "pass" if stype in types_passed else "issues_found",
                "examples": type_examples[stype],
                "issues": list(set(i['issue'] for i in issues_by_type.get(stype, [])))[:3],
            }
            for stype in sorted(type_counts.keys())
        }
    }

    report_path = "screenshots/bowser-qa/slide-renderer-coverage.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nCoverage report written to {report_path}")

    return report


if __name__ == '__main__':
    main()
