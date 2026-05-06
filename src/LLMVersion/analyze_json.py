import json

files = ['1707.07938v2_openai.json', '1707.07938v2_huggingface.json', '1707.07938v2_anthropic.json']

for f in files:
    print(f"\n{'='*60}")
    print(f"FILE: {f}")
    print('='*60)
    
    with open(f) as file:
        data = json.load(file)
    
    # Show top-level structure
    if isinstance(data, dict):
        print(f"Type: dict")
        print(f"Keys: {list(data.keys())}")
        
        # Show first few items of each key
        for key in data.keys():
            value = data[key]
            if isinstance(value, list):
                print(f"\n  {key}: list with {len(value)} items")
                if value:
                    print(f"    First item type: {type(value[0])}")
                    if isinstance(value[0], dict):
                        print(f"    First item keys: {list(value[0].keys())}")
                        if 'kind' in value[0]:
                            print(f"    First item 'kind': {value[0]['kind']}")
            else:
                print(f"\n  {key}: {type(value)}")
    elif isinstance(data, list):
        print(f"Type: list with {len(data)} items")
        if data:
            print(f"First item type: {type(data[0])}")
            if isinstance(data[0], dict):
                print(f"First item keys: {list(data[0].keys())}")
