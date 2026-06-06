# Fix string validations incorrectly passing for numeric arrays

## Problem
String-specific validation functions like `contains`, `startswith`, `lowercase`, `printascii`, and others did not verify that the field was actually a string. When a non-string value such as a numeric array (e.g., `[]int{3000}`) was validated, `.String()` would return a Go representation like `"[3000]"`, causing the validation to erroneously pass. This affected all validators intended for strings only.

## Fix
Added `reflect.String` kind checks to the affected validators. If the field is not a string, they now return `false` (validation failure) instead of operating on the incorrect `.String()` output. Specifically:

- `hasMultiByteCharacter`, `containsRune`, `containsAny`, `contains`, `startsWith`, `endsWith`: return `false` for non-string types.
- `isLowercase` and `isUppercase`: changed from panicking on non-strings to returning `false`.
- Updated test expectations: tests that previously expected a panic now expect a validation error.

This ensures only actual string values can satisfy these validations, closing the false-positive loophole.

Fixes #1481.
