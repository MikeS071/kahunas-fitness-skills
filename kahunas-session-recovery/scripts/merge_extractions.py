#!/usr/bin/env python3
"""
Merge partial and resume Kahunas extractions.

Usage:
    python3 merge_extractions.py --original partial.json --resume resume.json

Output: kahunas_merged.json (or custom --output)
"""

import json
import argparse
from datetime import datetime


def merge_extractions(original_file, resume_file, output_file='kahunas_merged.json'):
    """Merge two Kahunas JSON extractions, avoiding duplicates."""
    
    with open(original_file) as f:
        original = json.load(f)
    
    with open(resume_file) as f:
        resume = json.load(f)
    
    # Get existing checkin IDs
    existing_ids = set()
    for c in original.get('checkins_complete', []):
        cid = c.get('checkin_id') or c.get('id')
        if cid:
            existing_ids.add(cid)
    
    # Find new checkins
    new_checkins = []
    for c in resume:
        cid = c.get('checkin_id') or c.get('id')
        if cid and cid not in existing_ids:
            new_checkins.append(c)
            print(f"  + Adding: {c.get('number', '?')} ({c.get('date', '?')})")
    
    # Update metadata
    original['meta']['resumed_at'] = original['meta'].get('extracted_at')
    original['meta']['extracted_at'] = datetime.now().isoformat()
    original['meta']['resumed_count'] = len(new_checkins)
    
    # Merge
    original['checkins_complete'].extend(new_checkins)
    
    # Save
    with open(output_file, 'w') as f:
        json.dump(original, f, indent=2)
    
    print(f"\n✓ Merged {len(new_checkins)} new checkins")
    print(f"✓ Total: {len(original['checkins_complete'])} checkins")
    print(f"✓ Saved: {output_file}")
    
    return original


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Merge partial and resume Kahunas extractions'
    )
    parser.add_argument(
        '--original', '-i', 
        required=True, 
        help='Path to original/partial extraction JSON'
    )
    parser.add_argument(
        '--resume', '-r',
        required=True,
        help='Path to resume extraction JSON'
    )
    parser.add_argument(
        '--output', '-o',
        default='kahunas_merged.json',
        help='Output path (default: kahunas_merged.json)'
    )
    
    args = parser.parse_args()
    
    print(f"Original: {args.original}")
    print(f"Resume:   {args.resume}")
    print(f"Output:   {args.output}")
    print()
    
    merge_extractions(args.original, args.resume, args.output)
