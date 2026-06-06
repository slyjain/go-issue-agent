# Fix UUID validation to accept uppercase hex digits

## Description

The `uuid`, `uuid3`, `uuid4`, and `uuid5` validators incorrectly rejected valid UUIDs containing uppercase hexadecimal characters (A-F). Only the `uuid3_rfc4122`, `uuid4_rfc4122`, and `uuid5_rfc4122` validators correctly accepted mixed case, while the base UUID validators only matched lowercase.

This inconsistency dated back to the original regex patterns which restricted hex digits to `a-f`. This change updates the regex strings for `uuid3`, `uuid4`, and `uuid5` to include `A-F`, aligning them with the existing `uuid` regex and the RFC 4122 variants.

## Changes

- Updated `uUID3RegexString`, `uUID4RegexString`, and `uUID5RegexString` in `regexes.go` to accept uppercase hex characters.
- Added corresponding test cases for uppercase UUIDs in `validator_test.go` to ensure validation passes.

## How does this fix the issue?

Fixes #1550 by making the `uuid`, `uuid3`, `uuid4`, and `uuid5` validators case‑insensitive for hex digits, matching the behavior of `uuid_rfc4122` and standard UUID specifications.
