"""
Quick test of the new filtering logic in _parse_target
"""

import struct
from dataclasses import dataclass

# Inline the Target class to avoid needing imports
@dataclass
class Target:
    x: float
    y: float
    speed: float

def _parse_target(data: bytes, offset: int) -> Target | None:
    """
    Identical to LD2450._parse_target - for testing without serial dependency
    """
    x_mm, y_mm, v_mm, _ = struct.unpack_from('<hhhH', data, offset)

    # Empty slot (all zeros)
    if x_mm == 0 and y_mm == 0 and v_mm == 0:
        return None

    # Corrupt data: min/max int16 values indicate sensor error
    if x_mm in (-32768, 32767) or y_mm in (-32768, 32767) or v_mm in (-32768, 32767):
        return None

    # Out-of-range distance (LD2450 typically 0-9m, conservative ~9000mm)
    if abs(x_mm) > 9000 or abs(y_mm) > 9000:
        return None

    # Unrealistic speed (3 m/s = 3000 mm/s is max reasonable walking/running)
    if abs(v_mm) > 3000:
        return None

    return Target(
        x     = round(x_mm / 1000.0, 3),   # mm → metres
        y     = round(y_mm / 1000.0, 3),
        speed = round(v_mm / 1000.0, 3)
    )

def test_parse_target():
    """Test the _parse_target filtering"""
    
    test_cases = [
        # (x_mm, y_mm, v_mm, description, should_pass)
        (0, 0, 0, "all-zero (empty)", False),
        (-32768, 0, 0, "min int16 x (corrupt)", False),
        (0, 32767, 0, "max int16 y (corrupt)", False),
        (1000, 2000, 500, "valid target (1m, 2m, 0.5m/s)", True),
        (9500, 0, 0, "out of range x (> 9000mm)", False),
        (0, 10000, 0, "out of range y (> 9000mm)", False),
        (1000, 2000, 4000, "unrealistic speed (> 3000 mm/s)", False),
        (1000, 2000, 3000, "at speed limit (3000 mm/s)", True),
        (-3000, 5000, -1500, "valid negative coords", True),
    ]
    
    passed = 0
    failed = 0
    
    print("Testing _parse_target filtering:\n")
    
    for x, y, v, desc, should_pass in test_cases:
        # Pack as little-endian 8-byte target struct
        data = struct.pack('<hhhH', x, y, v, 0)  # last field is resolution (unused)
        
        result = _parse_target(data, 0)
        passed_filter = result is not None
        
        if passed_filter == should_pass:
            status = "✓ PASS"
            passed += 1
        else:
            status = "✗ FAIL"
            failed += 1
        
        print(f"{status} | {desc:45} | x={x:6}, y={y:6}, v={v:6}")
        if passed_filter:
            print(f"       → Result: Target(x={result.x:.1f}m, y={result.y:.1f}m, speed={result.speed:.1f}m/s)")
    
    print(f"\n{'='*80}")
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    
    if failed == 0:
        print("✓ All filtering tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1

if __name__ == '__main__':
    exit(test_parse_target())
